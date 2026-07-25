"""Threads provider - dedicated extraction, not yt-dlp.

yt-dlp ships no Threads extractor (every Threads URL falls through to `generic`,
which finds nothing), so this implements the Provider contract directly against
the page payload. The spec anticipated this: "Provider Threads basé sur yt-dlp
ou extraction dédiée".

Requires a logged-in session: Threads serves an empty app shell to anonymous
requests. The user picks their browser under Settings and we reuse its cookies.
"""

from __future__ import annotations

import re
import time
import urllib.error
import urllib.request
from pathlib import Path

from .. import config
from ..models import Format, MediaInfo
from .base import Provider, ProviderError, ProgressCallback
from .cookies import CookieError, _QuietLogger, select
from .threads_scrape import USER_AGENT, extract_media, fetch_post_html

THREADS_DOMAINS = ("threads.com", "threads.net")

_URL_RE = re.compile(
    r"^(https?://)?(www\.)?threads\.(net|com)/(@[\w.]+/post/|t/)([\w-]+)",
    re.IGNORECASE,
)


class ThreadsProvider(Provider):
    name = "threads"

    def supports(self, url: str) -> bool:
        return bool(_URL_RE.search(url.strip()))

    # ---------------------------------------------------------------- cookies

    def _cookies(self) -> dict[str, str]:
        browser = config.cookies_from_browser()
        if not browser:
            raise ProviderError(
                "Threads only serves post data to a logged-in session. Pick the browser "
                "you are signed in to Threads with under Settings.",
                needs_auth=True,
            )
        from yt_dlp.cookies import extract_cookies_from_browser

        try:
            jar = extract_cookies_from_browser(browser, logger=_QuietLogger())
        except Exception as exc:  # noqa: BLE001 - keyring/browser failures vary widely
            raise ProviderError(f"Could not read cookies from {browser}: {exc}", needs_auth=True) from exc

        # Only Threads' own cookies leave this function; the rest of the profile
        # is dropped here rather than being carried into the request.
        cookies = {c.name: c.value for c in select(jar, THREADS_DOMAINS)}
        if "sessionid" not in cookies:
            raise ProviderError(
                f"No Threads login found in {browser}. Open threads.com in {browser}, "
                "sign in, then try again.",
                needs_auth=True,
            )
        return cookies

    def _fetch(self, url: str) -> dict:
        try:
            html = fetch_post_html(url, self._cookies())
        except urllib.error.HTTPError as exc:
            raise ProviderError(f"Threads returned HTTP {exc.code} for this post.") from exc
        except urllib.error.URLError as exc:
            raise ProviderError(f"Could not reach Threads: {exc.reason}") from exc

        media = extract_media(html)
        if not media["videos"] and not media["images"]:
            raise ProviderError(
                "No media found in this Threads post. It may be text-only, deleted, "
                "or your session may have expired - try signing in again.",
                needs_auth=True,
            )
        return media

    # ---------------------------------------------------------------- resolve

    def resolve(self, url: str) -> MediaInfo:
        url = url.strip()
        media = self._fetch(url)
        handle = self._handle(url)
        is_image = not media["videos"]

        return MediaInfo(
            platform=self.name,
            title=media["caption"] or f"Threads post by {handle or 'unknown'}",
            author=handle,
            thumbnail=media["thumbnail"],
            duration=None,
            is_image=is_image,
            webpage_url=url,
            formats=[] if is_image else [Format(id="best", label="Best available", ext="mp4")],
        )

    @staticmethod
    def _handle(url: str) -> str | None:
        # The handle is in the URL, which is far more reliable than scraping it.
        match = re.search(r"threads\.(?:net|com)/@([\w.]+)/", url, re.IGNORECASE)
        return f"@{match.group(1)}" if match else None

    # --------------------------------------------------------------- download

    def download(
        self,
        url: str,
        fmt: str | None = "best",
        on_progress: ProgressCallback | None = None,
    ) -> str:
        url = url.strip()
        media = self._fetch(url)
        source = media["videos"][0] if media["videos"] else media["images"][0]

        title = media["caption"] or f"Threads post by {self._handle(url) or 'unknown'}"
        code_match = _URL_RE.search(url)
        code = code_match.group(5) if code_match else str(int(time.time()))
        ext = "mp4" if media["videos"] else self._image_ext(source)

        dest_dir = config.download_dir()
        dest_dir.mkdir(parents=True, exist_ok=True)
        dest = dest_dir / f"threads - {self._handle(url) or 'post'} [{code}].{ext}"

        self._stream(source, dest, title, on_progress)
        return str(dest)

    @staticmethod
    def _image_ext(url: str) -> str:
        match = re.search(r"\.(jpg|jpeg|png|webp|heic)", url, re.IGNORECASE)
        return match.group(1).lower() if match else "jpg"

    @staticmethod
    def _stream(
        source: str,
        dest: Path,
        title: str,
        on_progress: ProgressCallback | None,
    ) -> None:
        """Fetch a CDN URL to disk, emitting yt-dlp-shaped progress events."""
        req = urllib.request.Request(source, headers={"User-Agent": USER_AGENT})
        info = {"title": title}
        started = time.time()

        try:
            with urllib.request.urlopen(req, timeout=60) as resp:
                total = int(resp.headers.get("Content-Length") or 0)
                downloaded = 0
                # Write to a temp name so a failed download never looks complete.
                tmp = dest.with_suffix(dest.suffix + ".part")
                with open(tmp, "wb") as fh:
                    while chunk := resp.read(256 * 1024):
                        fh.write(chunk)
                        downloaded += len(chunk)
                        if on_progress:
                            elapsed = max(time.time() - started, 0.001)
                            speed = downloaded / elapsed
                            on_progress(
                                {
                                    "status": "downloading",
                                    "downloaded_bytes": downloaded,
                                    "total_bytes": total or None,
                                    "_speed_str": f"{speed / 1024 / 1024:.1f} MiB/s",
                                    "eta": int((total - downloaded) / speed) if total and speed else None,
                                    "info_dict": info,
                                }
                            )
                tmp.replace(dest)
        except urllib.error.HTTPError as exc:
            raise ProviderError(
                f"Threads CDN returned HTTP {exc.code}. The media link may have expired - "
                "run Analyze again."
            ) from exc
        except urllib.error.URLError as exc:
            raise ProviderError(f"Could not download from the Threads CDN: {exc.reason}") from exc

        if on_progress:
            on_progress({"status": "finished", "filename": str(dest), "info_dict": info})
