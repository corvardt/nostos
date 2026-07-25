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
- **Library sync**: archive whole music accounts in one pass — see below

## Library sync

The **Library** tab does the opposite of the Links tab. Instead of "fetch what is at this URL",
it answers "fetch everything I have on these services, once".

| Service | What it can read | Credentials |
|---|---|---|
| Apple Music | your library and playlists | two tokens from a signed-in web session |
| Spotify | Liked Songs and playlists | a free developer client id and secret |
| Deezer | favourites and playlists | none for public ones, an `arl` cookie for your own |
| YouTube / YT Music | any playlist, including Liked Music | none, unless the playlist is private |
| A JSON file | a tracklist you exported elsewhere | none |

Everything is merged before anything is downloaded. Tracks merge on **ISRC** — the identifier the
services themselves publish, unique per recording — so a song you liked on three platforms is
fetched once, while a remaster and its original stay separate even though their titles are
identical. Where no ISRC exists, which is everything sourced from YouTube, tracks fall back to
fuzzy matching on artist, title and duration.

Then each track has to be turned into something downloadable, because none of these services will
serve you audio. If [spotdl](https://github.com/spotDL/spotify-downloader) is installed it picks
the video, matching Spotify's catalogue first; otherwise candidates come from a YouTube search and
are scored on title, duration, channel and the words that betray a cover, a remix or an hour-long
loop. **A candidate that does not clearly match is refused rather than guessed at.** A wrong file
that downloads cleanly is worse than one that fails, because nothing downstream will ever flag it.

What survives is downloaded through the same queue as everything else — same pacing, same stop and
retry — then tagged from the *service's* metadata rather than the video title, and filed under
your music folder.

Point **Music you already have** in Settings at folders you already keep music in. Anything
matched there is never downloaded again, whichever service it turns up on. Matching is on artist
and title, so it recognises a song you fetched last year from a different video.

A pass is resumable: every track's state is recorded, so running it again only does what is left.

### Without the browser

```bash
nostos-library add-source spotify \
    --option client_id=... --option client_secret=... --option liked=true
nostos-library sync --dry-run   # collect, queue nothing
nostos-library sync             # and actually download
```

`sources`, `test-source`, `remove-source` and `status` do what they sound like. `--dry-run` first
is worth the habit: it tells you how much is actually missing before anything is fetched.

### Where the tokens come from

**Apple Music** has no public API for reading your own library, so this uses the web player's.
Open music.apple.com signed in, look at any `amp-api.music.apple.com` request in the network tab,
and copy two headers: `Authorization` (minus the `Bearer ` prefix) and `Music-User-Token`. The
first is short-lived and will need replacing; the second lasts about six months.

**Spotify** needs an app registered at developer.spotify.com — free, a minute's work. Liked Songs
and private playlists open a browser once to authorise, then remember.

**Deezer** needs nothing for public playlists. Your own private favourites need the `arl` cookie
from deezer.com.

All of it stays in the local database. Same rule as the rest of Nostos: nothing leaves the machine
except requests to the service being read.

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

## Install

```bash
curl -fsSL https://raw.githubusercontent.com/corvardt/nostos/main/scripts/install.sh | sh
nostos
```

That is the whole thing. **No Python, no Node, no ffmpeg to install first.** The
script installs [uv](https://docs.astral.sh/uv/) — one static binary, which
brings its own Python — then Nostos, then ffmpeg if you do not already have it.
`nostos` starts the server and opens the interface.

Already have a Python you like? `uv tool install nostos-app`, or `pipx install
nostos-app`, does the same thing without the script.

The distribution is called **nostos-app** because plain `nostos` on PyPI belongs
to an unrelated project. The command it installs is `nostos`.

### Where things go

Two directories, and nowhere else. No system Python is touched.

| | |
|---|---|
| The program and its Python | `~/.local/share/uv/tools/nostos-app` |
| Database, cookies, ffmpeg | `~/.local/share/nostos` |
| Downloads | `~/Downloads/Nostos` |
| Interface and API | <http://127.0.0.1:8000> (API docs at `/docs`) |

Uninstalling is `uv tool uninstall nostos-app` and deleting the second directory.
`NOSTOS_DATA_DIR` moves that directory somewhere else.

### Commands

| | |
|---|---|
| `nostos` | start it and open the interface |
| `nostos stop` | shut down the running server |
| `nostos status` | is it running, and which version |
| `nostos doctor` | what is installed, what is missing, where things are |
| `nostos ffmpeg` | fetch a static ffmpeg into the data directory |
| `nostos-library` | the library sync, without a browser |

Running `nostos` a second time opens another tab rather than starting a second
copy. If port 8000 is taken, the next free one is used rather than refusing to
start. `--port` chooses, `--no-browser` starts the server alone.

### About ffmpeg

ffmpeg is the one dependency pip cannot supply, and every conversion, tag and
cover-art embed goes through it. Nostos looks for it in this order:

1. **Your system's**, if `ffmpeg` and `ffprobe` are both on `PATH`. Always
   preferred — your distribution maintains it, and nobody has to maintain ours.
2. **One it fetched earlier**, in `~/.local/share/nostos/bin`.
3. Otherwise it downloads a static build once, about 40 MB, verified against the
   checksum the same host publishes, and puts it there. Nothing is installed
   system-wide, and deleting the data directory removes it completely.

On macOS there is no static build worth shipping, so `brew install ffmpeg` is
the answer and `nostos doctor` will say so. Start with `--no-download` to have a
missing ffmpeg reported rather than fetched.

## Using it

Two modes, named across the top of the window. **Links** takes one page at a time. **Library**
takes whole music accounts. They share the same queue, the same folder settings and the same
history.

### Links

Paste a link, press **Analyze**, pick a quality, press **Download**.

Paste several links, or a playlist URL, and you get a confirm step with the count and one quality
for the whole queue. That step is always shown, so a stray paste never starts downloads by
itself. Playlists are listed without fetching any videos, up to 200 items.

While a queue runs, finished items clear themselves after a few seconds. What stays on screen is
what still needs you: failed and stopped downloads, each with a **Retry**. **Clear** empties the
queue and stops anything running.

Downloads are paced per site: three at a time for YouTube, one at a time for Instagram and
Threads, which throttle bursts. Live broadcasts are refused, because they never finish.

### Library

The services are listed with what each one can read and what it costs to connect, before you fill
in anything. **Connect** one, then **Count what is missing** to see the size of the job without
starting it, then **Sync and download**.

## When something breaks

**A site suddenly stops working.** Usually the site changed and yt-dlp has caught up since.
Upgrading re-resolves the dependencies, which pulls the current yt-dlp:

```bash
uv tool upgrade nostos-app
```

**Something is wrong and you want to know what.** `nostos doctor` reports the Python and Nostos
versions, whether the interface is bundled, which ffmpeg is in use and where it came from, where
the database lives, and whether a server is up.

**Threads says you are not signed in.** Sessions expire. Sign in again in the browser you picked
in Settings.

**Instagram or Threads cookies cannot be read on Linux.** Chromium-family browsers need the
`secretstorage` package (already a dependency) and an unlocked keyring. Firefox needs neither.

## How it is built

```
URL -> provider resolver -> media info -> download manager -> file + history
```

Each platform implements one interface (`backend/nostos/providers/base.py`):

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
| POST | `/api/analyze` | `{url}` to media info |
| POST | `/api/download` | `{url, format}` to a job id |
| POST | `/api/download/batch` | many URLs, with a reason for any skipped |
| POST | `/api/expand` | a playlist's items |
| GET | `/api/jobs/{id}` | progress and final path |
| POST | `/api/jobs/{id}/retry` | queue a failed or stopped job again |
| DELETE | `/api/jobs/{id}`, `/api/jobs` | stop one, or everything |
| GET/DELETE | `/api/history` | list, or empty it |
| GET | `/health` | outside the prefix, for the launcher |
| GET/PUT | `/api/settings` | folders, cookies, music filing |

## Development

```bash
./run.sh                    # backend on :8000, Vite with hot reload on :5173
```

Open <http://localhost:5173> for the dev server. Vite proxies `/api` through to the backend
without rewriting the prefix, so `BASE` in `lib/api.ts` is the same string in development as it
is once installed, and no request is ever cross-origin.

```bash
cd backend
.venv/bin/python -m pip install -e ".[dev]"
.venv/bin/python -m pytest

../scripts/build-package.sh      # build the interface into the package
.venv/bin/python -m build   # then a wheel with the interface inside it
```

`scripts/build-package.sh` compiles `frontend/` into `backend/nostos/static/` and copies this file
to `backend/README.md` for the PyPI page. Both are gitignored and generated at release time. `scripts/install.sh` is what end users pipe into `sh`; it only needs
updating if the install story changes. With it present, `nostos` serves the whole application from one port;
without it, the API runs and the root path says what to do about it. The UI tests skip themselves
when nothing is built, so a fresh checkout still passes.

The tests never touch a real site: providers are faked and page payloads come from fixtures.

The frontend is plain React, TypeScript and Vite, which is what a Tauri shell would wrap. Every
backend call lives in `frontend/src/lib/api.ts` and no component calls `fetch`, so swapping the
transport is a one-file change.

The interface is the same instrument as the rest of the family: seven palette tokens
(`--c-void`, `--c-panel`, `--c-line`, `--c-land`, `--c-dim`, `--c-text`, `--c-strike`), IBM Plex
Mono throughout, and a 10–13px scale with uppercase tracked labels. Dark and light are two
*media*, not one palette inverted — a phosphor tube, and ink on a chart recorder's roll — which is
why every rule is written against a token and never against a colour. `--c-strike` is reserved:
nothing reaches it except a transfer that is actually moving and a file that actually landed.
Styling is hand-written CSS rather than Tailwind, so the token names match Keraunos and Tyche
while the build stays dependency-free.

To add a site with its own handling, subclass `YtDlpProvider` with a URL pattern and register it
in `providers/registry.py`. Nothing else changes.

To add a music service, subclass `Source` in `nostos/library/sources/`, return `Track`s from
`fetch()`, and register it in that package's `__init__.py`. Deduplication, resolution, downloading
and the UI all come free — a source's only job is to say what songs exist.

## Not implemented

Desktop packaging, multiple accounts per site, cloud or mobile sync, sharing.

## License

MIT. See [LICENSE](LICENSE).
