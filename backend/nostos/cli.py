"""The `nostos` command: start the server and open the interface.

One command, and a browser tab. The terminal is where this gets installed from,
not where it gets used.
"""

from __future__ import annotations

import argparse
import json
import os
import signal
import socket
import sys
import threading
import time
import urllib.error
import urllib.request
import webbrowser

from . import config, media, pidfile

DEFAULT_PORT = 8000
HOST = "127.0.0.1"

# What this is called on PyPI, which is not what it is called anywhere else:
# plain `nostos` belongs to an unrelated project. Only metadata lookups and the
# install line use this; the import package and the command are both `nostos`.
DISTRIBUTION = "nostos-app"

LOCAL_HOSTS = ("127.0.0.1", "localhost", "::1")


# --------------------------------------------------------------- the instance


def port_is_free(port: int, host: str = HOST) -> bool:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        try:
            sock.bind((host, port))
        except OSError:
            return False
    return True


def find_port(preferred: int, host: str = HOST) -> int:
    """The preferred port, or the next free one after it. Something else on 8000
    should not be a reason for the app to refuse to start."""
    for port in range(preferred, preferred + 20):
        if port_is_free(port, host):
            return port
    raise SystemExit(f"No free port between {preferred} and {preferred + 19}.")


def probe(port: int, host: str = HOST, timeout: float = 0.5) -> dict | None:
    """Ask whatever is on that port whether it is one of ours.

    A second launch should open a tab against the running instance rather than
    fail - and must not mistake an unrelated server for Nostos.
    """
    try:
        with urllib.request.urlopen(f"http://{host}:{port}/health", timeout=timeout) as res:
            body = json.loads(res.read())
    except (urllib.error.URLError, OSError, ValueError, TimeoutError):
        return None
    return body if body.get("status") == "ok" else None


def open_when_ready(url: str, host: str, port: int, timeout: float = 20.0) -> None:
    """Wait for the server this process is starting, then open the browser.
    Opening immediately races startup and lands on a connection error."""
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if probe(port, host):
            webbrowser.open(url)
            return
        time.sleep(0.15)
    print(f"The server did not answer within {timeout:.0f}s; open {url} yourself.", file=sys.stderr)


# ----------------------------------------------------------------- subcommands


def cmd_run(args: argparse.Namespace) -> int:
    running = probe(args.port, args.host)
    if running:
        url = f"http://{args.host}:{args.port}/"
        print(f"Nostos is already running at {url}")
        if not args.no_browser:
            webbrowser.open(url)
        return 0

    port = find_port(args.port, args.host)
    url = f"http://{args.host}:{port}/"

    from .ui import is_built

    if not is_built():
        print("Warning: no interface is bundled; the API will run but there is no page.", file=sys.stderr)

    if not args.no_ffmpeg:
        if not _provision_ffmpeg(auto=not args.no_download):
            print("Downloads that need converting or tagging will fail until ffmpeg is installed.\n", file=sys.stderr)

    # Directories are left to the app's own startup, which creates them after
    # the database exists: the download folder is a *setting*, so it cannot be
    # read before there is a settings table to read it from.
    #
    # Flushed explicitly, because redirected to a file this is block-buffered
    # and the URL would appear after uvicorn's logging rather than before it.
    print(f"Nostos  ->  {url}", flush=True)
    print(f"Data    ->  {config.DATA_DIR}", flush=True)
    if args.host not in LOCAL_HOSTS:
        print(
            "\n!! No authentication. Anyone who can reach this port can drive this machine. !!\n",
            file=sys.stderr,
            flush=True,
        )

    if not args.no_browser:
        threading.Thread(target=open_when_ready, args=(url, args.host, port), daemon=True).start()

    import uvicorn

    # The pid file is written and cleared by the app's lifespan, not here: on
    # SIGTERM uvicorn shuts down and then re-raises the signal with the default
    # handler restored, so nothing in this function would get to run.
    uvicorn.run(
        "nostos.main:app",
        host=args.host,
        port=port,
        reload=args.reload,
        log_level="warning" if args.quiet else "info",
        access_log=False,
    )
    return 0


def cmd_stop(args: argparse.Namespace) -> int:
    pid = pidfile.read()
    if pid is None:
        print("Nostos is not running.")
        return 0
    os.kill(pid, signal.SIGTERM)

    # Confirm rather than assume: a server mid-download takes a moment to unwind.
    for _ in range(50):
        time.sleep(0.1)
        if pidfile.read() is None:
            print(f"Stopped ({pid}).")
            return 0
    print(f"Process {pid} did not stop within 5s.", file=sys.stderr)
    return 1


