"""Persistence for the library: configured sources, and the state of each song.

Two tables beside Nostos's own. `history` still records every download, but it
is keyed by URL and append-only, which cannot answer the question a library
asks - "do I have this song?" - because the same song may arrive from a
different URL every time.
"""

from __future__ import annotations

import json
import sqlite3
from datetime import datetime, timezone
from typing import Any

from .. import config, db
from .models import LibraryTrack, SourceConfig, Track

SCHEMA = """
CREATE TABLE IF NOT EXISTS library_sources (
    id      INTEGER PRIMARY KEY AUTOINCREMENT,
    type    TEXT NOT NULL,
    label   TEXT NOT NULL DEFAULT '',
    enabled INTEGER NOT NULL DEFAULT 1,
    options TEXT NOT NULL DEFAULT '{}'
);

CREATE TABLE IF NOT EXISTS library_tracks (
    key        TEXT PRIMARY KEY,
    title      TEXT NOT NULL,
    artist     TEXT NOT NULL,
    album      TEXT NOT NULL DEFAULT '',
    isrc       TEXT NOT NULL DEFAULT '',
    duration_s INTEGER NOT NULL DEFAULT 0,
    status     TEXT NOT NULL DEFAULT 'wanted',
    filepath   TEXT,
    job_id     TEXT,
    error      TEXT,
    sources    TEXT NOT NULL DEFAULT '[]',
    playlists  TEXT NOT NULL DEFAULT '[]',
    updated_at TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE INDEX IF NOT EXISTS library_tracks_status ON library_tracks (status);
CREATE INDEX IF NOT EXISTS library_tracks_artist ON library_tracks (artist);
"""


def init() -> None:
    with db.connect() as conn:
        conn.executescript(SCHEMA)
        for key, value in DEFAULTS.items():
            conn.execute("INSERT OR IGNORE INTO settings (key, value) VALUES (?, ?)", (key, value))


# ------------------------------------------------------------------- settings

KEY_MUSIC_DIR = "music_dir"
KEY_MUSIC_LAYOUT = "music_layout"
KEY_MUSIC_FORMAT = "music_format"
KEY_MUSIC_QUALITY = "music_quality"
KEY_MUSIC_LIBRARY_DIRS = "music_library_dirs"
KEY_MUSIC_USE_SPOTDL = "music_use_spotdl"

LAYOUTS = ("flat", "artist", "artist-album")
AUDIO_FORMATS = ("mp3", "m4a", "opus", "flac")

DEFAULTS: dict[str, str] = {
    KEY_MUSIC_DIR: str(config.DEFAULT_DOWNLOAD_DIR.parent / "Music"),
    KEY_MUSIC_LAYOUT: "artist",
    KEY_MUSIC_FORMAT: "mp3",
    # yt-dlp's VBR scale, where 0 is the best the source can give.
    KEY_MUSIC_QUALITY: "0",
    # Newline-separated folders you already keep music in. Anything found there
    # is never downloaded again.
    KEY_MUSIC_LIBRARY_DIRS: "",
    KEY_MUSIC_USE_SPOTDL: "1",
}


def _setting(key: str) -> str:
    with db.connect() as conn:
        row = conn.execute("SELECT value FROM settings WHERE key = ?", (key,)).fetchone()
    return row["value"] if row else DEFAULTS.get(key, "")


def music_dir():
    from pathlib import Path

    return Path(_setting(KEY_MUSIC_DIR)).expanduser()


def layout() -> str:
    value = _setting(KEY_MUSIC_LAYOUT)
    return value if value in LAYOUTS else "flat"


def audio_format() -> str:
    value = _setting(KEY_MUSIC_FORMAT)
    return value if value in AUDIO_FORMATS else "mp3"


def audio_quality() -> str:
    return _setting(KEY_MUSIC_QUALITY) or "0"


def library_dirs() -> list[str]:
    raw = _setting(KEY_MUSIC_LIBRARY_DIRS)
    return [line.strip() for line in raw.splitlines() if line.strip()]


def use_spotdl() -> bool:
    return _setting(KEY_MUSIC_USE_SPOTDL) == "1"


# -------------------------------------------------------------------- sources


def _row_to_source(row: sqlite3.Row) -> SourceConfig:
    return SourceConfig(
        id=row["id"],
        type=row["type"],
        label=row["label"],
        enabled=bool(row["enabled"]),
        options=json.loads(row["options"] or "{}"),
    )


def list_sources(enabled_only: bool = False) -> list[SourceConfig]:
    query = "SELECT * FROM library_sources"
    if enabled_only:
        query += " WHERE enabled = 1"
    with db.connect() as conn:
        rows = conn.execute(query + " ORDER BY id").fetchall()
    return [_row_to_source(row) for row in rows]


def get_source(source_id: int) -> SourceConfig | None:
    with db.connect() as conn:
        row = conn.execute("SELECT * FROM library_sources WHERE id = ?", (source_id,)).fetchone()
    return _row_to_source(row) if row else None


def add_source(source: SourceConfig) -> SourceConfig:
    with db.connect() as conn:
        cursor = conn.execute(
            "INSERT INTO library_sources (type, label, enabled, options) VALUES (?, ?, ?, ?)",
            (source.type, source.label or source.type, int(source.enabled),
             json.dumps(source.options)),
        )
        source_id = int(cursor.lastrowid)
    return source.model_copy(update={"id": source_id})


