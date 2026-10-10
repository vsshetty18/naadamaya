"""
NAADAMAYA dashboard route.

    GET /dashboard    everything the Stage and Learn screens need in one call:
                      profile, subscription, usage, progress, recent attempts,
                      and practice recommendations from the latest report.

All values come from the database through the same services as the dedicated
endpoints, so they can never disagree. A new user gets empty lists and zeros.
"""

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.api.v1.deps import get_current_user
from app.core.database import get_db
from app.models.user import User
from app.schemas.common import COMMON_ERRORS
from app.schemas.dashboard import DashboardResponse
from app.services.dashboard.dashboard_service import get_dashboard

router = APIRouter(prefix="/dashboard", tags=["Dashboard"])


@router.get(
    "",
    response_model=DashboardResponse,
    summary="My dashboard",
    responses={401: COMMON_ERRORS[401]},
)
def dashboard(user: User = Depends(get_current_user), db: Session = Depends(get_db)) -> DashboardResponse:
    return get_dashboard(db, user)
