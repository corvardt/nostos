"""An index of the music you already have.

Nostos's own duplicate check is by URL, which cannot help here: the same song
downloaded last year from a different YouTube video is still the same song.
This matches on artist and title instead, against folders that Nostos never
wrote - an existing Spotify or Apple Music export, a ripped collection.
"""

from __future__ import annotations

import os
from pathlib import Path

from .models import Track
from .text import jaccard, tokenize

AUDIO_EXTENSIONS = {".mp3", ".m4a", ".flac", ".ogg", ".wav", ".opus", ".aac", ".wma"}

# Word overlap above which a file on disk *is* the track being asked for,
# whatever the word order or a leading track number.
MATCH_THRESHOLD = 0.7


class MusicIndex:
    """Filename-based index of one or more music folders.

    Built from filenames rather than tags: reading tags from thousands of files
    costs seconds per thousand and buys little, because anything that wrote
    those files also named them.
    """

    def __init__(self, directories: list[str] | None = None) -> None:
        self.entries: list[tuple[str, set[str]]] = []
        self._by_token: dict[str, list[int]] = {}
        self.missing_dirs: list[str] = []
        self._build(directories or [])

    def _build(self, directories: list[str]) -> None:
        for directory in directories:
            path = Path(directory).expanduser()
            if not path.is_dir():
                self.missing_dirs.append(str(path))
                continue
            for root, _, files in os.walk(path):
                for name in files:
                    stem, ext = os.path.splitext(name)
                    if ext.lower() not in AUDIO_EXTENSIONS:
                        continue
                    tokens = tokenize(stem)
                    if not tokens:
                        continue
                    self.entries.append((os.path.join(root, name), tokens))
                    index = len(self.entries) - 1
                    for token in tokens:
                        self._by_token.setdefault(token, []).append(index)

    def __len__(self) -> int:
        return len(self.entries)

    def find(self, track: Track) -> str | None:
        """Path of the file that already holds this track, if any.

        Only files sharing at least one word with the query are compared. A
        full scan per track turned a sync of a few hundred songs against a
        library of a few thousand files into minutes of pure comparison.
        """
        query = track.tokens
        if not query:
            return None

        seen: set[int] = set()
        for token in query:
            for index in self._by_token.get(token, ()):
                if index in seen:
                    continue
                seen.add(index)
                path, tokens = self.entries[index]
                if jaccard(query, tokens) >= MATCH_THRESHOLD:
                    return path
        return None
