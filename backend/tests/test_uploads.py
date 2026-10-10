"""
Upload tests: songs and recordings. Validation (real content, not names),
attempt numbering, ownership, deletion, and cleanup of stored files.
"""

import os
import uuid

from app.core.config import settings

from tests.conftest import make_wav


def post_song(client, account, data: bytes, name="song.wav", mime="audio/wav", **fields):
    return client.post(
        "/api/v1/songs/reference",
        headers=account.headers,
        files={"file": (name, data, mime)},
        data=fields,
    )


def post_recording(client, account, song_id, data: bytes, name="take.wav", mime="audio/wav", **fields):
    return client.post(
        "/api/v1/recordings",
        headers=account.headers,
        files={"file": (name, data, mime)},
        data={"song_id": song_id, **fields},
    )


# ---------------- songs ----------------
def test_upload_requires_auth(client, wav_bytes):
    r = client.post("/api/v1/songs/reference", files={"file": ("a.wav", wav_bytes, "audio/wav")})
    assert r.status_code == 401


def test_song_upload_ok(client, user_a, wav_bytes):
    r = post_song(client, user_a, wav_bytes, title="Mungaru Maleye", artist="Yograj Bhat")
    assert r.status_code == 201
    body = r.json()
    assert body["title"] == "Mungaru Maleye"
    assert 4.5 < body["duration"] < 5.5
    assert len(body["waveform"]) > 10
    assert body["audio_url"]
    # no storage keys or paths leak
    assert "file_key" not in body and "users/" not in str(body)


def test_title_falls_back_to_filename(client, user_a, wav_bytes):
    r = post_song(client, user_a, wav_bytes, name="my_song.wav")
    assert r.json()["title"] == "my_song"


def test_original_and_processed_files_are_stored(client, user_a, wav_bytes):
    song = post_song(client, user_a, wav_bytes).json()
    folder = os.path.join(settings.storage_local_dir, "users", user_a.user_id, "songs", song["id"])
    names = os.listdir(folder)
    assert any(n.endswith("-original.wav") for n in names)
    assert any(n.endswith("-processed.wav") for n in names)


def test_filename_is_never_used_as_path(client, user_a, wav_bytes):
    r = post_song(client, user_a, wav_bytes, name="../../etc/passwd.wav")
    assert r.status_code == 201
    assert "passwd" not in r.json().get("original_filename", "") or "/" not in r.json()["original_filename"]


def test_rejects_non_audio_content_with_audio_name(client, user_a):
    r = post_song(client, user_a, b"this is just text, not audio" * 100)
    assert r.status_code in (415, 422)


def test_rejects_executable_extension(client, user_a, wav_bytes):
    r = post_song(client, user_a, wav_bytes, name="song.exe", mime="audio/wav")
    assert r.status_code == 415


def test_rejects_double_extension(client, user_a, wav_bytes):
    r = post_song(client, user_a, wav_bytes, name="song.php.mp3", mime="audio/mpeg")
    assert r.status_code == 415


def test_rejects_non_audio_mime(client, user_a, wav_bytes):
    r = post_song(client, user_a, wav_bytes, mime="image/png")
    assert r.status_code == 415


def test_rejects_empty_file(client, user_a):
    r = post_song(client, user_a, b"")
    assert r.status_code == 422


def test_rejects_too_short(client, user_a):
    r = post_song(client, user_a, make_wav(seconds=1.0))
    assert r.status_code == 422
    assert r.json()["error"]["code"] == "INVALID_AUDIO"


def test_rejects_too_large(client, user_a, wav_bytes, monkeypatch):
    monkeypatch.setattr(settings, "max_upload_size_mb", 0)  # any non-empty file is too large
    r = post_song(client, user_a, wav_bytes)
    assert r.status_code == 413
    assert r.json()["error"]["code"] == "FILE_TOO_LARGE"


def test_rejects_silence(client, user_a):
    silent = make_wav(seconds=5.0)
    import io
    import numpy as np
    import soundfile as sf

    buf = io.BytesIO()
    sf.write(buf, np.zeros(22050 * 5, dtype="float32"), 22050, format="WAV", subtype="PCM_16")
    r = post_song(client, user_a, buf.getvalue())
    assert r.status_code == 422


def test_failed_upload_leaves_no_files(client, user_a):
    before = _count_files(user_a.user_id)
    post_song(client, user_a, b"garbage" * 500)
    assert _count_files(user_a.user_id) == before


def _count_files(user_id):
    root = os.path.join(settings.storage_local_dir, "users", user_id)
    return sum(len(files) for _, _, files in os.walk(root)) if os.path.isdir(root) else 0


