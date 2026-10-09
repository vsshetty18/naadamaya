"""
NAADAMAYA rate limiting middleware.

A fixed-window counter in Redis, keyed by client IP and a "bucket":

    auth      /auth/send-otp, /auth/verify-otp, /auth/refresh   (strict)
    upload    song, recording and photo uploads
    analysis  POST /analysis/start                              (strictest, expensive)
    default   everything else

Limits come from settings (RATE_LIMIT_*). Over the limit the client gets
429 RATE_LIMITED with a Retry-After header, in the standard error shape.

Design choices:
  - FAIL OPEN: if Redis is down, requests are allowed (and a warning is
    logged). The OTP service has its own database-backed limits, so the most
    abusable endpoint is still protected, and analysis is also guarded by
    credits.
  - The client IP is taken from the connection. X-Forwarded-For is used ONLY
    when TRUST_PROXY_HEADERS is on, because otherwise any caller could fake it
    to dodge limits. Behind a proxy or load balancer, turn that on.
  - Webhooks, health checks and CORS preflight requests are never limited.
  - Pure ASGI, so streaming responses are not buffered.
"""

import json
import os
import time

import redis
from starlette.types import ASGIApp, Receive, Scope, Send

from app.core.config import settings
from app.core.logging import get_logger, request_id_var

log = get_logger("naadamaya.ratelimit")

TRUST_PROXY_HEADERS = os.getenv("TRUST_PROXY_HEADERS", "false").lower() == "true"
EXEMPT_PREFIXES = ("/health", "/api/v1/webhooks")
WINDOW_SECONDS = 60

_client: redis.Redis | None = None


def _redis() -> redis.Redis:
    global _client
    if _client is None:
        _client = redis.Redis.from_url(
            settings.redis_url, socket_connect_timeout=0.3, socket_timeout=0.3
        )
    return _client


def _bucket(method: str, path: str) -> tuple[str, int, int]:
    """(name, limit, window_seconds) for this request."""
    p = settings.api_v1_prefix
    if path.startswith((f"{p}/auth/send-otp", f"{p}/auth/verify-otp", f"{p}/auth/refresh")):
        return "auth", 10, WINDOW_SECONDS
    if method == "POST" and path.startswith(f"{p}/analysis/start"):
        return "analysis", settings.rate_limit_analysis_per_hour, 3600
    if method in ("POST", "PUT") and path.startswith(
        (f"{p}/songs/reference", f"{p}/recordings", f"{p}/profile/photo")
    ):
        return "upload", settings.rate_limit_upload_per_minute, WINDOW_SECONDS
    return "default", settings.rate_limit_default_per_minute, WINDOW_SECONDS


def _client_ip(scope: Scope) -> str:
    if TRUST_PROXY_HEADERS:
        for name, value in scope.get("headers", []):
            if name == b"x-forwarded-for":
                first = value.decode("latin-1").split(",")[0].strip()
                if first:
                    return first[:45]
    client = scope.get("client")
    return client[0] if client else "unknown"


async def _reject(send: Send, retry_after: int) -> None:
    body = json.dumps(
        {
            "success": False,
            "error": {
                "code": "RATE_LIMITED",
                "message": "Too many requests. Please wait a moment and try again.",
                "retry_after": retry_after,
            },
            "request_id": request_id_var.get(),
        }
    ).encode()
    await send(
        {
            "type": "http.response.start",
            "status": 429,
            "headers": [
                (b"content-type", b"application/json"),
                (b"retry-after", str(retry_after).encode()),
                (b"content-length", str(len(body)).encode()),
            ],
        }
    )
    await send({"type": "http.response.body", "body": body})


class RateLimitMiddleware:
    def __init__(self, app: ASGIApp) -> None:
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if (
            scope["type"] != "http"
            or not settings.rate_limit_enabled
            or scope["method"] == "OPTIONS"
            or str(scope.get("path", "")).startswith(EXEMPT_PREFIXES)
        ):
            await self.app(scope, receive, send)
            return

        name, limit, window = _bucket(scope["method"], str(scope.get("path", "")))
        ip = _client_ip(scope)
        slot = int(time.time() // window)
        key = f"rl:{name}:{ip}:{slot}"

        try:
            pipe = _redis().pipeline()
            pipe.incr(key)
            pipe.expire(key, window + 5)
            count = int(pipe.execute()[0])
        except Exception:  # noqa: BLE001 - fail open
            log.warning("rate limiter unavailable (redis); allowing request")
            await self.app(scope, receive, send)
            return

        if count > limit:
            retry_after = max(1, window - int(time.time() % window))
            log.warning("rate limit hit: bucket=%s", name)
            await _reject(send, retry_after)
            return

        await self.app(scope, receive, send)
