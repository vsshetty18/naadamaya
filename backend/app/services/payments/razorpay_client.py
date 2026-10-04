"""
NAADAMAYA Razorpay client.

A thin wrapper around the official SDK. It only TALKS to Razorpay and checks
signatures. It decides nothing: whether a payment unlocks a plan is decided by
payment_service.py, after these checks pass.

    order   = create_order(amount=44900, currency="INR", receipt="nm_ab12", notes={...})
    ok      = verify_payment_signature(order_id, payment_id, signature)
    ok      = verify_webhook_signature(raw_body_bytes, header_signature)
    payment = fetch_payment(payment_id)

Security rules:
  - RAZORPAY_KEY_SECRET and RAZORPAY_WEBHOOK_SECRET stay on the server. Only
    the public key id (public_key_id()) is ever sent to the frontend.
  - Signatures are recomputed here with HMAC-SHA256 and compared in constant
    time. The frontend's claim that a payment succeeded is never trusted.
  - Payment signature = HMAC_SHA256(order_id + "|" + payment_id, key_secret).
  - Webhook signature = HMAC_SHA256(raw request body, webhook_secret). It must
    be computed over the exact raw bytes, never over re-serialised JSON.
  - Secrets and signatures are never logged.
  - SDK errors become ServiceUnavailableError / PaymentFailedError with a safe
    message. Details go to the logs (error type only).
"""

from functools import lru_cache
from typing import Any

import razorpay

from app.core.config import settings
from app.core.exceptions import PaymentFailedError, ServiceUnavailableError
from app.core.logging import get_logger
from app.core.security import constant_time_equals, hmac_sha256_hex

log = get_logger("naadamaya.payments.razorpay")


def is_configured() -> bool:
    return bool(settings.razorpay_key_id and settings.razorpay_key_secret)


def public_key_id() -> str:
    """The ONLY Razorpay credential the frontend may receive."""
    if not settings.razorpay_key_id:
        raise ServiceUnavailableError("Payments are not available right now.")
    return settings.razorpay_key_id


@lru_cache
def _client() -> razorpay.Client:
    if not is_configured():
        log.error("razorpay is not configured (key id / secret missing)")
        raise ServiceUnavailableError("Payments are not available right now.")
    client = razorpay.Client(auth=(settings.razorpay_key_id, settings.razorpay_key_secret))
    client.set_app_details({"title": "NAADAMAYA", "version": settings.analysis_version})
    return client


def _fail(action: str, exc: Exception) -> None:
    """Logs the error TYPE only (messages may echo request data) and raises a safe error."""
    log.error("razorpay %s failed (%s)", action, type(exc).__name__)
    if isinstance(exc, razorpay.errors.BadRequestError):
        raise PaymentFailedError("The payment provider rejected this request.") from exc
    raise ServiceUnavailableError("Payments are temporarily unavailable. Please try again shortly.") from exc


# ==========================================================
# Orders and payments
# ==========================================================
def create_order(
    *,
    amount: int,
    currency: str,
    receipt: str,
    notes: dict[str, str] | None = None,
) -> dict[str, Any]:
    """
    Creates a Razorpay order. `amount` is in the smallest unit (paise) and must
    come from the plans table. `receipt` may be at most 40 characters.
    """
    if amount <= 0:
        raise PaymentFailedError("This plan does not need a payment.")
    try:
        return _client().order.create(
            {
                "amount": int(amount),
                "currency": currency,
                "receipt": receipt[:40],
                "notes": notes or {},
                "payment_capture": 1,  # capture automatically on success
            }
        )
    except ServiceUnavailableError:
        raise
    except Exception as exc:  # noqa: BLE001 - SDK raises several unrelated types
        _fail("create_order", exc)


def fetch_payment(payment_id: str) -> dict[str, Any]:
    """The payment as Razorpay itself reports it (the source of truth for status and amount)."""
    try:
        return _client().payment.fetch(payment_id)
    except ServiceUnavailableError:
        raise
    except Exception as exc:  # noqa: BLE001
        _fail("fetch_payment", exc)


def fetch_order(order_id: str) -> dict[str, Any]:
    try:
        return _client().order.fetch(order_id)
    except ServiceUnavailableError:
        raise
    except Exception as exc:  # noqa: BLE001
        _fail("fetch_order", exc)


# ==========================================================
# Signatures
# ==========================================================
def verify_payment_signature(order_id: str, payment_id: str, signature: str) -> bool:
    """True only if the signature was made with OUR secret for exactly this order and payment."""
    if not (order_id and payment_id and signature) or not settings.razorpay_key_secret:
        return False
    expected = hmac_sha256_hex(settings.razorpay_key_secret, f"{order_id}|{payment_id}")
    return constant_time_equals(expected, signature.strip())


def verify_webhook_signature(raw_body: bytes, signature: str | None) -> bool:
    """
    True only for a delivery signed with RAZORPAY_WEBHOOK_SECRET.
    `raw_body` must be the exact bytes received. With no secret configured,
    every webhook is rejected (never accepted unsigned).
    """
    if not raw_body or not signature or not settings.razorpay_webhook_secret:
        return False
    expected = hmac_sha256_hex(settings.razorpay_webhook_secret, raw_body)
    return constant_time_equals(expected, signature.strip())
