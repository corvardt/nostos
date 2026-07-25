"""Recording which process is serving, so `nostos stop` has something to signal.

Written and cleared by the application's own lifespan rather than by the
launcher: uvicorn shuts down gracefully on SIGTERM and then re-raises the signal
with the default handler restored, so the process dies without unwinding, and a
`finally` in the launcher never runs. Lifespan shutdown does.

A leftover file is still expected - a kill -9, a power cut - so nothing here
trusts the file's mere existence. It is only ever believed about a pid that is
demonstrably still alive.
"""

from __future__ import annotations

import os

from . import config

PATH = config.DATA_DIR / "nostos.pid"


def write() -> None:
    PATH.parent.mkdir(parents=True, exist_ok=True)
    PATH.write_text(str(os.getpid()))


def clear() -> None:
    PATH.unlink(missing_ok=True)


def read() -> int | None:
    """The pid of a live server, or None. A file naming a dead process is not an
    error: it is what a crash or a reboot leaves behind."""
    try:
        pid = int(PATH.read_text().strip())
    except (OSError, ValueError):
        return None

    try:
        os.kill(pid, 0)  # signal 0 tests for existence without delivering one
    except OSError:
        return None
    return pid
