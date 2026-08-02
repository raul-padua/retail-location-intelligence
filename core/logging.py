"""Structured JSON logging with credential redaction."""

from __future__ import annotations

import json
import logging
import os
import re
import sys
from typing import Any

_SENSITIVE_KEY_RE = re.compile(r"(auth|token|secret|password|api[_-]?key|credential)", re.IGNORECASE)
_BEARER_RE = re.compile(r"(Bearer\s+)\S+", re.IGNORECASE)
_AUTH_PARAM_RE = re.compile(r"([?&]auth=)[^&\s]+", re.IGNORECASE)

REDACTED = "***REDACTED***"


def redact(value: Any) -> Any:
    """Recursively strip anything that looks like a credential.

    Applied to every log payload and to every raw request/response we persist for the
    trace panel, so a token can never reach a log file, the UI, or a sample output.
    """
    if isinstance(value, dict):
        return {
            key: (REDACTED if _SENSITIVE_KEY_RE.search(str(key)) else redact(item))
            for key, item in value.items()
        }
    if isinstance(value, (list, tuple)):
        return [redact(item) for item in value]
    if isinstance(value, str):
        return _AUTH_PARAM_RE.sub(rf"\1{REDACTED}", _BEARER_RE.sub(rf"\1{REDACTED}", value))
    return value


class JsonFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        payload: dict[str, Any] = {
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
        }
        extra = getattr(record, "context", None)
        if isinstance(extra, dict):
            payload["context"] = redact(extra)
        if record.exc_info:
            payload["exception"] = self.formatException(record.exc_info)
        return json.dumps(payload, default=str)


def configure_logging(level: str | None = None) -> None:
    resolved = (level or os.getenv("RLI_LOG_LEVEL", "INFO")).upper()
    root = logging.getLogger("rli")
    root.setLevel(resolved)
    root.propagate = False
    if not root.handlers:
        handler = logging.StreamHandler(sys.stderr)
        handler.setFormatter(JsonFormatter())
        root.addHandler(handler)


def get_logger(name: str) -> logging.Logger:
    configure_logging()
    return logging.getLogger(f"rli.{name}")


def log_event(logger: logging.Logger, level: int, message: str, **context: Any) -> None:
    logger.log(level, message, extra={"context": context})
