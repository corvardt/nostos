"""Finding and fetching ffmpeg.

Nothing here touches the network: archives are built on the fly, so the parts
that matter - what gets extracted, what gets rejected, what is preferred - are
tested without depending on an upstream host being up.
"""

from __future__ import annotations

import hashlib
import io
import tarfile
import zipfile
from pathlib import Path

import pytest

from nostos import media


def _tar(path: Path, names: list[str], prefix: str = "ffmpeg-7.0-static/") -> Path:
    """A tarball shaped like the real one: binaries inside a version folder."""
    with tarfile.open(path, "w:xz") as tar:
        for name in names:
            data = b"#!/bin/false\n" + name.encode()
            info = tarfile.TarInfo(prefix + name)
            info.size = len(data)
            tar.addfile(info, io.BytesIO(data))
    return path


def _zip(path: Path, names: list[str], prefix: str = "ffmpeg-7.0/bin/") -> Path:
    with zipfile.ZipFile(path, "w") as zf:
        for name in names:
            zf.writestr(prefix + name, b"binary " + name.encode())
    return path


# ------------------------------------------------------------------ selection


def test_a_system_ffmpeg_is_preferred(tmp_path, monkeypatch):
    """The distribution's build is somebody's job to maintain. Ours is not."""
    monkeypatch.setattr(media, "BIN_DIR", tmp_path)
    (tmp_path / "ffmpeg").touch()
    (tmp_path / "ffprobe").touch()
    monkeypatch.setattr(media.shutil, "which", lambda name: f"/usr/bin/{name}")

    assert media.locate() == Path("/usr/bin")


def test_the_managed_copy_is_used_when_there_is_no_system_one(tmp_path, monkeypatch):
    monkeypatch.setattr(media, "BIN_DIR", tmp_path)
    (tmp_path / "ffmpeg").touch()
    (tmp_path / "ffprobe").touch()
    monkeypatch.setattr(media.shutil, "which", lambda name: None)

    assert media.locate() == tmp_path


def test_ffmpeg_without_ffprobe_does_not_count(tmp_path, monkeypatch):
    """yt-dlp probes what it downloaded; half an install fails later and worse."""
    monkeypatch.setattr(media, "BIN_DIR", tmp_path)
    (tmp_path / "ffmpeg").touch()
    monkeypatch.setattr(media.shutil, "which", lambda name: None)

    assert media.locate() is None


def test_a_partial_system_install_does_not_count(monkeypatch, tmp_path):
    monkeypatch.setattr(media, "BIN_DIR", tmp_path / "empty")
    monkeypatch.setattr(media.shutil, "which", lambda name: "/usr/bin/ffmpeg" if name == "ffmpeg" else None)

    assert media.system_ffmpeg() is None


# ----------------------------------------------------------------- extraction


def test_binaries_are_pulled_out_of_a_nested_tarball(tmp_path):
    archive = _tar(tmp_path / "f.tar.xz", ["ffmpeg", "ffprobe", "qt-faststart", "GPLv3.txt"])
    out = tmp_path / "bin"
    media._extract_binaries(archive, out)

    assert sorted(p.name for p in out.iterdir()) == ["ffmpeg", "ffprobe"]


def test_binaries_are_pulled_out_of_a_zip(tmp_path, monkeypatch):
    """The Windows path, exercised on whatever this is running on: the names
    looked for follow the platform, so the platform is what gets faked."""
    monkeypatch.setattr(media.platform, "system", lambda: "Windows")
    archive = _zip(tmp_path / "f.zip", ["ffmpeg.exe", "ffprobe.exe", "ffplay.exe"])
    out = tmp_path / "bin"
    media._extract_binaries(archive, out)

    assert sorted(p.name for p in out.iterdir()) == ["ffmpeg.exe", "ffprobe.exe"]


def test_extracted_binaries_are_executable(tmp_path):
    archive = _tar(tmp_path / "f.tar.xz", ["ffmpeg", "ffprobe"])
    out = tmp_path / "bin"
    media._extract_binaries(archive, out)

    import os

    assert os.access(out / "ffmpeg", os.X_OK)


def test_an_archive_missing_a_binary_is_rejected(tmp_path):
    archive = _tar(tmp_path / "f.tar.xz", ["ffmpeg"])
    with pytest.raises(media.FFmpegError, match="ffprobe"):
        media._extract_binaries(archive, tmp_path / "bin")


def test_an_archive_cannot_write_outside_the_target(tmp_path):
    """Members are written by basename, so a path in the archive cannot decide
    where anything on this machine lands."""
    archive = _tar(tmp_path / "f.tar.xz", ["ffmpeg", "ffprobe"], prefix="../../../evil/")
    out = tmp_path / "bin"
    media._extract_binaries(archive, out)

    assert (out / "ffmpeg").is_file()
    assert not (tmp_path.parent / "evil").exists()


# ------------------------------------------------------------------- checksum


def test_a_matching_checksum_passes(tmp_path, monkeypatch):
    archive = tmp_path / "f.tar.xz"
    archive.write_bytes(b"payload")
    digest = hashlib.sha256(b"payload").hexdigest()
    _stub_checksum(monkeypatch, f"{digest}  ffmpeg.tar.xz\n")

    media._verify(archive, media.Build("http://x/f.tar.xz", "http://x/f.tar.xz.sha256"))


def test_a_mismatched_checksum_is_fatal(tmp_path, monkeypatch):
    """A corrupted or swapped download must install nothing at all."""
    archive = tmp_path / "f.tar.xz"
    archive.write_bytes(b"payload")
    _stub_checksum(monkeypatch, "0" * 64)

    with pytest.raises(media.FFmpegError, match="Checksum mismatch"):
        media._verify(archive, media.Build("http://x/f.tar.xz", "http://x/f.tar.xz.sha256"))


def test_an_unreachable_checksum_is_fatal(tmp_path, monkeypatch):
    """Unverified is not the same as fine, so it stops rather than proceeding."""
    archive = tmp_path / "f.tar.xz"
    archive.write_bytes(b"payload")

    def boom(*a, **k):
        raise OSError("no route to host")

    monkeypatch.setattr(media.urllib.request, "urlopen", boom)

    with pytest.raises(media.FFmpegError, match="Could not fetch the checksum"):
        media._verify(archive, media.Build("http://x/f.tar.xz", "http://x/f.tar.xz.sha256"))


def _stub_checksum(monkeypatch, body: str) -> None:
    class Response(io.BytesIO):
        def __enter__(self):
            return self

        def __exit__(self, *exc):
            return False

    monkeypatch.setattr(media.urllib.request, "urlopen", lambda *a, **k: Response(body.encode()))


# ------------------------------------------------------------------ platforms


def test_every_configured_build_has_a_checksum():
    """A build fetched without a way to verify it should not be in the table."""
    for key, build in media.BUILDS.items():
        assert build.checksum_url, f"{key} has no checksum sidecar"


def test_an_unsupported_platform_says_what_to_do_instead(monkeypatch):
    monkeypatch.setattr(media, "_platform_key", lambda: ("Haiku", "m68k"))
    with pytest.raises(media.FFmpegError, match="package manager"):
        media.fetch()
