"""Finding ffmpeg, and fetching it when it is not there.

ffmpeg is the one dependency pip cannot install and the one that actually stops
people. Every audio extraction, thumbnail embed and remux in this program is an
ffmpeg call, and yt-dlp needs **ffprobe** alongside it.

The order is: whatever is on PATH, then whatever we fetched earlier, then fetch
one. A downloaded copy lives inside the application's own data directory and
nowhere else, so uninstalling really uninstalls, and a system ffmpeg is always
preferred over ours - the distribution's build is somebody's job to maintain,
and ours is not.
"""

from __future__ import annotations

import hashlib
import logging
import os
import platform
import shutil
import stat
import tarfile
import tempfile
import urllib.request
import zipfile
from dataclasses import dataclass
from pathlib import Path

from . import config

log = logging.getLogger(__name__)

# Both, always. yt-dlp uses ffprobe to inspect what it just downloaded, and an
# ffmpeg without an ffprobe beside it fails later and less clearly.
REQUIRED = ("ffmpeg", "ffprobe")

BIN_DIR = config.DATA_DIR / "bin"


@dataclass(frozen=True)
class Build:
    """Where a static build for one platform comes from.

    `checksum_url` is a sidecar published by the same host, so it proves the
    download arrived intact - not that the host is honest. That is the same
    trust you extend to any distribution's package mirror, and it is worth
    saying out loud rather than implying more than it does.
    """

    url: str
    checksum_url: str | None = None
    checksum_kind: str = "sha256"


# Static builds that ship ffmpeg and ffprobe together. These URLs are the
# maintained "latest" ones, so they do not need updating per release - and they
# are also why the checksum has to be fetched rather than pinned here.
BUILDS: dict[tuple[str, str], Build] = {
    ("Linux", "x86_64"): Build(
        "https://johnvansickle.com/ffmpeg/releases/ffmpeg-release-amd64-static.tar.xz",
        "https://johnvansickle.com/ffmpeg/releases/ffmpeg-release-amd64-static.tar.xz.md5",
        "md5",
    ),
    ("Linux", "aarch64"): Build(
        "https://johnvansickle.com/ffmpeg/releases/ffmpeg-release-arm64-static.tar.xz",
        "https://johnvansickle.com/ffmpeg/releases/ffmpeg-release-arm64-static.tar.xz.md5",
        "md5",
    ),
    ("Windows", "AMD64"): Build(
        "https://www.gyan.dev/ffmpeg/builds/ffmpeg-release-essentials.zip",
        "https://www.gyan.dev/ffmpeg/builds/ffmpeg-release-essentials.zip.sha256",
    ),
}


class FFmpegError(RuntimeError):
    pass


# --------------------------------------------------------------------- lookup


def _has_both(directory: Path) -> bool:
    return all((directory / _exe(name)).is_file() for name in REQUIRED)


def _exe(name: str) -> str:
    return f"{name}.exe" if platform.system() == "Windows" else name


def system_ffmpeg() -> Path | None:
    """The directory holding a PATH ffmpeg, if ffprobe is there too."""
    found = [shutil.which(name) for name in REQUIRED]
    if all(found):
        return Path(found[0]).parent  # type: ignore[arg-type]
    return None


def managed_ffmpeg() -> Path | None:
    """The copy this program fetched earlier, if it is still intact."""
    return BIN_DIR if _has_both(BIN_DIR) else None


def locate() -> Path | None:
    """Where ffmpeg is, without fetching anything. None means it is missing."""
    return system_ffmpeg() or managed_ffmpeg()


def describe() -> dict[str, str | None]:
    """What `nostos doctor` reports."""
    system = system_ffmpeg()
    managed = managed_ffmpeg()
    return {
        "system": str(system) if system else None,
        "managed": str(managed) if managed else None,
        "using": str(system or managed) if (system or managed) else None,
        "downloadable": BUILDS.get(_platform_key()) and BUILDS[_platform_key()].url or None,
    }


def _platform_key() -> tuple[str, str]:
    machine = platform.machine()
    # macOS reports arm64, Linux reports aarch64 for the same thing.
    if machine == "arm64" and platform.system() == "Linux":
        machine = "aarch64"
    return platform.system(), machine


