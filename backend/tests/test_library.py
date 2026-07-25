"""Library sync: deduplication, ownership matching, candidate scoring, API."""

from __future__ import annotations

import json

import pytest
from fastapi.testclient import TestClient

from nostos.library import resolver, store
from nostos.library.models import Track, deduplicate
from nostos.library.scan import MusicIndex
from nostos.library.sources import build_source
from nostos.library.sources.base import SourceError
from nostos.library.text import safe_filename, split_artist_title
from nostos.main import app


@pytest.fixture
def client():
    with TestClient(app) as test_client:
        yield test_client
    # Each test starts from an empty library, since the database is shared.
    with store.db.connect() as conn:
        conn.execute("DELETE FROM library_sources")
        conn.execute("DELETE FROM library_tracks")


def track(title="Blue Monday", artist="New Order", **kwargs) -> Track:
    return Track(title=title, artist=artist, **kwargs)


# ----------------------------------------------------------------- dedupe


def test_isrc_decides_over_a_similar_title():
    """Same words, different recording. The ISRC is the only thing that knows."""
    original = track(isrc="GBAAA7900001", duration_s=450)
    live = track(isrc="GBAAA8800002", duration_s=455)

    assert not original.matches(live)
    assert len(deduplicate([original, live])) == 2


def test_same_isrc_merges_across_platforms():
    spotify = track(isrc="GBAAA7900001", origins={"spotify": "abc"}, playlists=["liked"])
    apple = track(isrc="gbaaa7900001", origins={"apple": "123"}, playlists=["library"])

    merged = deduplicate([spotify, apple])

    assert len(merged) == 1
    assert merged[0].origins == {"spotify": "abc", "apple": "123"}
    assert sorted(merged[0].playlists) == ["library", "liked"]


def test_fuzzy_merge_without_isrc():
    """No ISRC anywhere, which is every track that came from YouTube."""
    a = track(title="Blue Monday", artist="New Order", duration_s=450)
    b = track(title="Blue Monday (Official Video)", artist="New Order", duration_s=452)

    assert len(deduplicate([a, b])) == 1


def test_duration_keeps_an_edit_and_a_long_remix_apart():
    radio = track(duration_s=210)
    extended = track(duration_s=480)

    assert not radio.matches(extended)


def test_merge_fills_gaps_without_overwriting():
    first = track(album="Power, Corruption & Lies", origins={"spotify": "abc"})
    second = track(album="Substance", isrc="GBAAA7900001", origins={"deezer": "9"})

    first.merge(second)

    assert first.album == "Power, Corruption & Lies"  # kept
    assert first.isrc == "GBAAA7900001"  # filled


# ------------------------------------------------------------------- scan


def test_index_matches_regardless_of_word_order(tmp_path):
    (tmp_path / "01 - Blue Monday (New Order).mp3").write_bytes(b"")

    index = MusicIndex([str(tmp_path)])

    assert index.find(track()) is not None


def test_index_ignores_a_different_song(tmp_path):
    (tmp_path / "Joy Division - Transmission.mp3").write_bytes(b"")

    assert MusicIndex([str(tmp_path)]).find(track()) is None


def test_index_skips_non_audio_and_missing_folders(tmp_path):
    (tmp_path / "New Order - Blue Monday.txt").write_bytes(b"")

    index = MusicIndex([str(tmp_path), str(tmp_path / "nope")])

    assert len(index) == 0
    assert index.missing_dirs == [str(tmp_path / "nope")]


# --------------------------------------------------------------- resolver


def test_scoring_prefers_the_topic_channel():
    wanted = track(duration_s=450)
    topic = {"title": "Blue Monday", "uploader": "New Order - Topic", "duration": 450}
    random_upload = {"title": "Blue Monday", "uploader": "musicfan1987", "duration": 450}

    assert resolver.score_candidate(wanted, topic) > resolver.score_candidate(wanted, random_upload)


def test_scoring_punishes_a_cover():
    wanted = track(duration_s=450)
    real = {"title": "New Order - Blue Monday", "uploader": "New Order", "duration": 450}
    cover = {"title": "Blue Monday (cover)", "uploader": "somebody", "duration": 450}

    assert resolver.score_candidate(wanted, cover) < resolver.MIN_SCORE
    assert resolver.score_candidate(wanted, real) >= resolver.MIN_SCORE


def test_a_requested_live_version_is_not_punished():
    """Asking for a live recording should not rule out live recordings."""
    wanted = track(title="Blue Monday (Live at Reading)", duration_s=450)
    live = {"title": "New Order - Blue Monday (Live at Reading)", "uploader": "New Order", "duration": 450}

    assert resolver.score_candidate(wanted, live) >= resolver.MIN_SCORE


def test_wrong_duration_sinks_a_matching_title():
    wanted = track(duration_s=450)
    hour_long = {"title": "New Order - Blue Monday", "uploader": "New Order", "duration": 3600}

    assert resolver.score_candidate(wanted, hour_long) < resolver.MIN_SCORE


def test_a_youtube_track_needs_no_search():
    sourced = track(url="https://www.youtube.com/watch?v=FYH8DsU2WCk")

    resolution = resolver.resolve(sourced)

    assert resolution is not None
    assert resolution.url == sourced.url
    assert resolution.reason == "from source"


# ------------------------------------------------------------------- text


def test_filenames_drop_characters_that_break_subprocesses():
    """`$` and `%` survive the filesystem but not a shell or an output template."""
    name = safe_filename("Ty Dolla $ign - 100%")

    assert "$" not in name
    assert "%" not in name


