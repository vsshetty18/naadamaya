"""
NAADAMAYA request ID middleware.

Every request gets a unique ID. It is:
  - put in the logging context, so every log line from that request carries it
  - returned to the client in the X-Request-ID response header
  - included in error responses (by the error handler)

A client may send its own X-Request-ID (useful when tracing across systems),
but only a short, safe value is accepted. Anything else is replaced, so a
caller cannot inject odd characters into our logs.

Written as a pure ASGI middleware (not BaseHTTPMiddleware) so context
variables set here reach the route code and streaming responses (SSE) work.
"""

import re
import uuid

from starlette.datastructures import Headers, MutableHeaders
from starlette.types import ASGIApp, Message, Receive, Scope, Send

from app.core.logging import request_id_var, user_id_var

HEADER_NAME = "X-Request-ID"
_SAFE_ID = re.compile(r"^[A-Za-z0-9\-_]{8,64}$")


class RequestIDMiddleware:
    def __init__(self, app: ASGIApp) -> None:
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] not in ("http", "websocket"):
            await self.app(scope, receive, send)
            return

        incoming = Headers(scope=scope).get(HEADER_NAME, "")
        request_id = incoming if _SAFE_ID.match(incoming) else uuid.uuid4().hex

        scope.setdefault("state", {})["request_id"] = request_id
        rid_token = request_id_var.set(request_id)
        uid_token = user_id_var.set(None)

        async def send_with_id(message: Message) -> None:
            if message["type"] == "http.response.start":
                MutableHeaders(scope=message)[HEADER_NAME] = request_id
            await send(message)

        try:
            await self.app(scope, receive, send_with_id)
        finally:
            request_id_var.reset(rid_token)
            user_id_var.reset(uid_token)
