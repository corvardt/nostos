"""Shared yt-dlp implementation of the Provider contract.

Platform subclasses supply only a name, a URL pattern and any yt-dlp option
overrides - all of the resolve/download mechanics live here once.
"""

from __future__ import annotations

import re
from pathlib import Path
from typing import Any

from yt_dlp import YoutubeDL
from yt_dlp.utils import DownloadError, ExtractorError

from .. import config
from ..models import Format, MediaInfo
from .base import Provider, ProviderError, ProgressCallback

IMAGE_EXTS = {"jpg", "jpeg", "png", "webp", "heic", "gif"}

# Substrings yt-dlp puts in errors when a post is gated behind a login.
_AUTH_HINTS = (
    "login required",
    "log in",
    "requested content is not available",
    "rate-limit",
    "rate limit",
    "empty media response",
    "sign in",
    "private",
    "cookies",
)

# Standard ladder, filtered down to the heights the media actually offers.
_HEIGHT_LADDER = (2160, 1440, 1080, 720, 480, 360)


class YtDlpProvider(Provider):
    """Base class: subclasses set `name`, `url_pattern` and optionally `use_cookies`."""

    url_pattern: re.Pattern[str]
    use_cookies: bool = False

    def supports(self, url: str) -> bool:
        return bool(self.url_pattern.search(url.strip()))

    # ---------------------------------------------------------------- options

    def base_opts(self) -> dict[str, Any]:
        opts: dict[str, Any] = {
            "quiet": True,
            "no_warnings": True,
            "noprogress": True,
            "noplaylist": True,
            "extract_flat": False,
            # Progress hooks receive the same dict the console writer colorizes,
            # so without this `_speed_str` arrives wrapped in ANSI escape codes.
            "color": "no_color",
        }
        if self.use_cookies:
            browser = config.cookies_from_browser()
            if browser:
                opts["cookiesfrombrowser"] = (browser,)
        return opts

    # ---------------------------------------------------------------- resolve

    def resolve(self, url: str) -> MediaInfo:
        try:
            with YoutubeDL(self.base_opts()) as ydl:
                info = ydl.extract_info(url, download=False)
        except (DownloadError, ExtractorError) as exc:
            raise self._translate(exc) from exc

        if info is None:
            raise ProviderError("yt-dlp returned no information for this URL.")

        # Instagram/Threads posts arrive as a playlist of entries; preview the first.
        if info.get("_type") == "playlist" and info.get("entries"):
            entries = [e for e in info["entries"] if e]
            if not entries:
                raise ProviderError("This post contains no downloadable media.")
            info = entries[0]

        return self._to_media_info(info)

    def _to_media_info(self, info: dict[str, Any]) -> MediaInfo:
        is_image = self._is_image(info)
        return MediaInfo(
            platform=self.name,
            title=info.get("title") or info.get("id") or "Untitled",
            author=info.get("uploader") or info.get("channel") or info.get("uploader_id"),
            thumbnail=info.get("thumbnail"),
            duration=info.get("duration"),
            is_image=is_image,
            webpage_url=info.get("webpage_url"),
            formats=[] if is_image else self._simplify_formats(info),
        )

    @staticmethod
    def _is_image(info: dict[str, Any]) -> bool:
        if info.get("duration"):
            return False
        if (info.get("ext") or "").lower() in IMAGE_EXTS:
            return True
        formats = info.get("formats") or []
        if not formats:
            return (info.get("ext") or "").lower() in IMAGE_EXTS
        # No format carries a real video or audio codec -> it is a still image.
        return all(
            (f.get("vcodec") in (None, "none") and f.get("acodec") in (None, "none"))
            or (f.get("ext") or "").lower() in IMAGE_EXTS
            for f in formats
        )

    @staticmethod
    def _simplify_formats(info: dict[str, Any]) -> list[Format]:
        """Collapse yt-dlp's raw format list into a handful of meaningful choices.

        Selector *expressions* are returned rather than raw format ids: ids go stale
        between the analyze and download calls, expressions never do.
        """
        formats = info.get("formats") or []
        available = {f.get("height") for f in formats if f.get("height")}

        out = [Format(id="best", label="Best available", kind="video")]

        for height in _HEIGHT_LADDER:
            if any(h and h >= height for h in available):
                size = next(
                    (
                        f.get("filesize") or f.get("filesize_approx")
                        for f in formats
                        if f.get("height") == height
                    ),
                    None,
                )
                out.append(
                    Format(
                        id=f"bv*[height<={height}]+ba/b[height<={height}]",
                        label=f"{height}p",
                        ext="mp4",
                        height=height,
                        filesize=size,
                        kind="video",
                    )
                )

        if any(f.get("acodec") not in (None, "none") for f in formats):
            out.append(Format(id="ba[ext=m4a]/ba/b", label="Audio only (m4a)", ext="m4a", kind="audio"))

        return out

    # --------------------------------------------------------------- download

    def download(
        self,
        url: str,
        fmt: str | None = "best",
        on_progress: ProgressCallback | None = None,
    ) -> str:
        dest = config.download_dir()
        dest.mkdir(parents=True, exist_ok=True)

        opts = self.base_opts()
        opts.update(
            {
                "outtmpl": str(dest / "%(uploader,channel,extractor)s - %(title).100B [%(id)s].%(ext)s"),
                "restrictfilenames": True,
                "merge_output_format": "mp4",
                "windowsfilenames": True,
            }
        )
        # "best" needs an explicit selector so ffmpeg muxes video+audio together.
        opts["format"] = "bv*+ba/b" if fmt in (None, "", "best") else fmt
        if on_progress:
            opts["progress_hooks"] = [on_progress]

        try:
            with YoutubeDL(opts) as ydl:
                info = ydl.extract_info(url, download=True)
        except (DownloadError, ExtractorError) as exc:
            raise self._translate(exc) from exc

        path = self._final_path(info)
        if not path:
            raise ProviderError("Download finished but the output file could not be located.")
        return path

    @staticmethod
    def _final_path(info: dict[str, Any] | None) -> str | None:
        """Pull the post-merge path out of the info dict yt-dlp returns."""
        if not info:
            return None
        if info.get("_type") == "playlist" and info.get("entries"):
            info = next((e for e in info["entries"] if e), info)
        for download in info.get("requested_downloads") or []:
            path = download.get("filepath") or download.get("_filename")
            if path and Path(path).exists():
                return path
        path = info.get("filepath") or info.get("_filename")
        return path if path and Path(path).exists() else None

    # ----------------------------------------------------------------- errors

    def _translate(self, exc: Exception) -> ProviderError:
        """Turn a yt-dlp stack trace into something the UI can show a human."""
        message = str(exc).replace("ERROR: ", "").strip()
        lowered = message.lower()
        if self.use_cookies and any(hint in lowered for hint in _AUTH_HINTS):
            browser = config.cookies_from_browser()
            if browser:
                return ProviderError(
                    f"{self.name} refused the request even with {browser} cookies. "
                    "The post may be private, or you may need to log in to that browser again.",
                    needs_auth=True,
                )
            return ProviderError(
                f"{self.name} requires a login for this post. Pick the browser you are "
                "signed in with under Settings, and Nostos will reuse its cookies.",
                needs_auth=True,
            )
        return ProviderError(message or "yt-dlp failed to process this URL.")
