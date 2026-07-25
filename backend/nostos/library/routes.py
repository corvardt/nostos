"""HTTP surface for the library: `/library/...`.

A sync is long-running - minutes, for a large account - so it is started, not
awaited. The report comes back once collection and queueing are done; the
downloads themselves surface through the existing `/jobs` endpoints, which the
queue UI already polls.
"""

from __future__ import annotations

import anyio
from fastapi import APIRouter, HTTPException

from . import store, sync
from .models import LibraryTrack, SourceConfig, SyncReport, SyncRequest
from .sources import REGISTRY, SourceError, build_source, catalog

router = APIRouter(prefix="/library", tags=["library"])


@router.get("/source-types")
async def source_types() -> list[dict]:
    """The source types that can be configured, for the Add Source form."""
    return catalog()


@router.get("/sources", response_model=list[SourceConfig])
async def list_sources() -> list[SourceConfig]:
    return [source.redacted() for source in store.list_sources()]


@router.post("/sources", response_model=SourceConfig)
async def add_source(source: SourceConfig) -> SourceConfig:
    if source.type not in REGISTRY:
        raise HTTPException(
            status_code=400,
            detail=f"Unknown source type. Choose one of: {', '.join(sorted(REGISTRY))}.",
        )
    return store.add_source(source).redacted()


@router.put("/sources/{source_id}", response_model=SourceConfig)
async def update_source(source_id: int, source: SourceConfig) -> SourceConfig:
    if source.type not in REGISTRY:
        raise HTTPException(status_code=400, detail="Unknown source type.")
    updated = store.update_source(source_id, source)
    if updated is None:
        raise HTTPException(status_code=404, detail="No such source.")
    return updated.redacted()


@router.delete("/sources/{source_id}")
async def delete_source(source_id: int) -> dict[str, bool]:
    if not store.delete_source(source_id):
        raise HTTPException(status_code=404, detail="No such source.")
    return {"deleted": True}


@router.post("/sources/{source_id}/test")
async def test_source(source_id: int) -> dict:
    """Check the credentials and report the size of what it can see.

    Worth its own endpoint: finding out a token expired after a five-minute
    sync, rather than before it, is the difference between a fix and a rerun.
    """
    config_row = store.get_source(source_id)
    if config_row is None:
        raise HTTPException(status_code=404, detail="No such source.")

    source = build_source(config_row.type, config_row.options, config_row.label)
    try:
        tracks = await anyio.to_thread.run_sync(source.fetch)
    except SourceError as exc:
        raise HTTPException(status_code=422 if exc.needs_auth else 400, detail=exc.message) from exc

    with_isrc = sum(1 for track in tracks if track.isrc)
    return {
        "ok": True,
        "tracks": len(tracks),
        # Says how exact the cross-platform merge will be for this source.
        "with_isrc": with_isrc,
        "sample": [track.display_name for track in tracks[:5]],
    }


@router.post("/sync", response_model=SyncReport)
async def run_sync(request: SyncRequest | None = None) -> SyncReport:
    """Collect from every source, then queue whatever is missing."""
    return await anyio.to_thread.run_sync(sync.run, request or SyncRequest())


@router.get("/tracks", response_model=list[LibraryTrack])
async def list_tracks(
    status: str = "", search: str = "", limit: int = 200, offset: int = 0
) -> list[LibraryTrack]:
    return store.list_tracks(status=status, search=search, limit=min(limit, 1000), offset=offset)


@router.get("/stats")
async def stats() -> dict:
    counts = store.counts()
    return {
        "counts": counts,
        "total": sum(counts.values()),
        "sources": len(store.list_sources(enabled_only=True)),
        "music_dir": str(store.music_dir()),
    }


@router.post("/tracks/retry-failed")
async def retry_failed() -> dict[str, int]:
    """Mark failed tracks wanted again. The next sync picks them up."""
    return {"reset": store.reset_failed()}
