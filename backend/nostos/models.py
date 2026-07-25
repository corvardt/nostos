"""Pydantic models - the wire contract shared with the frontend (`src/lib/types.ts`)."""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field

JobStatus = Literal["queued", "running", "done", "error", "cancelled"]


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
    # Set when this exact URL was already downloaded and the file is still there.
    already_downloaded: str | None = None
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
    # Re-running a playlist should not refetch what is already on disk.
    skip_duplicates: bool = True
    # Titles already known, keyed by URL. A playlist expansion knows every one
    # of them, so the queue can name its rows before any of them start, and a
    # failure records a title rather than a bare URL.
    titles: dict[str, str] = Field(default_factory=dict)


class BatchItem(BaseModel):
    """One URL's outcome. A rejected URL reports why, rather than failing the lot."""

    url: str
    jobId: str | None = None  # noqa: N815 - matches DownloadResponse
    error: str | None = None
    # Not queued because it is already on disk, which is not a failure.
    skipped: bool = False


class BatchResponse(BaseModel):
    accepted: int
    rejected: int
    skipped: int = 0
    items: list[BatchItem]


class Job(BaseModel):
    id: str
    url: str
    # Kept so a failed or stopped job can be retried exactly as it was asked for.
    format: str | None = None
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
    error: str | None = None
    created_at: str


class Settings(BaseModel):
    download_dir: str
    cookies_from_browser: str = ""
    # Pasting a link analyzes and downloads it at best quality, with no clicks.
    auto_download: bool = False
    # Comma-separated language codes, e.g. "en,fr". Empty disables subtitles.
    subtitle_langs: str = ""
    # Reported so the UI can show where history lives; ignored on write.
    db_path: str = ""

    # --- library sync ---
    # Kept apart from download_dir: an archive of songs wants its own tree, not
    # to be mixed in with one-off videos.
    music_dir: str = ""
    # flat | artist | artist-album
    music_layout: str = "artist"
    music_format: str = "mp3"
    # Folders you already keep music in. Anything matched there is never
    # downloaded again. One per line.
    music_library_dirs: str = ""
    # Ask spotdl to pick the video first, when it is installed.
    music_use_spotdl: bool = True
