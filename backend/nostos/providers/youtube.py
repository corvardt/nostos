from __future__ import annotations

import re

from .ytdlp_base import YtDlpProvider

# A playlist page, or a video opened in the context of one (watch?v=..&list=..).
PLAYLIST_RE = re.compile(
    r"(youtube\.com/playlist\?|[?&]list=)",
    re.IGNORECASE,
)


class YouTubeProvider(YtDlpProvider):
    """Long-form videos, Shorts, youtu.be links and playlists."""

    name = "youtube"
    url_pattern = re.compile(
        r"^(https?://)?(www\.|m\.|music\.)?"
        r"(youtube\.com/(watch\?|shorts/|live/|embed/|v/|playlist\?)|youtu\.be/)",
        re.IGNORECASE,
    )
    use_cookies = False

    @staticmethod
    def is_playlist_url(url: str) -> bool:
        return bool(PLAYLIST_RE.search(url))
