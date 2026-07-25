"""A tracklist from a JSON file on disk.

Accepts both the minimal `{"title", "artist", "album"}` shape that a hand-rolled
export produces and the full Track shape this package writes. Useful for
replaying an export without touching any API, and for importing a list you
built somewhere else.
"""

from __future__ import annotations

import json
from pathlib import Path

from ..models import Track
from .base import Source, SourceError


class JsonFileSource(Source):
    name = "json"
    description = "A tracklist exported to a JSON file"

    def fetch(self) -> list[Track]:
        (raw_path,) = self.require("path")
        path = Path(raw_path).expanduser()
        if not path.exists():
            raise SourceError(f"{self.label}: no such file - {path}")

        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except json.JSONDecodeError as exc:
            raise SourceError(f"{self.label}: {path} is not valid JSON ({exc}).") from exc

        # Either a bare list of tracks, or an export object wrapping one.
        if isinstance(data, dict):
            data = data.get("tracks", [])
        if not isinstance(data, list):
            raise SourceError(f"{self.label}: expected a list of tracks in {path}.")

        tracks: list[Track] = []
        for row in data:
            if not isinstance(row, dict) or not row.get("title"):
                continue
            track = Track.model_validate(
                {k: v for k, v in row.items() if k in Track.model_fields}
            )
            if not track.playlists:
                track.playlists = [self.label]
            tracks.append(track)
        return tracks
