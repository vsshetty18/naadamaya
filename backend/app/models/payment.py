"""
NAADAMAYA payments (Razorpay).

The frontend is NEVER the source of truth for payment status. A row starts as
CREATED when the backend creates a Razorpay order, and becomes PAID only after
the backend verifies the Razorpay signature and amount (or the signed webhook
confirms it).

Idempotency:
  - razorpay_order_id is UNIQUE: one order, one row.
  - razorpay_payment_id is UNIQUE: the same payment can never be recorded twice.
  - `fulfilled_at` is set exactly once, inside the same transaction that grants
    the plan and credits. If it is already set, a repeated verify request or a
    duplicate webhook does nothing.

Money is stored in paise (smallest unit) as integers.
"""

import uuid
from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, Index, Integer, String, Text
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, TimestampMixin, UUIDMixin
from app.models.enums import PaymentStatus


class Payment(UUIDMixin, TimestampMixin, Base):
    __tablename__ = "payments"

    # RESTRICT: financial records must outlive an account deletion request
    # (legal and accounting retention). Account deletion anonymises the user
    # row instead of removing it.
    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="RESTRICT"),
        nullable=False,
    )
    plan_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("plans.id", ondelete="RESTRICT"),
        nullable=False,
    )

    razorpay_order_id: Mapped[str] = mapped_column(String(60), nullable=False, unique=True)
    razorpay_payment_id: Mapped[str | None] = mapped_column(String(60), nullable=True, unique=True)
    razorpay_signature: Mapped[str | None] = mapped_column(String(128), nullable=True)

    # Expected amount, copied from the plan when the order was created.
    amount: Mapped[int] = mapped_column(Integer, nullable=False)
    currency: Mapped[str] = mapped_column(String(3), nullable=False, default="INR")

    status: Mapped[str] = mapped_column(String(20), nullable=False, default=PaymentStatus.CREATED.value)
    method: Mapped[str | None] = mapped_column(String(30), nullable=True)  # card, upi, ...
    failure_reason: Mapped[str | None] = mapped_column(Text, nullable=True)

    verified_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    fulfilled_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    # Raw order/payment details from Razorpay for support and audits (no secrets).
    gateway_data: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict)

    __table_args__ = (
        Index("ix_payments_user_id_created_at", "user_id", "created_at"),
        Index("ix_payments_status", "status"),
    )