def test_youtube_title_splitting():
    assert split_artist_title("New Order - Blue Monday (Official Video)") == ("New Order", "Blue Monday")
    # No separator: fall back to the channel, minus the Topic suffix.
    assert split_artist_title("Blue Monday", "New Order - Topic") == ("New Order", "Blue Monday")


# ------------------------------------------------------------------ sources


def test_json_source_reads_the_legacy_export(tmp_path):
    path = tmp_path / "favourites.json"
    path.write_text(
        json.dumps([{"title": "Blue Monday", "artist": "New Order", "album": "Substance"}]),
        encoding="utf-8",
    )

    tracks = build_source("json", {"path": str(path)}, "export").fetch()

    assert [t.display_name for t in tracks] == ["New Order - Blue Monday"]
    assert tracks[0].playlists == ["export"]


def test_a_source_missing_credentials_says_which():
    with pytest.raises(SourceError, match="developer_token"):
        build_source("apple", {"playlists": ["pl.123"]}, "apple").fetch()


def test_unknown_source_type_is_rejected():
    with pytest.raises(SourceError, match="Unknown source type"):
        build_source("napster", {}, "napster")


# --------------------------------------------------------------------- API


def test_source_round_trip_masks_secrets(client):
    created = client.post(
        "/api/library/sources",
        json={"type": "deezer", "label": "deezer", "options": {"arl": "supersecret", "favorites": True}},
    ).json()

    assert created["options"]["arl"] == "********"
    assert "supersecret" not in json.dumps(client.get("/api/library/sources").json())
    # The real value is still stored, and still usable.
    assert store.get_source(created["id"]).options["arl"] == "supersecret"


def test_updating_a_source_keeps_a_masked_secret(client):
    created = client.post(
        "/api/library/sources",
        json={"type": "deezer", "options": {"arl": "supersecret"}},
    ).json()

    client.put(
        f"/api/library/sources/{created['id']}",
        json={"type": "deezer", "label": "renamed", "options": {"arl": "********"}},
    )

    updated = store.get_source(created["id"])
    assert updated.label == "renamed"
    assert updated.options["arl"] == "supersecret"


def test_sync_dry_run_collects_without_queueing(client, tmp_path):
    path = tmp_path / "tracks.json"
    path.write_text(
        json.dumps(
            [
                {"title": "Blue Monday", "artist": "New Order"},
                {"title": "Blue Monday", "artist": "New Order"},  # duplicate
                {"title": "Transmission", "artist": "Joy Division"},
            ]
        ),
        encoding="utf-8",
    )
    client.post("/api/library/sources", json={"type": "json", "options": {"path": str(path)}})

    report = client.post("/api/library/sync", json={"dry_run": True}).json()

    assert report["collected"] == 3
    assert report["unique"] == 2
    assert report["queued"] == 0
    assert client.get("/api/library/stats").json()["counts"] == {"wanted": 2}


def test_a_broken_source_does_not_abort_the_pass(client, tmp_path):
    """One expired token should not cost you every other source."""
    good = tmp_path / "good.json"
    good.write_text(json.dumps([{"title": "Blue Monday", "artist": "New Order"}]), encoding="utf-8")

    client.post("/api/library/sources", json={"type": "json", "label": "gone", "options": {"path": "/nope.json"}})
    client.post("/api/library/sources", json={"type": "json", "label": "good", "options": {"path": str(good)}})

    report = client.post("/api/library/sync", json={"dry_run": True}).json()

    assert report["unique"] == 1
    assert len(report["failed_sources"]) == 1
    assert "gone" in report["failed_sources"][0]


def test_owned_tracks_are_not_queued(client, tmp_path):
    music = tmp_path / "music"
    music.mkdir()
    (music / "New Order - Blue Monday.mp3").write_bytes(b"")

    settings = client.get("/api/settings").json()
    settings["music_library_dirs"] = str(music)
    client.put("/api/settings", json=settings)

    path = tmp_path / "tracks.json"
    path.write_text(json.dumps([{"title": "Blue Monday", "artist": "New Order"}]), encoding="utf-8")
    client.post("/api/library/sources", json={"type": "json", "options": {"path": str(path)}})

    report = client.post("/api/library/sync", json={}).json()

    assert report["already_owned"] == 1
    assert report["queued"] == 0
    assert client.get("/api/library/tracks").json()[0]["status"] == "owned"


def test_a_second_sync_does_not_requeue(client, tmp_path):
    path = tmp_path / "tracks.json"
    path.write_text(json.dumps([{"title": "Blue Monday", "artist": "New Order"}]), encoding="utf-8")
    client.post("/api/library/sources", json={"type": "json", "options": {"path": str(path)}})

    client.post("/api/library/sync", json={"dry_run": True})
    store.mark_downloaded("nm:new order|blue monday", "/tmp/blue.mp3")

    report = client.post("/api/library/sync", json={"dry_run": True}).json()

    assert report["already_downloaded"] == 1
    assert report["queued"] == 0


def test_settings_reject_a_bad_layout(client):
    settings = client.get("/api/settings").json()
    settings["music_layout"] = "by-mood"

    assert client.put("/api/settings", json=settings).status_code == 400


def test_track_filename_layouts():
    song = track(album="Power, Corruption & Lies")

    assert song.filename("flat") == "New Order - Blue Monday.mp3"
    assert song.filename("artist") == "New Order/New Order - Blue Monday.mp3"
    assert song.filename("artist-album") == (
        "New Order/Power, Corruption & Lies/New Order - Blue Monday.mp3"
    )
