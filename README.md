# Nostos

*(n.) the homecoming: the return journey that ends where you belong.*

A local media downloader for YouTube, Instagram and Threads. Paste a link, see a preview, get the
original file. Everything runs on your own machine: no account, no server, no external service.

## Features

- **Over 1700 sites.** YouTube, Instagram and Threads have dedicated handling; everything else
  yt-dlp supports (TikTok, X, Reddit, Vimeo, SoundCloud, Twitch and the rest) is picked up by a
  generic fallback.
- **Preview before you commit.** Title, author, thumbnail, duration and the qualities on offer.
- **Batch downloads.** Paste any number of links at once and queue them together.
- **Playlist expansion.** Paste a playlist and it lists its items, up to 200, in a couple of
  seconds without fetching a single video.
- **One quality for a whole queue**, chosen as a cap so mixed items each get their best.
- **Paste to download**, optional: one paste analyzes and fetches at top quality, no clicks.
- **Live transfer readout** with progress, speed, bytes moved and time remaining.
- **Stop anything mid-flight**, one item or the whole queue, and the partial files are cleaned up.
- **Tagged files.** Title, artist, date, source URL, chapters and cover art are embedded into
  every download. Subtitles too, if you name the languages.
- **Retry** anything that failed or was stopped, at the quality first asked for.
- **Skips what you already have.** Re-run a playlist and it only fetches the new items.
- **History** of everything downloaded, with the reason for any failure. Clearable from
  Settings, which never touches the files themselves.
- **Polite by default.** Downloads are paced per platform, and live broadcasts are refused
  rather than left running forever.

---

## ⚠️ Read this before running it

**Nostos has no authentication and is meant for `localhost` only.** Anyone who can reach the
backend port can make your machine download files and can read your download history. Do not
bind it to `0.0.0.0`, do not port-forward it, and do not put it on a public host. If you want it
on another device, put it behind a tunnel with access control (for example Cloudflare Tunnel plus
Cloudflare Access) rather than exposing the port.

**It reuses your browser's cookies, narrowly.** To reach Instagram and Threads, Nostos reads the
session cookies of a browser you select in Settings. It does not hand your browser profile to
yt-dlp: the jar is filtered to the domains being contacted, so an Instagram download carries
Instagram cookies and nothing else. Roughly 1% of a real profile reaches any single request.

The scoped cookies are written to a private file (mode `0600`, unpredictable name, under
`~/.local/share/nostos/cookies`) that exists only for the duration of that one call and is
deleted afterwards, including when the download fails. Cookie values are never logged. They still
grant access to your logged-in accounts, so only run this on a machine you trust.

**Download only what you have the right to.** This tool is for retrieving your own uploads or
content you are permitted to save. Respect each platform's terms of service and local copyright
law. You are responsible for how you use it.

---

## Quick start

Requires **Python 3.11+**, **Node 18+**, and **ffmpeg** (used to mux separate video and audio
streams).

```bash
git clone https://github.com/corvardt/nostos.git
cd nostos
./run.sh
```

Then open <http://localhost:5173>. On first run the script creates the Python virtualenv and
installs npm dependencies.

| | |
|---|---|
| Frontend | <http://localhost:5173> |
| Backend | <http://127.0.0.1:8000> (API docs at `/docs`) |
| Downloads | `~/Downloads/Nostos` |
| Database | `~/.local/share/nostos/nostos.db` |

Set `NOSTOS_DATA_DIR` to move the database somewhere else.

### Using it

1. Paste a link and press **Analyze** to see the title, author, thumbnail and available qualities.
2. Pick a quality and press **Download**. Progress is reported live; the file lands in your
   download folder.
3. Turn on **Download on paste** in Settings to skip both clicks. Pasting a link then analyzes
   and downloads it at the highest quality automatically.

### Batches and playlists

Paste several links at once, separated by anything, and Nostos offers to queue them together.
Paste a playlist URL and it expands to its items first, listing up to 200.

Both show a confirm step with the count before anything is queued, so a stray paste can never
start downloads on its own, even with paste-to-download enabled. Pick one quality for the whole
queue there. The options are height *caps*, hence "up to 1080p": a queue's items rarely share a
format ladder, so each one gets the best it has at or below the cap.

While a queue runs, a single download keeps the full transfer readout and several switch to
compact rows. Completed items retire themselves a few seconds after finishing, so what stays on
screen is exactly what still needs a decision: the failed and stopped ones, each with a Retry
button. `Clear` empties the queue outright, stopping anything still running.

