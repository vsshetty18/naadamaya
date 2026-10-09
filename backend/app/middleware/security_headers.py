"""
NAADAMAYA security headers middleware.

Adds protective headers to every response. The API returns JSON and audio, never
web pages, so the policy is strict:

  X-Content-Type-Options: nosniff        browsers must not guess content types
  X-Frame-Options: DENY                  the API can never be shown in a frame
  Referrer-Policy: no-referrer           nothing leaks through the Referer header
  Cross-Origin-Resource-Policy: same-site
  Permissions-Policy                     powerful browser features switched off
  Content-Security-Policy                "default-src 'none'" for API responses
  Cache-Control: no-store                API responses (tokens, reports, personal
                                         data) are never cached by browsers or
                                         proxies. Audio streams are excluded so
                                         players can seek and reuse them.
  Strict-Transport-Security              production only (HTTPS is required there)

The Swagger pages (/docs, /redoc) load scripts and styles from a CDN and need a
looser policy, so they keep the framework's defaults. They only exist outside
production.

Pure ASGI, so streaming responses (SSE) are not buffered.
"""

from starlette.datastructures import MutableHeaders
from starlette.types import ASGIApp, Message, Receive, Scope, Send

from app.core.config import settings

DOC_PATHS = ("/docs", "/redoc", "/openapi.json")

STATIC_HEADERS = {
    "X-Content-Type-Options": "nosniff",
    "X-Frame-Options": "DENY",
    "Referrer-Policy": "no-referrer",
    "Cross-Origin-Resource-Policy": "same-site",
    "Permissions-Policy": "camera=(), microphone=(), geolocation=(), payment=()",
}
API_CSP = "default-src 'none'; frame-ancestors 'none'"
HSTS = "max-age=31536000; includeSubDomains"


class SecurityHeadersMiddleware:
    def __init__(self, app: ASGIApp) -> None:
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        path = str(scope.get("path", ""))
        is_docs = path.startswith(DOC_PATHS)

        async def send_with_headers(message: Message) -> None:
            if message["type"] == "http.response.start":
                headers = MutableHeaders(scope=message)
                for name, value in STATIC_HEADERS.items():
                    headers.setdefault(name, value)
                if not is_docs:
                    headers.setdefault("Content-Security-Policy", API_CSP)
                    content_type = headers.get("content-type", "")
                    if not content_type.startswith("audio/") and "cache-control" not in headers:
                        headers["Cache-Control"] = "no-store"
                if settings.is_production:
                    headers.setdefault("Strict-Transport-Security", HSTS)
            await send(message)

        await self.app(scope, receive, send_with_headers)
