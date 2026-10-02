"""
NAADAMAYA subscriptions.

A subscription says which plan a user is on and for which period. It is
created or extended ONLY by the backend after a payment is verified (or by
the webhook). The frontend can never activate one.

Credits are granted per period. `credits_granted_for_period` and the
`period_key` on CreditTransaction make that grant idempotent: the same
payment or webhook delivered twice cannot add credits twice.

Every user always has exactly one ACTIVE subscription row. New users get the
FREE plan (created at sign-up). When a paid period ends without renewal, the
usage service falls back to FREE.
"""

import uuid
from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, Index, Integer, String, text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base, TimestampMixin, UUIDMixin
from app.models.enums import SubscriptionStatus


class Subscription(UUIDMixin, TimestampMixin, Base):
    __tablename__ = "subscriptions"

    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
    )
    plan_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("plans.id", ondelete="RESTRICT"),
        nullable=False,
    )

    status: Mapped[str] = mapped_column(
        String(20), nullable=False, default=SubscriptionStatus.ACTIVE.value
    )

    start_date: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    # None for the FREE plan (it does not expire). Paid plans have an end date.
    end_date: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    renewal_date: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    cancelled_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    # Allowance for the current period, copied from the plan at grant time so a
    # later plan edit never changes a period that was already paid for.
    credits_per_period: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    # Start of the current credit period. Usage is counted from here.
    period_start: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    period_end: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    # Only used if Razorpay recurring subscriptions are adopted later.
    razorpay_subscription_id: Mapped[str | None] = mapped_column(String(60), nullable=True, unique=True)

    plan: Mapped["Plan"] = relationship(lazy="joined")  # noqa: F821

    __table_args__ = (
        Index("ix_subscriptions_user_id_status", "user_id", "status"),
        Index("ix_subscriptions_end_date", "end_date"),
        # At most ONE active subscription per user, enforced by the database.
        Index(
            "uq_subscriptions_one_active_per_user",
            "user_id",
            unique=True,
            postgresql_where=text("status = 'ACTIVE'"),
        ),
    )
