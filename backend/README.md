# nostos-app

Paste a link, get the file. Archive whole music accounts. Entirely on your own machine.

This is the installable package: the FastAPI backend, the yt-dlp providers, the library sync, and
the built interface, which ships inside the wheel so that installing this installs the whole
application. It provides two commands:

| | |
|---|---|
| `nostos` | start the server and open the interface |
| `nostos-library` | the library sync, without a browser |

`nostos doctor` reports what is installed and where things live.

## Install

Not from an index. The wheel is attached to each GitHub release:

```bash
curl -fsSL https://raw.githubusercontent.com/corvardt/nostos/main/scripts/install.sh | sh
```

## Building this from a checkout

The interface is generated rather than committed, so a wheel built without it installs cleanly and
then serves a 503 where the page should be:

```bash
./scripts/build-package.sh      # compiles frontend/ into nostos/static/
python -m build backend
```

Tests need neither step — `pytest` from this directory puts the package on the path itself.

Everything else, including what it does and where the service tokens come from, is in the
[repository README](https://github.com/corvardt/nostos#readme).
