"""
NAADAMAYA credit ledger.

Every change to a user's analysis credits is one row here. The balance is
never stored as a loose number that can drift: it is derived from this
ledger (sum of `amount` for the current period). Grants are positive,
consumption is -1, refunds are +1.

Idempotency (the key requirement):
  - `idempotency_key` is UNIQUE. Examples:
        "grant:payment:<razorpay_payment_id>"   one grant per payment
        "grant:free:<user_id>:2026-10"          one free allowance per month
        "consume:analysis:<analysis_id>"        one charge per analysis
        "refund:analysis:<analysis_id>"         one refund per failed analysis
    Inserting the same key twice fails at the database, so a repeated
    request, a retried worker or a duplicate webhook can never double-charge
    or double-grant.
"""

import uuid
from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, Index, Integer, String, Text, func
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, UUIDMixin


class CreditTransaction(UUIDMixin, Base):
    __tablename__ = "credit_transactions"

    # RESTRICT: ledger rows are financial/audit records and outlive account deletion.
    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="RESTRICT"),
        nullable=False,
    )
    subscription_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("subscriptions.id", ondelete="SET NULL"),
        nullable=True,
    )

    # Positive = credits added, negative = credits used.
    amount: Mapped[int] = mapped_column(Integer, nullable=False)
    transaction_type: Mapped[str] = mapped_column(String(20), nullable=False)  # CreditTransactionType

    # What caused it: an analysis id, a payment id, "monthly_allowance", ...
    reference_id: Mapped[str | None] = mapped_column(String(100), nullable=True)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)

    idempotency_key: Mapped[str] = mapped_column(String(160), nullable=False, unique=True)

    # Start of the credit period this row belongs to (matches Subscription.period_start).
    period_start: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    __table_args__ = (
        Index("ix_credit_transactions_user_id_created_at", "user_id", "created_at"),
        Index("ix_credit_transactions_user_id_period", "user_id", "period_start"),
        Index("ix_credit_transactions_reference_id", "reference_id"),
    )
