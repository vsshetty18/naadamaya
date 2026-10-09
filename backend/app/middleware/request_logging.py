"""
NAADAMAYA request logging middleware.

One log line per request, after it finishes:

    method, path, status, duration_ms   (request_id and user_id come from the
                                         logging context set by other middleware)

What is NOT logged:
  - query strings (they can carry tokens or phone numbers)
  - request or response bodies (OTPs, tokens, audio, personal data)
  - headers (Authorization)

Paths are logged as the route TEMPLATE where known (for example
/api/v1/reports/{analysis_id}), so IDs do not flood the logs. If the route is
unknown (404), the raw path is logged, truncated.

Pure ASGI, so streaming responses (SSE) are not buffered. The duration is the
time until the response STARTS, which is the useful number for streams.
"""

import logging
import time

from starlette.types import ASGIApp, Message, Receive, Scope, Send

from app.core.logging import get_logger, log_event

log = get_logger("naadamaya.request")

SKIP_PATHS = {"/health", "/health/db", "/health/redis"}
MAX_PATH_LENGTH = 200


class RequestLoggingMiddleware:
    def __init__(self, app: ASGIApp) -> None:
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http" or scope.get("path") in SKIP_PATHS:
            await self.app(scope, receive, send)
            return

        started = time.perf_counter()
        status = {"code": 500}  # stays 500 if the app crashes before responding

        async def send_wrapper(message: Message) -> None:
            if message["type"] == "http.response.start":
                status["code"] = message["status"]
            await send(message)

        try:
            await self.app(scope, receive, send_wrapper)
        finally:
            route = scope.get("route")
            path = getattr(route, "path", None) or str(scope.get("path", ""))[:MAX_PATH_LENGTH]
            code = status["code"]
            level = logging.ERROR if code >= 500 else logging.WARNING if code >= 400 else logging.INFO
            log_event(
                log,
                "request",
                level=level,
                method=scope.get("method"),
                path=path,
                status=code,
                duration_ms=round((time.perf_counter() - started) * 1000, 1),
            )
