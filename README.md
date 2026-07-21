# Nostos

*(n.) the homecoming: the return journey that ends where you belong.*

Paste a link, see what it is, get the file. Nostos runs entirely on your own machine: no account,
no server, nothing sent anywhere except to the site you are downloading from.

## What works

| Platform | How | Login needed |
|---|---|---|
| YouTube | yt-dlp | no |
| Instagram | yt-dlp | usually not for public Reels |
| Threads | its own scraper, since yt-dlp has no Threads extractor | **always** |
| Anything else | passed to yt-dlp's extractors | depends |

The first three are the ones actually built and tested here. Everything else falls through to
yt-dlp, which supports a great many sites, but whether any given one works depends on yt-dlp and
on how recently that site changed. SoundCloud and direct media links work; Vimeo, at the time of
writing, does not. Treat the fallback as "worth a try", not a promise.

## Features

- Preview before downloading: title, author, thumbnail, duration, available qualities
- Queue many links at once, or expand a playlist and queue that
- One quality for a whole queue, chosen as a cap ("up to 1080p")
- Optional paste-to-download: one paste, no clicks
- Stop or retry anything, individually or all at once
- Title, artist, date, source URL, chapters and cover art embedded in every file
- Optional subtitles
- Skips what you have already downloaded
- A history of everything, with the reason for any failure

## Before you run it

**No authentication. Keep it on localhost.** Anyone who can reach the port can make your machine
download files and read your history. Do not bind it to `0.0.0.0` or put it on a public host. To
reach it from elsewhere, put a tunnel with access control in front, such as Cloudflare Tunnel
with Cloudflare Access.

**It reads your browser's cookies, narrowly.** Instagram and Threads need a logged-in session, so
Nostos reads cookies from a browser you pick in Settings. It does not hand your profile to
yt-dlp: the jar is filtered to the domain being contacted, written to a private file (`0600`,
inside `~/.local/share/nostos/cookies`) that exists only for that one request and is deleted
afterwards, including on failure. On a real profile of 790 cookies, 8 reached an Instagram
download. They still grant access to your accounts, so only run this on a machine you trust.

**Download only what you have the right to.** Respect each site's terms and your local copyright
law. You are responsible for how you use this.

## Quick start

Needs **Python 3.11+**, **Node 18+** and **ffmpeg**.

```bash
git clone https://github.com/corvardt/nostos.git
cd nostos
./run.sh
```

Open <http://localhost:5173>. The first run creates the virtualenv and installs npm packages.

| | |
|---|---|
| Frontend | <http://localhost:5173> |
| Backend | <http://127.0.0.1:8000> (API docs at `/docs`) |
| Downloads | `~/Downloads/Nostos` |
| Database | `~/.local/share/nostos/nostos.db` |

Set `NOSTOS_DATA_DIR` to keep the database somewhere else.

## Using it

Paste a link, press **Analyze**, pick a quality, press **Download**.

Paste several links, or a playlist URL, and you get a confirm step with the count and one quality
for the whole queue. That step is always shown, so a stray paste never starts downloads by
itself. Playlists are listed without fetching any videos, up to 200 items.

While a queue runs, finished items clear themselves after a few seconds. What stays on screen is
what still needs you: failed and stopped downloads, each with a **Retry**. **Clear** empties the
queue and stops anything running.

Downloads are paced per site: three at a time for YouTube, one at a time for Instagram and
Threads, which throttle bursts. Live broadcasts are refused, because they never finish.

## When something breaks

**A site suddenly stops working.** Usually the site changed and yt-dlp has caught up since:

```bash
backend/.venv/bin/pip install -U yt-dlp
```

**Threads says you are not signed in.** Sessions expire. Sign in again in the browser you picked
in Settings.

**Instagram or Threads cookies cannot be read on Linux.** Chromium-family browsers need the
`secretstorage` package (already a dependency) and an unlocked keyring. Firefox needs neither.

## How it is built

```
URL -> provider resolver -> media info -> download manager -> file + history
```

Each platform implements one interface (`backend/app/providers/base.py`):

```python
class Provider(ABC):
    def supports(self, url: str) -> bool: ...
    def resolve(self, url: str) -> MediaInfo: ...
    def download(self, url, fmt=None, on_progress=None) -> str: ...
```

`YtDlpProvider` implements it once over yt-dlp, and YouTube and Instagram supply little more than
a URL pattern. Threads implements the interface directly, because yt-dlp has no Threads
extractor: an anonymous request gets an empty page, so it needs a session cookie and browser-like
`Sec-Fetch-*` headers, then reads the media URLs out of the JSON inlined in the page.

Downloads run on a thread pool, since yt-dlp blocks. The UI polls `GET /jobs/{id}`.

### API

| Method | Path | |
|---|---|---|
| POST | `/analyze` | `{url}` to media info |
| POST | `/download` | `{url, format}` to a job id |
| POST | `/download/batch` | many URLs, with a reason for any skipped |
| POST | `/expand` | a playlist's items |
| GET | `/jobs/{id}` | progress and final path |
| POST | `/jobs/{id}/retry` | queue a failed or stopped job again |
| DELETE | `/jobs/{id}`, `/jobs` | stop one, or everything |
| GET/DELETE | `/history` | list, or empty it |
| GET/PUT | `/settings` | |

## Development

```bash
cd backend
.venv/bin/pip install -r requirements-dev.txt
.venv/bin/pytest

cd ../frontend && npm run build
```

The tests never touch a real site: providers are faked and page payloads come from fixtures.

The frontend is plain React, TypeScript and Vite, which is what a Tauri shell would wrap. Every
backend call lives in `frontend/src/lib/api.ts` and no component calls `fetch`, so swapping the
transport is a one-file change.

To add a site with its own handling, subclass `YtDlpProvider` with a URL pattern and register it
in `providers/registry.py`. Nothing else changes.

## Not implemented

Desktop packaging, multiple accounts per site, cloud or mobile sync, sharing.

## License

MIT. See [LICENSE](LICENSE).
