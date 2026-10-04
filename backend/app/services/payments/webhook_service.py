"""
NAADAMAYA Razorpay webhook processing.

    result = process_webhook(db, raw_body, event_id=header_event_id)

The webhook route (written later) has ALREADY verified the signature against
the raw body before calling this. Unsigned or forged deliveries never reach it.

Idempotency: every delivery is recorded in webhook_events first. The unique
event_id means a second delivery of the same event is detected and skipped
(Razorpay retries deliveries). A previous attempt that FAILED is retried.

Handled events:
    payment.captured          grants the plan (idempotent, shared with verify)
    payment.failed            marks the payment FAILED (never undoes a PAID one)
    subscription.cancelled / completed / halted
                              returns a recurring subscriber to FREE
Recorded but IGNORED:
    subscription.activated / charged, and every other event type.
    NAADAMAYA currently sells one-time orders, not Razorpay recurring
    subscriptions, so there is nothing to do for those yet.

Error handling decides what Razorpay does next:
    - permanent problem (bad data, amount mismatch): event is marked FAILED and
      we answer normally, so Razorpay stops retrying something that can never succeed
    - temporary problem (database, Razorpay API down): event is marked FAILED,
      that fact is committed, and ServiceUnavailableError is raised so Razorpay retries
"""

import hashlib
import json
from dataclasses import dataclass
from typing import Any

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.core.exceptions import AppError, BadRequestError, ServiceUnavailableError
from app.core.logging import get_logger, log_event
from app.core.security import utcnow
from app.models.subscription import Subscription
from app.models.webhook_event import WebhookEvent
from app.services.payments.payment_service import fulfill_captured_payment, mark_payment_failed
from app.services.subscriptions.subscription_service import downgrade_to_free

log = get_logger("naadamaya.payments.webhook")

STATUS_RECEIVED = "RECEIVED"
STATUS_PROCESSED = "PROCESSED"
STATUS_FAILED = "FAILED"
STATUS_IGNORED = "IGNORED"

SUBSCRIPTION_END_EVENTS = {"subscription.cancelled", "subscription.completed", "subscription.halted"}


@dataclass(frozen=True)
class WebhookResult:
    event_type: str
    outcome: str  # processed | ignored | duplicate | failed


def _entity(payload: dict[str, Any], key: str) -> dict[str, Any]:
    """payload["payload"]["payment"]["entity"] and similar. Missing parts give {}."""
    return ((payload.get("payload") or {}).get(key) or {}).get("entity") or {}


def _dispatch(db: Session, event_type: str, payload: dict[str, Any]) -> str:
    """Runs the event. Returns 'processed' or 'ignored'."""
    if event_type == "payment.captured":
        payment = _entity(payload, "payment")
        order_id = payment.get("order_id")
        if not payment.get("id") or not order_id:
            raise BadRequestError("Webhook payment is missing ids.")
        fulfill_captured_payment(db, order_id, payment)
        return "processed"

    if event_type == "payment.failed":
        payment = _entity(payload, "payment")
        order_id = payment.get("order_id")
        if not order_id:
            raise BadRequestError("Webhook payment is missing an order id.")
        mark_payment_failed(db, order_id, payment.get("id"), payment.get("error_description"))
        return "processed"

    if event_type in SUBSCRIPTION_END_EVENTS:
        razorpay_sub_id = _entity(payload, "subscription").get("id")
        if not razorpay_sub_id:
            raise BadRequestError("Webhook subscription is missing an id.")
        sub = db.scalar(
            select(Subscription).where(Subscription.razorpay_subscription_id == razorpay_sub_id)
        )
        if sub is None:
            return "ignored"  # not one of ours (we do not create recurring subscriptions yet)
        downgrade_to_free(db, sub.user_id, reason=event_type)
        return "processed"

    return "ignored"


def process_webhook(db: Session, raw_body: bytes, *, event_id: str | None) -> WebhookResult:
    try:
        payload = json.loads(raw_body)
        if not isinstance(payload, dict):
            raise ValueError
    except (ValueError, UnicodeDecodeError) as exc:
        raise BadRequestError("The webhook body is not valid.") from exc

    event_type = str(payload.get("event") or "unknown")[:60]
    # Razorpay sends a unique id header. If it is ever missing, derive a stable
    # one from the body so a retry of the same body is still recognised.
    key = (event_id or "").strip() or "body:" + hashlib.sha256(raw_body).hexdigest()
    key = key[:100]

    # ---- record the delivery (the unique key makes this idempotent) ----
    try:
        with db.begin_nested():
            event = WebhookEvent(
                provider="razorpay",
                event_id=key,
                event_type=event_type,
                status=STATUS_RECEIVED,
                attempts=0,
                payload=payload,
            )
            db.add(event)
            db.flush()
    except IntegrityError:
        event = db.scalar(
            select(WebhookEvent).where(WebhookEvent.event_id == key).with_for_update()
        )
        if event is None:
            raise
        if event.status in (STATUS_PROCESSED, STATUS_IGNORED):
            log_event(log, "webhook_duplicate", event_type=event_type)
            return WebhookResult(event_type, "duplicate")
        # A previous attempt FAILED (or never finished): try again.

    event.attempts += 1

    # ---- process inside a savepoint so a failure undoes only this event's work ----
    try:
        with db.begin_nested():
            outcome = _dispatch(db, event_type, payload)
    except AppError as exc:
        if exc.status_code >= 500:
            return _transient_failure(db, event, event_type, exc)
        # Permanent: retrying cannot help.
        event.status = STATUS_FAILED
        event.error = f"{exc.code}: {exc.message}"[:500]
        event.processed_at = utcnow()
        log_event(log, "webhook_failed_permanent", event_type=event_type, code=exc.code)
        return WebhookResult(event_type, "failed")
    except Exception as exc:  # noqa: BLE001 - anything unexpected is treated as temporary
        return _transient_failure(db, event, event_type, exc)

    event.status = STATUS_PROCESSED if outcome == "processed" else STATUS_IGNORED
    event.error = None
    event.processed_at = utcnow()
    log_event(log, "webhook_processed", event_type=event_type, outcome=outcome)
    return WebhookResult(event_type, outcome)


def _transient_failure(db: Session, event: WebhookEvent, event_type: str, exc: Exception):
    """Saves the FAILED state, then raises so Razorpay retries the delivery."""
    event.status = STATUS_FAILED
    event.error = f"{type(exc).__name__}"[:500]  # type only: messages can echo request data
    event.processed_at = utcnow()
    db.commit()  # get_db() would roll this back when we raise next
    log_event(log, "webhook_failed_transient", event_type=event_type, error=type(exc).__name__)
    raise ServiceUnavailableError("Webhook could not be processed yet.") from exc
