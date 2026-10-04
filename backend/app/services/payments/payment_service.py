"""
NAADAMAYA payments.

    order    = create_order(db, user, plan_code="PRO")
    result   = verify_payment(db, user, order_id, payment_id, signature)
    result   = fulfill_captured_payment(db, order_id, gateway_payment)   # webhook path
    mark_payment_failed(db, order_id, payment_id, reason)                # webhook path
    page     = list_payments(db, user.id, params)

The frontend is NEVER the source of truth. A plan is activated only when:
  1. the order belongs to the signed-in user,
  2. the signature is recomputed with our secret and matches,
  3. Razorpay itself reports the payment as captured,
  4. its amount, currency and order id equal what WE stored when the order
     was created (the amount came from the plans table, not from the app).

Idempotency: the payment row is locked (FOR UPDATE) and `fulfilled_at` is set
exactly once, in the same transaction that grants the plan and credits. A
repeated verify call or a duplicate webhook finds `fulfilled_at` set and does
nothing. activate_paid_plan() adds a second guard through the ledger's unique
idempotency key.

IMPORTANT: get_db() rolls back when a request raises. Where a state change
must survive an error (marking a payment FAILED), this module commits first.
"""

import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.exceptions import (
    NotFoundError,
    PaymentFailedError,
    PaymentVerificationFailedError,
)
from app.core.logging import get_logger, log_event
from app.core.security import utcnow
from app.models.enums import PaymentStatus
from app.models.payment import Payment
from app.models.plan import Plan
from app.models.user import User
from app.schemas.common import Page, PageParams
from app.schemas.payment import (
    CreateOrderResponse,
    PaymentResponse,
    VerifyPaymentResponse,
)
from app.services.payments import razorpay_client
from app.services.plans.plan_service import get_active_plan
from app.services.subscriptions.subscription_service import (
    activate_paid_plan,
    subscription_to_response,
)
from app.utils.phone import mask_phone

log = get_logger("naadamaya.payments")


# ==========================================================
# Create order
# ==========================================================
def create_order(
    db: Session,
    user: User,
    *,
    plan_code: str | None = None,
    plan_id: uuid.UUID | None = None,
) -> CreateOrderResponse:
    """The amount is read from the plan row. The app cannot choose a price."""
    plan = get_active_plan(db, code=plan_code, plan_id=plan_id)

    if plan.price_amount <= 0:
        raise PaymentFailedError("The free plan does not need a payment.")

    order = razorpay_client.create_order(
        amount=plan.price_amount,
        currency=plan.currency,
        receipt=f"nm_{uuid.uuid4().hex[:12]}",
        notes={"user_id": str(user.id), "plan_code": plan.code},
    )

    db.add(
        Payment(
            user_id=user.id,
            plan_id=plan.id,
            razorpay_order_id=order["id"],
            amount=plan.price_amount,   # what we expect to be paid
            currency=plan.currency,
            status=PaymentStatus.CREATED.value,
            gateway_data={"order": {"id": order["id"], "receipt": order.get("receipt")}},
        )
    )
    db.flush()

    log_event(log, "payment_order_created", user_id=str(user.id), plan=plan.code, amount=plan.price_amount)

    return CreateOrderResponse(
        key_id=razorpay_client.public_key_id(),
        order_id=order["id"],
        amount=plan.price_amount,
        currency=plan.currency,
        description=f"{plan.name} plan, 1 month",
        plan_code=plan.code,
        plan_name=plan.name,
        prefill_contact=user.phone_number_normalized,
    )


# ==========================================================
# Fulfilment (shared by verify and the webhook)
# ==========================================================
def _lock_payment_by_order(db: Session, order_id: str) -> Payment | None:
    return db.scalar(
        select(Payment).where(Payment.razorpay_order_id == order_id).with_for_update()
    )


def _check_gateway_payment(payment: Payment, order_id: str, gateway: dict[str, Any]) -> None:
    """Razorpay's own record must agree with the order we created."""
    if (
        gateway.get("order_id") != order_id
        or int(gateway.get("amount", -1)) != payment.amount
        or str(gateway.get("currency", "")).upper() != payment.currency.upper()
    ):
        log_event(
            log,
            "payment_mismatch",
            level=40,
            payment_row=str(payment.id),
            expected_amount=payment.amount,
        )
        raise PaymentVerificationFailedError()


def _fulfill(
    db: Session,
    payment: Payment,
    gateway: dict[str, Any],
    *,
    signature: str | None,
    source: str,
) -> VerifyPaymentResponse:
    """
    Grants the plan once. The caller holds the row lock and has already
    checked ownership, signature (or webhook signature) and amounts.
    """
    user = db.get(User, payment.user_id)
    plan = db.get(Plan, payment.plan_id)

    if payment.fulfilled_at is not None:
        sub = activate_paid_plan.__globals__["get_active_subscription"](db, payment.user_id)
        return VerifyPaymentResponse(
            status=payment.status,
            already_processed=True,
            subscription=subscription_to_response(sub),
            credits_granted=0,
        )

    payment_id = gateway["id"]
    now = utcnow()

    payment.razorpay_payment_id = payment_id
    if signature:
        payment.razorpay_signature = signature
    payment.method = gateway.get("method")
    payment.status = PaymentStatus.PAID.value
    payment.verified_at = now
    payment.failure_reason = None
    payment.gateway_data = {
        **(payment.gateway_data or {}),
        "payment": {
            "id": payment_id,
            "status": gateway.get("status"),
            "method": gateway.get("method"),
            "captured_via": source,
        },
    }

    sub = activate_paid_plan(db, user, plan, payment_id=payment_id)
    payment.fulfilled_at = now
    db.flush()

    log_event(log, "payment_fulfilled", user_id=str(user.id), plan=plan.code, source=source)

    return VerifyPaymentResponse(
        status=payment.status,
        already_processed=False,
        subscription=subscription_to_response(sub),
        credits_granted=plan.monthly_limit,
    )


