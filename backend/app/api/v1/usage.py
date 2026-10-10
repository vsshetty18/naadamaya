"""
NAADAMAYA usage routes (credits).

    GET /usage            plan, limit, used, remaining, reset date, recent analyses
    GET /usage/history    the credit ledger, newest first (paginated)

Every number is computed by the backend from the credit ledger and the active
subscription. The frontend never calculates usage, so it cannot be tampered
with. Credits change only through the credit service (reserve, refund, grant),
never through a request to these routes.
"""

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.api.v1.deps import get_current_user
from app.core.database import get_db
from app.models.user import User
from app.schemas.common import COMMON_ERRORS, Page, PageParams
from app.schemas.usage import CreditTransactionResponse, UsageResponse
from app.services.credits.credit_service import get_usage, list_transactions

router = APIRouter(prefix="/usage", tags=["Usage"])


@router.get(
    "",
    response_model=UsageResponse,
    summary="My credits and monthly allowance",
    responses={401: COMMON_ERRORS[401]},
)
def usage(user: User = Depends(get_current_user), db: Session = Depends(get_db)) -> UsageResponse:
    return get_usage(db, user.id)


@router.get(
    "/history",
    response_model=Page[CreditTransactionResponse],
    summary="My credit history",
    responses={401: COMMON_ERRORS[401]},
)
def usage_history(
    params: PageParams = Depends(),
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> Page[CreditTransactionResponse]:
    return list_transactions(db, user.id, params)
