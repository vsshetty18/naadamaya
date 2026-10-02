"""
NAADAMAYA security helpers.

- Access tokens: short-lived JWTs (PyJWT).
- Refresh tokens: long random strings. Only a keyed hash is stored in the
  database, so a database leak does not expose usable tokens.
- OTPs: hashed with HMAC-SHA256 (keyed with TOKEN_HASH_SECRET) before storing.
- Webhook / payment signatures: constant-time comparison.

No passwords exist in NAADAMAYA (phone number + OTP only).
"""

import hashlib
import hmac
import secrets
import uuid
from datetime import datetime, timedelta, timezone
from typing import Any

import jwt

from app.core.config import settings
from app.core.exceptions import InvalidTokenError, TokenExpiredError

ACCESS_TOKEN_TYPE = "access"


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


# ==========================================================
# Keyed hashing (OTPs and refresh tokens)
# ==========================================================
def _hash_key() -> bytes:
    if not settings.token_hash_secret:
        raise RuntimeError("TOKEN_HASH_SECRET is not set. Add it to your .env file.")
    return settings.token_hash_secret.encode("utf-8")


def hash_value(value: str, *, context: str = "") -> str:
    """
    HMAC-SHA256 of `value`, keyed with TOKEN_HASH_SECRET.
    `context` (for example the phone number) is mixed in so the same OTP
    for two different numbers never produces the same hash.
    """
    message = f"{context}|{value}".encode("utf-8")
    return hmac.new(_hash_key(), message, hashlib.sha256).hexdigest()


def constant_time_equals(a: str, b: str) -> bool:
    return hmac.compare_digest(a.encode("utf-8"), b.encode("utf-8"))


# ==========================================================
# OTP generation
# ==========================================================
def generate_otp(length: int | None = None) -> str:
    """
    A random numeric code. In development mode (never production) the
    fixed code from OTP_DEV_FIXED_CODE is used so no SMS provider is needed.
    """
    length = length or settings.otp_length
    if settings.otp_dev_mode:
        return settings.otp_dev_fixed_code[:length].ljust(length, "0")
    return "".join(secrets.choice("0123456789") for _ in range(length))


def hash_otp(phone_number: str, otp: str) -> str:
    return hash_value(otp, context=f"otp|{phone_number}")


def verify_otp_hash(phone_number: str, otp: str, stored_hash: str) -> bool:
    return constant_time_equals(hash_otp(phone_number, otp), stored_hash)


# ==========================================================
# Access tokens (JWT)
# ==========================================================
def _jwt_secret() -> str:
    if not settings.jwt_secret:
        raise RuntimeError("JWT_SECRET is not set. Add it to your .env file.")
    return settings.jwt_secret


def create_access_token(user_id: uuid.UUID, role: str = "USER") -> tuple[str, int]:
    """Returns (token, expires_in_seconds)."""
    expires_in = settings.jwt_access_expire_minutes * 60
    now = utcnow()
    payload = {
        "sub": str(user_id),
        "role": role,
        "type": ACCESS_TOKEN_TYPE,
        "jti": uuid.uuid4().hex,
        "iat": int(now.timestamp()),
        "exp": int((now + timedelta(seconds=expires_in)).timestamp()),
    }
    token = jwt.encode(payload, _jwt_secret(), algorithm=settings.jwt_algorithm)
    return token, expires_in


def decode_access_token(token: str) -> dict[str, Any]:
    """Validates signature, expiry and type. Raises our own auth errors."""
    try:
        payload = jwt.decode(
            token,
            _jwt_secret(),
            algorithms=[settings.jwt_algorithm],  # fixed list: blocks "alg: none" tricks
            options={"require": ["exp", "sub", "iat"]},
        )
    except jwt.ExpiredSignatureError as exc:
        raise TokenExpiredError() from exc
    except jwt.PyJWTError as exc:
        raise InvalidTokenError() from exc

    if payload.get("type") != ACCESS_TOKEN_TYPE:
        raise InvalidTokenError()
    return payload


# ==========================================================
# Refresh tokens (opaque random strings)
# ==========================================================
def generate_refresh_token() -> str:
    return secrets.token_urlsafe(48)


def hash_refresh_token(token: str) -> str:
    return hash_value(token, context="refresh")


# ==========================================================
# Signatures (Razorpay payments and webhooks)
# ==========================================================
def hmac_sha256_hex(secret: str, message: str | bytes) -> str:
    data = message.encode("utf-8") if isinstance(message, str) else message
    return hmac.new(secret.encode("utf-8"), data, hashlib.sha256).hexdigest()
