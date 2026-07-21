from __future__ import annotations

import re

from .ytdlp_base import YtDlpProvider


class InstagramProvider(YtDlpProvider):
    """Posts and Reels.

    Instagram gates most anonymous requests, so this provider opts into the
    cookies-from-browser setting. Swapping the implementation to Instaloader later
    means replacing this class only - the Provider contract stays identical.
    """

    name = "instagram"
    url_pattern = re.compile(
        r"^(https?://)?(www\.)?instagram\.com/(p/|reel/|reels/|tv/|share/)",
        re.IGNORECASE,
    )
    use_cookies = True
