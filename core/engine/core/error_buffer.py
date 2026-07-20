# engine/core/error_buffer.py
"""In-memory ring buffer of recent errors for /health/ops visibility.

Keeps the last N error events without any DB dependency. Intentionally
lightweight — this is for oncall triage, not persistent audit logging.

Usage:
    from core.engine.core.error_buffer import error_buffer

    error_buffer.record(cid="abc123", source="executor", error_type="TimeoutError", message="...")
    recent = error_buffer.recent()  # list[dict], newest first
"""

from __future__ import annotations

from collections import deque
from datetime import datetime, timezone
from typing import Any


class ErrorBuffer:
    """Thread-safe (GIL) ring buffer of the most recent error events.

    Fields per entry:
        timestamp   ISO-8601 UTC
        cid         correlation ID for cross-referencing logs
        source      component name (executor, sentinel, capture, etc.)
        error_type  exception class name
        message     str(exc) or short description
        context     optional dict of extra k/v (endpoint, product_id, etc.)
    """

    def __init__(self, maxlen: int = 50) -> None:
        self._buf: deque[dict[str, Any]] = deque(maxlen=maxlen)

    def record(
        self,
        source: str,
        error_type: str,
        message: str,
        cid: str = "",
        context: dict | None = None,
    ) -> None:
        """Add an error to the buffer. Never raises."""
        try:
            self._buf.appendleft(
                {
                    "timestamp": datetime.now(timezone.utc).isoformat(),
                    "cid": cid,
                    "source": source,
                    "error_type": error_type,
                    "message": str(message)[:500],
                    "context": context or {},
                }
            )
        except Exception:
            pass  # Buffer must never affect the caller

    def recent(self, n: int | None = None) -> list[dict]:
        """Return up to *n* most recent errors (default: all)."""
        items = list(self._buf)
        return items[:n] if n is not None else items

    def clear(self) -> None:
        self._buf.clear()

    @property
    def count(self) -> int:
        return len(self._buf)


# Module-level singleton — imported by exception handler, executor, sentinel
error_buffer = ErrorBuffer()
