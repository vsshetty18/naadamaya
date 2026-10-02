"""
NAADAMAYA webhook events (Razorpay).

Every webhook delivery is recorded here BEFORE it is processed. The unique
`event_id` makes processing idempotent: Razorpay retries deliveries, and a
second delivery of the same event hits the unique constraint and is ignored.

Only webhooks whose signature has been verified are processed. The raw body is
kept (without any secrets) so failed events can be inspected and replayed.

Status flow:
    RECEIVED -> PROCESSED
             -> FAILED  (error saved; can be retried)
             -> IGNORED (event type we do not handle)
"""

from datetime import datetime

from sqlalchemy import DateTime, Index, Integer, String, Text, func
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, UUIDMixin


class WebhookEvent(UUIDMixin, Base):
    __tablename__ = "webhook_events"

    provider: Mapped[str] = mapped_column(String(20), nullable=False, default="razorpay")
    # Razorpay's unique id for the delivery (X-Razorpay-Event-Id header).
    event_id: Mapped[str] = mapped_column(String(100), nullable=False, unique=True)
    event_type: Mapped[str] = mapped_column(String(60), nullable=False)  # e.g. "payment.captured"

    status: Mapped[str] = mapped_column(String(20), nullable=False, default="RECEIVED")
    attempts: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    error: Mapped[str | None] = mapped_column(Text, nullable=True)

    payload: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict)

    received_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    processed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    __table_args__ = (
        Index("ix_webhook_events_status", "status"),
        Index("ix_webhook_events_event_type_received", "event_type", "received_at"),
    )
