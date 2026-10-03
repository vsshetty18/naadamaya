"""
NAADAMAYA payment schemas (Razorpay).

Routes:
    POST /payments/create-order  CreateOrderRequest  -> CreateOrderResponse
    POST /payments/verify        VerifyPaymentRequest -> VerifyPaymentResponse
    GET  /payments               (paginated)          -> Page[PaymentResponse]
    POST /webhooks/razorpay      (raw signed body, no schema; see webhooks API)

Security rules built into the shapes:
  - CreateOrderRequest takes ONLY a plan. There is no amount or currency field,
    so the frontend cannot choose a price. The amount always comes from the
    plans table.
  - VerifyPaymentRequest carries the three values Razorpay Checkout returns.
    The backend recomputes the signature with the secret key, checks the
    amount, currency and ownership, and only then activates the plan. The
    response is the truth; the frontend never decides a payment succeeded.
  - Only the public key id (key_id) is ever sent to the frontend.
    RAZORPAY_KEY_SECRET and RAZORPAY_WEBHOOK_SECRET never appear in a response.

Idempotency: verifying the same payment twice returns the same result and
grants nothing twice (`already_processed` is true on the repeat).
"""

import uuid
from datetime import datetime

from pydantic import Field

from app.schemas.common import APIModel
from app.schemas.subscription import SubscriptionResponse


# ==========================================================
# Create order
# ==========================================================
class CreateOrderRequest(APIModel):
    # Either one identifies the plan. The code ("GO", "PRO") is what the app uses.
    plan_code: str | None = Field(default=None, max_length=30, examples=["PRO"])
    plan_id: uuid.UUID | None = None


class CreateOrderResponse(APIModel):
    success: bool = True
    # Values Razorpay Checkout needs:
    key_id: str = Field(description="Public Razorpay key id. Safe for the frontend.")
    order_id: str = Field(examples=["order_Nxxxxxxxxxxxxx"])
    amount: int = Field(description="Paise, taken from the plan.", examples=[44900])
    currency: str = Field(examples=["INR"])
    # Shown in the Checkout window.
    name: str = "NAADAMAYA"
    description: str = Field(examples=["Pro plan, 1 month"])
    plan_code: str
    plan_name: str
    prefill_contact: str | None = Field(
        default=None, description="The user's own phone number, to pre-fill Checkout."
    )


# ==========================================================
# Verify payment
# ==========================================================
class VerifyPaymentRequest(APIModel):
    razorpay_order_id: str = Field(min_length=5, max_length=60)
    razorpay_payment_id: str = Field(min_length=5, max_length=60)
    razorpay_signature: str = Field(min_length=10, max_length=128)


class VerifyPaymentResponse(APIModel):
    success: bool = True
    status: str = Field(examples=["PAID"], description="Payment status as the backend verified it.")
    already_processed: bool = Field(
        default=False, description="True when this payment had already been fulfilled."
    )
    subscription: SubscriptionResponse | None = Field(
        default=None, description="The updated subscription. The app should refresh usage too."
    )
    credits_granted: int = Field(default=0, ge=0)
    credits_remaining: int | None = None


# ==========================================================
# History
# ==========================================================
class PaymentResponse(APIModel):
    id: uuid.UUID
    plan_code: str | None = None
    plan_name: str | None = None
    razorpay_order_id: str
    razorpay_payment_id: str | None = None
    amount: int = Field(description="Paise.")
    price: float = Field(description="Rupees.")
    currency: str
    status: str = Field(examples=["PAID"], description="CREATED | PAID | FAILED | REFUNDED")
    method: str | None = None
    created_at: datetime
    verified_at: datetime | None = None
