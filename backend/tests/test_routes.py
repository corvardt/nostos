"""The HTTP surface, exercised end to end with the network stubbed out.

Providers are replaced with a fake, so these tests cover routing, validation,
duplicate skipping and the job lifecycle without touching a real site.
"""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from nostos import db, jobs
from nostos.main import app
from nostos.models import Format, MediaInfo
from nostos.providers.base import Provider, ProviderError


class FakeProvider(Provider):
    name = "fake"

    def __init__(self, *, fails: str | None = None) -> None:
        self.fails = fails

    def supports(self, url: str) -> bool:
        return "fake.test" in url

    def resolve(self, url: str) -> MediaInfo:
        if self.fails:
            raise ProviderError(self.fails, needs_auth="login" in self.fails)
        return MediaInfo(
            platform=self.name,
            title="A Fake Video",
            author="Someone",
            formats=[Format(id="best", label="Best available")],
        )

    def download(self, url, fmt="best", on_progress=None) -> str:
        return "/tmp/fake.mp4"


@pytest.fixture
def client():
    db.init()
    with TestClient(app) as c:
        yield c


@pytest.fixture(autouse=True)
def clean_jobs():
    jobs._jobs.clear()
    jobs._cancelled.clear()
    yield
    jobs._jobs.clear()
    jobs._cancelled.clear()


@pytest.fixture
def fake_provider(monkeypatch):
    """Route every URL to a provider that never touches the network."""

    def install(provider: Provider) -> Provider:
        monkeypatch.setattr("nostos.routes.resolve_provider", lambda url: provider)
        return provider

    return install


# ------------------------------------------------------------------ analyze


def test_analyze_returns_media_info(client, fake_provider):
    fake_provider(FakeProvider())
    r = client.post("/api/analyze", json={"url": "https://fake.test/1"})
    assert r.status_code == 200
    assert r.json()["title"] == "A Fake Video"


def test_analyze_reports_auth_failures_as_422(client, fake_provider):
    """422 is what tells the UI to point at the browser setting."""
    fake_provider(FakeProvider(fails="needs login"))
    r = client.post("/api/analyze", json={"url": "https://fake.test/1"})
    assert r.status_code == 422


def test_analyze_reports_other_failures_as_400(client, fake_provider):
    fake_provider(FakeProvider(fails="that post is gone"))
    assert client.post("/api/analyze", json={"url": "https://fake.test/1"}).status_code == 400


def test_analyze_rejects_a_non_url(client):
    assert client.post("/api/analyze", json={"url": "nonsense"}).status_code == 400


# ----------------------------------------------------------------- download


def test_download_starts_a_job(client, fake_provider):
    fake_provider(FakeProvider())
    r = client.post("/api/download", json={"url": "https://fake.test/1", "format": "best"})
    assert r.status_code == 200
    body = r.json()
    assert body["status"] == "started"
    assert client.get(f"/api/jobs/{body['jobId']}").status_code == 200


def test_unknown_job_is_404(client):
    assert client.get("/api/jobs/nope").status_code == 404


# -------------------------------------------------------------------- batch


def test_batch_deduplicates_and_reports_rejections(client, monkeypatch):
    real = FakeProvider()

    def route(url: str) -> Provider:
        if "fake.test" in url:
            return real
        raise ProviderError("No provider matched this URL.")

    monkeypatch.setattr("nostos.routes.resolve_provider", route)
    r = client.post(
        "/api/download/batch",
        json={
            "urls": [
                "https://fake.test/1",
                "https://fake.test/1",  # duplicate within the request
                "   ",  # blank
                "not-a-url",
            ],
            "format": "best",
            "skip_duplicates": False,
        },
    )
    body = r.json()
    assert body["accepted"] == 1
    assert body["rejected"] == 1
    assert len(body["items"]) == 2


def test_batch_rejects_an_empty_request(client):
    assert client.post("/api/download/batch", json={"urls": []}).status_code == 400


def test_batch_enforces_its_limit(client):
    urls = [f"https://fake.test/{n}" for n in range(500)]
    r = client.post("/api/download/batch", json={"urls": urls})
    assert r.status_code == 400
    assert "limit" in r.json()["detail"]


def test_batch_skips_what_is_already_downloaded(client, fake_provider, tmp_path):
    """Re-running a playlist should not refetch files that are still on disk."""
    fake_provider(FakeProvider())
    existing = tmp_path / "already.mp4"
    existing.write_text("downloaded earlier")
    url = "https://fake.test/seen"
    db.add_history(url, "fake", "Seen", "done", str(existing))

    body = client.post("/api/download/batch", json={"urls": [url], "skip_duplicates": True}).json()
    assert body["skipped"] == 1
    assert body["accepted"] == 0
    assert body["items"][0]["skipped"] is True