def update_source(source_id: int, source: SourceConfig) -> SourceConfig | None:
    existing = get_source(source_id)
    if existing is None:
        return None

    # A masked secret means "leave it alone": the UI never receives the real
    # value, so echoing what it sends back would wipe the stored one.
    options = dict(existing.options)
    for key, value in source.options.items():
        if value == "********":
            continue
        options[key] = value

    with db.connect() as conn:
        conn.execute(
            "UPDATE library_sources SET type = ?, label = ?, enabled = ?, options = ? WHERE id = ?",
            (source.type, source.label or source.type, int(source.enabled),
             json.dumps(options), source_id),
        )
    return get_source(source_id)


def delete_source(source_id: int) -> bool:
    with db.connect() as conn:
        cursor = conn.execute("DELETE FROM library_sources WHERE id = ?", (source_id,))
    return cursor.rowcount > 0


# --------------------------------------------------------------------- tracks


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _row_to_track(row: sqlite3.Row) -> LibraryTrack:
    return LibraryTrack(
        key=row["key"],
        title=row["title"],
        artist=row["artist"],
        album=row["album"],
        isrc=row["isrc"],
        duration_s=row["duration_s"],
        status=row["status"],
        filepath=row["filepath"],
        job_id=row["job_id"],
        error=row["error"],
        sources=json.loads(row["sources"] or "[]"),
        playlists=json.loads(row["playlists"] or "[]"),
        updated_at=row["updated_at"],
    )


def upsert_track(track: Track) -> LibraryTrack:
    """Record a track the sources reported, without disturbing its status.

    A second sync re-reports every track it already knows about. Overwriting
    the status here would forget every download and re-queue the lot.
    """
    with db.connect() as conn:
        conn.execute(
            """
            INSERT INTO library_tracks
                (key, title, artist, album, isrc, duration_s, sources, playlists, updated_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(key) DO UPDATE SET
                title      = excluded.title,
                artist     = excluded.artist,
                album      = CASE WHEN library_tracks.album = '' THEN excluded.album
                                  ELSE library_tracks.album END,
                isrc       = CASE WHEN library_tracks.isrc = '' THEN excluded.isrc
                                  ELSE library_tracks.isrc END,
                duration_s = excluded.duration_s,
                sources    = excluded.sources,
                playlists  = excluded.playlists,
                updated_at = excluded.updated_at
            """,
            (
                track.key, track.title, track.artist, track.album, track.isrc,
                track.duration_s, json.dumps(sorted(track.origins)),
                json.dumps(track.playlists), _now(),
            ),
        )
        row = conn.execute("SELECT * FROM library_tracks WHERE key = ?", (track.key,)).fetchone()
    return _row_to_track(row)


def set_status(key: str, status: str, **fields: Any) -> None:
    columns = ", ".join(f"{name} = ?" for name in fields)
    assignments = f"status = ?, updated_at = ?{', ' + columns if columns else ''}"
    with db.connect() as conn:
        conn.execute(
            f"UPDATE library_tracks SET {assignments} WHERE key = ?",  # noqa: S608 - names are literals
            (status, _now(), *fields.values(), key),
        )


def mark_queued(key: str, job_id: str) -> None:
    set_status(key, "queued", job_id=job_id, error=None)


def mark_downloaded(key: str, filepath: str) -> None:
    set_status(key, "downloaded", filepath=filepath, error=None)


def mark_owned(key: str, filepath: str) -> None:
    set_status(key, "owned", filepath=filepath, error=None)


def mark_failed(key: str, error: str) -> None:
    set_status(key, "failed", error=error)


def mark_skipped(key: str, reason: str) -> None:
    set_status(key, "skipped", error=reason)


def get_track(key: str) -> LibraryTrack | None:
    with db.connect() as conn:
        row = conn.execute("SELECT * FROM library_tracks WHERE key = ?", (key,)).fetchone()
    return _row_to_track(row) if row else None


def list_tracks(status: str = "", search: str = "", limit: int = 200, offset: int = 0) -> list[LibraryTrack]:
    clauses: list[str] = []
    params: list[Any] = []
    if status:
        clauses.append("status = ?")
        params.append(status)
    if search:
        clauses.append("(title LIKE ? OR artist LIKE ? OR album LIKE ?)")
        params += [f"%{search}%"] * 3
    where = f" WHERE {' AND '.join(clauses)}" if clauses else ""

    with db.connect() as conn:
        rows = conn.execute(
            f"SELECT * FROM library_tracks{where} ORDER BY artist, album, title LIMIT ? OFFSET ?",  # noqa: S608
            (*params, limit, offset),
        ).fetchall()
    return [_row_to_track(row) for row in rows]


def counts() -> dict[str, int]:
    with db.connect() as conn:
        rows = conn.execute("SELECT status, count(*) AS n FROM library_tracks GROUP BY status").fetchall()
    return {row["status"]: row["n"] for row in rows}


def reset_failed() -> int:
    """Put every failed track back in the queue's reach."""
    with db.connect() as conn:
        cursor = conn.execute(
            "UPDATE library_tracks SET status = 'wanted', error = NULL, updated_at = ? "
            "WHERE status = 'failed'",
            (_now(),),
        )
    return cursor.rowcount
