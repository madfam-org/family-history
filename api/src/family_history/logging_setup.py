"""Structured JSON logging that never carries names, emails or tokens.

Two layers of protection:
- structured `extra` fields whose key looks personal (name, email, token, authorization, ...)
  are replaced by `[redacted]`;
- every rendered message and string field is scrubbed for email addresses, bearer tokens and
  JWT-shaped strings.

Uvicorn's access log is silenced because it prints raw query strings (`?q=` holds names). The
request middleware logs method, route template, status and duration instead.
"""

from __future__ import annotations

import json
import logging
import re
import sys
from contextvars import ContextVar
from datetime import UTC, datetime
from typing import Any, Final

request_id_var: ContextVar[str | None] = ContextVar("fh_request_id", default=None)

REDACTED: Final = "[redacted]"

_SENSITIVE_KEY_PARTS: Final = (
    "name",
    "email",
    "token",
    "authorization",
    "password",
    "secret",
    "cookie",
    "credential",
    "ip",
)
# Keys that contain a sensitive fragment but are safe operational fields.
_SAFE_KEYS: Final = frozenset(
    {"logger", "route", "path", "method", "status", "duration_ms", "request_id", "level"}
)

_EMAIL_RE: Final = re.compile(r"[A-Za-z0-9._%+\-]+@[A-Za-z0-9.\-]+\.[A-Za-z]{2,}")
_BEARER_RE: Final = re.compile(r"(?i)bearer\s+[A-Za-z0-9._~+/\-]+=*")
_JWT_RE: Final = re.compile(r"eyJ[A-Za-z0-9_\-]+\.[A-Za-z0-9_\-]+\.[A-Za-z0-9_\-]*")

# Attributes every LogRecord has; anything else came in through `extra=`.
_RESERVED: Final = frozenset(
    vars(logging.LogRecord("x", logging.INFO, "x", 0, "x", None, None)).keys()
) | {"message", "asctime", "taskName"}


def scrub(text: str) -> str:
    """Remove emails, bearer tokens and JWTs from free text."""
    text = _JWT_RE.sub(REDACTED, text)
    text = _BEARER_RE.sub("Bearer " + REDACTED, text)
    return _EMAIL_RE.sub(REDACTED, text)


def _is_sensitive_key(key: str) -> bool:
    lowered = key.lower()
    if lowered in _SAFE_KEYS:
        return False
    segments = re.split(r"[_\-.]", lowered)
    return any(part in segments or part == lowered for part in _SENSITIVE_KEY_PARTS)


def redact_value(key: str, value: Any) -> Any:
    if _is_sensitive_key(key):
        return REDACTED
    if isinstance(value, str):
        return scrub(value)
    if isinstance(value, dict):
        return {str(k): redact_value(str(k), v) for k, v in value.items()}
    if isinstance(value, list | tuple):
        return [redact_value("", v) for v in value]
    if isinstance(value, int | float | bool) or value is None:
        return value
    return scrub(str(value))


class JsonFormatter(logging.Formatter):
    """One JSON object per line, redacted."""

    def format(self, record: logging.LogRecord) -> str:
        payload: dict[str, Any] = {
            "ts": datetime.fromtimestamp(record.created, tz=UTC).isoformat(),
            "level": record.levelname.lower(),
            "logger": record.name,
            "message": scrub(record.getMessage()),
        }
        request_id = request_id_var.get()
        if request_id:
            payload["request_id"] = request_id
        for key, value in record.__dict__.items():
            if key in _RESERVED or key.startswith("_"):
                continue
            payload[key] = redact_value(key, value)
        if record.exc_info and record.exc_info[0] is not None:
            payload["exc_type"] = record.exc_info[0].__name__
            payload["exc"] = scrub(self.formatException(record.exc_info))
        return json.dumps(payload, ensure_ascii=False, default=str)


_configured = False


def configure_logging(level: str = "INFO") -> None:
    """Install the JSON handler on the root logger. Idempotent."""
    global _configured
    root = logging.getLogger()
    if not _configured:
        handler = logging.StreamHandler(sys.stdout)
        handler.setFormatter(JsonFormatter())
        root.handlers = [handler]
        _configured = True
    root.setLevel(level)
    for name in ("uvicorn", "uvicorn.error"):
        uv_logger = logging.getLogger(name)
        uv_logger.handlers = []
        uv_logger.propagate = True
    access = logging.getLogger("uvicorn.access")
    access.handlers = []
    access.propagate = False
    access.disabled = True
