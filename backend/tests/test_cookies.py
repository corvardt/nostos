"""Cookie scoping. These are security properties, so they are asserted, not assumed."""

from __future__ import annotations

import stat
from http.cookiejar import Cookie

import pytest

from app.providers import cookies


def _cookie(name: str, domain: str) -> Cookie:
    return Cookie(
        version=0, name=name, value="secret", port=None, port_specified=False,
        domain=domain, domain_specified=True, domain_initial_dot=domain.startswith("."),
        path="/", path_specified=True, secure=True, expires=None, discard=False,
        comment=None, comment_url=None, rest={},
    )


JAR = [
    _cookie("sessionid", ".instagram.com"),
    _cookie("csrftoken", "www.instagram.com"),
    _cookie("sessionid", ".threads.com"),
    _cookie("auth", ".mybank.example"),
    _cookie("sid", "mail.google.com"),
    _cookie("x", "notinstagram.com"),
]


# ------------------------------------------------------------------ scoping


def test_only_the_named_domain_survives() -> None:
    """The whole point: a download must not carry unrelated sessions."""
    picked = cookies.select(JAR, ["instagram.com"])
    assert {c.domain for c in picked} == {".instagram.com", "www.instagram.com"}


def test_unrelated_sessions_are_dropped() -> None:
    picked = cookies.select(JAR, ["instagram.com"])
    names = {(c.domain, c.name) for c in picked}
    assert (".mybank.example", "auth") not in names
    assert ("mail.google.com", "sid") not in names


def test_a_lookalike_domain_does_not_match() -> None:
    """Suffix matching must respect the dot, or notinstagram.com would pass."""
    assert cookies.select(JAR, ["instagram.com"]) == [c for c in JAR if "instagram.com" in c.domain and c.domain != "notinstagram.com"]
    assert all(c.domain != "notinstagram.com" for c in cookies.select(JAR, ["instagram.com"]))


def test_subdomains_are_included() -> None:
    assert any(c.domain == "mail.google.com" for c in cookies.select(JAR, ["google.com"]))


# ------------------------------------------------------- domains from a URL


@pytest.mark.parametrize(
    ("url", "expected"),
    [
        ("https://soundcloud.com/a/b", {"soundcloud.com"}),
        ("https://www.vimeo.com/1", {"www.vimeo.com", "vimeo.com"}),
        ("https://media.example.co/x", {"media.example.co", "example.co"}),
    ],
)
def test_domains_derived_from_url(url: str, expected: set[str]) -> None:
    assert set(cookies.domains_for(url)) == expected


def test_a_url_with_no_host_yields_nothing() -> None:
    assert cookies.domains_for("not a url") == ()


# ------------------------------------------------------------- the file itself


def test_file_is_private_and_scoped(monkeypatch, tmp_path) -> None:
    monkeypatch.setattr(cookies.config, "DATA_DIR", tmp_path)
    monkeypatch.setattr(cookies, "extract_cookies_from_browser", lambda *a, **k: JAR)

    with cookies.scoped_cookie_file("brave", ["instagram.com"]) as path:
        assert path is not None
        mode = stat.S_IMODE(path.stat().st_mode)
        assert mode == 0o600, f"cookie file must be owner-only, got {mode:o}"

        body = path.read_text()
        assert "instagram.com" in body
        assert "mybank.example" not in body, "an unrelated session reached the file"
        assert "mail.google.com" not in body


def test_file_is_deleted_afterwards(monkeypatch, tmp_path) -> None:
    monkeypatch.setattr(cookies.config, "DATA_DIR", tmp_path)
    monkeypatch.setattr(cookies, "extract_cookies_from_browser", lambda *a, **k: JAR)

    with cookies.scoped_cookie_file("brave", ["instagram.com"]) as path:
        assert path.exists()
    assert not path.exists(), "the secret outlived the request that needed it"


def test_file_is_deleted_even_when_the_download_raises(monkeypatch, tmp_path) -> None:
    monkeypatch.setattr(cookies.config, "DATA_DIR", tmp_path)
    monkeypatch.setattr(cookies, "extract_cookies_from_browser", lambda *a, **k: JAR)

    seen = None
    with pytest.raises(RuntimeError):
        with cookies.scoped_cookie_file("brave", ["instagram.com"]) as path:
            seen = path
            raise RuntimeError("download blew up")
    assert seen is not None and not seen.exists()


def test_no_file_is_written_when_nothing_matches(monkeypatch, tmp_path) -> None:
    """Writing an empty file would put a pointless secret on disk."""
    monkeypatch.setattr(cookies.config, "DATA_DIR", tmp_path)
    monkeypatch.setattr(cookies, "extract_cookies_from_browser", lambda *a, **k: JAR)

    with cookies.scoped_cookie_file("brave", ["nowhere.example"]) as path:
        assert path is None
    assert list(tmp_path.glob("cookies/*")) == []


def test_no_browser_means_no_file(monkeypatch, tmp_path) -> None:
    monkeypatch.setattr(cookies.config, "DATA_DIR", tmp_path)
    with cookies.scoped_cookie_file("", ["instagram.com"]) as path:
        assert path is None
