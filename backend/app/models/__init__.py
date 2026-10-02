"""
NAADAMAYA models package.

Importing this package imports EVERY model, so SQLAlchemy can resolve
relationships written as strings (for example User -> "Profile") and
Alembic sees every table.

Always import models from here:
    from app.models import User, Profile, Analysis
"""

from app.models.analysis import (
    Analysis,
    AnalysisMetric,
    AnalysisSection,
    AnalysisTimeline,
    Insight,
    Recommendation,
)
from app.models.base import Base
from app.models.credit_transaction import CreditTransaction
from app.models.otp import OtpCode
from app.models.payment import Payment
from app.models.plan import Plan
from app.models.profile import Profile
from app.models.recording import Recording
from app.models.refresh_token import RefreshToken
from app.models.song import Song
from app.models.subscription import Subscription
from app.models.user import User
from app.models.webhook_event import WebhookEvent

__all__ = [
    "Base",
    "User",
    "Profile",
    "OtpCode",
    "RefreshToken",
    "Plan",
    "Subscription",
    "Payment",
    "WebhookEvent",
    "CreditTransaction",
    "Song",
    "Recording",
    "Analysis",
    "AnalysisMetric",
    "AnalysisSection",
    "Insight",
    "Recommendation",
    "AnalysisTimeline",
]
