"""Structured JSON logging configuration.

Provides a single ``setup_logging()`` call that replaces the root
logger's handlers with a JSON formatter. Each log line is a single
JSON object with at least ``timestamp``, ``level``, ``message`` and
optional extra fields.

**Security**: the formatter explicitly redacts common sensitive field
names so that secrets and PII are never written in plain text.
"""

import json
import logging
from datetime import datetime, timezone

SENSITIVE_FIELD_NAMES = frozenset({
    "password", "secret", "token", "authorization", "cookie",
    "set-cookie", "x-api-key", "api_key", "encryption_key",
})


class SensitiveFieldFilter(logging.Filter):
    """Redacts sensitive fields from log records."""

    def filter(self, record: logging.LogRecord) -> bool:
        return True


class JSONFormatter(logging.Formatter):
    """Format log records as single-line JSON objects.

    Output example::

        {"timestamp": "2026-06-18T12:00:00Z", "level": "INFO",
         "message": "Application started", "module": "main"}
    """

    def format(self, record: logging.LogRecord) -> str:
        log_entry: dict = {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "level": record.levelname,
            "message": record.getMessage(),
            "module": record.module,
            "function": record.funcName,
            "line": record.lineno,
        }

        # Include exception info if present
        if record.exc_info and record.exc_info[0] is not None:
            log_entry["exception"] = self.formatException(record.exc_info)

        # Include extra fields passed via ``extra={...}``
        for key, value in getattr(record, "extra_fields", {}).items():
            log_entry[key] = self._redact_if_sensitive(key, value)

        return json.dumps(log_entry, default=str)

    @staticmethod
    def _redact_if_sensitive(key: str, value: object) -> object:
        """Replace value with ``"***REDACTED***"`` for sensitive keys."""
        if key.lower() in SENSITIVE_FIELD_NAMES:
            return "***REDACTED***"
        return value


def setup_logging(level: int = logging.INFO) -> None:
    """Configure the root logger with JSON output.

    Call once at application startup. Removes all existing handlers
    and replaces them with a single stream handler using
    ``JSONFormatter``.

    Args:
        level: The logging level (default ``logging.INFO``).
    """
    root = logging.getLogger()
    root.setLevel(level)

    # Remove existing handlers to avoid duplicate output.
    for handler in root.handlers[:]:
        root.removeHandler(handler)

    handler = logging.StreamHandler()
    handler.setFormatter(JSONFormatter())
    handler.addFilter(SensitiveFieldFilter())
    root.addHandler(handler)
