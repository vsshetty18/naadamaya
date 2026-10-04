"""
NAADAMAYA subscriptions.

    sub = get_active_subscription(db, user_id)     # always returns one
    ensure_free_subscription(db, user)             # called at sign-up
    sub = activate_paid_plan(db, user, plan, payment_id=...)   # after a VERIFIED payment
    downgrade_to_free(db, user_id)                 # paid plan cancelled or halted

Rules:
  - Every user has exactly ONE ACTIVE subscription (the database enforces it
    with a partial unique index). New users start on FREE.
  - Paid plans are activated ONLY by the payment service after the Razorpay
    signature and amount are verified, or by the signed webhook. Nothing in
    the frontend can call this.
  - Credits are granted through the ledger with an idempotency key, so the
    same payment applied twice (a repeated verify call, a duplicate webhook)
    grants nothing the second time.
  - FREE credits renew every `period_days` automatically. A paid plan that
    passes its end_date expires and the user falls back to FREE.
  - A per-user advisory lock serialises these changes, so two simultaneous
    requests cannot both roll the period over or both activate a plan.

Credit period: a ledger row belongs to a period through period_start, which
equals Subscription.period_start. Usage is counted from the current period.

Simplifications (say if you want different rules):
  - Unused credits are NOT carried over when a period ends or a plan changes.
  - Buying the plan you are already on adds one more period to its end date and
    starts a fresh credit period.
"""

import math
import uuid
from datetime import datetime, timedelta

from sqlalchemy import select, text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.core.logging import get_logger, log_event
from app.core.security import utcnow
from app.models.credit_transaction import CreditTransaction
from app.models.enums import CreditTransactionType, SubscriptionStatus
from app.models.plan import Plan
from app.models.subscription import Subscription
from app.models.user import User
from app.schemas.subscription import SubscriptionResponse
from app.services.plans.plan_service import FREE_PLAN_CODE, get_free_plan, plan_to_response

log = get_logger("naadamaya.subscriptions")


# ==========================================================
# Internals
# ==========================================================
def _lock_user(db: Session, user_id: uuid.UUID) -> None:
    """Serialises subscription changes for one user until the transaction ends."""
    db.execute(text("SELECT pg_advisory_xact_lock(hashtext(:key))"), {"key": f"sub:{user_id}"})


def grant_credits(
    db: Session,
    user_id: uuid.UUID,
    sub: Subscription,
    amount: int,
    *,
    idempotency_key: str,
    reference_id: str | None,
    description: str,
) -> bool:
    """
    Adds credits to the ledger. Returns False (and changes nothing) if this
    idempotency key was already used. Safe to call twice with the same key.
    """
    if amount <= 0:
        return False
    try:
        with db.begin_nested():  # a duplicate key only undoes this block
            db.add(
                CreditTransaction(
                    user_id=user_id,
                    subscription_id=sub.id,
                    amount=amount,
                    transaction_type=CreditTransactionType.GRANT.value,
                    reference_id=reference_id,
                    description=description,
                    idempotency_key=idempotency_key,
                    period_start=sub.period_start,
                )
            )
            db.flush()
        return True
    except IntegrityError:
        return False


def _new_subscription(
    db: Session,
    user_id: uuid.UUID,
    plan: Plan,
    *,
    start: datetime,
    end_date: datetime | None,
) -> Subscription:
    sub = Subscription(
        user_id=user_id,
        plan_id=plan.id,
        plan=plan,
        status=SubscriptionStatus.ACTIVE.value,
        start_date=start,
        end_date=end_date,
        renewal_date=end_date,
        credits_per_period=plan.monthly_limit,
        period_start=start,
        period_end=start + timedelta(days=plan.period_days),
    )
    db.add(sub)
    db.flush()
    return sub


def _create_free(db: Session, user_id: uuid.UUID) -> Subscription:
    plan = get_free_plan(db)
    now = utcnow()
    sub = _new_subscription(db, user_id, plan, start=now, end_date=None)
    grant_credits(
        db,
        user_id,
        sub,
        plan.monthly_limit,
        idempotency_key=f"grant:free:{user_id}:{now.date().isoformat()}",
        reference_id="monthly_allowance",
        description="Free monthly analyses",
    )
    log_event(log, "free_subscription_created", user_id=str(user_id))
    return sub


def _select_active(db: Session, user_id: uuid.UUID) -> Subscription | None:
    return db.scalar(
        select(Subscription)
        .where(
            Subscription.user_id == user_id,
            Subscription.status == SubscriptionStatus.ACTIVE.value,
        )
        .order_by(Subscription.created_at.desc())
        .limit(1)
    )


