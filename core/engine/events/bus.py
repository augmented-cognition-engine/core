"""Event bus — lightweight in-process event system for reactive automation.

Events are fire-and-forget: handlers run as background tasks via asyncio.
This is NOT a message queue — it's a single-process pub/sub for triggering
automations without blocking the request path.
"""

from __future__ import annotations

import asyncio
import logging
from collections import defaultdict
from typing import Callable

# decision:znalk48vc0rluxl1ejdg — logged_task keeps a stable reference to
# the dispatched task and ensures any unhandled exception is logged + recorded.
from core.engine.core.tasks import logged_task

logger = logging.getLogger(__name__)


class EventBus:
    """In-process event bus with async handler dispatch."""

    def __init__(self) -> None:
        self._handlers: dict[str, list[Callable]] = defaultdict(list)
        self._emit_count: int = 0
        self._error_count: int = 0

    def _validate_event(self, event_type: str, payload: dict) -> None:
        """Validate event_type and payload before dispatch.

        Raises ValueError if event_type is empty, contains whitespace, or if
        payload is not a dict.  These invariants prevent handlers from receiving
        malformed events that could silently corrupt state.
        """
        if not event_type or not event_type.strip():
            raise ValueError(f"event_type must be non-empty, got {event_type!r}")
        if " " in event_type:
            raise ValueError(f"event_type must not contain spaces: {event_type!r}")
        if not isinstance(payload, dict):
            raise ValueError(f"payload must be a dict, got {type(payload).__name__}")

    def get_stats(self) -> dict:
        """Return emission statistics for monitoring and health checks."""
        return {
            "emit_count": self._emit_count,
            "error_count": self._error_count,
            "registered_event_types": len(self._handlers),
            "total_handlers": sum(len(h) for h in self._handlers.values()),
        }

    def on(self, event_type: str, handler: Callable) -> None:
        """Register a handler for an event type."""
        self._handlers[event_type].append(handler)
        logger.debug("Registered handler for %s: %s", event_type, handler.__name__)

    def off(self, event_type: str, handler: Callable) -> None:
        """Unregister a handler."""
        if handler in self._handlers[event_type]:
            self._handlers[event_type].remove(handler)

    async def emit(self, event_type: str, payload: dict) -> None:
        """Emit an event. Handlers run as fire-and-forget background tasks.

        Never raises — validation failures and handler errors are logged but
        do not propagate so event emission is always safe to call.
        """
        try:
            self._validate_event(event_type, payload)
        except ValueError as exc:
            logger.warning("Invalid event rejected: %s", exc)
            self._error_count += 1
            return

        handlers = self._handlers.get(event_type, []) + self._handlers.get("*", [])
        if not handlers:
            return

        self._emit_count += 1
        logger.debug("Emitting %s to %d handler(s)", event_type, len(handlers))

        for handler in handlers:
            try:
                logged_task(
                    _safe_call(handler, event_type, payload),
                    label=f"events.bus.{event_type}",
                )
            except Exception as exc:
                logger.warning("Failed to schedule handler for %s: %s", event_type, exc)
                self._error_count += 1

    def list_handlers(self) -> dict[str, list[str]]:
        """List all registered handlers by event type (for debugging)."""
        return {
            event_type: [h.__name__ for h in handlers] for event_type, handlers in self._handlers.items() if handlers
        }


async def _safe_call(handler: Callable, event_type: str, payload: dict) -> None:
    """Call a handler safely, catching and logging any exception."""
    logger.debug("Dispatching %s → %s", event_type, handler.__name__)
    try:
        result = handler(event_type, payload)
        if asyncio.iscoroutine(result):
            await result
        logger.debug("Handler %s completed for %s", handler.__name__, event_type)
    except Exception as exc:
        logger.warning("Handler %s failed for %s: %s", handler.__name__, event_type, exc)


# Singleton event bus instance
bus = EventBus()