def test_a_deleted_file_is_not_a_duplicate(client, fake_provider, tmp_path):
    """History alone is not enough: the point is to avoid refetching what you have."""
    fake_provider(FakeProvider())
    url = "https://fake.test/gone"
    db.add_history(url, "fake", "Gone", "done", str(tmp_path / "deleted.mp4"))

    body = client.post("/api/download/batch", json={"urls": [url], "skip_duplicates": True}).json()
    assert body["skipped"] == 0
    assert body["accepted"] == 1


# -------------------------------------------------------------------- retry


def test_retry_requeues_a_failed_job(client, fake_provider):
    fake_provider(FakeProvider())
    jobs._jobs["dead"] = jobs.Job(
        id="dead", url="https://fake.test/1", format="best", status="error", error="boom"
    )
    r = client.post("/api/jobs/dead/retry")
    assert r.status_code == 200
    assert r.json()["jobId"] != "dead"


def test_retry_refuses_a_job_that_is_still_running(client, fake_provider):
    fake_provider(FakeProvider())
    jobs._jobs["live"] = jobs.Job(id="live", url="https://fake.test/1", status="running")
    r = client.post("/api/jobs/live/retry")
    assert r.status_code == 409


def test_retry_of_an_unknown_job_is_404(client):
    assert client.post("/api/jobs/nope/retry").status_code == 404


# ------------------------------------------------------------------- cancel


def test_cancelling_a_queued_job(client):
    jobs._jobs["q"] = jobs.Job(id="q", url="https://fake.test/1", status="queued")
    assert client.delete("/api/jobs/q").json() == {"cancelled": True}
    assert client.get("/api/jobs/q").json()["status"] == "cancelled"


def test_cancelling_an_unknown_job_is_404(client):
    assert client.delete("/api/jobs/nope").status_code == 404


def test_cancel_all_counts_what_it_stopped(client):
    jobs._jobs["a"] = jobs.Job(id="a", url="https://fake.test/1", status="queued")
    jobs._jobs["b"] = jobs.Job(id="b", url="https://fake.test/2", status="running")
    jobs._jobs["c"] = jobs.Job(id="c", url="https://fake.test/3", status="done")
    assert client.delete("/api/jobs").json() == {"cancelled": 2}


# ----------------------------------------------------------------- settings


def test_settings_round_trip(client):
    r = client.put(
        "/api/settings",
        json={
            "download_dir": "/tmp/nostos-test",
            "cookies_from_browser": "firefox",
            "auto_download": True,
            "subtitle_langs": "en,fr",
        },
    )
    assert r.status_code == 200
    body = client.get("/api/settings").json()
    assert body["cookies_from_browser"] == "firefox"
    assert body["auto_download"] is True
    assert body["subtitle_langs"] == "en,fr"
    assert body["db_path"].endswith(".db")


def test_settings_rejects_an_unknown_browser(client):
    r = client.put(
        "/api/settings",
        json={"download_dir": "/tmp/x", "cookies_from_browser": "netscape"},
    )
    assert r.status_code == 400


# ------------------------------------------------------------------ history


def test_history_records_the_failure_reason(client):
    """Without this the queue is the only place a reason ever exists."""
    db.add_history("https://fake.test/bad", "fake", "Bad", "error", None, "it exploded")
    rows = client.get("/api/history").json()
    match = next(r for r in rows if r["url"] == "https://fake.test/bad")
    assert match["error"] == "it exploded"


def test_health(client):
    # Deliberately outside /api: the launcher waits on it before the UI exists.
    assert client.get("/health").json()["status"] == "ok"


def test_clearing_history_empties_the_log(client, tmp_path):
    """Clearing the log must not touch the files it was describing."""
    kept = tmp_path / "still-here.mp4"
    kept.write_text("a real download")
    db.add_history("https://fake.test/x", "fake", "X", "done", str(kept))

    assert client.get("/api/history").json() != []
    assert client.delete("/api/history").json()["cleared"] >= 1
    assert client.get("/api/history").json() == []
    assert kept.exists(), "the downloaded file must survive clearing history"


def test_batch_carries_known_titles_onto_the_jobs(client, fake_provider):
    """A playlist expansion knows every title, so queued rows should be named
    before they start rather than showing a bare URL."""
    fake_provider(FakeProvider())
    url = "https://fake.test/titled"
    body = client.post(
        "/api/download/batch",
        json={"urls": [url], "titles": {url: "A Known Title"}, "skip_duplicates": False},
    ).json()

    job = client.get(f"/api/jobs/{body['items'][0]['jobId']}").json()
    assert job["title"] == "A Known Title"
