"""
NAADAMAYA subscription plans.

Plans live in the database, not in code, so prices and limits can change
without a deploy. The initial migration seeds FREE, GO and PRO using the
same wording as the frontend Stage and Credits screens.

Money is stored as an integer in the smallest currency unit (paise for INR),
exactly what Razorpay expects. This avoids floating-point rounding errors.
The price used for a payment ALWAYS comes from this table, never from the
frontend.
"""

from sqlalchemy import Boolean, Index, Integer, String, Text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, TimestampMixin, UUIDMixin


class Plan(UUIDMixin, TimestampMixin, Base):
    __tablename__ = "plans"

    # Stable machine name used in code and by the frontend: "FREE", "GO", "PRO".
    code: Mapped[str] = mapped_column(String(30), nullable=False, unique=True)
    name: Mapped[str] = mapped_column(String(60), nullable=False)
    tagline: Mapped[str | None] = mapped_column(String(160), nullable=True)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)

    # 19900 = Rs 199.00. Zero for the free plan.
    price_amount: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    currency: Mapped[str] = mapped_column(String(3), nullable=False, default="INR")
    billing_period: Mapped[str] = mapped_column(String(20), nullable=False, default="monthly")

    # Analyses (credits) granted per billing period.
    monthly_limit: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    # How many days one paid period lasts.
    period_days: Mapped[int] = mapped_column(Integer, nullable=False, default=30)

    # Display list for the plan card: [{"text": "...", "included": true}, ...]
    features: Mapped[list] = mapped_column(JSONB, nullable=False, default=list)
    # Machine-readable switches: {"advanced_insights": true, "priority_processing": false, ...}
    feature_flags: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict)

    # Optional link to a Razorpay Plan (only if recurring subscriptions are used).
    razorpay_plan_id: Mapped[str | None] = mapped_column(String(60), nullable=True)

    rank: Mapped[int] = mapped_column(Integer, nullable=False, default=0)  # order and upgrade direction
    is_popular: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)

    __table_args__ = (Index("ix_plans_is_active_rank", "is_active", "rank"),)
