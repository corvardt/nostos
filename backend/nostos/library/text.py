"""String normalization and comparison.

Every kind of track matching goes through here - merging duplicates across
platforms, recognising a track you already own, scoring a search result - so
the thresholds that decide "same song?" live in one place.
"""

from __future__ import annotations

import difflib
import re
import unicodedata

# Promotional noise YouTube titles carry. Stripped for comparison only; the
# original string is still what gets written into the tags.
_NOISE = re.compile(
    r"\((official\s*)?(music\s*)?(video|audio|visualizer|lyrics?|hd|hq|4k)\)"
    r"|\[(official\s*)?(music\s*)?(video|audio|visualizer|lyrics?)\]"
    r"|\bofficial\s+(music\s+)?video\b"
    r"|\bfull\s+album\b",
    re.IGNORECASE,
)

# Edition suffixes that say nothing about which recording this is.
_ALBUM_SUFFIX = re.compile(
    r"\s*(-\s*(single|ep)|\((deluxe|remastered?|explicit)[^)]*\))\s*$",
    re.IGNORECASE,
)

# Separators between a credited artist and everything that follows.
_FEATURED = re.compile(r"\s*(?:,|&|feat\.?|ft\.?|with|vs\.?|\sx\s)\s+", re.IGNORECASE)

_UNSAFE_FILENAME_CHARS = '/\\$`"\'<>:|?*%\n\r\t'


def strip_noise(value: str) -> str:
    if not value:
        return ""
    return re.sub(r"\s+", " ", _NOISE.sub(" ", value)).strip(" -–—")


def strip_album_suffix(value: str) -> str:
    return _ALBUM_SUFFIX.sub("", value).strip() if value else ""


def normalize(value: str) -> str:
    """Lowercase, unaccented, punctuation-free, single-spaced."""
    if not value:
        return ""
    value = strip_noise(value)
    value = unicodedata.normalize("NFKD", value)
    value = "".join(c for c in value if not unicodedata.combining(c))
    return re.sub(r"[^a-z0-9]+", " ", value.lower()).strip()


def similarity(left: str, right: str) -> float:
    return difflib.SequenceMatcher(None, normalize(left), normalize(right)).ratio()


def tokenize(value: str) -> set[str]:
    """Word set, so word order stops mattering.

    "Artist - Title" and "01 Title (Artist)" describe the same file; comparing
    sets rather than strings is what lets both match.
    """
    normalized = normalize(value)
    return set(normalized.split()) if normalized else set()


def jaccard(left: set[str], right: set[str]) -> float:
    if not left or not right:
        return 0.0
    return len(left & right) / len(left | right)


def primary_artist(artist: str) -> str:
    """The first credited artist, without features.

    "Skrillex, Boys Noize & Ty Dolla $ign" -> "Skrillex", so filing by artist
    does not scatter a discography across one folder per collaboration.
    """
    if not artist:
        return ""
    return _FEATURED.split(artist, maxsplit=1)[0].strip() or artist.strip()


def safe_filename(name: str) -> str:
    """A name safe for the filesystem and for the tools we hand it to.

    Beyond the characters the filesystem rejects, this drops the ones a
    subprocess or an output template would reinterpret: `$` (yt-dlp and ffmpeg
    invocations read "Ty Dolla $ign" as an empty shell variable, leaving a
    truncated path) and `%` (yt-dlp reads it as an outtmpl field).
    """
    out = name
    for char in _UNSAFE_FILENAME_CHARS:
        out = out.replace(char, "-" if char in "/\\" else "")
    out = re.sub(r"\s+", " ", out).strip(" .")
    return out[:180] or "untitled"


def split_artist_title(raw_title: str, uploader: str = "") -> tuple[str, str]:
    """Guess (artist, title) from a YouTube video title.

    Outside YouTube Music there is no artist field, only a title following the
    "Artist - Title" convention. With no separator, the channel name is the
    best guess left - minus the "- Topic" suffix YouTube appends to the
    auto-generated channels that distributors upload through.
    """
    title = strip_noise(raw_title or "")
    channel = re.sub(r"\s*-\s*topic$", "", (uploader or "").strip(), flags=re.IGNORECASE)

    for separator in (" - ", " – ", " — ", " | "):
        if separator in title:
            left, right = (part.strip() for part in title.split(separator, 1))
            if left and right:
                # A channel matching the right-hand side means the title is
                # "Title - Artist", the other way round from the convention.
                if channel and similarity(channel, right) > 0.8:
                    return right, left
                return left, right

    return (channel or "Unknown artist"), title or (raw_title or "").strip()
