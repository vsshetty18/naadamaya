"""
NAADAMAYA admin routes (role-restricted).

    GET  /admin/stats                platform totals (users, analyses, revenue, failures)
    GET  /admin/users                users, newest first (paginated, optional ?q= masked search)
    GET  /admin/analyses/failed      recent failed analyses
    POST /admin/maintenance/fail-stuck   fail and refund analyses stuck over 30 minutes

Every route requires the ADMIN role (deps.require_admin). A normal user gets 403.
There is no API to become an admin: set `role = 'ADMIN'` on a user in the
database by hand.

Privacy: phone numbers are always returned MASKED. Admins never see audio,
reports, OTPs or tokens through this API.

Roles are strings, so SUPPORT / ANALYST / SUPER_ADMIN can be added later by
adding a dependency per role, with no schema change.
"""

from datetime import timedelta

from fastapi import APIRouter, Depends, Query
from pydantic import Field
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.api.v1.deps import require_admin
from app.core.database import get_db
from app.core.logging import get_logger, log_event
from app.core.security import utcnow
from app.models.analysis import Analysis
from app.models.enums import AnalysisStatus, PaymentStatus, SubscriptionStatus
from app.models.payment import Payment
from app.models.plan import Plan
from app.models.subscription import Subscription
from app.models.user import User
from app.schemas.common import APIModel, COMMON_ERRORS, Page, PageParams
from app.services.analysis.analysis_service import fail_stuck_analyses
from app.utils.phone import mask_phone

log = get_logger("naadamaya.admin")

router = APIRouter(prefix="/admin", tags=["Admin"], dependencies=[Depends(require_admin)])


class AdminStats(APIModel):
    total_users: int
    active_users_7d: int
    total_analyses: int
    analyses_24h: int
    failed_analyses_24h: int
    queued_or_processing: int
    paid_subscriptions: int
    revenue_total: float = Field(description="Rupees, from verified payments.")
    revenue_30d: float


class AdminUser(APIModel):
    id: str
    phone_masked: str
    role: str
    status: str
    created_at: str
    last_seen_at: str | None = None


class AdminFailure(APIModel):
    analysis_id: str
    created_at: str
    error_code: str | None = None
    error_message: str | None = None
    credit_refunded: bool


def _count(db: Session, *where) -> int:
    return db.scalar(select(func.count()).select_from(Analysis).where(*where)) or 0


@router.get("/stats", response_model=AdminStats, summary="Platform totals", responses={403: COMMON_ERRORS[403]})
def stats(db: Session = Depends(get_db)) -> AdminStats:
    now = utcnow()
    day, week, month = now - timedelta(days=1), now - timedelta(days=7), now - timedelta(days=30)
    paid = Payment.status == PaymentStatus.PAID.value

    def revenue(*extra) -> float:
        total = db.scalar(select(func.coalesce(func.sum(Payment.amount), 0)).where(paid, *extra)) or 0
        return round(total / 100, 2)

    paid_subs = db.scalar(
        select(func.count()).select_from(Subscription).join(Plan, Plan.id == Subscription.plan_id).where(
            Subscription.status == SubscriptionStatus.ACTIVE.value, Plan.price_amount > 0
        )
    ) or 0

    return AdminStats(
        total_users=db.scalar(select(func.count()).select_from(User).where(User.is_deleted.is_(False))) or 0,
        active_users_7d=db.scalar(
            select(func.count()).select_from(User).where(User.last_seen_at >= week, User.is_deleted.is_(False))
        ) or 0,
        total_analyses=_count(db),
        analyses_24h=_count(db, Analysis.created_at >= day),
        failed_analyses_24h=_count(db, Analysis.status == AnalysisStatus.FAILED.value, Analysis.created_at >= day),
        queued_or_processing=_count(
            db, Analysis.status.in_([AnalysisStatus.QUEUED.value, AnalysisStatus.PROCESSING.value])
        ),
        paid_subscriptions=paid_subs,
        revenue_total=revenue(),
        revenue_30d=revenue(Payment.verified_at >= month),
    )


@router.get("/users", response_model=Page[AdminUser], summary="Users (phone numbers masked)")
def users(
    params: PageParams = Depends(),
    status: str | None = Query(default=None, description="ACTIVE | SUSPENDED | DELETED"),
    db: Session = Depends(get_db),
) -> Page[AdminUser]:
    where = []
    if status:
        where.append(User.status == status.upper())
    total = db.scalar(select(func.count()).select_from(User).where(*where)) or 0
    rows = db.scalars(
        select(User).where(*where).order_by(User.created_at.desc()).offset(params.offset).limit(params.limit)
    ).all()
    items = [
        AdminUser(
            id=str(u.id),
            phone_masked="deleted" if u.is_deleted else mask_phone(u.phone_number_normalized),
            role=u.role,
            status=u.status,
            created_at=u.created_at.isoformat(),
            last_seen_at=u.last_seen_at.isoformat() if u.last_seen_at else None,
        )
        for u in rows
    ]
    return Page.build(items, total, params)


@router.get("/analyses/failed", response_model=Page[AdminFailure], summary="Recent failed analyses")
def failed(params: PageParams = Depends(), db: Session = Depends(get_db)) -> Page[AdminFailure]:
    where = (Analysis.status == AnalysisStatus.FAILED.value,)
    total = _count(db, *where)
    rows = db.scalars(
        select(Analysis).where(*where).order_by(Analysis.created_at.desc()).offset(params.offset).limit(params.limit)
    ).all()
    return Page.build(
        [
            AdminFailure(
                analysis_id=str(a.id),
                created_at=a.created_at.isoformat(),
                error_code=a.error_code,
                error_message=a.error_message,
                credit_refunded=a.credit_refunded,
            )
            for a in rows
        ],
        total,
        params,
    )


@router.post("/maintenance/fail-stuck", summary="Fail and refund stuck analyses")
def fail_stuck(db: Session = Depends(get_db)) -> dict:
    count = fail_stuck_analyses(db)
    log_event(log, "admin_fail_stuck", count=count)
    return {"failed": count}
