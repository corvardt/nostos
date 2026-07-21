from __future__ import annotations

import re

from .ytdlp_base import YtDlpProvider


class YouTubeProvider(YtDlpProvider):
    """Long-form videos, Shorts and youtu.be links."""

    name = "youtube"
    url_pattern = re.compile(
        r"^(https?://)?(www\.|m\.|music\.)?(youtube\.com/(watch\?|shorts/|live/|embed/|v/)|youtu\.be/)",
        re.IGNORECASE,
    )
    use_cookies = False
