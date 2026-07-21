"""Download Manager: an in-process job registry backed by a thread pool.

yt-dlp is blocking, so downloads must not run on the event loop. The registry is
deliberately in-memory - completed jobs are what get persisted, to `history`.
"""

from __future__ import annotations

import logging
import re
import threading
import uuid
from concurrent.futures import ThreadPoolExecutor

from . import db
from .models import Job
from .providers import Provider, ProviderError

log = logging.getLogger(__name__)

# Belt and braces: providers are told not to colorize, but anything bound for
# the UI gets scrubbed here too - a stray ESC renders as a literal "␛".
_ANSI_RE = re.compile(r"\x1b\[[0-9;]*[a-zA-Z]")


def _plain(value: str | None) -> str | None:
    if not value:
        return None
    return _ANSI_RE.sub("", value).strip() or None


_jobs: dict[str, Job] = {}
_lock = threading.Lock()
_executor = ThreadPoolExecutor(max_workers=3, thread_name_prefix="nostos-dl")


def get(job_id: str) -> Job | None:
    with _lock:
        job = _jobs.get(job_id)
        return job.model_copy(deep=True) if job else None


def _update(job_id: str, **fields) -> None:
    with _lock:
        job = _jobs.get(job_id)
        if job:
            for key, value in fields.items():
                setattr(job, key, value)


def start(url: str, fmt: str | None, provider: Provider, title: str | None = None) -> str:
    job_id = uuid.uuid4().hex[:12]
    with _lock:
        _jobs[job_id] = Job(id=job_id, url=url, platform=provider.name, title=title)
    _executor.submit(_run, job_id, url, fmt, provider)
    return job_id


def _run(job_id: str, url: str, fmt: str | None, provider: Provider) -> None:
    _update(job_id, status="running")

    def on_progress(payload: dict) -> None:
        status = payload.get("status")
        # The hook carries the info dict, so the title comes free - no second fetch.
        title = (payload.get("info_dict") or {}).get("title")
        if title and not (get(job_id) or Job(id=job_id, url=url)).title:
            _update(job_id, title=title)
        if status == "downloading":
            total = payload.get("total_bytes") or payload.get("total_bytes_estimate")
            downloaded = payload.get("downloaded_bytes") or 0
            percent = (downloaded / total * 100) if total else 0.0
            # Cap below 100: only a finished job reports 100, and a "best" download
            # streams video and audio separately before ffmpeg merges them.
            _update(
                job_id,
                progress=round(min(percent, 99.0), 1),
                speed=_plain(payload.get("_speed_str")),
                eta=payload.get("eta"),
                downloaded_bytes=downloaded or None,
                total_bytes=total,
            )
        elif status == "finished":
            # Post-processing (ffmpeg merge) still to come; hold just short of 100.
            _update(job_id, progress=99.0, speed=None, eta=None)

    try:
        path = provider.download(url, fmt, on_progress)
    except ProviderError as exc:
        _fail(job_id, url, provider.name, exc.message)
    except Exception as exc:  # noqa: BLE001 - a worker thread must never die silently
        log.exception("download failed for %s", url)
        _fail(job_id, url, provider.name, f"Unexpected error: {exc}")
    else:
        job = get(job_id)
        _update(job_id, status="done", progress=100.0, filepath=path, speed=None, eta=None)
        db.add_history(url, provider.name, job.title if job else None, "done", path)


def _fail(job_id: str, url: str, platform: str, message: str) -> None:
    job = get(job_id)
    _update(job_id, status="error", error=message, speed=None, eta=None)
    db.add_history(url, platform, job.title if job else None, "error", None)
