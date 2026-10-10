"""
Profile tests (partial updates, validation, photo) and account deletion.
"""

import io

from sqlalchemy import select

from app.models.credit_transaction import CreditTransaction
from app.models.profile import Profile
from app.models.user import User

from tests.conftest import phone_number

PNG = b"\x89PNG\r\n\x1a\n" + b"\x00" * 64


# ---------------- profile ----------------
def test_profile_requires_auth(client):
    assert client.get("/api/v1/profile").status_code == 401


def test_new_profile_is_empty_and_not_onboarded(client, user_a):
    r = client.get("/api/v1/profile", headers=user_a.headers)
    assert r.status_code == 200
    body = r.json()
    assert body["display_name"] is None
    assert body["preferred_languages"] == []
    assert body["onboarding_completed"] is False
    assert body["phone_number"] == phone_number(1)


def test_partial_update_changes_only_sent_fields(client, user_a):
    client.put("/api/v1/profile", headers=user_a.headers,
               json={"display_name": "V S Vighnesh", "preferred_languages": ["Kannada", "Hindi"]})
    r = client.put("/api/v1/profile", headers=user_a.headers, json={"experience_level": "intermediate"})
    body = r.json()
    assert body["display_name"] == "V S Vighnesh"          # untouched
    assert body["preferred_languages"] == ["Kannada", "Hindi"]
    assert body["experience_level"] == "intermediate"


def test_null_clears_a_field(client, user_a):
    client.put("/api/v1/profile", headers=user_a.headers, json={"display_name": "Someone"})
    r = client.put("/api/v1/profile", headers=user_a.headers, json={"display_name": None})
    assert r.json()["display_name"] is None


def test_vocal_range_marked_self_reported(client, user_a):
    r = client.put("/api/v1/profile", headers=user_a.headers,
                   json={"vocal_range_low": "c3", "vocal_range_high": "A4"})
    body = r.json()
    assert body["vocal_range_low"] == "C3"
    assert body["vocal_range_source"] == "self_reported"


def test_invalid_values_rejected(client, user_a):
    for payload in (
        {"vocal_range_low": "H9"},
        {"experience_level": "wizard"},
        {"email": "not-an-email"},
        {"display_name": "<script>"},
        {"username": "x"},
    ):
        r = client.put("/api/v1/profile", headers=user_a.headers, json=payload)
        assert r.status_code == 422, payload


def test_username_must_be_unique(client, user_a, user_b):
    assert client.put("/api/v1/profile", headers=user_a.headers, json={"username": "singer_one"}).status_code == 200
    r = client.put("/api/v1/profile", headers=user_b.headers, json={"username": "singer_one"})
    assert r.status_code == 409
    assert r.json()["error"]["code"] == "USERNAME_TAKEN"


def test_phone_cannot_be_changed_through_profile(client, user_a):
    client.put("/api/v1/profile", headers=user_a.headers, json={"phone_number": "+919999999999"})
    me = client.get("/api/v1/profile", headers=user_a.headers).json()
    assert me["phone_number"] == phone_number(1)


# ---------------- photo ----------------
def test_photo_upload_and_fetch(client, user_a):
    r = client.post("/api/v1/profile/photo", headers=user_a.headers,
                    files={"file": ("me.png", PNG, "image/png")})
    assert r.status_code == 200
    assert r.json()["profile_photo_url"]
    got = client.get("/api/v1/profile/photo", headers=user_a.headers)
    assert got.status_code == 200
    assert got.content == PNG


def test_photo_rejects_fake_image(client, user_a):
    r = client.post("/api/v1/profile/photo", headers=user_a.headers,
                    files={"file": ("me.png", b"this is not an image", "image/png")})
    assert r.status_code == 415


def test_photo_rejects_wrong_extension(client, user_a):
    r = client.post("/api/v1/profile/photo", headers=user_a.headers,
                    files={"file": ("me.exe", PNG, "image/png")})
    assert r.status_code == 415


def test_photo_rejects_too_large(client, user_a):
    big = b"\x89PNG\r\n\x1a\n" + b"\x00" * (5 * 1024 * 1024 + 10)
    r = client.post("/api/v1/profile/photo", headers=user_a.headers,
                    files={"file": ("me.png", big, "image/png")})
    assert r.status_code == 413


def test_photo_not_visible_to_other_user(client, user_a, user_b):
    client.post("/api/v1/profile/photo", headers=user_a.headers,
                files={"file": ("me.png", PNG, "image/png")})
    assert client.get("/api/v1/profile/photo", headers=user_b.headers).status_code == 404


# ---------------- account deletion ----------------
def test_delete_requires_confirmation(client, user_a):
    r = client.request("DELETE", "/api/v1/users/me", headers=user_a.headers, json={"confirm": "yes"})
    assert r.status_code == 422


def test_delete_account_removes_data_and_frees_number(client, db, login, upload_song, upload_recording):
    a = login(1)
    song = upload_song(a)
    upload_recording(a, song["id"])

    r = client.request("DELETE", "/api/v1/users/me", headers=a.headers, json={"confirm": "DELETE"})
    assert r.status_code == 200
    assert "payment_records" in r.json()["retained"]

    # the old token and refresh token no longer work
    assert client.get("/api/v1/auth/me", headers=a.headers).status_code in (401, 403)
    assert client.post("/api/v1/auth/refresh", json={"refresh_token": a.refresh_token}).status_code == 401

    user = db.get(User, a.user_id)
    db.refresh(user)
    assert user.is_deleted and user.phone_number_normalized != phone_number(1)
    assert db.scalar(select(Profile).where(Profile.user_id == a.user_id)) is None

    # the credit ledger is KEPT (financial record)
    assert db.scalars(select(CreditTransaction).where(CreditTransaction.user_id == a.user_id)).first() is not None

    # the same number can sign up again as a brand-new account
    again = login(1)
    assert again.user_id != a.user_id


def test_deleted_users_audio_is_removed(client, db, login, upload_song):
    import os
    from app.core.config import settings

    a = login(1)
    upload_song(a)
    user_dir = os.path.join(settings.storage_local_dir, "users", a.user_id)
    assert os.path.isdir(user_dir)
    client.request("DELETE", "/api/v1/users/me", headers=a.headers, json={"confirm": "DELETE"})
    assert not os.path.exists(user_dir)
