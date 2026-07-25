"""Spotify, through the Web API.

Two authentication modes, picked automatically:

  client credentials  enough for public playlists; no browser step
  authorization code  required for Liked Songs and private playlists

The OAuth flow opens a browser once and caches the refresh token, so only the
first sync is interactive. Register an app at developer.spotify.com to get the
client id and secret; the redirect URI there must match the one configured here.
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Any

from ..models import Track
from .base import Source, SourceError

log = logging.getLogger(__name__)

SCOPES = "user-library-read playlist-read-private playlist-read-collaborative"
DEFAULT_REDIRECT = "http://127.0.0.1:8888/callback"


class SpotifySource(Source):
    name = "spotify"
    description = "Spotify liked songs and playlists"
    secret_options = ("client_id", "client_secret")

    def _client(self):
        try:
            import spotipy
            from spotipy.oauth2 import SpotifyClientCredentials, SpotifyOAuth
        except ImportError as exc:  # pragma: no cover - dependency check
            raise SourceError(
                "Spotify support needs the spotipy package: "
                "pip install spotipy in backend/.venv"
            ) from exc

        client_id, client_secret = self.require("client_id", "client_secret")
        needs_user = bool(self.options.get("liked") or self.options.get("user_playlists"))

        if needs_user:
            cache = Path(self.options.get("cache_path", "~/.cache/nostos-spotify.json")).expanduser()
            cache.parent.mkdir(parents=True, exist_ok=True)
            auth = SpotifyOAuth(
                client_id=client_id,
                client_secret=client_secret,
                redirect_uri=self.options.get("redirect_uri", DEFAULT_REDIRECT),
                scope=SCOPES,
                cache_path=str(cache),
                open_browser=bool(self.options.get("open_browser", True)),
            )
        else:
            auth = SpotifyClientCredentials(client_id=client_id, client_secret=client_secret)

        return spotipy.Spotify(auth_manager=auth, requests_timeout=30, retries=3)

    @staticmethod
    def _to_track(item: dict, playlist: str) -> Track | None:
        # Saved tracks and playlist items both wrap the track; album endpoints
        # return it bare.
        raw: dict[str, Any] = item.get("track", item) or {}
        # Local files have no id and cannot be resolved anywhere else.
        if not raw.get("name") or raw.get("is_local"):
            return None
        album = raw.get("album", {}) or {}
        return Track(
            title=raw.get("name", ""),
            artist=", ".join(a["name"] for a in raw.get("artists", []) if a.get("name")),
            album=album.get("name", ""),
            duration_s=round((raw.get("duration_ms") or 0) / 1000),
            isrc=(raw.get("external_ids") or {}).get("isrc", "") or "",
            year=str(album.get("release_date", ""))[:4],
            origins={"spotify": raw.get("id") or ""},
            playlists=[playlist],
            url=(raw.get("external_urls") or {}).get("spotify", ""),
        )

    def _collect(self, client, page: dict, playlist: str, out: list[Track]) -> None:
        while page:
            for item in page.get("items", []):
                track = self._to_track(item, playlist)
                if track:
                    out.append(track)
            page = client.next(page) if page.get("next") else None

    def fetch(self) -> list[Track]:
        client = self._client()
        tracks: list[Track] = []

        if self.options.get("liked"):
            self._collect(
                client, client.current_user_saved_tracks(limit=50), f"{self.label}: liked", tracks
            )

        playlist_ids: list[str] = [str(p) for p in self.options.get("playlists", [])]

        if self.options.get("user_playlists"):
            page = client.current_user_playlists(limit=50)
            while page:
                playlist_ids += [p["id"] for p in page.get("items", []) if p and p.get("id")]
                page = client.next(page) if page.get("next") else None

        seen: set[str] = set()
        for raw_id in playlist_ids:
            playlist_id = raw_id.rstrip("/").split("/")[-1].split("?")[0]
            if playlist_id in seen:
                continue
            seen.add(playlist_id)
            try:
                self._collect(
                    client,
                    client.playlist_items(playlist_id, limit=100, additional_types=("track",)),
                    f"{self.label}: {playlist_id}",
                    tracks,
                )
            except Exception as exc:  # noqa: BLE001
                # One playlist that has been deleted or made private should not
                # cost the user every other playlist in the same account.
                log.warning("%s: skipping playlist %s (%s)", self.label, playlist_id, exc)

        return tracks
