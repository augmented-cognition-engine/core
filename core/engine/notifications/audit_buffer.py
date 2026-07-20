"""In-memory ring buffer for recent voice text samples.

Channels (discord, in_app, proactive_line) call record() on emit; the voice
audit sweeper calls drain_recent() to pull samples for periodic scoring.

Per-process state — restarts lose unwritten samples (acceptable per spec R1).
"""

from __future__ import annotations

from collections import deque
from threading import Lock

_BUFFER: dict[tuple[str, str], deque[str]] = {}
_LOCK = Lock()
_MAX_PER_KEY = 50


def record(channel: str, product_id: str, text: str) -> None:
    """Append a sample for (channel, product). Bounded ring buffer of 50 per key."""
    if not text:
        return
    key = (channel, product_id)
    with _LOCK:
        buf = _BUFFER.get(key)
        if buf is None:
            buf = deque(maxlen=_MAX_PER_KEY)
            _BUFFER[key] = buf
        buf.append(text)


def drain_recent(channel: str, product_id: str) -> list[str]:
    """Return + clear ALL buffered samples for (channel, product).

    The deque's maxlen=_MAX_PER_KEY (50) already caps in-memory size, so there is
    no need for a per-call cap that would silently discard older samples on drain.
    Returns [] if buffer is empty.
    """
    key = (channel, product_id)
    with _LOCK:
        buf = _BUFFER.get(key)
        if buf is None:
            return []
        items = list(buf)
        buf.clear()
    return items


def _reset() -> None:
    """Test helper — clear all buffers."""
    with _LOCK:
        _BUFFER.clear()
