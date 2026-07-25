"""Job registry: cancellation and progress sanitising. No network."""

from __future__ import annotations

import pytest

from nostos import jobs
from nostos.models import Job


@pytest.fixture(autouse=True)
def clean_registry():
    jobs._jobs.clear()
    jobs._cancelled.clear()
    yield
    jobs._jobs.clear()
    jobs._cancelled.clear()


def _register(job_id: str, status: str) -> None:
    jobs._jobs[job_id] = Job(id=job_id, url="https://example.com/x", status=status)


def test_cancelling_a_queued_job_retires_it_immediately() -> None:
    """A queued job never reaches a progress hook, so nothing else would move it."""
    _register("a", "queued")
    assert jobs.cancel("a") is True
    assert jobs.get("a").status == "cancelled"


def test_cancelling_a_running_job_only_flags_it() -> None:
    """The worker unwinds itself at the next progress tick."""
    _register("b", "running")
    assert jobs.cancel("b") is True
    assert jobs.is_cancelled("b") is True
    assert jobs.get("b").status == "running"


@pytest.mark.parametrize("status", ["done", "error", "cancelled"])
def test_cancelling_a_finished_job_does_nothing(status: str) -> None:
    _register("c", status)
    assert jobs.cancel("c") is False
    assert jobs.get("c").status == status


def test_cancelling_an_unknown_job_is_not_an_error() -> None:
    assert jobs.cancel("nope") is False


def test_cancel_all_counts_only_the_unfinished() -> None:
    _register("q", "queued")
    _register("r", "running")
    _register("d", "done")
    _register("e", "error")
    assert jobs.cancel_all() == 2
    assert jobs.get("d").status == "done"
    assert jobs.get("e").status == "error"


# ------------------------------------------------------- partial file tidy


def test_discard_partials_removes_only_scratch_files(tmp_path) -> None:
    """A cancel must not delete an earlier completed download that happens to
    share the target name, so only provably temporary siblings are removed."""
    target = tmp_path / "clip.mp4"
    target.write_text("a previous, finished download")
    (tmp_path / "clip.mp4.part").write_text("partial")
    (tmp_path / "clip.mp4.ytdl").write_text("resume state")
    (tmp_path / "clip.mp4.part-Frag3").write_text("fragment")
    unrelated = tmp_path / "other.mp4"
    unrelated.write_text("someone else's file")

    jobs._discard_partials({str(target)})

    assert not (tmp_path / "clip.mp4.part").exists()
    assert not (tmp_path / "clip.mp4.ytdl").exists()
    assert not (tmp_path / "clip.mp4.part-Frag3").exists()
    assert target.exists(), "the finished file must survive"
    assert unrelated.exists()


def test_discard_partials_tolerates_missing_files(tmp_path) -> None:
    jobs._discard_partials({str(tmp_path / "never-existed.mp4")})


def test_discard_partials_removes_the_orphaned_cover_art(tmp_path) -> None:
    """Thumbnails are named off the media stem, not the per-format filename, so
    a cancelled run leaves one behind unless it is derived."""
    (tmp_path / "clip [abc].f401.mp4.part").write_text("partial")
    (tmp_path / "clip [abc].webp").write_text("cover art")

    jobs._discard_partials({str(tmp_path / "clip [abc].f401.mp4")})

    assert not (tmp_path / "clip [abc].f401.mp4.part").exists()
    assert not (tmp_path / "clip [abc].webp").exists()
