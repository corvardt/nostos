from __future__ import annotations

import re
from typing import Any

from ..models import MediaInfo
from .ytdlp_base import YtDlpProvider

_HTTP_RE = re.compile(r"^https?://\S+$", re.IGNORECASE)


class GenericProvider(YtDlpProvider):
    """Anything yt-dlp can handle that no dedicated provider claimed.

    yt-dlp ships over 1700 extractors. Registered last, this hands them every
    URL the specific providers passed over, so TikTok, X, Reddit, Vimeo,
    SoundCloud, Twitch and the rest work without a class each.

    Cookies are offered because many of those sites gate content the same way
    Instagram does; they are only sent if a browser is configured in Settings.
    """

    name = "generic"
    url_pattern = _HTTP_RE
    use_cookies = True

    def supports(self, url: str) -> bool:
        return bool(_HTTP_RE.match(url.strip()))

    def _to_media_info(self, info: dict[str, Any]) -> MediaInfo:
        """Report the real site rather than "generic", so the preview names it."""
        media = super()._to_media_info(info)
        site = info.get("extractor_key") or info.get("extractor")
        if site and site.lower() != "generic":
            media.platform = site.lower()
        return media
