"""
NAADAMAYA application errors.

Services and API routes raise these. The error-handler middleware (written
later) turns them into one consistent response:

    {
      "success": false,
      "error": {
        "code": "USAGE_LIMIT_REACHED",
        "message": "Monthly analysis limit reached",
        "upgrade_required": true
      },
      "request_id": "..."
    }

Messages are safe to show to users. Internal details (stack traces, SQL,
file paths) are never put in an error. They go to the logs only.
"""

from typing import Any


class AppError(Exception):
    """Base class for every error that is deliberately sent to the client."""

    status_code: int = 500
    code: str = "INTERNAL_ERROR"
    message: str = "Something went wrong. Please try again."

    def __init__(
        self,
        message: str | None = None,
        *,
        code: str | None = None,
        status_code: int | None = None,
        headers: dict[str, str] | None = None,
        **extra: Any,
    ) -> None:
        self.message = message or self.message
        self.code = code or self.code
        self.status_code = status_code or self.status_code
        self.headers = headers
        # Extra public fields, e.g. upgrade_required=True or retry_after=30.
        self.extra = extra
        super().__init__(self.message)

    def to_error_body(self) -> dict[str, Any]:
        return {"code": self.code, "message": self.message, **self.extra}


# ==========================================================
# 400 / 422: the request itself is wrong
# ==========================================================
class BadRequestError(AppError):
    status_code = 400
    code = "BAD_REQUEST"
    message = "The request could not be processed."


class ValidationFailedError(AppError):
    status_code = 422
    code = "VALIDATION_ERROR"
    message = "Some of the information provided is not valid."


class InvalidPhoneNumberError(AppError):
    status_code = 422
    code = "INVALID_PHONE_NUMBER"
    message = "Please enter a valid phone number."


# ==========================================================
# Audio and files
# ==========================================================
class InvalidAudioError(AppError):
    status_code = 422
    code = "INVALID_AUDIO"
    message = "This audio file could not be read. Please use a valid audio file."


class FileTooLargeError(AppError):
    status_code = 413
    code = "FILE_TOO_LARGE"
    message = "This file is too large."


class UnsupportedMediaError(AppError):
    status_code = 415
    code = "UNSUPPORTED_MEDIA_TYPE"
    message = "This file type is not supported."


# ==========================================================
# 401: who are you?
# ==========================================================
class AuthRequiredError(AppError):
    status_code = 401
    code = "AUTH_REQUIRED"
    message = "Authentication required."

    def __init__(self, message: str | None = None, **kwargs: Any) -> None:
        kwargs.setdefault("headers", {"WWW-Authenticate": "Bearer"})
        super().__init__(message, **kwargs)


class InvalidTokenError(AuthRequiredError):
    code = "INVALID_TOKEN"
    message = "Your session is not valid. Please sign in again."


class TokenExpiredError(AuthRequiredError):
    code = "TOKEN_EXPIRED"
    message = "Your session has expired. Please sign in again."


class InvalidOtpError(AppError):
    status_code = 400
    code = "INVALID_OTP"
    message = "That code is not correct."


class OtpExpiredError(AppError):
    status_code = 400
    code = "OTP_EXPIRED"
    message = "That code has expired. Please request a new one."


# ==========================================================
# 403: you are known, but not allowed
# ==========================================================
class ForbiddenError(AppError):
    status_code = 403
    code = "FORBIDDEN"
    message = "You do not have permission to do this."


class AccountDisabledError(ForbiddenError):
    code = "ACCOUNT_DISABLED"
    message = "This account is not active."


class SubscriptionRequiredError(ForbiddenError):
    code = "SUBSCRIPTION_REQUIRED"
    message = "This feature needs a paid plan."

    def __init__(self, message: str | None = None, **kwargs: Any) -> None:
        kwargs.setdefault("upgrade_required", True)
        super().__init__(message, **kwargs)


class UsageLimitReachedError(ForbiddenError):
    code = "USAGE_LIMIT_REACHED"
    message = "Monthly analysis limit reached."

    def __init__(self, message: str | None = None, **kwargs: Any) -> None:
        kwargs.setdefault("upgrade_required", True)
        super().__init__(message, **kwargs)


# ==========================================================
# 404 / 409
# ==========================================================
class NotFoundError(AppError):
    """
    Also used when a resource belongs to someone else. Answering "not found"
    instead of "forbidden" avoids confirming that another user's ID exists.
    """

    status_code = 404
    code = "RESOURCE_NOT_FOUND"
    message = "We could not find what you asked for."


class ConflictError(AppError):
    status_code = 409
    code = "CONFLICT"
    message = "This action conflicts with the current state."


class DuplicateRequestError(ConflictError):
    code = "DUPLICATE_REQUEST"
    message = "This request is already being processed."


# ==========================================================
# 429: slow down
# ==========================================================
class RateLimitedError(AppError):
    status_code = 429
    code = "RATE_LIMITED"
    message = "Too many requests. Please wait a moment and try again."

    def __init__(self, message: str | None = None, *, retry_after: int | None = None, **kwargs: Any) -> None:
        if retry_after is not None:
            kwargs["retry_after"] = retry_after
            kwargs.setdefault("headers", {"Retry-After": str(retry_after)})
        super().__init__(message, **kwargs)


class OtpRateLimitedError(RateLimitedError):
    code = "OTP_RATE_LIMITED"
    message = "Too many code requests. Please wait before trying again."


# ==========================================================
# Payments
# ==========================================================
class PaymentFailedError(AppError):
    status_code = 402
    code = "PAYMENT_FAILED"
    message = "The payment could not be completed."


class PaymentVerificationFailedError(AppError):
    status_code = 400
    code = "PAYMENT_VERIFICATION_FAILED"
    message = "We could not verify this payment."


# ==========================================================
# Analysis and server-side problems
# ==========================================================
class AnalysisFailedError(AppError):
    status_code = 500
    code = "ANALYSIS_FAILED"
    message = "We could not finish analysing this performance."


class ServiceUnavailableError(AppError):
    status_code = 503
    code = "SERVICE_UNAVAILABLE"
    message = "This service is temporarily unavailable. Please try again shortly."


class NotAvailableYetError(AppError):
    """For features that are designed but not built yet. Never fakes a result."""

    status_code = 501
    code = "NOT_AVAILABLE_YET"
    message = "This feature is not available yet."
