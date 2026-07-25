"""Application settings, persisted in SQLite with sane local defaults."""

from __future__ import annotations

import os
from pathlib import Path

APP_NAME = "nostos"

DATA_DIR = Path(os.environ.get("NOSTOS_DATA_DIR", Path.home() / ".local" / "share" / APP_NAME))
DB_PATH = DATA_DIR / "nostos.db"

DEFAULT_DOWNLOAD_DIR = Path.home() / "Downloads" / "Nostos"

# Settings keys stored in the `settings` table.
KEY_DOWNLOAD_DIR = "download_dir"
KEY_COOKIES_FROM_BROWSER = "cookies_from_browser"
KEY_AUTO_DOWNLOAD = "auto_download"
KEY_SUBTITLE_LANGS = "subtitle_langs"

DEFAULTS: dict[str, str] = {
    KEY_DOWNLOAD_DIR: str(DEFAULT_DOWNLOAD_DIR),
    KEY_COOKIES_FROM_BROWSER: "",
    # Off by default: pasting should not move files without being asked to.
    KEY_AUTO_DOWNLOAD: "0",
    # Comma-separated language codes, e.g. "en,fr". Empty means no subtitles.
    KEY_SUBTITLE_LANGS: "",
}

# Browsers yt-dlp can pull cookies from. Empty string means "no cookies".
SUPPORTED_BROWSERS = ("", "firefox", "chrome", "chromium", "brave", "edge", "opera", "vivaldi", "safari")


def ensure_dirs() -> None:
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    download_dir().mkdir(parents=True, exist_ok=True)


def download_dir() -> Path:
    from . import db

    return Path(db.get_setting(KEY_DOWNLOAD_DIR)).expanduser()


def cookies_from_browser() -> str:
    from . import db

    return db.get_setting(KEY_COOKIES_FROM_BROWSER).strip()


def subtitle_langs() -> list[str]:
    from . import db

    raw = db.get_setting(KEY_SUBTITLE_LANGS)
    return [code.strip() for code in raw.split(",") if code.strip()]