# ---------------- ownership ----------------
def test_other_user_cannot_see_song(client, user_a, user_b, upload_song):
    song = upload_song(user_a)
    assert client.get(f"/api/v1/songs/{song['id']}", headers=user_b.headers).status_code == 404
    assert client.get(f"/api/v1/songs/{song['id']}/audio", headers=user_b.headers).status_code == 404
    assert client.delete(f"/api/v1/songs/{song['id']}", headers=user_b.headers).status_code == 404
    listing = client.get("/api/v1/songs", headers=user_b.headers).json()
    assert listing["total"] == 0


def test_song_audio_streams_for_owner(client, user_a, upload_song):
    song = upload_song(user_a)
    r = client.get(f"/api/v1/songs/{song['id']}/audio", headers=user_a.headers)
    assert r.status_code == 200
    assert r.content[:4] == b"RIFF"


# ---------------- recordings ----------------
def test_recording_attempt_numbers_increase(client, user_a, upload_song, upload_recording):
    song = upload_song(user_a)
    numbers = [upload_recording(user_a, song["id"])["attempt_number"] for _ in range(3)]
    assert numbers == [1, 2, 3]


def test_attempt_numbers_are_per_user_and_song(client, user_a, user_b, upload_song, upload_recording):
    s1, s2 = upload_song(user_a, "One"), upload_song(user_a, "Two")
    assert upload_recording(user_a, s1["id"])["attempt_number"] == 1
    assert upload_recording(user_a, s2["id"])["attempt_number"] == 1
    assert upload_recording(user_a, s1["id"])["attempt_number"] == 2


def test_attempt_number_survives_deleting_an_older_take(client, user_a, upload_song, upload_recording):
    song = upload_song(user_a)
    first = upload_recording(user_a, song["id"])
    upload_recording(user_a, song["id"])
    client.delete(f"/api/v1/recordings/{first['id']}", headers=user_a.headers)
    assert upload_recording(user_a, song["id"])["attempt_number"] == 3


def test_browser_recording_source_and_bad_source(client, user_a, upload_song, upload_recording, wav_bytes):
    song = upload_song(user_a)
    assert upload_recording(user_a, song["id"], source="browser_recording")["source"] == "browser_recording"
    r = post_recording(client, user_a, song["id"], wav_bytes, source="carrier_pigeon")
    assert r.status_code == 422


def test_cannot_record_against_someone_elses_song(client, user_a, user_b, upload_song, wav_bytes):
    song = upload_song(user_a)
    r = post_recording(client, user_b, song["id"], wav_bytes)
    assert r.status_code == 404


def test_cannot_record_against_unknown_song(client, user_a, wav_bytes):
    assert post_recording(client, user_a, str(uuid.uuid4()), wav_bytes).status_code == 404


def test_other_user_cannot_see_recording(client, user_a, user_b, upload_song, upload_recording):
    song = upload_song(user_a)
    rec = upload_recording(user_a, song["id"])
    for path in (f"/api/v1/recordings/{rec['id']}", f"/api/v1/recordings/{rec['id']}/audio"):
        assert client.get(path, headers=user_b.headers).status_code == 404
    assert client.delete(f"/api/v1/recordings/{rec['id']}", headers=user_b.headers).status_code == 404
    assert client.get("/api/v1/recordings", headers=user_b.headers).json()["total"] == 0


def test_list_recordings_filters_by_song(client, user_a, upload_song, upload_recording):
    s1, s2 = upload_song(user_a, "One"), upload_song(user_a, "Two")
    upload_recording(user_a, s1["id"])
    upload_recording(user_a, s2["id"])
    r = client.get(f"/api/v1/recordings?song_id={s1['id']}", headers=user_a.headers).json()
    assert r["total"] == 1


# ---------------- deletion ----------------
def test_delete_song_removes_recordings_and_files(client, user_a, upload_song, upload_recording):
    song = upload_song(user_a)
    upload_recording(user_a, song["id"])
    assert client.delete(f"/api/v1/songs/{song['id']}", headers=user_a.headers).status_code == 200
    assert client.get(f"/api/v1/songs/{song['id']}", headers=user_a.headers).status_code == 404
    assert client.get("/api/v1/recordings", headers=user_a.headers).json()["total"] == 0
    assert _count_files(user_a.user_id) == 0


def test_pagination_limits(client, user_a):
    assert client.get("/api/v1/songs?page_size=500", headers=user_a.headers).status_code == 422
    assert client.get("/api/v1/songs?page=0", headers=user_a.headers).status_code == 422
