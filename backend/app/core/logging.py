"""
NAADAMAYA structured logging.

- Development: readable single-line logs.
- Production: one JSON object per line (easy for log tools to parse).
- Every log line carries the request_id and user_id when they are known.
- Sensitive values (OTPs, tokens, passwords, secrets, signatures) are
  redacted automatically, even if someone logs them by accident.
"""

import json
import logging
import re
import sys
from contextvars import ContextVar
from datetime import datetime, timezone

from app.core.config import settings

# Set by the request-ID and authentication middleware for the current request.
request_id_var: ContextVar[str | None] = ContextVar("request_id", default=None)
user_id_var: ContextVar[str | None] = ContextVar("user_id", default=None)

# Matches things like  otp=123456,  "access_token": "abc",  password: xyz
_SENSITIVE_KEYS = (
    "otp",
    "password",
    "passwd",
    "secret",
    "token",
    "authorization",
    "signature",
    "api_key",
    "apikey",
    "razorpay_signature",
)
_KEY_PATTERN = "|".join(_SENSITIVE_KEYS)
_REDACT_RE = re.compile(
    rf"""(?ix)
    (["']?(?:[a-z_]*(?:{_KEY_PATTERN})[a-z_]*)["']?   # the key
     \s*[:=]\s*)                                        # separator
    (["']?)[^\s,"'}}\]]+\2                              # the value
    """
)
_BEARER_RE = re.compile(r"(?i)bearer\s+[a-z0-9\-._~+/]+=*")

REDACTED = "[REDACTED]"


def redact(text: str) -> str:
    """Hides sensitive values inside a log message."""
    text = _REDACT_RE.sub(lambda m: f"{m.group(1)}{REDACTED}", text)
    return _BEARER_RE.sub(f"Bearer {REDACTED}", text)


class ContextFilter(logging.Filter):
    """Adds request_id / user_id to every record and redacts the message."""

    def filter(self, record: logging.LogRecord) -> bool:
        record.request_id = request_id_var.get() or "-"
        record.user_id = user_id_var.get() or "-"
        try:
            record.msg = redact(record.getMessage())
            record.args = ()
        except Exception:  # never let logging break the app
            pass
        return True


class JsonFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        payload = {
            "time": datetime.fromtimestamp(record.created, tz=timezone.utc).isoformat(),
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
            "request_id": getattr(record, "request_id", "-"),
            "user_id": getattr(record, "user_id", "-"),
        }
        extra = getattr(record, "event", None)
        if isinstance(extra, dict):
            payload.update({k: v for k, v in extra.items() if k not in payload})
        if record.exc_info:
            payload["exception"] = redact(self.formatException(record.exc_info))
        return json.dumps(payload, default=str)


class ReadableFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        base = (
            f"{self.formatTime(record, '%H:%M:%S')} {record.levelname:<7} "
            f"[{getattr(record, 'request_id', '-')}] {record.name}: {record.getMessage()}"
        )
        extra = getattr(record, "event", None)
        if isinstance(extra, dict) and extra:
            base += " " + " ".join(f"{k}={v}" for k, v in extra.items())
        if record.exc_info:
            base += "\n" + redact(self.formatException(record.exc_info))
        return base


def setup_logging() -> None:
    """Call once at startup (app/main.py and the Celery worker)."""
    handler = logging.StreamHandler(sys.stdout)
    handler.addFilter(ContextFilter())
    handler.setFormatter(JsonFormatter() if settings.is_production else ReadableFormatter())

    root = logging.getLogger()
    root.handlers.clear()
    root.addHandler(handler)
    root.setLevel(settings.log_level.upper())

    # Quieter third-party loggers.
    logging.getLogger("uvicorn.access").setLevel(logging.WARNING)  # we log requests ourselves
    logging.getLogger("sqlalchemy.engine").setLevel(logging.WARNING)
    logging.getLogger("botocore").setLevel(logging.WARNING)


def get_logger(name: str) -> logging.Logger:
    return logging.getLogger(name)


def log_event(logger: logging.Logger, message: str, level: int = logging.INFO, **fields) -> None:
    """
    Logs a message plus structured fields, e.g.
        log_event(log, "analysis_started", analysis_id=str(a.id), song_id=str(s.id))
    Field values are redacted if they look sensitive.
    """
    safe = {
        k: (REDACTED if any(s in k.lower() for s in _SENSITIVE_KEYS) else v)
        for k, v in fields.items()
    }
    logger.log(level, message, extra={"event": safe})
