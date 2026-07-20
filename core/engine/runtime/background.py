"""Dynamic backgrounding — auto-promote long-running tasks.

Tasks can be registered as background work. They run as asyncio tasks
and notify via callback on completion. The manager tracks active tasks
and supports cancellation.

Modeled on Claude Code's dynamic backgrounding (120s auto-promote).
"""

from __future__ import annotations

import asyncio
import logging
import uuid
from typing import Any, Callable, Coroutine

logger = logging.getLogger(__name__)


class BackgroundManager:
    """Manages background tasks with lifecycle tracking."""

    def __init__(self) -> None:
        self._tasks: dict[str, dict] = {}

    def register(
        self,
        coro: Coroutine,
        label: str = "",
        on_complete: Callable[[Any], None] | None = None,
    ) -> str:
        """Register a coroutine as a background task. Returns task_id."""
        task_id = str(uuid.uuid4())[:8]
        asyncio_task = asyncio.get_event_loop().create_task(coro)

        self._tasks[task_id] = {
            "task": asyncio_task,
            "label": label or task_id,
            "on_complete": on_complete,
        }

        asyncio_task.add_done_callback(lambda t: self._on_done(task_id, t))
        return task_id

    def _on_done(self, task_id: str, task: asyncio.Task) -> None:
        entry = self._tasks.get(task_id)
        if not entry:
            return
        callback = entry.get("on_complete")
        if callback and not task.cancelled():
            try:
                callback(task.result())
            except Exception:
                logger.exception("Background task %s callback failed", task_id)
        self._tasks.pop(task_id, None)

    def is_running(self, task_id: str) -> bool:
        entry = self._tasks.get(task_id)
        return entry is not None and not entry["task"].done()

    def cancel(self, task_id: str) -> None:
        entry = self._tasks.get(task_id)
        if entry and not entry["task"].done():
            entry["task"].cancel()

    def list_running(self) -> list[dict]:
        return [
            {"task_id": tid, "label": entry["label"]} for tid, entry in self._tasks.items() if not entry["task"].done()
        ]
