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
import contextvars
import logging

logger = logging.getLogger(__name__)
_background_tasks: set[asyncio.Task] = set()


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


def logged_task(
    coro,
    *,
    label: str = "unknown",
    context: contextvars.Context | None = None,
) -> asyncio.Task:
    """Create an asyncio.Task that logs and records exceptions on failure.

    Drop-in replacement for asyncio.create_task() for fire-and-forget usage.
    Exceptions are captured to error_buffer and logged at ERROR level instead
    of being silently discarded.
    """
    task = asyncio.create_task(coro, context=context)
    # asyncio keeps only weak references to tasks. Retain fire-and-forget work
    # until completion so telemetry jobs cannot disappear under GC pressure.
    _background_tasks.add(task)

    def _done(completed: asyncio.Task) -> None:
        _background_tasks.discard(completed)
        _on_task_done(label, completed)

    task.add_done_callback(_done)
    return task
