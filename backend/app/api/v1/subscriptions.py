"""
NAADAMAYA subscription routes.

    GET /subscriptions/plans    the plans on offer (from the database)
    GET /subscriptions/me       my current subscription

There is NO route that activates or changes a plan. A paid plan is activated
only by the backend after a Razorpay payment is verified (POST /payments/verify)
or by the signed webhook. The frontend can never mark a plan as bought.

/plans is public so the pricing screen can load before sign-in. When a valid
access token is sent, the user's own plan is marked `is_current`.
"""

from fastapi import APIRouter, Depends
from fastapi.security import HTTPAuthorizationCredentials
from sqlalchemy.orm import Session

from app.api.v1.deps import bearer_scheme, get_current_user
from app.core.database import get_db
from app.core.exceptions import AppError
from app.models.user import User
from app.schemas.common import COMMON_ERRORS
from app.schemas.subscription import PlanResponse, SubscriptionResponse
from app.services.plans.plan_service import list_active_plans, plan_to_response
from app.services.subscriptions.subscription_service import (
    get_active_subscription,
    subscription_to_response,
)

router = APIRouter(prefix="/subscriptions", tags=["Subscriptions"])


@router.get("/plans", response_model=list[PlanResponse], summary="Available plans")
def plans(
    credentials: HTTPAuthorizationCredentials | None = Depends(bearer_scheme),
    db: Session = Depends(get_db),
) -> list[PlanResponse]:
    current_code = None
    if credentials is not None:
        try:
            user = get_current_user(credentials, db)
            current_code = get_active_subscription(db, user.id).plan.code
        except AppError:
            current_code = None   # a bad or expired token just means "not marked"
    return [plan_to_response(p, current_code) for p in list_active_plans(db)]


@router.get(
    "/me",
    response_model=SubscriptionResponse,
    summary="My subscription",
    responses={401: COMMON_ERRORS[401]},
)
def my_subscription(user: User = Depends(get_current_user), db: Session = Depends(get_db)) -> SubscriptionResponse:
    return subscription_to_response(get_active_subscription(db, user.id))
