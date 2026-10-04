"""
NAADAMAYA credits.

    usage = get_usage(db, user_id)                       # GET /usage
    reserve_credit(db, user_id, analysis_id)             # when an analysis is queued
    refund_credit(db, user_id, analysis_id)              # when it fails on OUR side
    page = list_transactions(db, user_id, params)        # GET /usage/history

The balance is never a stored number. It is derived from the ledger
(credit_transactions) for the CURRENT period:

    remaining = sum(amount) of rows with period_start == subscription.period_start

Grants are positive, consumption is -1, refunds are +1. The frontend never
calculates usage.

Double-spend protection:
  - A per-user advisory lock serialises reserve and refund, so two simultaneous
    analyses cannot both spend the last credit.
  - The ledger's unique idempotency key makes each charge and each refund
    happen at most once per analysis:
        consume:analysis:<analysis_id>
        refund:analysis:<analysis_id>
    A retried request or worker cannot charge or refund twice.

Credits are only reserved when an analysis is queued, and refunded when it
fails because of a server problem. A refund is booked in the SAME period as
the charge it reverses, even if the period rolled over in between.
"""

import uuid
from datetime import datetime

from sqlalchemy import func, select, text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.core.exceptions import UsageLimitReachedError
from app.core.logging import get_logger, log_event
from app.models.analysis import Analysis
from app.models.credit_transaction import CreditTransaction
from app.models.enums import CreditTransactionType
from app.schemas.common import Page, PageParams
from app.schemas.usage import CreditTransactionResponse, RecentUsage, UsageResponse
from app.services.subscriptions.subscription_service import get_active_subscription

log = get_logger("naadamaya.credits")


def _lock_credits(db: Session, user_id: uuid.UUID) -> None:
    db.execute(text("SELECT pg_advisory_xact_lock(hashtext(:key))"), {"key": f"credits:{user_id}"})


def _balance(db: Session, user_id: uuid.UUID, period_start: datetime) -> int:
    total = db.scalar(
        select(func.coalesce(func.sum(CreditTransaction.amount), 0)).where(
            CreditTransaction.user_id == user_id,
            CreditTransaction.period_start == period_start,
        )
    )
    return int(total or 0)


def get_remaining(db: Session, user_id: uuid.UUID) -> int:
    sub = get_active_subscription(db, user_id)
    return max(0, _balance(db, user_id, sub.period_start))


# ==========================================================
# Reserve and refund
# ==========================================================
def reserve_credit(db: Session, user_id: uuid.UUID, analysis_id: uuid.UUID) -> int:
    """
    Spends one credit for this analysis. Returns credits remaining.
    Raises UsageLimitReachedError when none are left. Idempotent per analysis.
    """
    sub = get_active_subscription(db, user_id)
    _lock_credits(db, user_id)

    key = f"consume:analysis:{analysis_id}"
    existing = db.scalar(select(CreditTransaction.id).where(CreditTransaction.idempotency_key == key))
    if existing is not None:
        return max(0, _balance(db, user_id, sub.period_start))

    remaining = _balance(db, user_id, sub.period_start)
    if remaining < 1:
        raise UsageLimitReachedError("Monthly analysis limit reached.")

    try:
        with db.begin_nested():
            db.add(
                CreditTransaction(
                    user_id=user_id,
                    subscription_id=sub.id,
                    amount=-1,
                    transaction_type=CreditTransactionType.CONSUME.value,
                    reference_id=str(analysis_id),
                    description="Analysis",
                    idempotency_key=key,
                    period_start=sub.period_start,
                )
            )
            db.flush()
    except IntegrityError:
        pass  # another request already charged this analysis

    log_event(log, "credit_consumed", user_id=str(user_id), analysis_id=str(analysis_id))
    return max(0, _balance(db, user_id, sub.period_start))


def refund_credit(db: Session, user_id: uuid.UUID, analysis_id: uuid.UUID) -> bool:
    """
    Gives back the credit for an analysis that failed on our side. Returns True
    if a refund was booked now. Safe to call twice.
    """
    _lock_credits(db, user_id)

    charge = db.scalar(
        select(CreditTransaction).where(
            CreditTransaction.idempotency_key == f"consume:analysis:{analysis_id}"
        )
    )
    if charge is None:
        return False  # nothing was charged, so nothing to refund

    try:
        with db.begin_nested():
            db.add(
                CreditTransaction(
                    user_id=user_id,
                    subscription_id=charge.subscription_id,
                    amount=1,
                    transaction_type=CreditTransactionType.REFUND.value,
                    reference_id=str(analysis_id),
                    description="Analysis failed, credit returned",
                    idempotency_key=f"refund:analysis:{analysis_id}",
                    period_start=charge.period_start,  # same period as the charge
                )
            )
            db.flush()
    except IntegrityError:
        return False

    log_event(log, "credit_refunded", user_id=str(user_id), analysis_id=str(analysis_id))
    return True


# ==========================================================
# Reading
# ==========================================================
def get_usage(db: Session, user_id: uuid.UUID) -> UsageResponse:
    sub = get_active_subscription(db, user_id)
    remaining = max(0, _balance(db, user_id, sub.period_start))
    limit = sub.credits_per_period
    used = max(0, limit - remaining)

    rows = db.execute(
        select(CreditTransaction, Analysis)
        .outerjoin(Analysis, Analysis.id == func.cast(CreditTransaction.reference_id, Analysis.id.type))
        .where(
            CreditTransaction.user_id == user_id,
            CreditTransaction.transaction_type == CreditTransactionType.CONSUME.value,
        )
        .order_by(CreditTransaction.created_at.desc())
        .limit(6)
    ).all()

    recent = []
    for tx, analysis in rows:
        title = None
        if analysis is not None and not analysis.is_deleted and analysis.song is not None:
            title = analysis.song.title
        recent.append(
            RecentUsage(
                analysis_id=analysis.id if analysis is not None else None,
                title=title,
                credits=abs(tx.amount),
                date=tx.created_at,
            )
        )

    return UsageResponse(
        plan_code=sub.plan.code,
        plan_name=sub.plan.name,
        subscription_status=sub.status,
        limit=limit,
        used=used,
        remaining=remaining,
        percent_remaining=round(100.0 * remaining / limit, 1) if limit > 0 else 0.0,
        period_start=sub.period_start,
        reset_at=sub.period_end if sub.plan.code == "FREE" else (sub.end_date or sub.period_end),
        can_analyze=remaining > 0,
        upgrade_required=remaining <= 0,
        recent=recent,
    )


def list_transactions(
    db: Session, user_id: uuid.UUID, params: PageParams
) -> Page[CreditTransactionResponse]:
    total = db.scalar(
        select(func.count()).select_from(CreditTransaction).where(CreditTransaction.user_id == user_id)
    ) or 0
    rows = db.scalars(
        select(CreditTransaction)
        .where(CreditTransaction.user_id == user_id)
        .order_by(CreditTransaction.created_at.desc())
        .offset(params.offset)
        .limit(params.limit)
    ).all()
    return Page.build([CreditTransactionResponse.model_validate(r) for r in rows], total, params)
