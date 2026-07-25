"""Threads dedicated extraction. Fixtures mirror the real page payload shape."""

from __future__ import annotations

from nostos.providers import resolve_provider
from nostos.providers.threads import ThreadsProvider
from nostos.providers.threads_scrape import extract_media

# Threads inlines the payload as escaped JSON, hence the \" and \/ sequences.
VIDEO_PAGE = r'''
<script>{"post":{"caption":{"text":"Hello テスト"},
"image_versions2":{"candidates":[
 {"width":640,"height":480,"url":"https:\/\/cdn.example.com\/cover_640.jpg"},
 {"width":150,"height":100,"url":"https:\/\/cdn.example.com\/cover_150.jpg"}]},
"video_versions":[
 {"type":101,"url":"https:\/\/cdn.example.com\/clip.mp4"},
 {"type":102,"url":"https:\/\/cdn.example.com\/clip.mp4"},
 {"type":103,"url":"https:\/\/cdn.example.com\/clip.mp4"}]}}</script>
'''

IMAGE_PAGE = r'''
<script>{"post":{"caption":{"text":"a photo"},
"image_versions2":{"candidates":[
 {"width":1080,"height":1080,"url":"https:\/\/cdn.example.com\/photo_1080.jpg"},
 {"width":320,"height":320,"url":"https:\/\/cdn.example.com\/photo_320.jpg"}]}}}</script>
'''


def test_extracts_single_video_despite_repeated_types() -> None:
    media = extract_media(VIDEO_PAGE)
    # The three `type` entries all point at the same MP4 - it must appear once.
    assert media["videos"] == ["https://cdn.example.com/clip.mp4"]


def test_prefers_widest_image_as_thumbnail() -> None:
    media = extract_media(VIDEO_PAGE)
    assert media["thumbnail"] == "https://cdn.example.com/cover_640.jpg"


def test_decodes_unicode_escapes_in_caption() -> None:
    assert extract_media(VIDEO_PAGE)["caption"] == "Hello テスト"


def test_image_post_has_no_videos() -> None:
    media = extract_media(IMAGE_PAGE)
    assert media["videos"] == []
    assert media["images"][0] == "https://cdn.example.com/photo_1080.jpg"


def test_text_only_post_yields_nothing() -> None:
    media = extract_media('<script>{"post":{"caption":{"text":"just words"}}}</script>')
    assert media["videos"] == [] and media["images"] == []


def test_empty_shell_yields_nothing() -> None:
    media = extract_media("<html><body>no payload here</body></html>")
    assert media["videos"] == [] and media["images"] == []


# ------------------------------------------------------------------- routing


def test_short_link_form_routes_to_threads() -> None:
    # threads.com/t/CODE is the share-sheet form and must not fall through.
    assert resolve_provider("https://www.threads.com/t/C0ffeeShortId").name == "threads"


def test_handle_is_taken_from_the_url() -> None:
    handle = ThreadsProvider._handle("https://www.threads.com/@example.user/post/C0ffeePostId")
    assert handle == "@example.user"


def test_handle_absent_for_short_links() -> None:
    assert ThreadsProvider._handle("https://www.threads.com/t/C0ffeeShortId") is None


def test_threads_no_longer_uses_ytdlp() -> None:
    # yt-dlp has no Threads extractor; inheriting from it would silently fall
    # through to the `generic` extractor and find nothing.
    from nostos.providers.ytdlp_base import YtDlpProvider

    assert not isinstance(resolve_provider("https://www.threads.com/t/abc"), YtDlpProvider)
