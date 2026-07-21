"""HTTP surface. `/analyze`, `/download` and `/jobs/{id}` match the POC spec exactly."""

from __future__ import annotations

import anyio
from fastapi import APIRouter, HTTPException

from . import config, db, jobs
from .models import (
    AnalyzeRequest,
    BatchDownloadRequest,
    BatchItem,
    BatchResponse,
    DownloadRequest,
    DownloadResponse,
    HistoryEntry,
    Job,
    MediaInfo,
    Playlist,
    PlaylistEntry,
    Settings,
)
from .providers import ProviderError, resolve_provider

router = APIRouter()

# A guard against a stray paste queueing thousands of downloads.
MAX_BATCH = 200


@router.post("/analyze", response_model=MediaInfo)
async def analyze(req: AnalyzeRequest) -> MediaInfo:
    try:
        provider = resolve_provider(req.url)
    except ProviderError as exc:
        raise HTTPException(status_code=400, detail=exc.message) from exc

    try:
        # Metadata extraction is blocking network I/O - keep it off the event loop.
        return await anyio.to_thread.run_sync(provider.resolve, req.url)
    except ProviderError as exc:
        raise HTTPException(status_code=422 if exc.needs_auth else 400, detail=exc.message) from exc


@router.post("/download", response_model=DownloadResponse)
async def download(req: DownloadRequest) -> DownloadResponse:
    try:
        provider = resolve_provider(req.url)
    except ProviderError as exc:
        raise HTTPException(status_code=400, detail=exc.message) from exc

    job_id = jobs.start(req.url, req.format, provider)
    return DownloadResponse(status="started", jobId=job_id)


@router.post("/expand", response_model=Playlist)
async def expand(req: AnalyzeRequest) -> Playlist:
    """List a playlist's items so the UI can confirm before queueing them."""
    try:
        provider = resolve_provider(req.url)
    except ProviderError as exc:
        raise HTTPException(status_code=400, detail=exc.message) from exc

    expander = getattr(provider, "expand_playlist", None)
    if expander is None:
        raise HTTPException(
            status_code=400, detail=f"{provider.name} does not support playlists."
        )

    try:
        title, entries, truncated = await anyio.to_thread.run_sync(
            expander, req.url, MAX_BATCH
        )
    except ProviderError as exc:
        raise HTTPException(status_code=422 if exc.needs_auth else 400, detail=exc.message) from exc

    return Playlist(
        title=title,
        count=len(entries),
        truncated=truncated,
        entries=[
            PlaylistEntry(
                url=e.get("url") or e.get("webpage_url") or "",
                title=e.get("title"),
                thumbnail=(e.get("thumbnails") or [{}])[0].get("url"),
            )
            for e in entries
            if e.get("url") or e.get("webpage_url")
        ],
    )


@router.post("/download/batch", response_model=BatchResponse)
async def download_batch(req: BatchDownloadRequest) -> BatchResponse:
    """Queue many URLs at once. Unsupported ones are reported, not fatal."""
    if not req.urls:
        raise HTTPException(status_code=400, detail="No URLs provided.")
    if len(req.urls) > MAX_BATCH:
        raise HTTPException(
            status_code=400,
            detail=f"That is {len(req.urls)} links. The limit is {MAX_BATCH} per batch.",
        )

    items: list[BatchItem] = []
    seen: set[str] = set()
    for raw in req.urls:
        url = raw.strip()
        if not url or url in seen:
            continue
        seen.add(url)
        try:
            provider = resolve_provider(url)
        except ProviderError as exc:
            items.append(BatchItem(url=url, error=exc.message))
            continue
        items.append(BatchItem(url=url, jobId=jobs.start(url, req.format, provider)))

    accepted = sum(1 for i in items if i.jobId)
    return BatchResponse(accepted=accepted, rejected=len(items) - accepted, items=items)


@router.get("/jobs/{job_id}", response_model=Job)
async def get_job(job_id: str) -> Job:
    job = jobs.get(job_id)
    if job is None:
        raise HTTPException(status_code=404, detail="Unknown job id.")
    return job


@router.delete("/jobs/{job_id}")
async def cancel_job(job_id: str) -> dict[str, bool]:
    if jobs.get(job_id) is None:
        raise HTTPException(status_code=404, detail="Unknown job id.")
    return {"cancelled": jobs.cancel(job_id)}


@router.delete("/jobs")
async def cancel_all_jobs() -> dict[str, int]:
    """Stop everything still queued or running, for a batch started by mistake."""
    return {"cancelled": jobs.cancel_all()}


@router.get("/history", response_model=list[HistoryEntry])
async def history(limit: int = 50) -> list[HistoryEntry]:
    return [HistoryEntry(**row) for row in db.list_history(limit)]


@router.get("/settings", response_model=Settings)
async def get_settings() -> Settings:
    return Settings(
        download_dir=db.get_setting(config.KEY_DOWNLOAD_DIR),
        cookies_from_browser=db.get_setting(config.KEY_COOKIES_FROM_BROWSER),
        auto_download=db.get_setting(config.KEY_AUTO_DOWNLOAD) == "1",
        subtitle_langs=db.get_setting(config.KEY_SUBTITLE_LANGS),
        db_path=str(config.DB_PATH),
    )


@router.put("/settings", response_model=Settings)
async def put_settings(settings: Settings) -> Settings:
    if settings.cookies_from_browser not in config.SUPPORTED_BROWSERS:
        raise HTTPException(
            status_code=400,
            detail=f"Unsupported browser. Choose one of: {', '.join(b for b in config.SUPPORTED_BROWSERS if b)}.",
        )
    db.set_setting(config.KEY_DOWNLOAD_DIR, settings.download_dir)
    db.set_setting(config.KEY_COOKIES_FROM_BROWSER, settings.cookies_from_browser)
    db.set_setting(config.KEY_AUTO_DOWNLOAD, "1" if settings.auto_download else "0")
    db.set_setting(config.KEY_SUBTITLE_LANGS, settings.subtitle_langs.strip())
    config.ensure_dirs()
    return await get_settings()


@router.get("/health")
async def health() -> dict[str, str]:
    return {"status": "ok"}