def _roll_free_period(db: Session, sub: Subscription, now: datetime) -> None:
    """Starts the next monthly credit period of the FREE plan."""
    length = timedelta(days=sub.plan.period_days)
    steps = max(1, math.floor((now - sub.period_start) / length))
    sub.period_start = sub.period_start + length * steps
    sub.period_end = sub.period_start + length
    sub.credits_per_period = sub.plan.monthly_limit
    db.flush()
    grant_credits(
        db,
        sub.user_id,
        sub,
        sub.plan.monthly_limit,
        idempotency_key=f"grant:free:{sub.user_id}:{sub.period_start.date().isoformat()}",
        reference_id="monthly_allowance",
        description="Free monthly analyses",
    )
    log_event(log, "free_period_renewed", user_id=str(sub.user_id))


# ==========================================================
# Reading (with automatic renewal and expiry)
# ==========================================================
def get_active_subscription(db: Session, user_id: uuid.UUID) -> Subscription:
    """
    The user's current subscription. Always returns one: it creates the FREE
    plan if missing, renews the FREE month when due, and expires a paid plan
    that passed its end date (falling back to FREE).
    """
    sub = _select_active(db, user_id)
    now = utcnow()

    needs_change = (
        sub is None
        or (sub.plan.code == FREE_PLAN_CODE and sub.period_end is not None and now >= sub.period_end)
        or (sub.plan.code != FREE_PLAN_CODE and sub.end_date is not None and now >= sub.end_date)
    )
    if not needs_change:
        return sub

    _lock_user(db, user_id)
    sub = _select_active(db, user_id)  # re-check: another request may have done the work

    if sub is None:
        return _create_free(db, user_id)

    if sub.plan.code == FREE_PLAN_CODE:
        if sub.period_end is not None and now >= sub.period_end:
            _roll_free_period(db, sub, now)
        return sub

    if sub.end_date is not None and now >= sub.end_date:
        sub.status = SubscriptionStatus.EXPIRED.value
        db.flush()  # the old row must stop being ACTIVE before the new one is added
        log_event(log, "subscription_expired", user_id=str(user_id), plan=sub.plan.code)
        return _create_free(db, user_id)

    return sub


def ensure_free_subscription(db: Session, user: User) -> Subscription:
    """Called at sign-up. Safe to call again: it returns the existing subscription."""
    _lock_user(db, user.id)
    return _select_active(db, user.id) or _create_free(db, user.id)


# ==========================================================
# Changing plan
# ==========================================================
def activate_paid_plan(
    db: Session,
    user: User,
    plan: Plan,
    *,
    payment_id: str,
) -> Subscription:
    """
    Puts the user on a paid plan and grants its credits. Call ONLY after the
    payment has been verified by the backend. Idempotent per payment_id.
    """
    _lock_user(db, user.id)
    grant_key = f"grant:payment:{payment_id}"

    already = db.scalar(
        select(CreditTransaction.id).where(CreditTransaction.idempotency_key == grant_key)
    )
    if already is not None:
        return get_active_subscription(db, user.id)  # this payment was already applied

    now = utcnow()
    current = _select_active(db, user.id)
    period = timedelta(days=plan.period_days)

    end_date = now + period
    if current is not None:
        if current.plan_id == plan.id and current.end_date and current.end_date > now:
            end_date = current.end_date + period  # same plan: add another period
        current.status = (
            SubscriptionStatus.EXPIRED.value
            if current.plan.code == FREE_PLAN_CODE
            else SubscriptionStatus.CANCELLED.value
        )
        if current.status == SubscriptionStatus.CANCELLED.value:
            current.cancelled_at = now
        db.flush()  # free the "one active subscription" slot

    sub = _new_subscription(db, user.id, plan, start=now, end_date=end_date)
    grant_credits(
        db,
        user.id,
        sub,
        plan.monthly_limit,
        idempotency_key=grant_key,
        reference_id=payment_id,
        description=f"{plan.name} plan credits",
    )
    log_event(log, "subscription_activated", user_id=str(user.id), plan=plan.code)
    return sub


def downgrade_to_free(db: Session, user_id: uuid.UUID, *, reason: str = "cancelled") -> Subscription:
    """A paid plan was cancelled or halted: the user returns to FREE."""
    _lock_user(db, user_id)
    current = _select_active(db, user_id)
    if current is not None and current.plan.code == FREE_PLAN_CODE:
        return current
    if current is not None:
        current.status = SubscriptionStatus.CANCELLED.value
        current.cancelled_at = utcnow()
        db.flush()
    log_event(log, "subscription_downgraded", user_id=str(user_id), reason=reason)
    return _create_free(db, user_id)


# ==========================================================
# Response
# ==========================================================
def subscription_to_response(sub: Subscription) -> SubscriptionResponse:
    return SubscriptionResponse(
        id=sub.id,
        plan=plan_to_response(sub.plan, current_plan_code=sub.plan.code),
        status=sub.status,
        start_date=sub.start_date,
        end_date=sub.end_date,
        renewal_date=sub.renewal_date,
        cancelled_at=sub.cancelled_at,
        period_start=sub.period_start,
        period_end=sub.period_end,
        credits_per_period=sub.credits_per_period,
        features={k: bool(v) for k, v in (sub.plan.feature_flags or {}).items()},
    )
