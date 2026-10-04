"""
NAADAMAYA plan lookups.

Plans live in the database (models/plan.py), so prices and limits can change
without a deploy. This module is the only place that reads them.

    plan = get_plan_by_code(db, "GO")
    plans = list_active_plans(db)
    response = plan_to_response(plan, current_plan_code="FREE")

DEFAULT_PLANS holds the starting FREE / GO / PRO plans, worded like the
frontend Stage and Credits screens. ensure_default_plans() inserts any that
are missing and NEVER overwrites an existing row, so a price you edit in the
database is not reset by a restart or a re-seed.

The price used for a payment always comes from these rows, never from the
frontend.
"""

import uuid

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.exceptions import NotFoundError, ServiceUnavailableError
from app.core.logging import get_logger
from app.models.plan import Plan
from app.schemas.subscription import PlanFeature, PlanResponse

log = get_logger("naadamaya.plans")

FREE_PLAN_CODE = "FREE"

# Prices are in paise (19900 = Rs 199.00).
DEFAULT_PLANS: list[dict] = [
    {
        "code": "FREE",
        "name": "Free",
        "tagline": "Get started on your musical journey.",
        "price_amount": 0,
        "monthly_limit": 10,
        "rank": 0,
        "is_popular": False,
        "features": [
            {"text": "10 analysis credits", "included": True},
            {"text": "Basic comparison report", "included": True},
            {"text": "Standard analysis", "included": True},
            {"text": "Advanced insights", "included": False},
            {"text": "Priority processing", "included": False},
            {"text": "AI suggestions", "included": False},
        ],
        "feature_flags": {
            "advanced_insights": False,
            "priority_processing": False,
            "ai_suggestions": False,
        },
    },
    {
        "code": "GO",
        "name": "Go",
        "tagline": "For consistent learners who want to grow more.",
        "price_amount": 19900,
        "monthly_limit": 30,
        "rank": 1,
        "is_popular": False,
        "features": [
            {"text": "30 analysis credits", "included": True},
            {"text": "Detailed comparison report", "included": True},
            {"text": "Advanced analysis", "included": True},
            {"text": "AI suggestions", "included": True},
            {"text": "Priority processing", "included": False},
            {"text": "Early access to new features", "included": False},
        ],
        "feature_flags": {
            "advanced_insights": True,
            "priority_processing": False,
            "ai_suggestions": True,
        },
    },
    {
        "code": "PRO",
        "name": "Pro",
        "tagline": "For serious singers ready to go beyond.",
        "price_amount": 44900,
        "monthly_limit": 100,
        "rank": 2,
        "is_popular": True,
        "features": [
            {"text": "100 analysis credits", "included": True},
            {"text": "Complete AI report", "included": True},
            {"text": "Advanced insights & tips", "included": True},
            {"text": "Priority processing", "included": True},
            {"text": "Early access to new features", "included": True},
            {"text": "Support & community access", "included": True},
        ],
        "feature_flags": {
            "advanced_insights": True,
            "priority_processing": True,
            "ai_suggestions": True,
            "early_access": True,
        },
    },
]


# ==========================================================
# Lookups
# ==========================================================
def get_plan_by_id(db: Session, plan_id: uuid.UUID) -> Plan:
    plan = db.get(Plan, plan_id)
    if plan is None:
        raise NotFoundError("That plan does not exist.")
    return plan


def get_plan_by_code(db: Session, code: str) -> Plan:
    plan = db.scalar(select(Plan).where(Plan.code == (code or "").strip().upper()))
    if plan is None:
        raise NotFoundError("That plan does not exist.")
    return plan


def get_active_plan(db: Session, *, code: str | None = None, plan_id: uuid.UUID | None = None) -> Plan:
    """The plan a user is trying to buy. It must exist AND be active."""
    if code:
        plan = get_plan_by_code(db, code)
    elif plan_id:
        plan = get_plan_by_id(db, plan_id)
    else:
        raise NotFoundError("Choose a plan.")
    if not plan.is_active:
        raise NotFoundError("That plan is not available.")
    return plan


def get_free_plan(db: Session) -> Plan:
    plan = db.scalar(select(Plan).where(Plan.code == FREE_PLAN_CODE))
    if plan is None:
        log.error("the FREE plan is missing from the database; run the seed")
        raise ServiceUnavailableError()
    return plan


def list_active_plans(db: Session) -> list[Plan]:
    return list(
        db.scalars(select(Plan).where(Plan.is_active.is_(True)).order_by(Plan.rank, Plan.created_at))
    )


# ==========================================================
# Response building
# ==========================================================
def plan_to_response(plan: Plan, current_plan_code: str | None = None) -> PlanResponse:
    return PlanResponse(
        id=plan.id,
        code=plan.code,
        name=plan.name,
        tagline=plan.tagline,
        description=plan.description,
        price_amount=plan.price_amount,
        price=round(plan.price_amount / 100, 2),
        currency=plan.currency,
        billing_period=plan.billing_period,
        monthly_limit=plan.monthly_limit,
        period_days=plan.period_days,
        features=[
            PlanFeature(text=f["text"], included=bool(f.get("included", True)))
            for f in (plan.features or [])
            if isinstance(f, dict) and f.get("text")
        ],
        feature_flags={k: bool(v) for k, v in (plan.feature_flags or {}).items()},
        rank=plan.rank,
        is_popular=plan.is_popular,
        is_current=bool(current_plan_code and plan.code == current_plan_code),
    )


# ==========================================================
# Seeding
# ==========================================================
def ensure_default_plans(db: Session) -> int:
    """Inserts any default plan that is missing. Never changes existing rows. Returns how many were added."""
    existing = set(db.scalars(select(Plan.code)))
    added = 0
    for spec in DEFAULT_PLANS:
        if spec["code"] in existing:
            continue
        db.add(
            Plan(
                code=spec["code"],
                name=spec["name"],
                tagline=spec["tagline"],
                price_amount=spec["price_amount"],
                currency="INR",
                billing_period="monthly",
                monthly_limit=spec["monthly_limit"],
                period_days=30,
                features=spec["features"],
                feature_flags=spec["feature_flags"],
                rank=spec["rank"],
                is_popular=spec["is_popular"],
                is_active=True,
            )
        )
        added += 1
    if added:
        db.flush()
        log.info("seeded %d default plan(s)", added)
    return added
