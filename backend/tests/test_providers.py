"""Provider routing and info-dict mapping. No network - fixtures only."""

from __future__ import annotations

import pytest

from app.providers import ProviderError, resolve_provider
from app.providers.ytdlp_base import YtDlpProvider


@pytest.mark.parametrize(
    ("url", "expected"),
    [
        ("https://www.youtube.com/watch?v=dQw4w9WgXcQ", "youtube"),
        ("https://youtu.be/dQw4w9WgXcQ", "youtube"),
        ("https://www.youtube.com/shorts/abc123", "youtube"),
        ("https://m.youtube.com/watch?v=abc", "youtube"),
        ("https://music.youtube.com/watch?v=abc", "youtube"),
        ("https://www.instagram.com/p/Cxyz/", "instagram"),
        ("https://www.instagram.com/reel/Cxyz/", "instagram"),
        ("https://instagram.com/tv/Cxyz/", "instagram"),
        ("https://www.threads.net/@someone/post/Cxyz", "threads"),
        ("https://www.threads.com/@someone/post/Cxyz", "threads"),
    ],
)
def test_routes_to_expected_provider(url: str, expected: str) -> None:
    assert resolve_provider(url).name == expected


@pytest.mark.parametrize("url", ["not a url", "", "   ", "ftp://example.com/x", "javascript:alert(1)"])
def test_rejects_things_that_are_not_links(url: str) -> None:
    with pytest.raises(ProviderError):
        resolve_provider(url)


@pytest.mark.parametrize(
    "url",
    [
        "https://vimeo.com/12345",
        "https://www.tiktok.com/@someone/video/123",
        "https://x.com/someone/status/1",
        "https://soundcloud.com/artist/track",
        # A bare Instagram profile is a feed, not a post, so the dedicated
        # provider passes and the fallback takes it.
        "https://www.instagram.com/someuser/",
    ],
)
def test_unclaimed_links_fall_through_to_generic(url: str) -> None:
    assert resolve_provider(url).name == "generic"


def test_dedicated_providers_still_win_over_generic() -> None:
    assert resolve_provider("https://youtu.be/abc").name == "youtube"
    assert resolve_provider("https://www.instagram.com/reel/Cxyz/").name == "instagram"
    assert resolve_provider("https://www.threads.com/@a/post/b").name == "threads"


def test_whitespace_is_tolerated() -> None:
    assert resolve_provider("  https://youtu.be/abc  ").name == "youtube"


# ------------------------------------------------------------- info mapping


def test_maps_video_info_to_media_info() -> None:
    provider = resolve_provider("https://youtu.be/abc")
    info = {
        "title": "A Video",
        "uploader": "Someone",
        "thumbnail": "https://example.com/t.jpg",
        "duration": 212.0,
        "webpage_url": "https://youtu.be/abc",
        "formats": [
            {"height": 1080, "ext": "mp4", "vcodec": "avc1", "acodec": "none", "filesize": 1000},
            {"height": 360, "ext": "mp4", "vcodec": "avc1", "acodec": "mp4a"},
            {"height": None, "ext": "m4a", "vcodec": "none", "acodec": "mp4a"},
        ],
    }

    media = provider._to_media_info(info)

    assert media.platform == "youtube"
    assert media.title == "A Video"
    assert media.author == "Someone"
    assert media.duration == 212.0
    assert media.is_image is False

    labels = [f.label for f in media.formats]
    assert labels[0] == "Best available"
    assert "1080p" in labels
    assert "360p" in labels
    # Nothing above 1080p was offered, so the ladder must not invent 1440p/2160p.
    assert "1440p" not in labels
    assert "Audio only (m4a)" in labels


def test_image_post_is_flagged_and_offers_no_formats() -> None:
    provider = resolve_provider("https://www.instagram.com/p/Cxyz/")
    info = {
        "title": "A photo",
        "ext": "jpg",
        "duration": None,
        "formats": [{"ext": "jpg", "vcodec": "none", "acodec": "none"}],
    }

    media = provider._to_media_info(info)

    assert media.is_image is True
    assert media.formats == []


def test_duration_alone_rules_out_image() -> None:
    assert YtDlpProvider._is_image({"duration": 30, "ext": "jpg"}) is False


def test_final_path_missing_file_returns_none() -> None:
    assert YtDlpProvider._final_path({"filepath": "/nope/missing.mp4"}) is None
    assert YtDlpProvider._final_path(None) is None


# ------------------------------------------------------- progress sanitising


def test_speed_string_is_stripped_of_ansi_colour() -> None:
    """yt-dlp colorizes `_speed_str` in the same dict it gives progress hooks,
    so an unscrubbed value reaches the browser as a literal "␛"."""
    from app.jobs import _plain

    assert _plain("\x1b[0;32m   2.15MiB/s\x1b[0m") == "2.15MiB/s"


def test_plain_handles_empty_and_uncoloured_values() -> None:
    from app.jobs import _plain

    assert _plain("  1.2MiB/s  ") == "1.2MiB/s"
    assert _plain("") is None
    assert _plain(None) is None
    assert _plain("\x1b[0;32m\x1b[0m") is None


# ------------------------------------------------------------ live streams


def test_live_stream_is_detected() -> None:
    """A running broadcast never finishes downloading, so it must be refused
    rather than left to occupy a worker forever."""
    assert YtDlpProvider._is_live({"is_live": True}) is True
    assert YtDlpProvider._is_live({"live_status": "is_live"}) is True


def test_finished_stream_is_downloadable() -> None:
    assert YtDlpProvider._is_live({"live_status": "was_live"}) is False
    assert YtDlpProvider._is_live({"live_status": "not_live"}) is False
    assert YtDlpProvider._is_live({}) is False


def test_live_detected_through_playlist_wrapper() -> None:
    assert YtDlpProvider._is_live({"_type": "playlist", "entries": [{"is_live": True}]}) is True


def test_unknown_codecs_are_not_treated_as_an_image() -> None:
    """Many extractors leave vcodec/acodec unset. Reading "not reported" as
    "not present" made direct video links look like stills, which hid the
    quality picker and mislabelled them in the preview."""
    info = {"ext": "webm", "formats": [{"ext": "webm", "vcodec": None, "acodec": None}]}
    assert YtDlpProvider._is_image(info) is False


def test_image_formats_are_still_detected() -> None:
    info = {"ext": "jpg", "formats": [{"ext": "jpg"}, {"ext": "webp"}]}
    assert YtDlpProvider._is_image(info) is True
