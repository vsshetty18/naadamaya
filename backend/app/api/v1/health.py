"""
NAADAMAYA health checks.

    GET /health          the API process is up (used by Docker's health check)
    GET /health/db       PostgreSQL answers
    GET /health/redis    Redis answers (cache, rate limits, Celery broker)

These live at the root (not under /api/v1) and need no sign-in, so load
balancers and Docker can call them. They reveal only "ok" or "unavailable",
never connection strings or error details. The request logger skips them.
"""

import redis
from fastapi import APIRouter
from fastapi.responses import JSONResponse

from app.core.config import settings
from app.core.database import check_database

router = APIRouter(tags=["Health"])


def _status(ok: bool, name: str) -> JSONResponse:
    return JSONResponse(
        status_code=200 if ok else 503,
        content={"status": "ok" if ok else "unavailable", "check": name},
    )


@router.get("/health", summary="API is running")
def health() -> dict:
    return {
        "status": "ok",
        "service": "NAADAMAYA",
        "environment": settings.environment,
        "analysis_mode": settings.analysis_mode,
    }


@router.get("/health/db", summary="Database connection")
def health_db() -> JSONResponse:
    return _status(check_database(), "database")


@router.get("/health/redis", summary="Redis connection")
def health_redis() -> JSONResponse:
    try:
        client = redis.Redis.from_url(
            settings.redis_url, socket_connect_timeout=1, socket_timeout=1
        )
        ok = bool(client.ping())
    except Exception:  # noqa: BLE001
        ok = False
    return _status(ok, "redis")
