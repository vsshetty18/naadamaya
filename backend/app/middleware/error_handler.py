"""
NAADAMAYA global error handling.

    register_exception_handlers(app)     # called once in main.py

Every error leaves the API in ONE shape:

    {
      "success": false,
      "error": {"code": "USAGE_LIMIT_REACHED", "message": "...", ...extras},
      "request_id": "..."
    }

Handled:
  AppError                  our own errors (exceptions.py): status, code and
                            message are already safe for users
  RequestValidationError    bad input (FastAPI/Pydantic): 422 VALIDATION_ERROR
                            with a short per-field list, WITHOUT echoing the
                            submitted values (they may be OTPs or phone numbers)
  HTTPException             framework errors (404 route not found, 405, ...)
  anything else             logged in full (with stack trace) and answered with
                            a generic 500. Internals are never sent to the client.

In development (DEBUG=true) the generic 500 also includes the exception type
to help debugging. Never the message or stack trace, and never in production.
"""

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException

from app.core.config import settings
from app.core.exceptions import AppError
from app.core.logging import get_logger, request_id_var

log = get_logger("naadamaya.errors")

HTTP_CODES = {
    400: "BAD_REQUEST",
    401: "AUTH_REQUIRED",
    403: "FORBIDDEN",
    404: "RESOURCE_NOT_FOUND",
    405: "METHOD_NOT_ALLOWED",
    409: "CONFLICT",
    413: "FILE_TOO_LARGE",
    415: "UNSUPPORTED_MEDIA_TYPE",
    422: "VALIDATION_ERROR",
    429: "RATE_LIMITED",
}
HTTP_MESSAGES = {
    404: "We could not find what you asked for.",
    405: "This action is not allowed here.",
}


def _response(status: int, error: dict, headers: dict[str, str] | None = None) -> JSONResponse:
    return JSONResponse(
        status_code=status,
        content={"success": False, "error": error, "request_id": request_id_var.get()},
        headers=headers,
    )


def register_exception_handlers(app: FastAPI) -> None:
    @app.exception_handler(AppError)
    async def handle_app_error(request: Request, exc: AppError) -> JSONResponse:
        if exc.status_code >= 500:
            log.error("app error %s on %s", exc.code, request.url.path)
        return _response(exc.status_code, exc.to_error_body(), exc.headers)

    @app.exception_handler(RequestValidationError)
    async def handle_validation(request: Request, exc: RequestValidationError) -> JSONResponse:
        fields = []
        for err in exc.errors()[:10]:
            location = [str(p) for p in err.get("loc", []) if p not in ("body", "query", "path")]
            fields.append({"field": ".".join(location) or "request", "message": str(err.get("msg", "Invalid value"))})
        return _response(
            422,
            {
                "code": "VALIDATION_ERROR",
                "message": "Some of the information provided is not valid.",
                "fields": fields,
            },
        )

    @app.exception_handler(StarletteHTTPException)
    async def handle_http(request: Request, exc: StarletteHTTPException) -> JSONResponse:
        code = HTTP_CODES.get(exc.status_code, "ERROR" if exc.status_code < 500 else "INTERNAL_ERROR")
        message = HTTP_MESSAGES.get(exc.status_code) or (
            exc.detail if isinstance(exc.detail, str) and exc.status_code < 500 else "Something went wrong."
        )
        return _response(exc.status_code, {"code": code, "message": message}, getattr(exc, "headers", None))

    @app.exception_handler(Exception)
    async def handle_unexpected(request: Request, exc: Exception) -> JSONResponse:
        log.exception("unhandled error on %s %s", request.method, request.url.path)
        error = {"code": "INTERNAL_ERROR", "message": "Something went wrong. Please try again."}
        if settings.debug and not settings.is_production:
            error["type"] = type(exc).__name__
        return _response(500, error)
