"""
NAADAMAYA API entry point.

This file only wires things together: logging, middleware, error handlers
and routers. No business logic lives here.
"""

from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.v1 import health
from app.api.v1.router import api_router
from app.core.config import settings
from app.core.database import engine
from app.core.logging import get_logger, log_event, setup_logging
from app.middleware.error_handler import register_exception_handlers
from app.middleware.rate_limit import RateLimitMiddleware
from app.middleware.request_id import RequestIDMiddleware
from app.middleware.request_logging import RequestLoggingMiddleware
from app.middleware.security_headers import SecurityHeadersMiddleware

setup_logging()
log = get_logger("naadamaya.main")

TAGS_METADATA = [
    {"name": "Health", "description": "Service, database and Redis status."},
    {"name": "Auth", "description": "Phone number + OTP sign-in, token refresh, logout."},
    {"name": "Users", "description": "The signed-in account, including account deletion."},
    {"name": "Profile", "description": "Singer profile and onboarding."},
    {"name": "Songs", "description": "Reference (original) songs."},
    {"name": "Recordings", "description": "The singer's own recordings."},
    {"name": "Analysis", "description": "Start an analysis and follow its progress."},
    {"name": "Reports", "description": "Finished comparison reports."},
    {"name": "Progress", "description": "Attempt history and improvement over time."},
    {"name": "Dashboard", "description": "Summary for the home screen."},
    {"name": "Usage", "description": "Credits and monthly allowance."},
    {"name": "Subscriptions", "description": "Plans and the current subscription."},
    {"name": "Payments", "description": "Razorpay orders and payment verification."},
    {"name": "Webhooks", "description": "Signed callbacks from Razorpay."},
    {"name": "Admin", "description": "Role-restricted administration."},
]


@asynccontextmanager
async def lifespan(app: FastAPI):
    log_event(
        log,
        "startup",
        environment=settings.environment,
        analysis_mode=settings.analysis_mode,
        otp_mode=settings.otp_mode,
        storage=settings.storage_provider,
    )
    if settings.use_mock_analysis:
        log.warning("ANALYSIS_MODE=mock: reports are SIMULATED and clearly labelled. Never use in production.")
    yield
    engine.dispose()
    log.info("shutdown")


def create_app() -> FastAPI:
    app = FastAPI(
        title="NAADAMAYA API",
        description=(
            "NAADAMAYA: sing. evolve. globally.\n\n"
            "Authenticate with `POST /api/v1/auth/send-otp` then `POST /api/v1/auth/verify-otp`, "
            "and send the returned access token as `Authorization: Bearer <token>`."
        ),
        version=settings.analysis_version,
        openapi_tags=TAGS_METADATA,
        lifespan=lifespan,
        # Interactive docs are available in development and staging only.
        docs_url=None if settings.is_production else "/docs",
        redoc_url=None if settings.is_production else "/redoc",
        openapi_url=None if settings.is_production else "/openapi.json",
    )

    # Middleware: the LAST one added is the OUTERMOST (runs first).
    # Request path:  RequestID -> Logging -> SecurityHeaders -> CORS -> RateLimit -> routes
    app.add_middleware(RateLimitMiddleware)
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origins_list,  # exact origins, never "*" in production
        allow_credentials=False,                   # tokens travel in the Authorization header
        allow_methods=["GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS"],
        allow_headers=["Authorization", "Content-Type", "Idempotency-Key", "X-Request-ID"],
        expose_headers=["X-Request-ID", "Retry-After"],
        max_age=600,
    )
    app.add_middleware(SecurityHeadersMiddleware)
    app.add_middleware(RequestLoggingMiddleware)
    app.add_middleware(RequestIDMiddleware)

    register_exception_handlers(app)

    # Health checks at the root (used by Docker): /health, /health/db, /health/redis
    app.include_router(health.router)
    # Everything else is versioned: /api/v1/...
    app.include_router(api_router, prefix=settings.api_v1_prefix)

    return app


app = create_app()
