from __future__ import annotations

import re
from typing import Any

from ..models import MediaInfo
from .ytdlp_base import YtDlpProvider

_HTTP_RE = re.compile(r"^https?://\S+$", re.IGNORECASE)


class GenericProvider(YtDlpProvider):
    """Anything yt-dlp can handle that no dedicated provider claimed.

    Registered last, this hands yt-dlp every URL the specific providers passed
    over. Whether any given site works is up to yt-dlp and how recently that
    site changed, so this is a best effort rather than a supported list.

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
