"""
NAADAMAYA usage and credit schemas.

Routes:
    GET /usage            -> UsageResponse        (balance, limit, reset date)
    GET /usage/history    -> Page[CreditTransactionResponse]

Every number comes from the backend credit ledger (credit_transactions) and
the active subscription. The frontend never calculates usage itself, so it
cannot be tampered with.

  limit      credits granted for the current period (from the subscription)
  used       credits consumed this period, net of refunds
  remaining  limit - used, never below zero
  reset_at   when the current period ends and credits renew

The frontend Credits screen maps these like so:
    credits.total     <- limit
    credits.remaining <- remaining
    credits.plan      <- plan_code (lower-cased by the adapter)
"""

import uuid
from datetime import datetime

from pydantic import Field

from app.schemas.common import APIModel


class RecentUsage(APIModel):
    """One row of 'Recent Analysis' on the Credits screen."""

    analysis_id: uuid.UUID | None = None
    title: str | None = Field(default=None, description="Song title, if the analysis still exists.")
    credits: int = Field(default=1, description="Credits used (1 per analysis).")
    date: datetime


class UsageResponse(APIModel):
    plan_code: str = Field(examples=["FREE"])
    plan_name: str = Field(examples=["Free"])
    subscription_status: str = Field(examples=["ACTIVE"])

    limit: int = Field(ge=0, examples=[10])
    used: int = Field(ge=0, examples=[4])
    remaining: int = Field(ge=0, examples=[6])
    percent_remaining: float = Field(ge=0, le=100, examples=[60.0])

    period_start: datetime
    reset_at: datetime | None = Field(
        default=None, description="When credits renew. Null only if the plan has no period end."
    )

    can_analyze: bool = Field(description="False when remaining is 0.")
    upgrade_required: bool = Field(
        description="True when no credits remain and a plan change would help."
    )

    recent: list[RecentUsage] = Field(default_factory=list)


class CreditTransactionResponse(APIModel):
    id: uuid.UUID
    amount: int = Field(description="Positive = credits added, negative = credits used.", examples=[-1])
    transaction_type: str = Field(examples=["CONSUME"], description="GRANT | CONSUME | REFUND | ADJUSTMENT")
    description: str | None = None
    reference_id: str | None = Field(default=None, description="Analysis or payment id that caused it.")
    created_at: datetime
