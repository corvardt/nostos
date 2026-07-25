"""The Provider that downloads one song.

Nostos's providers are stateless and keyed by URL, because a pasted link is all
they ever get. A library track carries more than its URL - the artist, album
and ISRC the *source* reported, which are more trustworthy than anything
YouTube will say about the same recording - so this provider is constructed per
track and keeps it.

That also gives the library row somewhere to be updated from: the provider
knows both the track and the outcome, so `jobs.py` needs no library-specific
hooks at all.
"""

from __future__ import annotations

import logging
import re
from pathlib import Path
from typing import Any

from ..providers.base import ProgressCallback, ProviderError
from ..providers.ytdlp_base import YtDlpProvider
from . import store
from .models import Track

log = logging.getLogger(__name__)

# Its own platform name, so `jobs.py` gives music downloads their own worker
# pool and history rows can be told apart from pasted links.
PLATFORM = "music"

# Anything yt-dlp might leave beside the finished audio.
_AUDIO_EXTS = ("mp3", "m4a", "opus", "flac", "ogg", "wav")


class TrackProvider(YtDlpProvider):
    """Audio-only download of one known song, tagged from the source metadata."""

    name = PLATFORM
    url_pattern = re.compile(r"^https?://", re.IGNORECASE)
    use_cookies = False

    def __init__(self, track: Track, dest: Path, audio_format: str = "mp3", quality: str = "0") -> None:
        self.track = track
        self.dest = dest
        self.audio_format = audio_format
        # yt-dlp's scale for VBR codecs: "0" is best, "5" is middling. A plain
        # number of kbps also works for CBR formats.
        self.quality = quality

    # ---------------------------------------------------------------- options

    def _postprocessors(self) -> list[dict[str, Any]]:
        """Extract audio and embed cover art. No FFmpegMetadata: it would write
        YouTube's idea of the title, which the tagging step then has to undo."""
        return [
            {
                "key": "FFmpegExtractAudio",
                "preferredcodec": self.audio_format,
                "preferredquality": self.quality,
            },
            {"key": "EmbedThumbnail", "already_have_thumbnail": False},
        ]

    def download(
        self,
        url: str,
        fmt: str | None = "best",
        on_progress: ProgressCallback | None = None,
    ) -> str:
        target = self.dest / self.track.filename(store.layout(), self.audio_format)
        target.parent.mkdir(parents=True, exist_ok=True)

        extra: dict[str, Any] = {
            # yt-dlp fills in %(ext)s, then the extract-audio postprocessor
            # renames to the final codec, landing exactly on `target`.
            "outtmpl": str(target.with_suffix("")) + ".%(ext)s",
            "format": "bestaudio/best",
            "writethumbnail": True,
            "postprocessors": self._postprocessors(),
            "noplaylist": True,
        }
        if on_progress:
            extra["progress_hooks"] = [on_progress]

        try:
            with self._session(url, extra) as opts, _ydl(opts) as ydl:
                ydl.extract_info(url, download=True)
        except Exception as exc:  # noqa: BLE001
            path = self._find_output(target)
            if not path:
                message = self._translate(exc).message if _is_ytdlp_error(exc) else str(exc)
                store.mark_failed(self.track.key, message)
                raise ProviderError(message) from exc
            # The audio is on disk and only a postprocessor failed - usually
            # artwork the container rejected. Keep the file.
            log.warning("post-processing failed for %s: %s", self.track.display_name, exc)
        else:
            path = self._find_output(target)

        if not path:
            message = "The download finished but produced no audio file."
            store.mark_failed(self.track.key, message)
            raise ProviderError(message)

        write_tags(path, self.track)
        store.mark_downloaded(self.track.key, str(path))
        return str(path)

    def _find_output(self, target: Path) -> Path | None:
        """Locate the finished audio.

        The postprocessor decides the final extension, and it does not always
        agree with what was asked for - a source already in the requested codec
        is passed through untouched. Look for the stem in any audio extension.
        """
        if target.exists():
            return target
        for ext in _AUDIO_EXTS:
            candidate = target.with_suffix(f".{ext}")
            if candidate.exists():
                return candidate
        return None


def _ydl(opts: dict):
    from yt_dlp import YoutubeDL

    return YoutubeDL(opts)


def _is_ytdlp_error(exc: Exception) -> bool:
    from yt_dlp.utils import DownloadError, ExtractorError

    return isinstance(exc, (DownloadError, ExtractorError))


# --------------------------------------------------------------------- tagging


def write_tags(path: Path, track: Track) -> bool:
    """Write the source's metadata over whatever YouTube supplied.

    This is the point of the whole exercise: the file is named and tagged from
    Spotify's or Apple's catalogue, not from a video title, so the archive is
    consistent no matter which video each track happened to come from.
    """
    try:
        from mutagen import File as MutagenFile
        from mutagen.easyid3 import EasyID3
        from mutagen.id3 import ID3NoHeaderError
    except ImportError:
        log.warning("mutagen is not installed; %s keeps YouTube's tags", path.name)
        return False

    try:
        if path.suffix.lower() == ".mp3":
            try:
                tags = EasyID3(str(path))
            except ID3NoHeaderError:
                tags = EasyID3()
                tags.save(str(path))
                tags = EasyID3(str(path))
        else:
            tags = MutagenFile(str(path), easy=True)
            if tags is None:
                return False

        tags["title"] = track.title
        tags["artist"] = track.artist
        if track.album:
            tags["album"] = track.album
        if track.year:
            tags["date"] = track.year
        if track.isrc:
            tags["isrc"] = track.isrc
        tags.save()
        return True
    except Exception as exc:  # noqa: BLE001 - untagged beats no file
        log.warning("could not tag %s: %s", path.name, exc)
        return False
