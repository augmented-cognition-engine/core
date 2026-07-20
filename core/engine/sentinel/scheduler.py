# engine/sentinel/scheduler.py
"""SentinelScheduler — APScheduler wrapper for overnight engine execution.

Starts/stops APScheduler's AsyncIOScheduler in-process with FastAPI.
Iterates the engine registry to create cron jobs. Logs every execution
to the engine_run table. Stateless on restart.

Spec: docs/superpowers/specs/2026-03-21-phase3a-scheduler-signals.md §1
"""

from __future__ import annotations

import asyncio
import logging
import time
from typing import Any

from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger

from core.engine.core.db import parse_rows
from core.engine.sentinel.registry import engine_registry, get_engine

logger = logging.getLogger(__name__)


class SentinelScheduler:
    """Wraps APScheduler to run registered sentinel engines on cron schedules."""

    def __init__(
        self,
        db_pool: Any,
        default_org_id: str = "product:platform",
    ) -> None:
        self._db_pool = db_pool
        self._default_org_id = default_org_id
        self._scheduler: AsyncIOScheduler | None = None
        self._running = False
        self._running_engines: set[str] = set()
        self._lock = asyncio.Lock()

    @property
    def running(self) -> bool:
        return self._running

    async def load_overrides(self, product_id: str) -> dict[str, dict]:
        """Load engine schedule overrides from DB for the given org.

        Returns {engine_name: {cron: str|None, enabled: bool}}.
        Returns empty dict if no overrides exist.
        """
        try:
            async with self._db_pool.connection() as db:
                rows = await db.query(
                    """
                    SELECT engine, cron, enabled FROM engine_schedule_override
                    WHERE product = <record>$product
                    """,
                    {"product": product_id},
                )
            parsed = parse_rows(rows)
            return {row["engine"]: {"cron": row.get("cron"), "enabled": row.get("enabled", True)} for row in parsed}
        except Exception as exc:
            logger.warning(f"Failed to load schedule overrides: {exc}")
            return {}

    def start(self, overrides: dict[str, dict] | None = None) -> None:
        """Register all engines from the registry and start the APScheduler.

        Args:
            overrides: Optional dict of {engine_name: {cron, enabled}} from load_overrides().
                       Disabled engines are skipped. Cron overrides replace registry defaults.
        """
        # Extension-contributed sentinels register through the extension API at
        # flavor-load time — make sure they are in engine_registry before we
        # schedule. ensure_loaded() never raises (loader contract).
        from core.engine.extensions.loader import ensure_loaded

        ensure_loaded()

        self._scheduler = AsyncIOScheduler()
        overrides = overrides or {}

        skipped = 0
        for name, entry in engine_registry.items():
            override = overrides.get(name, {})

            # Skip disabled engines
            if override.get("enabled") is False:
                logger.info(f"Engine {name} disabled by override — skipping")
                skipped += 1
                continue

            # Use override cron if provided, else registry default
            cron = override.get("cron") or entry["cron"]

            trigger = CronTrigger.from_crontab(cron)
            self._scheduler.add_job(
                self._run_engine_job,
                trigger=trigger,
                args=[name, self._default_org_id],
                id=f"sentinel_{name}",
                name=f"sentinel:{name}",
                replace_existing=True,
            )
            logger.info(f"Registered engine: {name} ({cron})")

        self._scheduler.start()
        self._running = True
        logger.info(
            f"Sentinel scheduler started with {len(engine_registry) - skipped} engine(s)"
            f" ({skipped} disabled by override)"
        )

    def reschedule_engine(self, name: str, cron: str) -> None:
        """Change the cron schedule for a running engine.

        Removes the existing APScheduler job and adds a new one with the
        updated trigger. If the job was previously disabled (not in scheduler),
        adds it fresh.
        """
        if self._scheduler is None:
            raise RuntimeError("Scheduler not started")

        entry = get_engine(name)
        if entry is None:
            raise KeyError(f"Engine '{name}' not registered")

        job_id = f"sentinel_{name}"
        # Remove existing job if present
        existing = self._scheduler.get_job(job_id)
        if existing:
            self._scheduler.remove_job(job_id)

        trigger = CronTrigger.from_crontab(cron)
        self._scheduler.add_job(
            self._run_engine_job,
            trigger=trigger,
            args=[name, self._default_org_id],
            id=job_id,
            name=f"sentinel:{name}",
            replace_existing=True,
        )
        logger.info(f"Rescheduled engine: {name} ({cron})")

    def disable_engine(self, name: str) -> None:
        """Remove an engine's APScheduler job so it will no longer run."""
        if self._scheduler is None:
            raise RuntimeError("Scheduler not started")

        job_id = f"sentinel_{name}"
        existing = self._scheduler.get_job(job_id)
        if existing:
            self._scheduler.remove_job(job_id)
            logger.info(f"Disabled engine: {name}")
        else:
            logger.debug(f"disable_engine: {name} not found in scheduler (already disabled?)")

    def enable_engine(self, name: str, cron: str) -> None:
        """Add an engine's APScheduler job back (re-enable a disabled engine)."""
        if self._scheduler is None:
            raise RuntimeError("Scheduler not started")

        entry = get_engine(name)
        if entry is None:
            raise KeyError(f"Engine '{name}' not registered")

        job_id = f"sentinel_{name}"
        trigger = CronTrigger.from_crontab(cron)
        self._scheduler.add_job(
            self._run_engine_job,
            trigger=trigger,
            args=[name, self._default_org_id],
            id=job_id,
            name=f"sentinel:{name}",
            replace_existing=True,
        )
        logger.info(f"Enabled engine: {name} ({cron})")

    def shutdown(self) -> None:
        """Stop the APScheduler gracefully."""
        if self._scheduler and self._running:
            self._scheduler.shutdown(wait=False)
            self._running = False
            logger.info("Sentinel scheduler stopped")

    async def _run_engine_job(self, engine_name: str, product_id: str) -> None:
        """Cron job wrapper — acquires DB connection, calls execute_engine."""
        async with self._db_pool.connection() as db:
            await self.execute_engine(engine_name, product_id, db=db)

    async def execute_engine(
        self,
        engine_name: str,
        product_id: str,
        db: Any,
    ) -> dict[str, Any]:
        """Execute a single engine, logging to engine_run table.

        Can be called directly for manual triggers (POST /sentinel/trigger).
        Returns the engine_run result dict.
        """
        entry = get_engine(engine_name)
        if entry is None:
            raise KeyError(f"Engine '{engine_name}' not registered")

        # Prevent concurrent execution of the same engine
        async with self._lock:
            if engine_name in self._running_engines:
                logger.info(f"Engine {engine_name} already running, skipping")
                return {"status": "skipped", "reason": "already running"}
            self._running_engines.add(engine_name)

        try:
            return await self._execute_engine_inner(engine_name, entry, product_id, db)
        finally:
            self._running_engines.discard(engine_name)

    async def _execute_engine_inner(self, engine_name: str, entry: dict, product_id: str, db: Any) -> dict[str, Any]:
        """Inner execution logic — called after concurrency guard."""
        # Trigger gate: when an engine declares a `trigger`, run it first.
        # False → skip; True → proceed. Triggers are pure DB reads (no LLM
        # calls). On exception, the trigger primitives fail-open (return True),
        # so we never silently disable an engine here.
        trigger = entry.get("trigger")
        if trigger is not None:
            try:
                should_run = await trigger(product_id)
            except Exception as exc:
                logger.warning("engine %s trigger raised; running anyway: %s", engine_name, exc)
                should_run = True
            if not should_run:
                from core.engine.core.metrics import sentinel_engine_total

                sentinel_engine_total.labels(engine=engine_name, status="skipped").inc()
                logger.info("engine %s skipped by trigger", engine_name)
                return {"status": "skipped", "reason": "trigger_returned_false"}

        # Create engine_run record with status='running'
        create_result = await db.query(
            """
            CREATE engine_run SET
                product = <record>$product,
                engine = $engine,
                status = 'running',
                started_at = time::now()
            """,
            {"product": product_id, "engine": engine_name},
        )
        from core.engine.core.db import parse_one

        raw = parse_one(create_result)
        run_id = raw["id"] if raw else "unknown"

        # Propagate sentinel run_id as correlation ID so all log records are traceable
        from core.engine.core.log_context import set_correlation_id

        set_correlation_id(str(run_id))

        from core.engine.core.metrics import sentinel_engine_duration, sentinel_engine_total

        start_time = time.monotonic()
        try:
            result = await entry["fn"](product_id)
            duration_ms = int((time.monotonic() - start_time) * 1000)

            sentinel_engine_duration.labels(engine=engine_name).observe(duration_ms / 1000)
            sentinel_engine_total.labels(engine=engine_name, status="completed").inc()

            update_result = await db.query(
                """
                UPDATE <record>$run_id SET
                    status = 'completed',
                    results = $results,
                    duration_ms = $duration_ms,
                    completed_at = time::now(),
                    cost = $cost
                """,
                {
                    "run_id": run_id,
                    "results": result,
                    "duration_ms": duration_ms,
                    "cost": result.get("cost", 0.0) if isinstance(result, dict) else 0.0,
                },
            )
            if isinstance(update_result, str):
                logger.warning(f"Engine {engine_name} run UPDATE failed: {update_result}")
            logger.info(f"Engine {engine_name} completed in {duration_ms}ms: {result}")

            try:
                from core.engine.events.bus import bus as _bus

                await _bus.emit(
                    "engine_run.completed",
                    {
                        "engine": engine_name,
                        "product_id": product_id,
                        "engine_run_id": str(run_id),
                        "duration_ms": duration_ms,
                    },
                )
            except Exception as _emit_exc:
                logger.debug("engine_run.completed emit failed (non-fatal): %s", _emit_exc)

            return {
                "engine_run_id": str(run_id),
                "status": "completed",
                "results": result,
                "duration_ms": duration_ms,
            }

        except Exception as exc:
            duration_ms = int((time.monotonic() - start_time) * 1000)
            error_msg = f"{type(exc).__name__}: {exc}"

            sentinel_engine_duration.labels(engine=engine_name).observe(duration_ms / 1000)
            sentinel_engine_total.labels(engine=engine_name, status="failed").inc()

            from core.engine.core.error_buffer import error_buffer
            from core.engine.core.log_context import get_correlation_id

            error_buffer.record(
                source=f"sentinel.{engine_name}",
                error_type=type(exc).__name__,
                message=str(exc),
                cid=get_correlation_id(),
                context={"engine": engine_name, "duration_ms": duration_ms},
            )

            await db.query(
                """
                UPDATE <record>$run_id SET
                    status = 'failed',
                    error = $error,
                    duration_ms = $duration_ms,
                    completed_at = time::now()
                """,
                {
                    "run_id": run_id,
                    "error": error_msg,
                    "duration_ms": duration_ms,
                },
            )
            logger.error(f"Engine {engine_name} failed: {error_msg}")
            return {
                "engine_run_id": str(run_id),
                "status": "failed",
                "error": error_msg,
                "duration_ms": duration_ms,
            }
