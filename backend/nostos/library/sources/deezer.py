"""Deezer, by two routes depending on what you are asking for.

  api.deezer.com  public playlists and the favourites of a public profile,
                  with no credentials at all
  gw-light        the site's own internal API, reached with your `arl` cookie,
                  for private favourites and playlists

The public API only returns an ISRC on the per-track endpoint, never in a
listing. `fetch_isrc` goes and gets them one request at a time: slow on a large
library, but ISRCs are what make deduplication against Spotify and Apple exact
rather than approximate.
"""

from __future__ import annotations

import time
from collections.abc import Iterator

import httpx

from ..models import Track
from .base import Source, SourceError

API = "https://api.deezer.com"
GW = "https://www.deezer.com/ajax/gw-light.php"
PAGE_SIZE = 100
PAGE_DELAY_S = 0.15
ISRC_DELAY_S = 0.1
# gw-light accepts far larger pages than the public API.
GW_PAGE_SIZE = 2000

USER_AGENT = (
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/120.0 Safari/537.36"
)


class DeezerSource(Source):
    name = "deezer"
    description = "Deezer favourites and playlists"
    secret_options = ("arl",)

    # ------------------------------------------------------------- public API

    def _get(self, client: httpx.Client, path: str, params: dict | None = None) -> dict:
        response = client.get(f"{API}{path}", params=params or {})
        if response.status_code != 200:
            raise SourceError(f"{self.label}: HTTP {response.status_code} on {path}")
        payload = response.json()
        # Deezer answers 200 with an error body rather than an HTTP error code.
        if isinstance(payload, dict) and payload.get("error"):
            error = payload["error"]
            raise SourceError(f"{self.label}: {error.get('type')} - {error.get('message')}")
        return payload

    def _paginate(self, client: httpx.Client, path: str) -> Iterator[dict]:
        index = 0
        while True:
            payload = self._get(client, path, {"limit": PAGE_SIZE, "index": index})
            data = payload.get("data", [])
            if not data:
                return
            yield from data
            if not payload.get("next"):
                return
            index += len(data)
            time.sleep(PAGE_DELAY_S)

    @staticmethod
    def _from_api(row: dict, playlist: str) -> Track | None:
        if not row.get("title"):
            return None
        return Track(
            title=row.get("title", ""),
            artist=(row.get("artist") or {}).get("name", ""),
            album=(row.get("album") or {}).get("title", ""),
            duration_s=int(row.get("duration") or 0),
            isrc=row.get("isrc", "") or "",
            origins={"deezer": str(row.get("id", ""))},
            playlists=[playlist],
            url=row.get("link", "") or "",
        )

    # ---------------------------------------------------------------- gw-light

    def _gw_login(self, client: httpx.Client, arl: str) -> str:
        """Open a gw-light session from the arl cookie, returning its API token.

        Every later gw call must carry that token; without it the endpoint
        answers as an anonymous visitor rather than refusing outright, which is
        why an expired arl looks like an empty library instead of an error.
        """
        client.cookies.set("arl", arl, domain=".deezer.com")
        response = client.post(
            GW,
            params={"method": "deezer.getUserData", "input": "3", "api_version": "1.0", "api_token": ""},
            json={},
        )
        results = response.json().get("results", {})
        token = results.get("checkForm")
        user_id = str((results.get("USER") or {}).get("USER_ID") or "0")

        if not token or user_id == "0":
            raise SourceError(
                f"{self.label}: that arl cookie is expired or invalid. Copy a fresh one "
                "from deezer.com (Application tab > Cookies > arl) while signed in.",
                needs_auth=True,
            )
        return token

    def _gw_call(self, client: httpx.Client, method: str, token: str, payload: dict) -> dict:
        response = client.post(
            GW,
            params={"method": method, "input": "3", "api_version": "1.0", "api_token": token},
            json=payload,
        )
        body = response.json()
        if body.get("error"):
            raise SourceError(f"{self.label}: gw-light {method} failed - {body['error']}")
        return body.get("results", {})

    @staticmethod
    def _from_gw(row: dict, playlist: str) -> Track:
        artist = row.get("ART_NAME", "")
        credited = row.get("ARTISTS") or []
        if len(credited) > 1:
            artist = ", ".join(a.get("ART_NAME", "") for a in credited if a.get("ART_NAME"))
        # VERSION holds "(Radio Edit)", "(Live)" and the like, which the title
        # field omits and which distinguishes one recording from another.
        version = row.get("VERSION") or ""
        return Track(
            title=f"{row.get('SNG_TITLE', '')} {version}".strip(),
            artist=artist,
            album=row.get("ALB_TITLE", ""),
            duration_s=int(row.get("DURATION") or 0),
            isrc=row.get("ISRC", "") or "",
            year=str(row.get("PHYSICAL_RELEASE_DATE", ""))[:4],
            origins={"deezer": str(row.get("SNG_ID", ""))},
            playlists=[playlist],
        )

    def _fetch_favourites(self, client: httpx.Client) -> list[Track]:
        playlist = f"{self.label}: favourites"
        arl = self.options.get("arl")

        if arl:
            token = self._gw_login(client, arl)
            tracks: list[Track] = []
            start = 0
            while True:
                results = self._gw_call(
                    client, "favorite_song.getList", token,
                    {"start": start, "nb": GW_PAGE_SIZE, "tab": "loved"},
                )
                rows = results.get("data", [])
                if not rows:
                    break
                tracks += [self._from_gw(row, playlist) for row in rows]
                if len(rows) < GW_PAGE_SIZE:
                    break
                start += len(rows)
            return tracks

        user_id = self.options.get("user_id")
        if not user_id:
            raise SourceError(
                f"{self.label}: reading favourites needs either an arl cookie (your own "
                "account) or a user_id (a public profile).",
                needs_auth=True,
            )
        return [
            track
            for row in self._paginate(client, f"/user/{user_id}/tracks")
            if (track := self._from_api(row, playlist))
        ]

    # -------------------------------------------------------------------- API

    def fetch(self) -> list[Track]:
        tracks: list[Track] = []

        with httpx.Client(headers={"User-Agent": USER_AGENT}, timeout=30, follow_redirects=True) as client:
            if self.options.get("favorites"):
                tracks += self._fetch_favourites(client)

            for raw_id in self.options.get("playlists", []):
                playlist_id = str(raw_id).rstrip("/").split("/")[-1].split("?")[0]
                playlist = f"{self.label}: {playlist_id}"
                tracks += [
                    track
                    for row in self._paginate(client, f"/playlist/{playlist_id}/tracks")
                    if (track := self._from_api(row, playlist))
                ]

            if self.options.get("fetch_isrc"):
                for track in tracks:
                    track_id = track.origins.get("deezer")
                    if track.isrc or not track_id:
                        continue
                    try:
                        track.isrc = self._get(client, f"/track/{track_id}").get("isrc", "") or ""
                    except SourceError:
                        pass  # a missing ISRC degrades dedup, it does not break it
                    time.sleep(ISRC_DELAY_S)

        return tracks
