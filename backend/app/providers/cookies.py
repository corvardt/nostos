"""Scoped, short-lived cookie files.

Handing yt-dlp `cookiesfrombrowser` gives it the whole browser profile: every
session you hold, for every site, on every request. A Threads download has no
business carrying your bank's session cookie.

So instead the jar is read once, filtered to the domains actually being talked
to, and written to a private file that exists only for the duration of the call.

The file is a secret while it lives, so:
  * it is created by `mkstemp` (mode 0600, unpredictable name, no race),
  * it lives under the app's own data directory, not in shared `/tmp`,
  * it is deleted in a `finally`, including when the download raises,
  * nothing about its contents is ever logged.
"""

from __future__ import annotations

import contextlib
import os
import stat
import tempfile
from collections.abc import Iterator, Sequence
from http.cookiejar import Cookie
from pathlib import Path
from urllib.parse import urlparse

from yt_dlp.cookies import YoutubeDLCookieJar, extract_cookies_from_browser

from .. import config


class _QuietLogger:
    """yt-dlp's cookie loader wants a logger. Cookie values must never be logged."""

    def debug(self, msg: str) -> None: ...
    def info(self, msg: str) -> None: ...
    def warning(self, msg: str, **kwargs) -> None: ...
    def error(self, msg: str) -> None: ...


def _cookie_dir() -> Path:
    path = config.DATA_DIR / "cookies"
    path.mkdir(parents=True, exist_ok=True)
    # Owner-only, in case the data directory itself is laxer.
    path.chmod(stat.S_IRWXU)
    return path


def domains_for(url: str) -> tuple[str, ...]:
    """The hostname of a URL plus its registrable parent, e.g. soundcloud.com."""
    host = (urlparse(url).hostname or "").lower().lstrip(".")
    if not host:
        return ()
    labels = host.split(".")
    parent = ".".join(labels[-2:]) if len(labels) > 2 else host
    return tuple({host, parent})


def _matches(cookie_domain: str, wanted: Sequence[str]) -> bool:
    domain = (cookie_domain or "").lower().lstrip(".")
    return any(domain == w or domain.endswith("." + w) for w in wanted)


def select(jar: Sequence[Cookie], domains: Sequence[str]) -> list[Cookie]:
    return [c for c in jar if _matches(c.domain, domains)]


@contextlib.contextmanager
def scoped_cookie_file(browser: str, domains: Sequence[str]) -> Iterator[Path | None]:
    """Yield a private cookie file holding only `domains`, or None if there are none.

    Yielding None matters: writing an empty file would put a pointless secret on
    disk and make yt-dlp think cookies were supplied when none were.
    """
    if not browser or not domains:
        yield None
        return

    try:
        source = extract_cookies_from_browser(browser, logger=_QuietLogger())
    except Exception as exc:  # noqa: BLE001 - keyring and profile failures vary
        raise CookieError(f"Could not read cookies from {browser}: {exc}") from exc

    wanted = select(source, domains)
    if not wanted:
        yield None
        return

    jar = YoutubeDLCookieJar()
    for cookie in wanted:
        jar.set_cookie(cookie)

    handle, name = tempfile.mkstemp(prefix="cookies-", suffix=".txt", dir=_cookie_dir())
    os.close(handle)  # mkstemp already created it 0600; write through the jar
    path = Path(name)
    try:
        jar.save(str(path), ignore_discard=True, ignore_expires=True)
        path.chmod(stat.S_IRUSR | stat.S_IWUSR)
        yield path
    finally:
        # The secret must not outlive the request that needed it, whatever happened.
        path.unlink(missing_ok=True)


class CookieError(Exception):
    """Reading the browser's cookie store failed."""
