# engine/core/tasks.py
"""Safe asyncio.create_task() wrapper.

Usage:
    from core.engine.core.tasks import logged_task

    # Instead of: asyncio.create_task(my_coro())
    logged_task(my_coro(), label="my_feature.my_coro")

The label appears in error_buffer source and log messages so failures
are traceable without a stack walk.
"""

from __future__ import annotations

import asyncio
import logging

logger = logging.getLogger(__name__)


def _on_task_done(label: str, task: asyncio.Task) -> None:
    """Exception callback attached to every logged_task."""
    try:
        exc = task.exception()
    except asyncio.CancelledError:
        return  # cancellation is not an error
    if exc is None:
        return

    from core.engine.core.error_buffer import error_buffer
    from core.engine.core.log_context import get_correlation_id

    logger.error(
        "Background task %r raised %s: %s",
        label,
        type(exc).__name__,
        exc,
        exc_info=exc,
    )
    error_buffer.record(
        source=f"background_task.{label}",
        error_type=type(exc).__name__,
        message=str(exc),
        cid=get_correlation_id(),
    )


def logged_task(coro, *, label: str = "unknown") -> asyncio.Task:
    """Create an asyncio.Task that logs and records exceptions on failure.

    Drop-in replacement for asyncio.create_task() for fire-and-forget usage.
    Exceptions are captured to error_buffer and logged at ERROR level instead
    of being silently discarded.
    """
    task = asyncio.create_task(coro)
    task.add_done_callback(lambda t: _on_task_done(label, t))
    return task
