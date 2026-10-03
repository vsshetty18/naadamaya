"""
NAADAMAYA dashboard schema.

Route:
    GET /dashboard  -> DashboardResponse

One call gives the app everything the Stage and Learn screens show about the
signed-in user, so it does not have to make five separate requests:

    profile        who they are
    subscription   which plan they are on
    usage          credits remaining and when they reset
    progress       totals, averages and streak
    recent         their latest completed analyses
    recommendations practice steps taken from their most recent report

Every value is read from the database by dashboard_service. Nothing is
hardcoded, and a new user simply gets empty lists and zeros.

Frontend mapping:
    Stage profile card    <- profile
    Stage statistics      <- progress.songs_practiced / songs_recorded
    Credits bar in nav    <- usage.remaining / usage.limit
"""

from pydantic import Field

from app.schemas.common import APIModel
from app.schemas.profile import ProfileResponse
from app.schemas.progress import AttemptEntry, ProgressOverview
from app.schemas.report import ReportRecommendation
from app.schemas.subscription import SubscriptionResponse
from app.schemas.usage import UsageResponse


class DashboardResponse(APIModel):
    profile: ProfileResponse
    subscription: SubscriptionResponse
    usage: UsageResponse
    progress: ProgressOverview

    recent: list[AttemptEntry] = Field(
        default_factory=list,
        description="Latest completed analyses, newest first (at most 5).",
    )
    recommendations: list[ReportRecommendation] = Field(
        default_factory=list,
        description="From the most recent completed report. Empty if there is none yet.",
    )
    latest_analysis_id: str | None = Field(
        default=None,
        description="Lets the app open the newest report directly.",
    )
