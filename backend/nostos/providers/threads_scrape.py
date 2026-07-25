"""Threads page fetching and media extraction.

yt-dlp has no Threads extractor, so this is the "extraction dédiée" the POC spec
allowed for. Threads inlines the post payload as escaped JSON inside the page -
but only for a request that looks like a real logged-in browser navigation.
Without the Sec-Fetch-* headers the server returns a 256 KB empty app shell.
"""

from __future__ import annotations

import gzip
import json
import re
import urllib.request
from typing import Any

USER_AGENT = (
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36"
)

# A plain GET gets the empty shell; these make it a "real navigation".
NAV_HEADERS = {
    "User-Agent": USER_AGENT,
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "en-US,en;q=0.9",
    "Sec-Fetch-Dest": "document",
    "Sec-Fetch-Mode": "navigate",
    "Sec-Fetch-Site": "none",
    "Sec-Fetch-User": "?1",
    "Upgrade-Insecure-Requests": "1",
}


def fetch_post_html(url: str, cookies: dict[str, str], timeout: int = 30) -> str:
    headers = dict(NAV_HEADERS)
    if cookies:
        headers["Cookie"] = "; ".join(f"{k}={v}" for k, v in cookies.items())
    req = urllib.request.Request(url, headers=headers)
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        raw = resp.read()
    if raw[:2] == b"\x1f\x8b":
        raw = gzip.decompress(raw)
    return raw.decode("utf-8", "replace")


def _unescape(html: str) -> str:
    """Undo the JSON-in-HTML escaping, preserving genuine escaped quotes."""
    return html.replace('\\"', "\x00").replace("\\/", "/").replace("\x00", '\\"')


def _json_at(text: str, start: int) -> Any:
    """Parse the JSON array/object starting at `start`, respecting string escapes."""
    open_ch = text[start]
    close_ch = {"[": "]", "{": "}"}[open_ch]
    depth = 0
    in_string = False
    escaped = False
    for i in range(start, len(text)):
        ch = text[i]
        if in_string:
            if escaped:
                escaped = False
            elif ch == "\\":
                escaped = True
            elif ch == '"':
                in_string = False
            continue
        if ch == '"':
            in_string = True
        elif ch == open_ch:
            depth += 1
        elif ch == close_ch:
            depth -= 1
            if depth == 0:
                return json.loads(text[start : i + 1])
    raise ValueError("unterminated JSON literal")


def _decode_text(raw: str) -> str:
    """Turn a raw JSON string body (with \\uXXXX escapes) into real text."""
    try:
        return json.loads(f'"{raw}"')
    except json.JSONDecodeError:
        return raw


def extract_media(html: str) -> dict[str, Any]:
    """Pull video URLs, image candidates and caption out of a Threads post page.

    Threads repeats the payload several times per page, so everything is
    de-duplicated by URL while preserving first-seen order.
    """
    text = _unescape(html)

    videos: list[str] = []
    for match in re.finditer(r'"video_versions":\s*(\[)', text):
        try:
            entries = _json_at(text, match.start(1))
        except (ValueError, json.JSONDecodeError):
            continue
        # Every `type` (101/102/103) points at the same progressive MP4.
        for entry in entries:
            url = entry.get("url")
            if url and url not in videos:
                videos.append(url)

    images: list[tuple[int, str]] = []
    seen_images: set[str] = set()
    for match in re.finditer(r'"image_versions2":\s*(\{)', text):
        try:
            obj = _json_at(text, match.start(1))
        except (ValueError, json.JSONDecodeError):
            continue
        for cand in obj.get("candidates") or []:
            url = cand.get("url")
            if url and url not in seen_images:
                seen_images.add(url)
                images.append((cand.get("width") or 0, url))
    images.sort(key=lambda pair: pair[0], reverse=True)

    caption = None
    cap_match = re.search(r'"caption":\s*\{.*?"text":\s*"(.*?)(?<!\\)"', text, re.DOTALL)
    if cap_match:
        caption = _decode_text(cap_match.group(1)).strip() or None

    return {
        "videos": videos,
        "images": [url for _, url in images],
        "thumbnail": images[0][1] if images else None,
        "caption": caption,
    }
