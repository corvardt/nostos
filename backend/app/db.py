"""SQLite persistence: download history and user settings.

Stdlib sqlite3, no ORM - the schema is two tables and the prototype is single-user.
Connections are created per call because yt-dlp downloads run on worker threads.
"""

from __future__ import annotations

import sqlite3
from pathlib import Path
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
    error      TEXT,
    created_at TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE INDEX IF NOT EXISTS history_url ON history (url);

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


# Columns added after the first release, applied to databases that predate them.
MIGRATIONS = {
    "error": "ALTER TABLE history ADD COLUMN error TEXT",
}


def init() -> None:
    with connect() as conn:
        conn.executescript(SCHEMA)

        existing = {row["name"] for row in conn.execute("PRAGMA table_info(history)")}
        for column, statement in MIGRATIONS.items():
            if column not in existing:
                conn.execute(statement)

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
    error: str | None = None,
) -> int:
    with connect() as conn:
        cur = conn.execute(
            "INSERT INTO history (url, platform, title, status, filepath, error) "
            "VALUES (?, ?, ?, ?, ?, ?)",
            (url, platform, title, status, filepath, error),
        )
    return int(cur.lastrowid)


def last_successful_download(url: str) -> dict[str, Any] | None:
    """The most recent completed download of this URL whose file is still there.

    A history row whose file has since been deleted is not a duplicate: the
    point of the check is to avoid fetching something you already have.
    """
    with connect() as conn:
        row = conn.execute(
            "SELECT * FROM history WHERE url = ? AND status = 'done' "
            "ORDER BY id DESC LIMIT 1",
            (url,),
        ).fetchone()
    if row is None:
        return None
    filepath = row["filepath"]
    if not filepath or not Path(filepath).exists():
        return None
    return dict(row)


def clear_history() -> int:
    """Forget every recorded download. The files themselves are left alone."""
    with connect() as conn:
        count = conn.execute("SELECT count(*) FROM history").fetchone()[0]
        conn.execute("DELETE FROM history")
        conn.execute("DELETE FROM sqlite_sequence WHERE name = 'history'")
    return int(count)


def list_history(limit: int = 50) -> list[dict[str, Any]]:
    with connect() as conn:
        rows = conn.execute(
            "SELECT * FROM history ORDER BY id DESC LIMIT ?", (limit,)
        ).fetchall()
    return [dict(row) for row in rows]