# ==========================================================
# Verify (called by the app after Razorpay Checkout)
# ==========================================================
def verify_payment(
    db: Session,
    user: User,
    order_id: str,
    payment_id: str,
    signature: str,
) -> VerifyPaymentResponse:
    payment = _lock_payment_by_order(db, order_id)

    # Someone else's order looks exactly like a missing one.
    if payment is None or payment.user_id != user.id:
        raise NotFoundError("We could not find that payment.")

    # Already done: a repeated request grants nothing and returns the same result.
    if payment.fulfilled_at is not None:
        return _fulfill(db, payment, {"id": payment.razorpay_payment_id}, signature=None, source="repeat")

    # 1. Signature, recomputed with our secret. Do NOT mark the payment failed
    #    on a bad signature: a forged request must not be able to spoil a real one.
    if not razorpay_client.verify_payment_signature(order_id, payment_id, signature):
        log_event(log, "payment_bad_signature", level=40, user_id=str(user.id))
        raise PaymentVerificationFailedError()

    # 2. A payment id can belong to only one order.
    clash = db.scalar(
        select(Payment.id).where(
            Payment.razorpay_payment_id == payment_id, Payment.id != payment.id
        )
    )
    if clash is not None or (
        payment.razorpay_payment_id and payment.razorpay_payment_id != payment_id
    ):
        raise PaymentVerificationFailedError()

    # 3. Razorpay's own record is the source of truth for status and amount.
    gateway = razorpay_client.fetch_payment(payment_id)
    _check_gateway_payment(payment, order_id, gateway)

    status = gateway.get("status")
    if status == "failed":
        mark_payment_failed(db, order_id, payment_id, gateway.get("error_description") or "Payment failed")
        db.commit()  # keep the FAILED status even though we raise next
        raise PaymentFailedError()
    if status != "captured":
        # Authorised but not captured yet. The signed webhook completes it.
        raise PaymentVerificationFailedError("Your payment is still being confirmed. Please check again shortly.")

    return _fulfill(db, payment, gateway, signature=signature, source="verify")


# ==========================================================
# Webhook paths (the webhook signature was already verified by the route)
# ==========================================================
def fulfill_captured_payment(db: Session, order_id: str, gateway: dict[str, Any]) -> bool:
    """
    payment.captured. Returns True if a plan was granted now, False if it was
    already done or the order is unknown to us.
    """
    payment = _lock_payment_by_order(db, order_id)
    if payment is None:
        log_event(log, "webhook_unknown_order", level=30)
        return False
    if payment.fulfilled_at is not None:
        return False
    if gateway.get("status") != "captured":
        return False

    _check_gateway_payment(payment, order_id, gateway)

    clash = db.scalar(
        select(Payment.id).where(
            Payment.razorpay_payment_id == gateway["id"], Payment.id != payment.id
        )
    )
    if clash is not None:
        raise PaymentVerificationFailedError()

    _fulfill(db, payment, gateway, signature=None, source="webhook")
    return True


def mark_payment_failed(
    db: Session,
    order_id: str,
    payment_id: str | None,
    reason: str | None,
) -> bool:
    """payment.failed. Never downgrades a payment that was already paid."""
    payment = _lock_payment_by_order(db, order_id)
    if payment is None or payment.fulfilled_at is not None:
        return False
    if payment.status == PaymentStatus.PAID.value:
        return False

    payment.status = PaymentStatus.FAILED.value
    payment.failure_reason = (reason or "Payment failed")[:500]
    db.flush()
    log_event(log, "payment_failed", user_id=str(payment.user_id))
    return True


# ==========================================================
# History
# ==========================================================
def _to_response(payment: Payment, plan: Plan | None) -> PaymentResponse:
    return PaymentResponse(
        id=payment.id,
        plan_code=plan.code if plan else None,
        plan_name=plan.name if plan else None,
        razorpay_order_id=payment.razorpay_order_id,
        razorpay_payment_id=payment.razorpay_payment_id,
        amount=payment.amount,
        price=round(payment.amount / 100, 2),
        currency=payment.currency,
        status=payment.status,
        method=payment.method,
        created_at=payment.created_at,
        verified_at=payment.verified_at,
    )


def list_payments(db: Session, user_id: uuid.UUID, params: PageParams) -> Page[PaymentResponse]:
    """The user's own payments, newest first. Abandoned (never paid) orders are hidden."""
    where = (
        Payment.user_id == user_id,
        Payment.status.in_([PaymentStatus.PAID.value, PaymentStatus.FAILED.value, PaymentStatus.REFUNDED.value]),
    )
    total = db.scalar(select(func.count()).select_from(Payment).where(*where)) or 0
    rows = db.execute(
        select(Payment, Plan)
        .join(Plan, Plan.id == Payment.plan_id)
        .where(*where)
        .order_by(Payment.created_at.desc())
        .offset(params.offset)
        .limit(params.limit)
    ).all()
    return Page.build([_to_response(p, plan) for p, plan in rows], total, params)
