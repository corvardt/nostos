"""SQLite persistence: download history and user settings.

Stdlib sqlite3, no ORM - the schema is two tables and the prototype is single-user.
Connections are created per call because yt-dlp downloads run on worker threads.
"""

from __future__ import annotations

import sqlite3
from typing import Any

from . import config

SCHEMA = """
CREATE TABLE IF NOT EXISTS history (
    id         INTEGER PRIMARY KEY AUTOINCREMENT,
    url        TEXT NOT NULL,
    platform   TEXT,
    title      TEXT,
    status     TEXT NOT NULL,
    filepath   TEXT,
    created_at TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS settings (
    key   TEXT PRIMARY KEY,
    value TEXT NOT NULL
);
"""


def connect() -> sqlite3.Connection:
    config.DATA_DIR.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(config.DB_PATH, timeout=10)
    conn.row_factory = sqlite3.Row
    return conn


def init() -> None:
    with connect() as conn:
        conn.executescript(SCHEMA)
        for key, value in config.DEFAULTS.items():
            conn.execute("INSERT OR IGNORE INTO settings (key, value) VALUES (?, ?)", (key, value))


def get_setting(key: str) -> str:
    with connect() as conn:
        row = conn.execute("SELECT value FROM settings WHERE key = ?", (key,)).fetchone()
    return row["value"] if row else config.DEFAULTS.get(key, "")


def set_setting(key: str, value: str) -> None:
    with connect() as conn:
        conn.execute(
            "INSERT INTO settings (key, value) VALUES (?, ?) "
            "ON CONFLICT(key) DO UPDATE SET value = excluded.value",
            (key, value),
        )


def add_history(
    url: str,
    platform: str | None,
    title: str | None,
    status: str,
    filepath: str | None,
) -> int:
    with connect() as conn:
        cur = conn.execute(
            "INSERT INTO history (url, platform, title, status, filepath) VALUES (?, ?, ?, ?, ?)",
            (url, platform, title, status, filepath),
        )
    return int(cur.lastrowid)


def list_history(limit: int = 50) -> list[dict[str, Any]]:
    with connect() as conn:
        rows = conn.execute(
            "SELECT * FROM history ORDER BY id DESC LIMIT ?", (limit,)
        ).fetchall()
    return [dict(row) for row in rows]
