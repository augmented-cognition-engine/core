# engine/atc/scheduler.py
"""ATC Scheduler — capability-aware task scheduling.

Sits between the TaskRunner poll loop and task execution. Before a task
is cleared for execution, the scheduler:

1. Resolves which capabilities the task will touch (via graph or description)
2. Registers the task as a flight
3. Checks for capability conflicts with active flights
4. If clear: transitions to 'cleared' (task can execute)
5. If blocked: transitions to 'holding' (task stays queued)

After execution completes:
6. Transitions to 'landing' then 'landed'
7. Releases capability locks
8. Clears any holding flights that were waiting on this one
"""

from __future__ import annotations

import logging

from core.engine.atc.registry import FlightRegistry
from core.engine.core.db import parse_rows

logger = logging.getLogger(__name__)


class ATCScheduler:
    """Capability-aware task scheduling for the TaskRunner."""

    def __init__(self, db_pool):
        self._pool = db_pool
        self._registry = FlightRegistry(db_pool=db_pool)
        # Track flight_id per queue_id so we can transition on completion
        self._queue_to_flight: dict[str, str] = {}

    async def try_clear(self, queue_id: str, item: dict, product_id: str) -> bool:
        """Attempt to clear a task for execution.

        Returns True if cleared (task can execute), False if blocked
        (task should stay queued / enter holding pattern).
        """
        # 1. Resolve capabilities for this task
        capabilities = await self._resolve_capabilities(item, product_id)

        if not capabilities:
            # No capabilities resolved — let it through (can't enforce ATC)
            logger.debug("No capabilities resolved for %s — bypassing ATC", queue_id)
            return True

        # 2. Register as a flight (if not already registered)
        flight_id = self._queue_to_flight.get(queue_id)

        if not flight_id:
            flight = await self._registry.register(
                product_id=product_id,
                source="task",
                source_id=queue_id,
                title=item.get("title", item.get("description", "")[:80]),
                capabilities=capabilities,
                files_predicted=item.get("files_predicted", []),
                priority=item.get("priority", 50),
            )
            flight_id = flight.id
            self._queue_to_flight[queue_id] = flight_id

        # 3. Check for capability conflicts
        conflicts = await self._registry.check_capability_conflicts(
            capabilities=capabilities,
            product_id=product_id,
            exclude_flight=flight_id,
        )

        if conflicts:
            # Blocked — put in holding pattern
            blocker = conflicts[0]  # blocked by highest-priority conflict
            try:
                await self._registry.hold(flight_id, blocked_by=blocker.id)
            except Exception as exc:
                logger.debug("Hold transition failed (may already be holding): %s", exc)

            logger.info(
                "ATC: task %s holding — capability conflict with %s (%s)",
                queue_id,
                blocker.source_id,
                ", ".join(c for c in capabilities if c in blocker.capabilities),
            )
            return False

        # 4. Clear for execution
        try:
            await self._registry.transition(flight_id, "cleared")
        except Exception as exc:
            logger.debug("Clear transition failed: %s", exc)

        logger.info("ATC: task %s cleared for execution (capabilities: %s)", queue_id, capabilities)
        return True

    async def on_execution_start(self, queue_id: str) -> None:
        """Called when task execution actually begins."""
        flight_id = self._queue_to_flight.get(queue_id)
        if flight_id:
            try:
                await self._registry.transition(flight_id, "active")
            except Exception as exc:
                logger.debug("Active transition failed: %s", exc)

    async def on_execution_complete(
        self, queue_id: str, product_id: str, files_actual: list[str] | None = None
    ) -> None:
        """Called when task execution finishes successfully.

        Transitions: active → landing → landed, then clears holding flights.
        """
        flight_id = self._queue_to_flight.pop(queue_id, None)
        if not flight_id:
            return

        try:
            if files_actual:
                await self._registry.update_files_actual(flight_id, files_actual)

            await self._registry.transition(flight_id, "landing")
            await self._registry.transition(flight_id, "landed")

            # Cascade: clear any flights that were waiting on this one
            cleared = await self._registry.clear_holding_flights(flight_id, product_id)
            if cleared:
                logger.info(
                    "ATC: %d flights cleared after %s landed",
                    len(cleared),
                    queue_id,
                )
        except Exception as exc:
            logger.warning("ATC completion handling failed for %s: %s", queue_id, exc)

    async def on_execution_failed(self, queue_id: str, product_id: str) -> None:
        """Called when task execution fails."""
        flight_id = self._queue_to_flight.pop(queue_id, None)
        if not flight_id:
            return

        try:
            await self._registry.transition(flight_id, "failed")

            # Still cascade — holding flights should re-evaluate
            await self._registry.clear_holding_flights(flight_id, product_id)
        except Exception as exc:
            logger.debug("ATC failure handling: %s", exc)

    async def _resolve_capabilities(self, item: dict, product_id: str) -> list[str]:
        """Resolve which capabilities a task will touch.

        Priority:
        1. Explicit capabilities on the queue item (from decomposition)
        2. Work item's capabilities (from the initiative's decomposition)
        3. Graph-based: map predicted files → capabilities via realizes edges
        4. Graph-based: extract file refs from description → capabilities
        """
        # 1. Explicit capabilities
        caps = item.get("capabilities", [])
        if caps:
            return caps

        # 2. From work item (if this task is part of an initiative)
        work_item_id = item.get("work_item_id")
        if work_item_id:
            try:
                async with self._pool.connection() as db:
                    result = await db.query(
                        "SELECT capabilities FROM ONLY <record>$id",
                        {"id": work_item_id},
                    )
                    rows = parse_rows(result)
                    if rows and rows[0].get("capabilities"):
                        return rows[0]["capabilities"]
            except Exception:
                pass

        # 3. From predicted files → graph realizes edges
        files = item.get("files_predicted", [])
        if not files:
            # Try to extract from description (look for file-like patterns)
            desc = item.get("description", "")
            files = [w for w in desc.split() if "/" in w and "." in w.split("/")[-1]]

        if files:
            try:
                async with self._pool.connection() as db:
                    result = await db.query(
                        """SELECT out.slug AS slug FROM realizes
                        WHERE in.path IN $paths
                        GROUP BY slug""",
                        {"paths": files},
                    )
                    rows = parse_rows(result)
                    caps = [r["slug"] for r in rows if r.get("slug")]
                    if caps:
                        return caps
            except Exception:
                pass

        return []
