import asyncio
import logging

from core.engine.core.db import parse_record_ids

logger = logging.getLogger(__name__)


class TaskRunner:
    """Watches task_queue and executes items with concurrency control.

    Runs as an asyncio task within FastAPI lifespan.
    """

    def __init__(self, db_pool, default_org: str = "product:default"):
        self._pool = db_pool
        self._org = default_org
        self._task: asyncio.Task | None = None
        self._running = False
        self._active: dict[str, asyncio.Task] = {}  # queue_id -> execution task
        self._scheduler = None  # ATCScheduler, lazy-loaded

    async def start(self):
        """Start the runner loop."""
        self._running = True
        # Ensure runner_config exists
        async with self._pool.connection() as db:
            existing = await db.query(
                "SELECT * FROM runner_config WHERE product = <record>$product LIMIT 1",
                {"product": self._org},
            )
            if not existing or (
                isinstance(existing, list) and not existing[0] if isinstance(existing[0], list) else not existing
            ):
                await db.query(
                    "CREATE runner_config SET product = <record>$product, status = 'running', updated_at = time::now()",
                    {"product": self._org},
                )
            else:
                await db.query(
                    "UPDATE runner_config SET status = 'running', updated_at = time::now() WHERE product = <record>$product",
                    {"product": self._org},
                )
            # Mark any previously-running items as failed (interrupted on crash)
            # Don't re-queue — mark as failed so the user can decide to retry
            await db.query(
                "UPDATE task_queue SET status = 'failed', error = 'Interrupted by restart', slot_number = NONE WHERE status = 'running' AND product = <record>$product",
                {"product": self._org},
            )

        # Initialize ATC scheduler for capability-aware sequencing
        try:
            from core.engine.atc.scheduler import ATCScheduler

            self._scheduler = ATCScheduler(db_pool=self._pool)
            logger.info("ATC scheduler initialized")
        except Exception as exc:
            logger.warning("ATC scheduler unavailable (proceeding without): %s", exc)

        self._task = asyncio.create_task(self._loop())
        logger.info("TaskRunner started for %s", self._org)

    async def stop(self):
        """Stop the runner gracefully."""
        self._running = False
        if self._task:
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass
        # Wait for active executions to finish
        if self._active:
            logger.info("Waiting for %d active tasks to finish...", len(self._active))
            await asyncio.gather(*self._active.values(), return_exceptions=True)
        async with self._pool.connection() as db:
            await db.query(
                "UPDATE runner_config SET status = 'stopped', updated_at = time::now() WHERE product = <record>$product",
                {"product": self._org},
            )
        logger.info("TaskRunner stopped")

    async def _get_config(self) -> dict:
        """Load runner config from DB."""
        async with self._pool.connection() as db:
            rows = await db.query(
                "SELECT * FROM runner_config WHERE product = <record>$product LIMIT 1",
                {"product": self._org},
            )
            if rows and isinstance(rows[0], dict):
                return rows[0]
            if rows and isinstance(rows[0], list) and rows[0]:
                return rows[0][0]
            return {"max_concurrent": 3, "mode": "all", "status": "running"}

    async def _loop(self):
        """Main poll loop -- check for queued items every 2 seconds."""
        logger.info("Runner loop starting")
        while self._running:
            try:
                config = await self._get_config()

                # Respect pause/stop
                if config.get("status") == "paused" or config.get("mode") == "paused":
                    await asyncio.sleep(2)
                    continue

                # Clean up finished tasks
                done = [qid for qid, t in self._active.items() if t.done()]
                for qid in done:
                    del self._active[qid]

                max_concurrent = config.get("max_concurrent", 3)
                available_slots = max_concurrent - len(self._active)

                if available_slots <= 0:
                    await asyncio.sleep(2)
                    continue

                # Fetch next queued items
                mode = config.get("mode", "all")
                mode_filter = ""
                if mode == "user_only":
                    mode_filter = "AND source = 'user'"

                async with self._pool.connection() as db:
                    rows = await db.query(
                        f"""
                        SELECT * FROM task_queue
                        WHERE product = <record>$product AND status = 'queued' {mode_filter}
                        ORDER BY priority ASC, created_at ASC
                        LIMIT $limit
                        """,
                        {"product": self._org, "limit": available_slots},
                    )

                items = (
                    rows
                    if isinstance(rows, list) and rows and isinstance(rows[0], dict)
                    else (rows[0] if rows and isinstance(rows[0], list) else [])
                )

                if items:
                    logger.info("Runner found %d queued items", len(items))

                for item in items:
                    if not isinstance(item, dict):
                        continue
                    qid = str(item.get("id", ""))
                    if qid in self._active:
                        continue
                    logger.info("Runner picking up: %s", qid)

                    # Check dependencies
                    deps = item.get("dependencies", [])
                    if deps:
                        async with self._pool.connection() as db:
                            dep_check = await db.query(
                                "SELECT id, status FROM task_queue WHERE id IN $deps",
                                {"deps": parse_record_ids(deps)},
                            )
                            dep_items = (
                                dep_check
                                if isinstance(dep_check, list) and dep_check and isinstance(dep_check[0], dict)
                                else (dep_check[0] if dep_check and isinstance(dep_check[0], list) else [])
                            )
                            blocked = any(
                                d.get("status") not in ("completed",) for d in dep_items if isinstance(d, dict)
                            )
                            if blocked:
                                continue

                    # ATC: check capability conflicts before clearing for execution
                    if self._scheduler:
                        cleared = await self._scheduler.try_clear(qid, item, self._org)
                        if not cleared:
                            continue  # holding — skip to next item

                    # Mark as running
                    slot = len(self._active) + 1
                    raw_id = item["id"]  # Keep original RecordID object
                    async with self._pool.connection() as db:
                        await db.query(
                            "UPDATE <record>$id SET status = 'running', slot_number = $slot, started_at = time::now()",
                            {"id": raw_id, "slot": slot},
                        )

                    # Start execution
                    self._active[qid] = asyncio.create_task(self._execute_item(raw_id, item))

            except asyncio.CancelledError:
                break
            except Exception as exc:
                logger.error("Runner loop error: %s", exc)

            await asyncio.sleep(2)

    async def _execute_item(self, queue_id, item: dict):
        """Execute a single queue item via SessionRunner."""
        product_id = str(item.get("product", self._org))
        qid = str(queue_id)

        # ATC: notify execution start
        if self._scheduler:
            await self._scheduler.on_execution_start(qid)

        try:
            from core.engine.live.session_runner import SessionRunner

            runner = SessionRunner(db_pool=self._pool)
            result = await runner.run(
                queue_item={
                    "description": item.get("description", ""),
                    "work_item_id": item.get("work_item_id"),
                },
                product_id=product_id,
            )

            async with self._pool.connection() as db:
                await db.query(
                    """UPDATE <record>$id SET
                        status = 'completed', output = $output,
                        domain_path = $domain, task_id = $task_id,
                        cost = $cost, completed_at = time::now(),
                        slot_number = NONE""",
                    {
                        "id": queue_id,
                        "output": result.output[:500],
                        "domain": result.classification.get("domain_path", ""),
                        "task_id": result.task_id or "",
                        "cost": 0.0,
                    },
                )
            logger.info("Queue item %s completed", queue_id)

            # Feed completed task output into always-on capture pipeline
            try:
                from core.engine.capture.service import capture_service

                await capture_service.emit_task_completion(
                    product_id=product_id,
                    task_id=result.task_id or str(queue_id),
                    description=item.get("description", ""),
                    output=result.output,
                    discipline=result.classification.get("discipline", result.classification.get("domain_path", "")),
                    workspace_id=str(item.get("workspace", "")) or None,
                )
            except Exception as exc:
                logger.debug("Capture emit failed for queue item %s: %s", queue_id, exc)

            # ATC: land the flight, release capabilities, clear holding flights
            if self._scheduler:
                await self._scheduler.on_execution_complete(qid, product_id)

        except Exception as exc:
            logger.error("Queue item %s failed: %s", queue_id, exc)
            async with self._pool.connection() as db:
                await db.query(
                    "UPDATE <record>$id SET status = 'failed', error = $err, completed_at = time::now(), slot_number = NONE",
                    {"id": queue_id, "err": str(exc)[:500]},
                )

            # ATC: mark flight as failed, release capabilities
            if self._scheduler:
                await self._scheduler.on_execution_failed(qid, product_id)

    async def get_status(self) -> dict:
        """Get current runner status."""
        config = await self._get_config()

        async with self._pool.connection() as db:
            active = await db.query(
                "SELECT * FROM task_queue WHERE product = <record>$product AND status = 'running'",
                {"product": self._org},
            )
            queued = await db.query(
                "SELECT count() FROM task_queue WHERE product = <record>$product AND status = 'queued' GROUP ALL",
                {"product": self._org},
            )
            completed = await db.query(
                "SELECT count() FROM task_queue WHERE product = <record>$product AND status = 'completed' AND completed_at > time::now() - 24h GROUP ALL",
                {"product": self._org},
            )

        active_items = (
            active
            if isinstance(active, list) and active and isinstance(active[0], dict)
            else (active[0] if active and isinstance(active[0], list) else [])
        )
        queued_count = queued[0].get("count", 0) if queued and isinstance(queued[0], dict) else 0
        completed_count = completed[0].get("count", 0) if completed and isinstance(completed[0], dict) else 0

        return {
            "running": self._running and config.get("status") != "paused",
            "config": {
                "max_concurrent": config.get("max_concurrent", 3),
                "mode": config.get("mode", "all"),
                "auto_approve": config.get("auto_approve", True),
                "status": config.get("status", "running"),
            },
            "active_count": len(active_items),
            "queued_count": queued_count,
            "completed_today": completed_count,
            "daily_cost": config.get("daily_cost", 0.0),
            "active_items": active_items,
        }
