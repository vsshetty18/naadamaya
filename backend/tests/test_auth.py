"""
Authentication tests: OTP, one account per phone number, token refresh,
logout, and protected routes.
"""

from sqlalchemy import func, select

from app.core.config import settings
from app.models.otp import OtpCode
from app.models.user import User

from tests.conftest import phone_number


def send(client, phone):
    return client.post("/api/v1/auth/send-otp", json={"phone_number": phone})


def verify(client, phone, otp="123456"):
    return client.post("/api/v1/auth/verify-otp", json={"phone_number": phone, "otp": otp})


# ---------------- send OTP ----------------
def test_send_otp_returns_timings_and_masked_phone(client):
    r = send(client, phone_number(1))
    assert r.status_code == 200
    body = r.json()
    assert body["success"] is True
    assert body["expires_in"] == settings.otp_expire_seconds
    assert "9876" not in body["masked_phone"] or "X" in body["masked_phone"]
    assert body["development_otp"] == "123456"   # development mode only


def test_send_otp_rejects_invalid_number(client):
    r = send(client, "12345")
    assert r.status_code == 422
    assert r.json()["error"]["code"] == "INVALID_PHONE_NUMBER"


def test_otp_is_stored_hashed_never_plain(client, db):
    send(client, phone_number(1))
    row = db.scalar(select(OtpCode))
    assert row.code_hash != "123456"
    assert len(row.code_hash) == 64


# ---------------- verify OTP / accounts ----------------
def test_first_verify_creates_account(client):
    send(client, phone_number(1))
    r = verify(client, phone_number(1))
    assert r.status_code == 200
    body = r.json()
    assert body["is_new_user"] is True
    assert body["access_token"] and body["refresh_token"]
    assert body["user"]["phone_number"] == phone_number(1)


def test_second_login_same_number_is_same_account(client, db):
    send(client, phone_number(1))
    first = verify(client, phone_number(1)).json()
    send(client, phone_number(1))
    second = verify(client, phone_number(1)).json()
    assert second["is_new_user"] is False
    assert second["user"]["id"] == first["user"]["id"]
    assert db.scalar(select(func.count()).select_from(User)) == 1


def test_phone_formats_map_to_one_account(client, db):
    for raw in ("+919876500001", "98765 00001", "919876500001", "09876500001"):
        send(client, raw)
        assert verify(client, raw).status_code == 200
    assert db.scalar(select(func.count()).select_from(User)) == 1


def test_wrong_otp_rejected(client):
    send(client, phone_number(1))
    r = verify(client, phone_number(1), "000000")
    assert r.status_code == 400
    assert r.json()["error"]["code"] == "INVALID_OTP"


def test_otp_works_only_once(client):
    send(client, phone_number(1))
    assert verify(client, phone_number(1)).status_code == 200
    again = verify(client, phone_number(1))
    assert again.status_code == 400
    assert again.json()["error"]["code"] == "OTP_EXPIRED"


def test_too_many_wrong_attempts_kills_the_code(client):
    send(client, phone_number(1))
    for _ in range(settings.otp_max_verify_attempts):
        verify(client, phone_number(1), "000000")
    # even the correct code no longer works
    r = verify(client, phone_number(1), "123456")
    assert r.status_code in (400, 429)
    assert r.json()["error"]["code"] in ("OTP_EXPIRED", "OTP_RATE_LIMITED")


def test_new_otp_invalidates_previous(client, db):
    send(client, phone_number(1))
    send(client, phone_number(1))
    live = db.scalars(
        select(OtpCode).where(OtpCode.verified_at.is_(None), OtpCode.invalidated_at.is_(None))
    ).all()
    assert len(live) == 1


def test_verify_without_requesting_fails(client):
    r = verify(client, phone_number(9))
    assert r.status_code == 400
    assert r.json()["error"]["code"] == "OTP_EXPIRED"


def test_resend_cooldown(client, monkeypatch):
    monkeypatch.setattr(settings, "otp_resend_cooldown_seconds", 30)
    assert send(client, phone_number(1)).status_code == 200
    r = send(client, phone_number(1))
    assert r.status_code == 429
    assert r.json()["error"]["code"] == "OTP_RATE_LIMITED"
    assert "Retry-After" in r.headers


# ---------------- tokens ----------------
def test_me_requires_token(client):
    r = client.get("/api/v1/auth/me")
    assert r.status_code == 401
    assert r.json()["error"]["code"] == "AUTH_REQUIRED"
    assert r.json()["success"] is False


def test_me_with_token(client, user_a):
    r = client.get("/api/v1/auth/me", headers=user_a.headers)
    assert r.status_code == 200
    assert r.json()["id"] == user_a.user_id


def test_garbage_token_rejected(client):
    r = client.get("/api/v1/auth/me", headers={"Authorization": "Bearer not-a-token"})
    assert r.status_code == 401


def test_refresh_rotates_token(client, user_a):
    r = client.post("/api/v1/auth/refresh", json={"refresh_token": user_a.refresh_token})
    assert r.status_code == 200
    new = r.json()
    assert new["refresh_token"] != user_a.refresh_token
    # new access token works
    ok = client.get("/api/v1/auth/me", headers={"Authorization": f"Bearer {new['access_token']}"})
    assert ok.status_code == 200


def test_reusing_old_refresh_token_revokes_the_family(client, user_a):
    first = client.post("/api/v1/auth/refresh", json={"refresh_token": user_a.refresh_token}).json()
    # the OLD token is presented again: treated as theft
    reuse = client.post("/api/v1/auth/refresh", json={"refresh_token": user_a.refresh_token})
    assert reuse.status_code == 401
    # ...and the newer token from the same family is now dead too
    dead = client.post("/api/v1/auth/refresh", json={"refresh_token": first["refresh_token"]})
    assert dead.status_code == 401


def test_logout_revokes_refresh_token(client, user_a):
    out = client.post("/api/v1/auth/logout", json={"refresh_token": user_a.refresh_token})
    assert out.status_code == 200
    r = client.post("/api/v1/auth/refresh", json={"refresh_token": user_a.refresh_token})
    assert r.status_code == 401


def test_logout_never_fails(client):
    assert client.post("/api/v1/auth/logout", json={}).status_code == 200
    assert client.post("/api/v1/auth/logout", json={"refresh_token": "x" * 40}).status_code == 200


def test_suspended_user_is_blocked_immediately(client, user_a, db):
    user = db.get(User, user_a.user_id)
    user.status = "SUSPENDED"
    db.commit()
    r = client.get("/api/v1/auth/me", headers=user_a.headers)
    assert r.status_code == 403
    assert r.json()["error"]["code"] == "ACCOUNT_DISABLED"


def test_new_account_gets_free_plan_with_credits(client, user_a):
    r = client.get("/api/v1/usage", headers=user_a.headers)
    assert r.status_code == 200
    body = r.json()
    assert body["plan_code"] == "FREE"
    assert body["remaining"] == 10


def test_error_shape_includes_request_id(client):
    r = client.get("/api/v1/auth/me")
    assert r.json()["request_id"]
    assert r.headers["X-Request-ID"] == r.json()["request_id"]
