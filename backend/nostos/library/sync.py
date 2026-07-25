"""One pass: every source in, one archive out.

The pass is deliberately ordered cheapest-check-first. Resolving a track means
a network search, and downloading it means a file transfer, so anything that
can rule a track out - already recorded, already on disk, already in a folder
you keep music in - happens before either.

Resolution runs in a small thread pool because it is pure network latency, but
the downloads themselves are handed to `jobs.py`, which already knows how to
pace a platform and how to be cancelled.
"""

from __future__ import annotations

import logging
from concurrent.futures import ThreadPoolExecutor

from .. import jobs
from ..providers.base import ProviderError
from . import resolver, store
from .models import SyncReport, SyncRequest, Track
from .provider import TrackProvider
from .scan import MusicIndex
from .sources import SourceError, build_source

log = logging.getLogger(__name__)

# Resolution is network-bound and hits YouTube search. A handful at a time is
# quick without looking like scraping.
RESOLVE_WORKERS = 4


def collect(source_ids: list[int] | None = None) -> tuple[list[Track], list[str]]:
    """Fetch from every enabled source. Returns (tracks, failures).

    A source that fails - an expired token, a playlist made private - costs you
    that source and nothing else. Reporting it and carrying on beats aborting a
    sync that would have worked for everything else.
    """
    tracks: list[Track] = []
    failures: list[str] = []

    for config_row in store.list_sources(enabled_only=True):
        if source_ids and config_row.id not in source_ids:
            continue
        try:
            source = build_source(config_row.type, config_row.options, config_row.label)
            found = source.fetch()
        except SourceError as exc:
            log.warning("source %s failed: %s", config_row.label, exc.message)
            failures.append(f"{config_row.label}: {exc.message}")
            continue
        except Exception as exc:  # noqa: BLE001 - a broken source must not kill the pass
            log.exception("source %s raised", config_row.label)
            failures.append(f"{config_row.label}: unexpected error - {exc}")
            continue

        log.info("source %s returned %d tracks", config_row.label, len(found))
        tracks += found

    return tracks, failures


def run(request: SyncRequest | None = None) -> SyncReport:
    request = request or SyncRequest()
    report = SyncReport()

    tracks, report.failed_sources = collect(request.source_ids or None)
    report.collected = len(tracks)

    from .models import deduplicate

    unique = deduplicate(tracks)
    report.unique = len(unique)

    if request.retry_failed:
        store.reset_failed()

    index = MusicIndex(store.library_dirs())
    if index.missing_dirs:
        log.warning("music folders not found, skipped for matching: %s", ", ".join(index.missing_dirs))

    pending: list[Track] = []
    for track in unique:
        stored = store.upsert_track(track)

        if stored.status in ("downloaded", "owned"):
            report.already_downloaded += 1
            continue
        if stored.status == "failed" and not request.retry_failed:
            continue
        if stored.status == "queued" and jobs.get(stored.job_id or "") is not None:
            continue  # still moving through the queue from an earlier pass

        owned = index.find(track)
        if owned:
            store.mark_owned(track.key, owned)
            report.already_owned += 1
            continue

        pending.append(track)

    if request.limit:
        pending = pending[: request.limit]

    if request.dry_run:
        return report

    for track, resolution in _resolve_all(pending):
        if resolution is None:
            store.mark_failed(track.key, "No matching track found to download.")
            continue
        job_id = _queue(track, resolution)
        if job_id:
            report.queued += 1
            report.job_ids.append(job_id)

    return report


def _resolve_all(tracks: list[Track]):
    """Resolve tracks to URLs concurrently, yielding as each finishes."""
    if not tracks:
        return

    use_spotdl = store.use_spotdl()
    with ThreadPoolExecutor(max_workers=RESOLVE_WORKERS, thread_name_prefix="nostos-resolve") as pool:
        futures = {
            pool.submit(resolver.best_resolution, track, use_spotdl): track for track in tracks
        }
        for future in futures:
            track = futures[future]
            try:
                yield track, future.result()
            except Exception as exc:  # noqa: BLE001
                log.warning("resolving %s failed: %s", track.display_name, exc)
                yield track, None


def _queue(track: Track, resolution: resolver.Resolution) -> str | None:
    provider = TrackProvider(
        track,
        dest=store.music_dir(),
        audio_format=store.audio_format(),
        quality=store.audio_quality(),
    )
    try:
        job_id = jobs.start(resolution.url, "bestaudio/best", provider, track.display_name)
    except ProviderError as exc:
        store.mark_failed(track.key, exc.message)
        return None
    store.mark_queued(track.key, job_id)
    log.info("queued %s (%s, score %.2f)", track.display_name, resolution.reason, resolution.score)
    return job_id
