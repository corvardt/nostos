"""The library wire contract: a Track, and what a sync does to it.

Nostos's own models describe *a URL being fetched*. These describe *a song you
own or want*, which is a different thing: it exists before any URL is known,
and it survives the URL that satisfied it going dead.
"""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field

from .text import jaccard, normalize, primary_artist, safe_filename, similarity, strip_album_suffix, tokenize

TrackStatus = Literal["wanted", "queued", "downloaded", "owned", "failed", "skipped"]

# Two tracks with no ISRC between them are the same song above this much
# word overlap.
FUZZY_DUPLICATE_THRESHOLD = 0.82

# How far two durations may differ and still be one recording. Wide enough for
# a fade-out difference, narrow enough to keep a radio edit and an eight-minute
# remix apart.
DURATION_TOLERANCE_S = 12


class Track(BaseModel):
    title: str
    artist: str
    album: str = ""
    duration_s: int = 0
    #: International Standard Recording Code. Unique per *recording*, which is
    #: what makes it the only trustworthy key across platforms.
    isrc: str = ""
    year: str = ""
    #: Platform ids this track was seen under, e.g. {"spotify": "3n3P...", ...}.
    origins: dict[str, str] = Field(default_factory=dict)
    #: Which source playlists or libraries it came from.
    playlists: list[str] = Field(default_factory=list)
    url: str = ""

    # ------------------------------------------------------------------ derived

    @property
    def display_name(self) -> str:
        return f"{self.artist} - {self.title}"

    @property
    def key(self) -> str:
        """Stable identity, used as the primary key in the database.

        Falls back to normalized artist+title when there is no ISRC, which is
        the case for anything sourced from YouTube.
        """
        if self.isrc:
            return f"isrc:{self.isrc.upper()}"
        return f"nm:{normalize(self.artist)}|{normalize(self.title)}"

    @property
    def tokens(self) -> set[str]:
        return tokenize(f"{self.artist} {self.title}")

    def filename(self, layout: str = "flat", ext: str = "mp3") -> str:
        """Path relative to the music directory, per the chosen layout."""
        base = safe_filename(self.display_name)
        if layout == "artist":
            return f"{safe_filename(primary_artist(self.artist))}/{base}.{ext}"
        if layout == "artist-album":
            album = safe_filename(strip_album_suffix(self.album) or "Singles")
            return f"{safe_filename(primary_artist(self.artist))}/{album}/{base}.{ext}"
        return f"{base}.{ext}"

    # ------------------------------------------------------------------ merging

    def matches(self, other: Track) -> bool:
        """Same recording as `other`?

        When both carry an ISRC it decides outright, in both directions: two
        different ISRCs mean two different recordings even under identical
        titles, which is exactly how a remaster or a live cut is told apart
        from the original.
        """
        if self.isrc and other.isrc:
            return self.isrc.upper() == other.isrc.upper()

        if jaccard(self.tokens, other.tokens) < FUZZY_DUPLICATE_THRESHOLD:
            return False

        if self.duration_s and other.duration_s:
            if abs(self.duration_s - other.duration_s) > DURATION_TOLERANCE_S:
                return False

        # High word overlap can come from a wordy artist name alone, so require
        # the titles themselves to resemble each other too.
        return similarity(self.title, other.title) >= 0.7

    def merge(self, other: Track) -> None:
        """Absorb the same song as seen by another platform."""
        self.origins.update(other.origins)
        for playlist in other.playlists:
            if playlist not in self.playlists:
                self.playlists.append(playlist)
        # Fill gaps only: whichever source saw it first keeps its version.
        for field in ("album", "isrc", "year", "url"):
            if not getattr(self, field) and getattr(other, field):
                setattr(self, field, getattr(other, field))
        if not self.duration_s and other.duration_s:
            self.duration_s = other.duration_s


def deduplicate(tracks: list[Track]) -> list[Track]:
    """Collapse the same song appearing in several sources into one Track.

    Indexed by ISRC where available, and otherwise compared only against tracks
    sharing at least one word. Comparing every track to every other is
    quadratic, which on a library of a few thousand songs is the slowest part
    of a sync by a wide margin.
    """
    merged: list[Track] = []
    by_isrc: dict[str, Track] = {}
    by_token: dict[str, list[int]] = {}

    for track in tracks:
        if track.isrc:
            existing = by_isrc.get(track.isrc.upper())
            if existing is not None:
                existing.merge(track)
                continue

        match: Track | None = None
        for token in track.tokens:
            for index in by_token.get(token, ()):
                if merged[index].matches(track):
                    match = merged[index]
                    break
            if match:
                break

        if match is not None:
            match.merge(track)
            if match.isrc:
                by_isrc.setdefault(match.isrc.upper(), match)
            continue

        merged.append(track)
        index = len(merged) - 1
        if track.isrc:
            by_isrc[track.isrc.upper()] = track
        for token in track.tokens:
            by_token.setdefault(token, []).append(index)

    return merged


# --------------------------------------------------------------------- the API


class LibraryTrack(BaseModel):
    """A track as stored: the song, plus what happened to it."""

    key: str
    title: str
    artist: str
    album: str = ""
    isrc: str = ""
    duration_s: int = 0
    status: TrackStatus = "wanted"
    filepath: str | None = None
    job_id: str | None = None
    error: str | None = None
    sources: list[str] = Field(default_factory=list)
    playlists: list[str] = Field(default_factory=list)
    updated_at: str = ""


class SourceConfig(BaseModel):
    """One configured place to pull tracks from."""

    id: int | None = None
    type: str
    label: str = ""
    enabled: bool = True
    #: Type-specific settings: tokens, playlist ids, flags. Secrets included,
    #: which is why this never leaves the machine and why `redacted()` exists.
    options: dict = Field(default_factory=dict)

    def redacted(self) -> SourceConfig:
        """A copy safe to send to the UI, with credentials masked."""
        secret_keys = {"developer_token", "user_token", "client_secret", "arl", "client_id"}
        options = {
            key: ("********" if key in secret_keys and value else value)
            for key, value in self.options.items()
        }
        return self.model_copy(update={"options": options})


class SyncRequest(BaseModel):
    #: Limit the pass to these source ids. Empty means every enabled source.
    source_ids: list[int] = Field(default_factory=list)
    #: Collect and store tracks, but queue nothing.
    dry_run: bool = False
    #: Retry tracks that previously failed to download.
    retry_failed: bool = False
    #: Cap on how many downloads one pass may queue.
    limit: int = 0


class SyncReport(BaseModel):
    collected: int = 0        # tracks returned by the sources, before merging
    unique: int = 0           # after cross-platform deduplication
    already_owned: int = 0    # found in an existing music folder
    already_downloaded: int = 0
    queued: int = 0
    failed_sources: list[str] = Field(default_factory=list)
    job_ids: list[str] = Field(default_factory=list)
