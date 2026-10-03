"""
NAADAMAYA subscription and plan schemas.

Routes:
    GET /subscriptions/plans  -> list[PlanResponse]          (public, from the database)
    GET /subscriptions/me     -> SubscriptionResponse        (the signed-in user's plan)

There is NO request schema that can activate or change a plan. A paid plan is
activated only by the backend after a Razorpay payment is verified (or by the
signed webhook). The frontend can never mark a plan as bought.

Money is sent two ways so the frontend never does arithmetic on paise:
    price_amount   integer in the smallest unit (19900 = Rs 199.00)
    price          the same value as a plain number in rupees (199.0)

The frontend Stage and Credits cards map these like so:
    plan.id            <- code (lower-cased by the adapter: "free", "go", "pro")
    plan.price         <- price
    plan.credits       <- monthly_limit
    plan.popular       <- is_popular
    plan.features      <- features  [{text, included}]
"""

import uuid
from datetime import datetime

from pydantic import Field

from app.schemas.common import APIModel


class PlanFeature(APIModel):
    text: str = Field(examples=["30 analysis credits"])
    included: bool = True


class PlanResponse(APIModel):
    id: uuid.UUID
    code: str = Field(examples=["GO"], description="Stable name: FREE, GO, PRO.")
    name: str = Field(examples=["Go"])
    tagline: str | None = None
    description: str | None = None

    price_amount: int = Field(ge=0, examples=[19900], description="Smallest currency unit (paise).")
    price: float = Field(ge=0, examples=[199.0], description="Same price in rupees.")
    currency: str = Field(examples=["INR"])
    billing_period: str = Field(examples=["monthly"])

    monthly_limit: int = Field(ge=0, examples=[30], description="Analyses per period.")
    period_days: int = Field(ge=1, examples=[30])

    features: list[PlanFeature] = Field(default_factory=list)
    feature_flags: dict[str, bool] = Field(default_factory=dict)

    rank: int = Field(description="Order, and the direction of an upgrade.")
    is_popular: bool = False

    is_current: bool = Field(default=False, description="True for the signed-in user's plan.")


class SubscriptionResponse(APIModel):
    id: uuid.UUID
    plan: PlanResponse
    status: str = Field(examples=["ACTIVE"])

    start_date: datetime
    end_date: datetime | None = Field(default=None, description="Null for the free plan.")
    renewal_date: datetime | None = None
    cancelled_at: datetime | None = None

    period_start: datetime
    period_end: datetime | None = None
    credits_per_period: int

    features: dict[str, bool] = Field(
        default_factory=dict, description="Feature flags the backend enforces for this plan."
    )
