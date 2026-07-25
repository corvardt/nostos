"""Headless one-pass archive: `python -m app.library.cli sync`.

Same code the API runs, without needing the server or the browser - which is
what a cron job wants. Downloads go through the same job queue, so the process
must stay alive until they finish; `sync` waits for them and reports.
"""

from __future__ import annotations

import argparse
import json
import sys
import time

from .. import config, db
from . import store, sync
from .models import SourceConfig, SyncRequest
from .sources import REGISTRY, SourceError, build_source

POLL_INTERVAL_S = 1.0


def _bootstrap() -> None:
    db.init()
    store.init()
    config.ensure_dirs()
    store.music_dir().mkdir(parents=True, exist_ok=True)


def cmd_sources(args: argparse.Namespace) -> int:
    sources = store.list_sources()
    if not sources:
        print("No sources configured. Add one with:")
        print('  python -m app.library.cli add-source spotify --option liked=true \\')
        print('      --option client_id=... --option client_secret=...')
        return 0
    for source in sources:
        state = "" if source.enabled else "  (disabled)"
        print(f"[{source.id}] {source.label} — {source.type}{state}")
        for key, value in source.redacted().options.items():
            print(f"      {key} = {value}")
    return 0


def _parse_option(raw: str) -> tuple[str, object]:
    if "=" not in raw:
        raise SystemExit(f"Options look like key=value, not {raw!r}.")
    key, value = raw.split("=", 1)
    key, value = key.strip(), value.strip()

    if value.lower() in ("true", "false"):
        return key, value.lower() == "true"
    if value.startswith("["):
        return key, json.loads(value)
    # A comma in a value means a list; playlist ids are the only thing that
    # arrives this way and they never contain commas themselves.
    if "," in value:
        return key, [part.strip() for part in value.split(",") if part.strip()]
    return key, value


def cmd_add_source(args: argparse.Namespace) -> int:
    if args.type not in REGISTRY:
        print(f"Unknown source type {args.type!r}. Available: {', '.join(sorted(REGISTRY))}.")
        return 2
    options = dict(_parse_option(raw) for raw in args.option or [])
    source = store.add_source(
        SourceConfig(type=args.type, label=args.label or args.type, options=options)
    )
    print(f"Added source [{source.id}] {source.label}.")
    return 0


def cmd_remove_source(args: argparse.Namespace) -> int:
    if not store.delete_source(args.id):
        print(f"No source with id {args.id}.")
        return 1
    print(f"Removed source {args.id}.")
    return 0


def cmd_test(args: argparse.Namespace) -> int:
    row = store.get_source(args.id)
    if row is None:
        print(f"No source with id {args.id}.")
        return 1
    try:
        tracks = build_source(row.type, row.options, row.label).fetch()
    except SourceError as exc:
        print(f"{row.label}: {exc.message}")
        return 1
    with_isrc = sum(1 for track in tracks if track.isrc)
    print(f"{row.label}: {len(tracks)} tracks, {with_isrc} with an ISRC.")
    for track in tracks[:10]:
        print(f"  {track.display_name}")
    return 0


def cmd_status(args: argparse.Namespace) -> int:
    counts = store.counts()
    if not counts:
        print("Nothing collected yet. Run: python -m app.library.cli sync")
        return 0
    width = max(len(status) for status in counts)
    for status, count in sorted(counts.items(), key=lambda item: -item[1]):
        print(f"  {status:<{width}}  {count}")
    print(f"  {'total':<{width}}  {sum(counts.values())}")
    print(f"\nMusic folder: {store.music_dir()}")
    return 0


def cmd_sync(args: argparse.Namespace) -> int:
    from .. import jobs

    report = sync.run(
        SyncRequest(
            source_ids=args.source or [],
            dry_run=args.dry_run,
            retry_failed=args.retry_failed,
            limit=args.limit,
        )
    )

    print(f"  collected           {report.collected}")
    print(f"  unique tracks       {report.unique}")
    print(f"  already downloaded  {report.already_downloaded}")
    print(f"  already owned       {report.already_owned}")
    print(f"  queued              {report.queued}")
    for failure in report.failed_sources:
        print(f"  ! {failure}")

    if args.dry_run or not report.job_ids:
        return 1 if report.failed_sources else 0

    print(f"\nDownloading {len(report.job_ids)} tracks. Ctrl-C stops after the current one.")
    done = 0
    try:
        while True:
            states = [jobs.get(job_id) for job_id in report.job_ids]
            finished = [job for job in states if job and job.status in ("done", "error", "cancelled")]
            if len(finished) != done:
                done = len(finished)
                print(f"\r  {done}/{len(report.job_ids)} finished", end="", flush=True)
            if done == len(report.job_ids):
                break
            time.sleep(POLL_INTERVAL_S)
    except KeyboardInterrupt:
        jobs.cancel_all()
        print("\nStopped. Re-run to pick up where this left off.")
        return 130

    errors = [job for job in (jobs.get(j) for j in report.job_ids) if job and job.status == "error"]
    print(f"\n\n{len(report.job_ids) - len(errors)} downloaded, {len(errors)} failed.")
    for job in errors[:20]:
        print(f"  ! {job.title or job.url}: {job.error}")
    return 1 if errors else 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="python -m app.library.cli",
        description="Archive your music library from Apple Music, Spotify, Deezer and YouTube.",
    )
    sub = parser.add_subparsers(dest="command", required=True)

    sync_parser = sub.add_parser("sync", help="one pass: collect, then download what is missing")
    sync_parser.add_argument("--source", type=int, action="append", help="limit to this source id")
    sync_parser.add_argument("--dry-run", action="store_true", help="collect and record, queue nothing")
    sync_parser.add_argument("--retry-failed", action="store_true", help="try failed tracks again")
    sync_parser.add_argument("--limit", type=int, default=0, help="queue at most this many tracks")
    sync_parser.set_defaults(func=cmd_sync)

    sub.add_parser("sources", help="list configured sources").set_defaults(func=cmd_sources)
    sub.add_parser("status", help="what has been collected and downloaded").set_defaults(func=cmd_status)

    add_parser = sub.add_parser("add-source", help="configure a new source")
    add_parser.add_argument("type", choices=sorted(REGISTRY))
    add_parser.add_argument("--label", default="", help="name to show for it")
    add_parser.add_argument("--option", action="append", metavar="KEY=VALUE")
    add_parser.set_defaults(func=cmd_add_source)

    remove_parser = sub.add_parser("remove-source", help="delete a source")
    remove_parser.add_argument("id", type=int)
    remove_parser.set_defaults(func=cmd_remove_source)

    test_parser = sub.add_parser("test-source", help="check one source's credentials")
    test_parser.add_argument("id", type=int)
    test_parser.set_defaults(func=cmd_test)

    args = parser.parse_args(argv)
    _bootstrap()
    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())
