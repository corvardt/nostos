"""HTTP surface. `/analyze`, `/download` and `/jobs/{id}` match the POC spec exactly."""

from __future__ import annotations

import anyio
from fastapi import APIRouter, HTTPException

from . import config, db, jobs
from .models import (
    AnalyzeRequest,
    DownloadRequest,
    DownloadResponse,
    HistoryEntry,
    Job,
    MediaInfo,
    Settings,
)
from .providers import ProviderError, resolve_provider

router = APIRouter()


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


@router.get("/jobs/{job_id}", response_model=Job)
async def get_job(job_id: str) -> Job:
    job = jobs.get(job_id)
    if job is None:
        raise HTTPException(status_code=404, detail="Unknown job id.")
    return job


@router.get("/history", response_model=list[HistoryEntry])
async def history(limit: int = 50) -> list[HistoryEntry]:
    return [HistoryEntry(**row) for row in db.list_history(limit)]


@router.get("/settings", response_model=Settings)
async def get_settings() -> Settings:
    return Settings(
        download_dir=db.get_setting(config.KEY_DOWNLOAD_DIR),
        cookies_from_browser=db.get_setting(config.KEY_COOKIES_FROM_BROWSER),
        auto_download=db.get_setting(config.KEY_AUTO_DOWNLOAD) == "1",
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
    config.ensure_dirs()
    return await get_settings()


@router.get("/health")
async def health() -> dict[str, str]:
    return {"status": "ok"}