# ------------------------------------------------------------------- fetching


def _download(url: str, dest: Path, on_progress=None) -> None:
    with urllib.request.urlopen(url, timeout=60) as res:
        total = int(res.headers.get("Content-Length") or 0)
        done = 0
        with dest.open("wb") as out:
            while chunk := res.read(1 << 16):
                out.write(chunk)
                done += len(chunk)
                if on_progress and total:
                    on_progress(done, total)


def _digest(path: Path, kind: str) -> str:
    digest = hashlib.new(kind)
    with path.open("rb") as handle:
        while chunk := handle.read(1 << 20):
            digest.update(chunk)
    return digest.hexdigest()


def _verify(archive: Path, build: Build) -> None:
    if not build.checksum_url:
        log.warning("No checksum published for %s; skipping verification.", build.url)
        return
    try:
        with urllib.request.urlopen(build.checksum_url, timeout=30) as res:
            published = res.read().decode().split()[0].strip().lower()
    except Exception as exc:  # noqa: BLE001 - any failure here means "unverified"
        raise FFmpegError(f"Could not fetch the checksum for {build.url}: {exc}") from exc

    actual = _digest(archive, build.checksum_kind)
    if actual != published:
        raise FFmpegError(
            f"Checksum mismatch for {build.url}: expected {published}, got {actual}. "
            "The download was corrupted or tampered with; nothing was installed."
        )


def _extract_binaries(archive: Path, into: Path) -> None:
    """Pull just ffmpeg and ffprobe out, wherever they sit in the archive.

    Only these two members are ever written, and each is written by basename, so
    a path in the archive cannot decide where anything on this machine lands.
    """
    wanted = {_exe(name) for name in REQUIRED}
    into.mkdir(parents=True, exist_ok=True)
    found: set[str] = set()

    if archive.suffixes[-2:] == [".tar", ".xz"] or archive.suffix in (".xz", ".gz", ".bz2"):
        with tarfile.open(archive) as tar:
            for member in tar.getmembers():
                name = Path(member.name).name
                if member.isfile() and name in wanted:
                    source = tar.extractfile(member)
                    if source is None:
                        continue
                    (into / name).write_bytes(source.read())
                    found.add(name)
    else:
        with zipfile.ZipFile(archive) as zf:
            for member in zf.infolist():
                name = Path(member.filename).name
                if not member.is_dir() and name in wanted:
                    (into / name).write_bytes(zf.read(member))
                    found.add(name)

    missing = wanted - found
    if missing:
        raise FFmpegError(f"The archive did not contain {', '.join(sorted(missing))}.")

    for name in found:
        target = into / name
        target.chmod(target.stat().st_mode | stat.S_IXUSR | stat.S_IXGRP | stat.S_IXOTH)


def fetch(on_progress=None) -> Path:
    """Download a static ffmpeg into the data directory and return its folder."""
    key = _platform_key()
    build = BUILDS.get(key)
    if build is None:
        raise FFmpegError(
            f"No static build is configured for {key[0]} {key[1]}. "
            "Install ffmpeg through your package manager - on macOS, `brew install ffmpeg`."
        )

    with tempfile.TemporaryDirectory(prefix="nostos-ffmpeg-") as tmp:
        archive = Path(tmp) / Path(build.url).name
        log.info("Downloading ffmpeg from %s", build.url)
        _download(build.url, archive, on_progress)
        _verify(archive, build)
        # Extract beside the target and swap, so an interrupted run never leaves
        # a half-populated bin/ that would then look like a working install.
        staging = Path(tmp) / "bin"
        _extract_binaries(archive, staging)
        BIN_DIR.mkdir(parents=True, exist_ok=True)
        for item in staging.iterdir():
            os.replace(item, BIN_DIR / item.name)

    if not _has_both(BIN_DIR):
        raise FFmpegError("ffmpeg was downloaded but is not usable.")
    return BIN_DIR


def ensure(auto: bool = True, on_progress=None) -> Path | None:
    """Where ffmpeg is, fetching one if there is none and we are allowed to."""
    found = locate()
    if found or not auto:
        return found
    return fetch(on_progress)
