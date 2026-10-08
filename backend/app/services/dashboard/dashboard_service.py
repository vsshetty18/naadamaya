"""
NAADAMAYA dashboard.

    data = get_dashboard(db, user)       # GET /dashboard

One call for the Stage and Learn screens. It reuses the existing services, so
every number is the same as on the dedicated endpoints:

    profile        profile_service.get_profile_response
    subscription   subscription_service.get_active_subscription
    usage          credit_service.get_usage
    progress       progress_service.get_overview
    recent         the 5 latest completed analyses
    recommendations  from the MOST RECENT completed report only

Nothing is invented. A new user gets empty lists and zeros.
"""

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.analysis import Analysis
from app.models.enums import AnalysisStatus
from app.models.song import Song
from app.models.user import User
from app.schemas.dashboard import DashboardResponse
from app.schemas.progress import AttemptEntry
from app.schemas.report import ReportRecommendation
from app.services.credits.credit_service import get_usage
from app.services.profile.profile_service import get_profile_response
from app.services.progress.progress_service import get_overview
from app.services.subscriptions.subscription_service import (
    get_active_subscription,
    subscription_to_response,
)

RECENT_LIMIT = 5


def get_dashboard(db: Session, user: User) -> DashboardResponse:
    rows = db.execute(
        select(Analysis, Song)
        .join(Song, Song.id == Analysis.song_id)
        .where(
            Analysis.user_id == user.id,
            Analysis.status == AnalysisStatus.COMPLETED.value,
            Analysis.is_deleted.is_(False),
        )
        .order_by(Analysis.completed_at.desc())
        .limit(RECENT_LIMIT)
    ).all()

    recent = [
        AttemptEntry(
            analysis_id=a.id,
            song_id=a.song_id,
            song_title=s.title,
            attempt=a.attempt_number,
            score=a.overall_score,
            date=a.completed_at or a.created_at,
            is_simulated=a.is_simulated,
            strengths=[i.title for i in a.insights if i.type == "positive"][:3],
            improvements=[i.title for i in a.insights if i.type == "improvement"][:3],
        )
        for a, s in rows
    ]

    recommendations: list[ReportRecommendation] = []
    latest_id = None
    if rows:
        latest = rows[0][0]
        latest_id = str(latest.id)
        recommendations = [
            ReportRecommendation(
                id=str(r.id),
                title=r.title,
                description=r.description,
                priority=r.priority,
                metric_id=r.metric_type,
                section_id=r.section_key,
                duration_minutes=r.duration_minutes,
            )
            for r in latest.recommendations
        ]

    return DashboardResponse(
        profile=get_profile_response(db, user),
        subscription=subscription_to_response(get_active_subscription(db, user.id)),
        usage=get_usage(db, user.id),
        progress=get_overview(db, user.id),
        recent=recent,
        recommendations=recommendations,
        latest_analysis_id=latest_id,
    )
