"""Turning a song into something downloadable.

The sources hand back songs, not links. Spotify will not serve you audio and
neither will Apple, so every track has to be matched to a YouTube video before
Nostos's queue can do anything with it. Getting that match wrong is the one
failure mode that matters: a wrong file that downloads cleanly is worse than a
right file that fails, because nothing downstream will ever flag it.

So candidates are scored rather than taken in order, and a weak best candidate
is refused outright.
"""

from __future__ import annotations

import logging
import re
import shutil
import subprocess
from dataclasses import dataclass

from yt_dlp import YoutubeDL

from .models import Track
from .text import normalize, similarity

log = logging.getLogger(__name__)

SEARCH_RESULTS = 6

# Words that mean "a different recording than the one asked for". Only counted
# against a candidate when the request does not contain them itself - searching
# for "Live at Pompeii" should obviously return a live recording.
PENALTIES = {
    "live": 0.25,
    "cover": 0.35,
    "remix": 0.30,
    "karaoke": 0.50,
    "instrumental": 0.30,
    "reaction": 0.60,
    "tutorial": 0.60,
    "lesson": 0.50,
    "sped up": 0.30,
    "slowed": 0.30,
    "nightcore": 0.40,
    "8d": 0.30,
    "full album": 0.50,
    "loop": 0.30,
}

# Below this, refuse rather than guess. A track that fails is visible in the
# queue and can be fixed by hand; a wrong track that succeeds is silent.
MIN_SCORE = 0.55

# Enough of a match to stop looking for a better one.
GOOD_ENOUGH_SCORE = 0.85

_TOPIC_CHANNEL = re.compile(r"-\s*topic$", re.IGNORECASE)


@dataclass
class Resolution:
    url: str
    score: float
    title: str
    reason: str = ""

    @property
    def confident(self) -> bool:
        return self.score >= MIN_SCORE


def score_candidate(track: Track, entry: dict) -> float:
    """How well one YouTube result matches the track being looked for.

    A ranking score, not a probability: it starts around 1.0 for a title that
    matches outright and is then pushed up or down by the other evidence. It is
    deliberately not clamped at the top, because two candidates with equally
    perfect titles still need separating - and the one on the label's own
    channel is the better file.
    """
    title = entry.get("title") or ""
    uploader = entry.get("uploader") or entry.get("channel") or ""

    # A YouTube title usually holds artist *and* title, but not always in that
    # shape, so take the best of three readings rather than assuming one.
    score = max(
        similarity(f"{track.artist} {track.title}", f"{uploader} {title}"),
        similarity(f"{track.artist} {track.title}", title),
        similarity(track.title, title) * 0.9,
    )

    # Duration is the strongest signal available whenever the source gave one:
    # titles lie or abbreviate, a runtime does not. Past a minute out the
    # penalty grows with the gap, because the things that carry a correct title
    # at completely the wrong length - full-album rips, hour-long loops - are
    # exactly what a title comparison cannot catch.
    duration = entry.get("duration") or 0
    if track.duration_s and duration:
        delta = abs(duration - track.duration_s)
        if delta <= 3:
            score += 0.15
        elif delta <= 10:
            score += 0.05
        elif delta <= 25:
            pass
        elif delta <= 60:
            score -= 0.15
        else:
            score -= min(0.9, 0.35 + (delta - 60) / 300)

    # "- Topic" channels are auto-generated from what the distributor delivered,
    # so both the audio and the metadata come from the label.
    if _TOPIC_CHANNEL.search(uploader):
        score += 0.12
    if entry.get("track") and entry.get("artist"):
        score += 0.05

    haystack = normalize(f"{title} {uploader}")
    requested = normalize(f"{track.title} {track.album}")
    for term, penalty in PENALTIES.items():
        if term in haystack and term not in requested:
            score -= penalty

    return max(0.0, score)


def _search_options() -> dict:
    return {
        "quiet": True,
        "no_warnings": True,
        "skip_download": True,
        "extract_flat": False,
        "ignoreerrors": True,
        "noplaylist": True,
        "noprogress": True,
        "color": "no_color",
    }


def resolve(track: Track) -> Resolution | None:
    """Find the best YouTube URL for a track, or None if nothing fits.

    A track that came from YouTube already has its URL and skips the search.
    """
    if track.url and ("youtube.com" in track.url or "youtu.be" in track.url):
        return Resolution(track.url, 1.0, track.display_name, "from source")

    queries = [f"{track.artist} - {track.title}", f"{track.artist} {track.title} audio"]
    best: dict | None = None
    best_score = 0.0
    seen: set[str] = set()

    try:
        with YoutubeDL(_search_options()) as ydl:
            for query in queries:
                info = ydl.extract_info(f"ytsearch{SEARCH_RESULTS}:{query}", download=False)
                for entry in (info or {}).get("entries") or []:
                    if not entry or entry.get("id") in seen:
                        continue
                    seen.add(entry.get("id"))
                    score = score_candidate(track, entry)
                    if score > best_score:
                        best, best_score = entry, score
                if best_score >= GOOD_ENOUGH_SCORE:
                    break
    except Exception as exc:  # noqa: BLE001 - a failed search is a failed track, not a crash
        log.warning("search failed for %s: %s", track.display_name, exc)
        return None

    if not best:
        return None

    url = best.get("webpage_url") or f"https://www.youtube.com/watch?v={best.get('id')}"
    return Resolution(url, best_score, best.get("title") or "", "youtube search")


# --------------------------------------------------------------------- spotdl

def spotdl_available() -> bool:
    return shutil.which("spotdl") is not None


def resolve_with_spotdl(track: Track, timeout: int = 90) -> Resolution | None:
    """Ask spotdl for the URL it would download, without downloading it.

    spotdl matches against Spotify's catalogue first - title, artist, duration,
    album - and only then picks the YouTube Music result closest to that
    metadata. That is a better match than any title comparison can be, so when
    spotdl is installed it is worth asking first. It only knows tracks that
    exist on Spotify, which is why the search above remains the fallback.
    """
    if not spotdl_available():
        return None

    try:
        result = subprocess.run(
            ["spotdl", "url", f"{track.artist} - {track.title}"],
            capture_output=True,
            text=True,
            timeout=timeout,
        )
    except (subprocess.TimeoutExpired, OSError) as exc:
        log.warning("spotdl lookup failed for %s: %s", track.display_name, exc)
        return None

    if result.returncode != 0:
        return None

    # spotdl prints progress alongside the URL; take the last thing that is one.
    for line in reversed((result.stdout or "").splitlines()):
        line = line.strip()
        if line.startswith("http") and ("youtube.com" in line or "youtu.be" in line):
            return Resolution(line, 0.95, track.display_name, "spotdl")
    return None


def best_resolution(track: Track, use_spotdl: bool = True) -> Resolution | None:
    """The URL to download this track from, from whichever method finds one."""
    if use_spotdl:
        resolution = resolve_with_spotdl(track)
        if resolution:
            return resolution
    resolution = resolve(track)
    if resolution and not resolution.confident:
        log.info(
            "no confident match for %s (best %.2f: %r)",
            track.display_name, resolution.score, resolution.title,
        )
        return None
    return resolution
