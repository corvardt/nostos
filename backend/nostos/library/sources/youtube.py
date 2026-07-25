"""YouTube and YouTube Music playlists, via yt-dlp.

Any playlist URL works, including Liked Music and mixes. Private ones need a
signed-in session, which reuses the browser Nostos is already configured to
read cookies from in Settings.

The metadata is the weak point: outside YouTube Music there are no artist or
album fields, only a video title. Flat extraction is fast but gives just that
title, so the artist is inferred from the "Artist - Title" convention.
`resolve_metadata` extracts every entry in full instead, which YouTube Music
answers with real artist/track/album fields - correct, and far slower.
"""

from __future__ import annotations

import logging
from typing import Any

from ... import config
from ...providers.cookies import CookieError, scoped_cookie_file
from ..models import Track
from ..text import split_artist_title
from .base import Source, SourceError

log = logging.getLogger(__name__)

COOKIE_DOMAINS = ("youtube.com", "google.com")


class YouTubeSource(Source):
    name = "youtube"
    description = "YouTube / YouTube Music playlists"

    def _options(self, flat: bool) -> dict[str, Any]:
        return {
            "quiet": True,
            "no_warnings": True,
            "skip_download": True,
            "ignoreerrors": True,
            "extract_flat": "in_playlist" if flat else False,
            "noprogress": True,
            "color": "no_color",
        }

    @staticmethod
    def _to_track(entry: dict, playlist: str) -> Track | None:
        if not entry:
            return None

        # YouTube Music fills track/artist; plain YouTube leaves both unset.
        title = entry.get("track") or entry.get("title") or ""
        artist = entry.get("artist") or entry.get("creator") or ""
        if not artist:
            artist, title = split_artist_title(
                entry.get("title", ""),
                entry.get("uploader") or entry.get("channel") or "",
            )
        if not title:
            return None

        video_id = entry.get("id", "")
        return Track(
            title=title,
            artist=artist,
            album=entry.get("album", "") or "",
            duration_s=int(entry.get("duration") or 0),
            year=str(entry.get("release_year") or "")[:4],
            origins={"youtube": video_id},
            playlists=[playlist],
            # A YouTube track already knows where it lives, so the resolver can
            # skip searching for it entirely.
            url=entry.get("webpage_url")
            or (f"https://www.youtube.com/watch?v={video_id}" if video_id else ""),
        )

    def fetch(self) -> list[Track]:
        from yt_dlp import YoutubeDL

        urls = self.options.get("playlists", [])
        if not urls:
            raise SourceError(f"{self.label}: no playlist URL configured.")

        flat = not self.options.get("resolve_metadata", False)
        options = self._options(flat)
        tracks: list[Track] = []

        browser = config.cookies_from_browser() if self.options.get("use_cookies") else ""
        try:
            with scoped_cookie_file(browser, COOKIE_DOMAINS) as jar:
                if jar:
                    options["cookiefile"] = str(jar)
                with YoutubeDL(options) as ydl:
                    for url in urls:
                        info = ydl.extract_info(url, download=False)
                        if not info:
                            log.warning("%s: could not read playlist %s", self.label, url)
                            continue
                        playlist = f"{self.label}: {info.get('title') or info.get('id') or url}"
                        # A single video URL comes back without an entries list.
                        entries = info.get("entries")
                        if entries is None:
                            entries = [info]
                        for entry in entries:
                            track = self._to_track(entry, playlist)
                            if track:
                                tracks.append(track)
        except CookieError as exc:
            raise SourceError(str(exc), needs_auth=True) from exc

        return tracks
