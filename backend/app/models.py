"""Pydantic models - the wire contract shared with the frontend (`src/lib/types.ts`)."""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field

JobStatus = Literal["queued", "running", "done", "error"]


class Format(BaseModel):
    """One selectable download option, already simplified from yt-dlp's raw format list."""

    id: str
    label: str
    ext: str | None = None
    height: int | None = None
    filesize: int | None = None
    kind: Literal["video", "audio", "image"] = "video"


class MediaInfo(BaseModel):
    platform: str
    title: str
    author: str | None = None
    thumbnail: str | None = None
    duration: float | None = None
    is_image: bool = False
    is_live: bool = False
    webpage_url: str | None = None
    formats: list[Format] = Field(default_factory=list)


class AnalyzeRequest(BaseModel):
    url: str


class DownloadRequest(BaseModel):
    url: str
    format: str | None = "best"


class DownloadResponse(BaseModel):
    status: Literal["started"] = "started"
    jobId: str  # noqa: N815 - the spec names this field `jobId`


class PlaylistEntry(BaseModel):
    url: str
    title: str | None = None
    thumbnail: str | None = None


class Playlist(BaseModel):
    title: str
    count: int
    entries: list[PlaylistEntry]
    truncated: bool = False


class BatchDownloadRequest(BaseModel):
    urls: list[str]
    format: str | None = "best"


class BatchItem(BaseModel):
    """One URL's outcome. A rejected URL reports why, rather than failing the lot."""

    url: str
    jobId: str | None = None  # noqa: N815 - matches DownloadResponse
    error: str | None = None


class BatchResponse(BaseModel):
    accepted: int
    rejected: int
    items: list[BatchItem]


class Job(BaseModel):
    id: str
    url: str
    platform: str | None = None
    title: str | None = None
    status: JobStatus = "queued"
    progress: float = 0.0  # 0..100
    speed: str | None = None
    eta: int | None = None
    downloaded_bytes: int | None = None
    total_bytes: int | None = None
    filepath: str | None = None
    error: str | None = None


class HistoryEntry(BaseModel):
    id: int
    url: str
    platform: str | None = None
    title: str | None = None
    status: str
    filepath: str | None = None
    created_at: str


class Settings(BaseModel):
    download_dir: str
    cookies_from_browser: str = ""
    # Pasting a link analyzes and downloads it at best quality, with no clicks.
    auto_download: bool = False
    # Reported so the UI can show where history lives; ignored on write.
    db_path: str = ""
