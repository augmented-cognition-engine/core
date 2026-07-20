# engine/core/log_context.py
"""Per-request correlation ID using contextvars.

Mirrors the token accumulator pattern (engine/core/tokens.py): set once at the
request/task boundary, readable anywhere downstream without threading through
every function signature.

Usage:
    # At API entry (set by CorrelationIDMiddleware automatically)
    cid = new_correlation_id()

    # At task/job entry (background workers, sentinel engines)
    set_correlation_id("job_gap_analyzer_abc123")

    # Anywhere in the call stack
    logger.warning("Pool exhausted [%s]", get_correlation_id())
"""

from __future__ import annotations

import json
import logging
import uuid
from contextvars import ContextVar

_correlation_id_var: ContextVar[str] = ContextVar("correlation_id", default="")


def get_correlation_id() -> str:
    """Return the current correlation ID, or empty string if none set."""
    return _correlation_id_var.get()


def set_correlation_id(cid: str) -> None:
    """Set the correlation ID for the current async context."""
    _correlation_id_var.set(cid)


def new_correlation_id() -> str:
    """Generate, set, and return a new 12-char hex correlation ID."""
    cid = uuid.uuid4().hex[:12]
    _correlation_id_var.set(cid)
    return cid


class CorrelationIDFilter(logging.Filter):
    """Inject the current correlation_id into every LogRecord.

    Install once at app startup:
        logging.getLogger().addFilter(CorrelationIDFilter())

    Every handler (console, file, JSON) then has access to
    record.correlation_id without any per-call threading.
    """

    def filter(self, record: logging.LogRecord) -> bool:
        record.correlation_id = get_correlation_id() or "-"
        return True


class JSONLogFormatter(logging.Formatter):
    """Emit each log record as a single JSON line.

    Fields: timestamp (ISO-8601), level, logger, message, correlation_id.
    Extra keys on the LogRecord (set via logger.info("…", extra={…})) are
    forwarded verbatim so callers can add span_id or other trace fields.

    Enable in production by replacing the default StreamHandler formatter:
        handler.setFormatter(JSONLogFormatter())
    """

    _SKIP = frozenset(logging.LogRecord("", 0, "", 0, "", (), None).__dict__)

    def format(self, record: logging.LogRecord) -> str:
        doc: dict = {
            "timestamp": self.formatTime(record, "%Y-%m-%dT%H:%M:%S.{ms}Z").format(ms=f"{record.msecs:03.0f}"),
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
            "correlation_id": getattr(record, "correlation_id", "-"),
        }
        if record.exc_info:
            doc["exc_info"] = self.formatException(record.exc_info)
        # Forward any extra keys the caller attached
        for key, val in record.__dict__.items():
            if key not in self._SKIP and not key.startswith("_"):
                doc[key] = val
        return json.dumps(doc, default=str)
