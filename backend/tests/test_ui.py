"""Serving the bundled interface from the same process as the API.

These run against whatever is on disk: with no bundle built they check the
API-only behaviour, and with one they check it is served correctly. Both paths
are real, so neither is skipped for the wrong reason.
"""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from nostos import ui
from nostos.main import app


@pytest.fixture
def client():
    with TestClient(app) as c:
        yield c


built = pytest.mark.skipif(not ui.is_built(), reason="no interface built; run scripts/build-package.sh")


def test_health_sits_outside_the_api_prefix(client):
    """The launcher polls this before it assumes anything else about the app."""
    assert client.get("/health").json()["status"] == "ok"
    assert client.get("/api/health").status_code == 404


def test_the_api_lives_under_its_prefix(client):
    assert client.get("/api/settings").status_code == 200
    assert client.get("/api/library/stats").status_code == 200


def test_an_unknown_api_path_is_a_404_not_the_page(client):
    """The catch-all must never answer an API call with index.html: the UI would
    parse HTML as JSON and report something incomprehensible."""
    r = client.get("/api/no-such-endpoint")
    assert r.status_code == 404
    assert r.headers["content-type"].startswith("application/json")


@built
def test_the_root_serves_the_page(client):
    r = client.get("/")
    assert r.status_code == 200
    assert b'<div id="root"' in r.content


@built
def test_a_client_route_serves_the_page(client):
    """The UI's own views are not server routes; they all resolve to the page."""
    assert b'<div id="root"' in client.get("/library").content


@built
def test_the_page_is_never_cached(client):
    """A cached index keeps requesting the previous build's asset names."""
    assert client.get("/").headers["cache-control"] == "no-store"


@built
def test_assets_are_cached_forever(client):
    """Safe only because Vite fingerprints the filenames."""
    name = next(p.name for p in (ui.STATIC_DIR / "assets").iterdir() if p.is_file())
    r = client.get(f"/assets/{name}")
    assert r.status_code == 200
    assert "immutable" in r.headers["cache-control"]


@built
def test_traversal_does_not_escape_the_bundle(client):
    """It falls through to the page rather than erroring, but the one thing that
    must never happen is a file from outside the bundle coming back."""
    for path in ["/../../etc/passwd", "/assets/../../../etc/passwd", "/%2e%2e/%2e%2e/etc/passwd"]:
        r = client.get(path)
        assert b"root:x:" not in r.content
