"""
NAADAMAYA v1 API router.

Collects every route module under one router. main.py mounts it at
settings.api_v1_prefix (/api/v1), so the final paths are, for example:

    /api/v1/auth/send-otp
    /api/v1/reports/{analysis_id}
    /api/v1/payments/verify

The health routes are NOT here: they live at the root (/health) so Docker and
load balancers can reach them (see main.py).
"""

from fastapi import APIRouter

from app.api.v1 import (
    admin,
    analysis,
    auth,
    dashboard,
    payments,
    profile,
    progress,
    recordings,
    reports,
    songs,
    subscriptions,
    usage,
    users,
    webhooks,
)

api_router = APIRouter()

for module in (
    auth,
    users,
    profile,
    songs,
    recordings,
    analysis,
    reports,
    progress,
    dashboard,
    usage,
    subscriptions,
    payments,
    webhooks,
    admin,
):
    api_router.include_router(module.router)
