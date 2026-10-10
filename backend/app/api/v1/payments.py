"""
NAADAMAYA payment routes (Razorpay).

    POST /payments/create-order   start a purchase: the backend creates the order
    POST /payments/verify         verify what Razorpay Checkout returned
    GET  /payments                my payments (paginated)

Flow:
  1. App sends only a plan code. The price is read from the plans table.
  2. Backend creates a Razorpay order and returns the order id and the PUBLIC
     key id (the secret never leaves the server).
  3. App opens Razorpay Checkout.
  4. App sends the three values Razorpay returned to /verify.
  5. Backend recomputes the signature, asks Razorpay for the payment, checks
     amount, currency and ownership, and only then activates the plan.

Verifying the same payment twice is safe (already_processed=true, no second grant).

Failed verifications that must survive the error rollback are committed
inside payment_service before raising.
"""

import uuid

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.api.v1.deps import get_current_user
from app.core.database import get_db
from app.models.user import User
from app.schemas.common import COMMON_ERRORS, Page, PageParams
from app.schemas.payment import (
    CreateOrderRequest,
    CreateOrderResponse,
    PaymentResponse,
    VerifyPaymentRequest,
    VerifyPaymentResponse,
)
from app.services.credits.credit_service import get_remaining
from app.services.payments.payment_service import create_order, list_payments, verify_payment

router = APIRouter(prefix="/payments", tags=["Payments"])


@router.post(
    "/create-order",
    response_model=CreateOrderResponse,
    summary="Create a Razorpay order for a plan",
    responses={401: COMMON_ERRORS[401], 404: COMMON_ERRORS[404], 429: COMMON_ERRORS[429]},
)
def create_order_route(
    payload: CreateOrderRequest,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> CreateOrderResponse:
    return create_order(db, user, plan_code=payload.plan_code, plan_id=payload.plan_id)


@router.post(
    "/verify",
    response_model=VerifyPaymentResponse,
    summary="Verify a payment and activate the plan",
    description="The response is the only truth about the payment. Refresh /usage and /subscriptions/me afterwards.",
    responses={400: {"description": "PAYMENT_VERIFICATION_FAILED"}, 401: COMMON_ERRORS[401], 404: COMMON_ERRORS[404]},
)
def verify_route(
    payload: VerifyPaymentRequest,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> VerifyPaymentResponse:
    result = verify_payment(
        db,
        user,
        payload.razorpay_order_id,
        payload.razorpay_payment_id,
        payload.razorpay_signature,
    )
    result.credits_remaining = get_remaining(db, user.id)
    return result


@router.get(
    "",
    response_model=Page[PaymentResponse],
    summary="My payments",
    responses={401: COMMON_ERRORS[401]},
)
def my_payments(
    params: PageParams = Depends(),
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> Page[PaymentResponse]:
    return list_payments(db, user.id, params)
