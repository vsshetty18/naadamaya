"""
NAADAMAYA webhook routes.

    POST /webhooks/razorpay    signed callbacks from Razorpay

Security:
  - The signature (X-Razorpay-Signature) is computed over the EXACT raw body,
    so the body is read as bytes and never re-serialised.
  - The signature is verified BEFORE anything is stored or processed. An
    unsigned or forged call gets 400 and touches nothing.
  - With no RAZORPAY_WEBHOOK_SECRET configured, every webhook is rejected.
  - Processing is idempotent (webhook_service): Razorpay retries, and a
    duplicate delivery returns 200 without doing anything twice.

Response codes tell Razorpay what to do:
  200  handled, ignored or duplicate: stop retrying
  400  bad signature or body: retrying cannot help
  503  temporary problem: Razorpay will retry later

This route has no sign-in: Razorpay calls it. It is exempt from rate limiting
(see middleware/rate_limit.py).
"""

from fastapi import APIRouter, Depends, Header, Request
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.exceptions import BadRequestError
from app.core.logging import get_logger
from app.services.payments.razorpay_client import verify_webhook_signature
from app.services.payments.webhook_service import process_webhook

log = get_logger("naadamaya.webhooks")

router = APIRouter(prefix="/webhooks", tags=["Webhooks"])

MAX_BODY_BYTES = 1024 * 1024


@router.post(
    "/razorpay",
    summary="Razorpay webhook (signed)",
    description="Called by Razorpay only. Requests without a valid signature are rejected.",
)
async def razorpay_webhook(
    request: Request,
    x_razorpay_signature: str | None = Header(default=None),
    x_razorpay_event_id: str | None = Header(default=None),
    db: Session = Depends(get_db),
) -> dict:
    raw = await request.body()
    if len(raw) > MAX_BODY_BYTES:
        raise BadRequestError("The webhook body is too large.")

    if not verify_webhook_signature(raw, x_razorpay_signature):
        log.warning("webhook rejected: invalid signature")
        raise BadRequestError("Invalid webhook signature.", code="INVALID_SIGNATURE")

    result = process_webhook(db, raw, event_id=x_razorpay_event_id)
    return {"received": True, "event": result.event_type, "outcome": result.outcome}