Re-queueing a URL already downloaded is skipped when the file is still on disk, so re-running a
playlist only fetches what is new. Analyze says so too, before you click.

Downloads are paced per platform: YouTube runs three at a time, Instagram and Threads one at a
time with a short gap, because they throttle bursts.

Anything still queued or running can be stopped, individually or all at once. A cancelled
download takes its scratch files with it (`.part`, fragments, orphaned cover art), since there is
no resume to use them for.

**Live broadcasts are refused.** They download in real time and never finish, so a single live
item in a playlist would hold a worker open indefinitely. Analyze flags them before you click.

## Platform notes

Open **Settings** and pick the browser you are signed in with; Nostos reuses that browser's
cookies. On Linux this needs the `secretstorage` package (already in `requirements.txt`) to
decrypt Chromium-family cookie stores via the OS keyring. Firefox does not need it.

| Platform | Engine | Login needed |
|---|---|---|
| YouTube | yt-dlp | no |
| Instagram | yt-dlp | usually not for public Reels |
| Threads | dedicated scraper | **yes, always** |
| Everything else | yt-dlp generic fallback | depends on the site |

Anything the three dedicated providers do not claim goes to the fallback, which hands it to
yt-dlp's full extractor set. Cookies are offered there too, so gated sites work the same way.

**Threads has no yt-dlp extractor.** Every Threads URL falls through to yt-dlp's `generic`
extractor, which finds nothing, so `providers/threads.py` implements the Provider contract
directly. Two things make it work:

- A logged-in `sessionid` cookie. Anonymous requests get a ~256 KB empty app shell with no post
  data at all; the same URL with a session returns ~720 KB including the payload.
- Browser-like `Sec-Fetch-*` navigation headers. Without them the server serves the empty shell
  even *with* valid cookies.

Media URLs are parsed from the inlined JSON (`video_versions`, `image_versions2`) and fetched
straight from the CDN, so no ffmpeg is needed: they arrive already muxed.

If Threads stops working, your session most likely expired: sign in again in that browser. The
error messages distinguish "no browser configured", "no login found", and "session expired".

## Architecture

```
URL -> Provider Resolver -> MediaInfo -> Download Manager -> file + history
```

Every platform implements one interface (`backend/app/providers/base.py`):

```python
class Provider(ABC):
    def supports(self, url: str) -> bool: ...
    def resolve(self, url: str) -> MediaInfo: ...
    def download(self, url, fmt=None, on_progress=None) -> str: ...
```

`YtDlpProvider` implements resolve/download once on top of yt-dlp; `youtube.py` and
`instagram.py` supply only a URL pattern and options. `threads.py` implements the interface
directly. `registry.py` maps a URL to the first provider that claims it.

Downloads run on a thread pool (`jobs.py`) because yt-dlp blocks; the UI polls `GET /jobs/{id}`.
Completed and failed jobs are written to SQLite (`db.py`).

### API

| Method | Path | Purpose |
|---|---|---|
| POST | `/analyze` | `{url}` → `MediaInfo` |
| POST | `/download` | `{url, format}` → `{status, jobId}` |
| GET | `/jobs/{id}` | progress and final path |
| GET | `/history` | recent downloads |
| DELETE | `/jobs/{id}` | stop one download |
| POST | `/jobs/{id}/retry` | queue a failed or stopped job again |
| DELETE | `/jobs` | stop everything queued or running |
| DELETE | `/history` | empty the log, leaving files alone |
| GET/PUT | `/settings` | download folder, browser, paste behaviour, subtitles |

## Development

```bash
cd backend && .venv/bin/pytest      # providers, parsing, sanitising (no network)
cd frontend && npm run build        # typecheck + bundle
```

The frontend is plain React + TypeScript + Vite, which is exactly what a Tauri desktop shell
would wrap. All backend calls live in `frontend/src/lib/api.ts`, and no component calls `fetch`
directly, so swapping HTTP for Tauri commands is a one-file change.

### Extending

- **New platform**: subclass `YtDlpProvider` with a URL pattern, register it in
  `providers/registry.py`. Nothing else changes.
- **Persistent or queued jobs**: `jobs.py` holds the whole registry behind `start()`/`get()`.

## Not implemented

Tauri desktop packaging, multiple accounts per platform, cloud sync, mobile sync, sharing.

## License

MIT. See [LICENSE](LICENSE).
