"""Download Manager: an in-process job registry backed by a thread pool.

yt-dlp is blocking, so downloads must not run on the event loop. The registry is
deliberately in-memory - completed jobs are what get persisted, to `history`.
"""

from __future__ import annotations

import logging
import re
import threading
import time
import uuid
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

from yt_dlp.utils import DownloadCancelled

from . import db
from .models import Job
from .providers import Provider, ProviderError

log = logging.getLogger(__name__)


class Cancelled(DownloadCancelled):
    """Raised out of the progress hook to unwind a download in progress.

    Subclasses yt-dlp's own cancellation signal so it is treated as a deliberate
    abort, not a download error that `ignoreerrors` would swallow.
    """

# Belt and braces: providers are told not to colorize, but anything bound for
# the UI gets scrubbed here too - a stray ESC renders as a literal "␛".
_ANSI_RE = re.compile(r"\x1b\[[0-9;]*[a-zA-Z]")

# Strips yt-dlp's per-format tail, e.g. "clip [id].f401.mp4" -> "clip [id]".
_MEDIA_STEM_RE = re.compile(r"(\.f\d+)?\.[A-Za-z0-9]{2,5}$")


def _plain(value: str | None) -> str | None:
    if not value:
        return None
    return _ANSI_RE.sub("", value).strip() or None


_jobs: dict[str, Job] = {}
# Ids asked to stop. Checked when a worker picks a job up and on every progress
# tick, which is the only place a running yt-dlp download can be interrupted.
_cancelled: set[str] = set()
_lock = threading.Lock()

# One executor per platform, so a batch is paced by what that platform tolerates.
# YouTube is happy with parallel downloads. Instagram and Threads throttle or
# soft-ban on bursts, and the Threads provider costs two page fetches per item
# (once to resolve, once to download), so both are serialised.
_WORKERS = {"youtube": 3, "instagram": 1, "threads": 1, "music": 3}
_DEFAULT_WORKERS = 1

# Seconds to wait before starting an item, for platforms that dislike bursts.
_PACING = {"instagram": 2.0, "threads": 2.0}

_executors: dict[str, ThreadPoolExecutor] = {
    name: ThreadPoolExecutor(max_workers=count, thread_name_prefix=f"nostos-{name}")
    for name, count in _WORKERS.items()
}


def _executor_for(platform: str) -> ThreadPoolExecutor:
    if platform not in _executors:
        _executors[platform] = ThreadPoolExecutor(
            max_workers=_DEFAULT_WORKERS, thread_name_prefix=f"nostos-{platform}"
        )
    return _executors[platform]


def get(job_id: str) -> Job | None:
    with _lock:
        job = _jobs.get(job_id)
        return job.model_copy(deep=True) if job else None


def is_cancelled(job_id: str) -> bool:
    with _lock:
        return job_id in _cancelled


def cancel(job_id: str) -> bool:
    """Ask a job to stop. Returns False if it had already finished."""
    with _lock:
        job = _jobs.get(job_id)
        if job is None or job.status in ("done", "error", "cancelled"):
            return False
        _cancelled.add(job_id)
        # A queued job never reaches a progress hook, so retire it here.
        if job.status == "queued":
            job.status = "cancelled"
    return True


def cancel_all() -> int:
    with _lock:
        pending = [j.id for j in _jobs.values() if j.status in ("queued", "running")]
    return sum(1 for job_id in pending if cancel(job_id))


def _update(job_id: str, **fields) -> None:
    with _lock:
        job = _jobs.get(job_id)
        if job:
            for key, value in fields.items():
                setattr(job, key, value)


def start(url: str, fmt: str | None, provider: Provider, title: str | None = None) -> str:
    job_id = uuid.uuid4().hex[:12]
    with _lock:
        _jobs[job_id] = Job(id=job_id, url=url, format=fmt, platform=provider.name, title=title)
    _executor_for(provider.name).submit(_run, job_id, url, fmt, provider)
    return job_id


def _discard_partials(filenames: set[str]) -> None:
    """Remove the scratch files a cancelled download left behind.

    Only provably temporary siblings are touched (.part, .ytdl, fragments).
    The target name itself is left alone: an earlier, completed download of the
    same media would share it, and losing that to a cancel would be worse than
    a stray file.
    """
    for name in filenames:
        base = Path(name)
        for leftover in (base.with_name(base.name + ".part"), base.with_name(base.name + ".ytdl")):
            leftover.unlink(missing_ok=True)

        parent = base.parent
        if not parent.is_dir():
            continue
        for frag in parent.glob(base.name + ".part-Frag*"):
            frag.unlink(missing_ok=True)

        # The cover art written for embedding is named off the media stem, not
        # the per-format filename ("clip [id].webp" beside "clip [id].f401.mp4"),
        # so it needs deriving. A finished download consumes its own thumbnail,
        # which is why one still sitting here belongs to the cancelled run.
        stem = _MEDIA_STEM_RE.sub("", base.name)
        for ext in (".webp", ".jpg", ".jpeg", ".png"):
            parent.joinpath(stem + ext).unlink(missing_ok=True)


def _run(job_id: str, url: str, fmt: str | None, provider: Provider) -> None:
    # Queued items wait their turn in the executor; pace the throttled platforms
    # so a long batch does not arrive as a burst.
    if is_cancelled(job_id):
        _update(job_id, status="cancelled")
        return

    delay = _PACING.get(provider.name)
    if delay:
        time.sleep(delay)

    if is_cancelled(job_id):
        _update(job_id, status="cancelled")
        return

    _update(job_id, status="running")
    touched: set[str] = set()

    def on_progress(payload: dict) -> None:
        name = payload.get("filename")
        if name:
            touched.add(name)

        # The only interruption point inside a running download.
        if is_cancelled(job_id):
            raise Cancelled()

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
    except Cancelled:
        _discard_partials(touched)
        _update(job_id, status="cancelled", speed=None, eta=None)
        return
    except ProviderError as exc:
        if is_cancelled(job_id):
            _discard_partials(touched)
            _update(job_id, status="cancelled", speed=None, eta=None)
            return
        _discard_partials(touched)
        _fail(job_id, url, provider.name, exc.message)
    except Exception as exc:  # noqa: BLE001 - a worker thread must never die silently
        log.exception("download failed for %s", url)
        _discard_partials(touched)
        _fail(job_id, url, provider.name, f"Unexpected error: {exc}")
    else:
        # Extraction runs before the first progress hook, so a job cancelled in
        # that window gets here having finished. Honour the cancel: do not
        # record it as a download the user asked for.
        if is_cancelled(job_id):
            _update(job_id, status="cancelled", speed=None, eta=None)
            return
        job = get(job_id)
        _update(job_id, status="done", progress=100.0, filepath=path, speed=None, eta=None)
        db.add_history(url, provider.name, job.title if job else None, "done", path)


def _fail(job_id: str, url: str, platform: str, message: str) -> None:
    job = get(job_id)
    _update(job_id, status="error", error=message, speed=None, eta=None)
    # The reason is stored, so history can explain a failure long after the
    # queue that showed it has gone.
    db.add_history(url, platform, job.title if job else None, "error", None, message)