def cmd_status(args: argparse.Namespace) -> int:
    found = probe(args.port, args.host)
    if found:
        print(f"running   http://{args.host}:{args.port}/  (version {found.get('version', '?')})")
        return 0
    print("stopped")
    return 1


def cmd_doctor(args: argparse.Namespace) -> int:
    """What is installed, what is missing, and where everything lives."""
    from .ui import is_built

    where = media.describe()
    lines = [
        ("python", sys.version.split()[0]),
        ("nostos", _version()),
        ("interface", "bundled" if is_built() else "NOT BUILT - run scripts/build-package.sh"),
        ("ffmpeg", where["using"] or "MISSING"),
        ("  from", "your system" if where["system"] else ("downloaded by nostos" if where["managed"] else "-")),
        ("data", str(config.DATA_DIR)),
        ("database", str(config.DB_PATH)),
        ("server", "running" if probe(args.port, args.host) else "stopped"),
    ]
    for label, value in lines:
        print(f"{label:<12}{value}")

    if not where["using"]:
        print("\nffmpeg is missing. `nostos ffmpeg` will fetch a static build into the data")
        print("directory, or install it with your package manager, which is the better option.")
        return 1
    return 0


def cmd_ffmpeg(args: argparse.Namespace) -> int:
    """Fetch ffmpeg on purpose, rather than as a side effect of starting."""
    where = media.locate()
    if where and not args.force:
        print(f"ffmpeg is already available at {where}")
        return 0
    return 0 if _provision_ffmpeg(auto=True, force=args.force) else 1


def _provision_ffmpeg(auto: bool, force: bool = False) -> bool:
    """Returns whether ffmpeg ended up available. Never raises: a machine with
    no ffmpeg should still get a running server and a clear explanation."""
    if not force and media.locate():
        return True
    if not auto:
        print("ffmpeg is missing. Run `nostos ffmpeg` to fetch one.", file=sys.stderr)
        return False

    print("ffmpeg is missing; fetching a static build (about 40 MB, once).", file=sys.stderr)
    last = [-1]

    def progress(done: int, total: int) -> None:
        pct = done * 100 // total
        if pct != last[0] and pct % 10 == 0:
            last[0] = pct
            print(f"  {pct}%", end="\r", file=sys.stderr, flush=True)

    try:
        where = media.fetch(progress)
    except media.FFmpegError as exc:
        print(f"\nCould not install ffmpeg: {exc}", file=sys.stderr)
        return False
    except Exception as exc:  # noqa: BLE001 - a failed fetch must not stop the app
        print(f"\nCould not download ffmpeg: {exc}", file=sys.stderr)
        return False

    # The progress line ends in a carriage return, so start a fresh one.
    print(f"\n  ffmpeg installed into {where}", file=sys.stderr)
    return True


def _version() -> str:
    from importlib.metadata import PackageNotFoundError, version

    try:
        return version(DISTRIBUTION)
    except PackageNotFoundError:
        return "unknown (not installed as a package)"


# ---------------------------------------------------------------------- entry


COMMANDS = {
    "run": cmd_run,
    "stop": cmd_stop,
    "status": cmd_status,
    "doctor": cmd_doctor,
    "ffmpeg": cmd_ffmpeg,
}


def build_parser() -> argparse.ArgumentParser:
    """One flat parser rather than subparsers, deliberately.

    Subparsers would require every global flag before the command word, so
    `nostos status --port 9000` would be an error while `nostos --port 9000
    status` was fine. Nobody should have to know that.
    """
    parser = argparse.ArgumentParser(prog="nostos", description="Download things, and keep them.")
    parser.add_argument(
        "command",
        nargs="?",
        default="run",
        choices=sorted(COMMANDS),
        help="run (the default), stop, status, doctor, ffmpeg",
    )
    parser.add_argument("--version", action="store_true", help="print the version and exit")
    parser.add_argument("--port", type=int, default=DEFAULT_PORT, help=f"default {DEFAULT_PORT}")
    parser.add_argument(
        "--host",
        default=HOST,
        help="default 127.0.0.1. There is no authentication: do not bind this to 0.0.0.0.",
    )
    parser.add_argument("--no-browser", action="store_true", help="run: start the server only")
    parser.add_argument("--no-ffmpeg", action="store_true", help="run: skip the ffmpeg check")
    parser.add_argument("--no-download", action="store_true", help="run: report a missing ffmpeg, never fetch it")
    parser.add_argument("--reload", action="store_true", help="run: restart on code changes")
    parser.add_argument("--quiet", action="store_true", help="run: log warnings and errors only")
    parser.add_argument("--force", action="store_true", help="ffmpeg: fetch even if one is present")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)

    if args.version:
        print(_version())
        return 0

    return int(COMMANDS[args.command](args))


if __name__ == "__main__":
    raise SystemExit(main())
