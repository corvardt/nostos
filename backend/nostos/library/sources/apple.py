"""Apple Music, through amp-api - the API music.apple.com calls itself.

There is no public API for reading someone's own library, so this uses the web
player's, which needs two tokens lifted from a signed-in session:

  developer_token  the `Authorization: Bearer ...` header (hours to months)
  user_token       the `Music-User-Token` header (about six months)

Both are visible in the network tab on music.apple.com. They are yours; nothing
here shares them.
"""

from __future__ import annotations

import time
from collections.abc import Iterator
from typing import Any

import httpx

from ..models import Track
from .base import Source, SourceError

API = "https://amp-api.music.apple.com"
PAGE_SIZE = 100
# Apple rate-limits bursts on the web player API well before it says so.
PAGE_DELAY_S = 0.2


class AppleMusicSource(Source):
    name = "apple"
    description = "Apple Music library and playlists (needs web player tokens)"
    secret_options = ("developer_token", "user_token")

    @property
    def storefront(self) -> str:
        return self.options.get("storefront", "us")

    def _headers(self) -> dict[str, str]:
        developer_token, user_token = self.require("developer_token", "user_token")
        return {
            "Authorization": f"Bearer {developer_token}",
            "Music-User-Token": user_token,
            "Origin": "https://music.apple.com",
        }

    def _paginate(self, client: httpx.Client, path: str, params: dict | None = None) -> Iterator[dict]:
        """Walk one endpoint to the end.

        Apple mixes two pagination styles: a `next` cursor on some endpoints
        and plain offsets on others. Following `next` when present and falling
        back to "a short page means the end" covers both.
        """
        query: dict[str, Any] = dict(params or {})
        query.setdefault("limit", PAGE_SIZE)
        offset = 0

        while True:
            query["offset"] = offset
            response = client.get(f"{API}{path}", params=query)

            if response.status_code == 401:
                raise SourceError(
                    f"{self.label}: Apple rejected the tokens. The developer token is "
                    "short-lived - open music.apple.com while signed in and copy a fresh one.",
                    needs_auth=True,
                )
            if response.status_code == 403:
                raise SourceError(
                    f"{self.label}: Apple refused access to {path}. A library playlist "
                    "needs the user token that belongs to that same account.",
                    needs_auth=True,
                )
            if response.status_code != 200:
                raise SourceError(f"{self.label}: HTTP {response.status_code} - {response.text[:200]}")

            payload = response.json()
            data = payload.get("data", [])
            if not data:
                return
            yield from data

            if not payload.get("next") and len(data) < query["limit"]:
                return
            offset += len(data)
            time.sleep(PAGE_DELAY_S)

    def _to_track(self, item: dict, playlist: str) -> Track | None:
        attributes = item.get("attributes", {}) or {}
        if not attributes.get("name"):
            return None
        play_params = attributes.get("playParams", {}) or {}
        duration_ms = attributes.get("durationInMillis") or 0
        return Track(
            title=attributes.get("name", ""),
            artist=attributes.get("artistName", ""),
            album=attributes.get("albumName", ""),
            duration_s=round(duration_ms / 1000) if duration_ms else 0,
            isrc=attributes.get("isrc", "") or "",
            year=str(attributes.get("releaseDate", ""))[:4],
            origins={"apple": str(play_params.get("catalogId") or item.get("id") or "")},
            playlists=[playlist],
            url=attributes.get("url", "") or "",
        )

    def fetch(self) -> list[Track]:
        tracks: list[Track] = []

        with httpx.Client(headers=self._headers(), timeout=30) as client:
            if self.options.get("library_songs"):
                label = f"{self.label}: library"
                for item in self._paginate(client, "/v1/me/library/songs", {"include": "catalog"}):
                    # Library entries often lack an ISRC; the catalog relation
                    # carries it, and without it cross-platform dedup falls
                    # back to fuzzy title matching.
                    catalog = (item.get("relationships", {}).get("catalog", {}).get("data") or [])
                    track = self._to_track(catalog[0] if catalog else item, label)
                    if track:
                        tracks.append(track)

            for raw_id in self.options.get("playlists", []):
                playlist_id = str(raw_id).rstrip("/").split("/")[-1].split("?")[0]
                label = f"{self.label}: {playlist_id}"
                # "p." prefixes a playlist you made, which only exists under
                # your library; anything else is a catalog playlist.
                path = (
                    f"/v1/me/library/playlists/{playlist_id}/tracks"
                    if playlist_id.startswith("p.")
                    else f"/v1/catalog/{self.storefront}/playlists/{playlist_id}/tracks"
                )
                for item in self._paginate(client, path):
                    track = self._to_track(item, label)
                    if track:
                        tracks.append(track)

        return tracks
