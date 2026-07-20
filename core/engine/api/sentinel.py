# engine/api/sentinel.py
"""Sentinel API — scheduler status, engine run history, manual triggers,
schedule override management.

GET  /sentinel/status              — scheduler status + enriched engine list
GET  /sentinel/runs                — engine run history (filterable by engine name)
POST /sentinel/trigger/{name}      — manually trigger an engine run
PUT  /sentinel/schedule/{name}     — update cron / enabled for an engine

Spec: docs/superpowers/specs/2026-03-21-phase3a-scheduler-signals.md
"""

from __future__ import annotations

from datetime import datetime, timezone

from croniter import croniter
from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel

from core.engine.core.auth import get_current_user
from core.engine.core.db import parse_one, parse_rows, pool
from core.engine.sentinel.registry import get_engine, list_engines
from core.engine.sentinel.scheduler import SentinelScheduler

# ---------------------------------------------------------------------------
# Display metadata
# ---------------------------------------------------------------------------

ENGINE_DISPLAY_NAMES: dict[str, str] = {
    "evaluator_honesty": "Evaluator Honesty",
    "simplicity_audit": "Simplicity Audit",
    "knowledge_verifier": "Knowledge Verifier",
    "failure_analysis": "Failure Analysis",
    "calibration": "Calibration",
    "gap_analyzer": "Gap Analyzer",
    "gap_researcher": "Gap Researcher",
    "domain_research": "Domain Research",
    "specialty_deepener": "Specialty Deepener",
    "seam_analyzer": "Seam Analyzer",
    "perspective_gap_detector": "Perspective Gaps",
    "adversarial_synthesis": "Adversarial Synthesis",
    "question_generator": "Question Generator",
    "self_optimizer": "Self Optimizer",
    "template_detector": "Template Detector",
    "pm_optimizer": "PM Optimizer",
    "ecosystem_scanner": "Ecosystem Scanner",
    "competitive_observer": "Competitive Observer",
    "briefing_generator": "Briefing Generator",
    "idea_incubator": "Idea Incubator",
    "decay_manager": "Decay Manager",
    "conflict_detector": "Conflict Detector",
}

ENGINE_GROUPS: dict[str, str] = {
    "evaluator_honesty": "verification",
    "simplicity_audit": "verification",
    "knowledge_verifier": "verification",
    "failure_analysis": "overnight_intelligence",
    "calibration": "overnight_intelligence",
    "gap_analyzer": "overnight_intelligence",
    "gap_researcher": "overnight_intelligence",
    "domain_research": "overnight_intelligence",
    "specialty_deepener": "overnight_intelligence",
    "seam_analyzer": "product_quality",
    "perspective_gap_detector": "product_quality",
    "adversarial_synthesis": "product_quality",
    "question_generator": "product_quality",
    "self_optimizer": "optimization",
    "template_detector": "optimization",
    "pm_optimizer": "optimization",
    "ecosystem_scanner": "external",
    "competitive_observer": "external",
    "briefing_generator": "reporting",
    "idea_incubator": "reporting",
    "decay_manager": "maintenance",
    "conflict_detector": "maintenance",
}


# ---------------------------------------------------------------------------
# Cron validation
# ---------------------------------------------------------------------------

_MIN_INTERVAL_MINUTES = 15


def _validate_cron(cron_expr: str) -> tuple[bool, str]:
    """Validate a 5-field cron expression with minimum 15-minute interval.

    Returns (True, "") on success, (False, "reason") on failure.
    """
    parts = cron_expr.strip().split()
    if len(parts) != 5:
        return False, f"cron must have exactly 5 fields, got {len(parts)}"

    try:
        base = datetime(2026, 1, 1, 0, 0, tzinfo=timezone.utc)
        it = croniter(cron_expr, base)
        t1 = it.get_next(datetime)
        t2 = it.get_next(datetime)
    except Exception as exc:
        return False, f"invalid cron syntax: {exc}"

    interval_minutes = (t2 - t1).total_seconds() / 60
    if interval_minutes < _MIN_INTERVAL_MINUTES:
        return False, (f"minimum schedule interval is {_MIN_INTERVAL_MINUTES} minutes, got ~{interval_minutes:.0f} min")

    return True, ""


def _next_run_from_cron(cron_expr: str) -> str | None:
    """Calculate next run time from a cron expression."""
    try:
        cron = croniter(cron_expr, datetime.now(timezone.utc))
        return cron.get_next(datetime).isoformat()
    except Exception:
        return None


# ---------------------------------------------------------------------------
# Pydantic models
# ---------------------------------------------------------------------------


class ScheduleUpdate(BaseModel):
    cron: str | None = None
    enabled: bool | None = None


# ---------------------------------------------------------------------------
# Router
# ---------------------------------------------------------------------------

router = APIRouter(prefix="/sentinel", tags=["sentinel"])

# Module-level scheduler reference — set by main.py during lifespan
_scheduler: SentinelScheduler | None = None


def set_scheduler(scheduler: SentinelScheduler) -> None:
    """Called by main.py lifespan to set the active scheduler instance."""
    global _scheduler
    _scheduler = scheduler


def get_scheduler() -> SentinelScheduler | None:
    """Return the active sentinel scheduler, or None if not yet started."""
    return _scheduler


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------


@router.get("/status")
async def sentinel_status(
    product: str = Query(default="product:default"),
    user=Depends(get_current_user),
):
    """Return scheduler status and enriched engine list with last run info."""
    engines = list_engines()

    # Load overrides for this org
    async with pool.connection() as db:
        override_rows = await db.query(
            """
            SELECT engine, cron, enabled FROM engine_schedule_override
            WHERE product = <record>$product
            """,
            {"product": product},
        )
    overrides: dict[str, dict] = {}
    for row in parse_rows(override_rows):
        overrides[row["engine"]] = {"cron": row.get("cron"), "enabled": row.get("enabled", True)}

    # Fetch last run for each engine
    engine_status = []
    async with pool.connection() as db:
        for eng in engines:
            rows = await db.query(
                """
                SELECT * FROM engine_run
                WHERE engine = $engine
                ORDER BY started_at DESC
                LIMIT 1
                """,
                {"engine": eng["name"]},
            )
            last_run = None
            runs = parse_rows(rows)
            if runs:
                r = runs[0]
                last_run = {
                    "started_at": r.get("started_at"),
                    "status": r.get("status"),
                    "duration_ms": r.get("duration_ms"),
                }

            name = eng["name"]
            override = overrides.get(name, {})
            default_cron = eng["cron"]
            effective_cron = override.get("cron") or default_cron
            enabled = override.get("enabled", True)
            overridden = name in overrides

            engine_status.append(
                {
                    "name": name,
                    "display_name": ENGINE_DISPLAY_NAMES.get(name, name),
                    "group": ENGINE_GROUPS.get(name, "other"),
                    "cron": effective_cron,
                    "default_cron": default_cron,
                    "enabled": enabled,
                    "overridden": overridden,
                    "description": eng["description"],
                    "last_run": last_run,
                    "next_run": _next_run_from_cron(effective_cron) if enabled else None,
                }
            )

    return {
        "scheduler_running": _scheduler.running if _scheduler else False,
        "engines": engine_status,
    }


@router.get("/runs")
async def sentinel_runs(
    product: str = Query(default="product:default"),
    engine: str | None = Query(default=None),
    limit: int = Query(default=20, le=100),
    user=Depends(get_current_user),
):
    """Return engine run history, optionally filtered by engine name."""
    async with pool.connection() as db:
        if engine:
            rows = await db.query(
                """
                SELECT * FROM engine_run
                WHERE product = <record>$product AND engine = $engine
                ORDER BY started_at DESC
                LIMIT $limit
                """,
                {"product": product, "engine": engine, "limit": limit},
            )
        else:
            rows = await db.query(
                """
                SELECT * FROM engine_run
                WHERE product = <record>$product
                ORDER BY started_at DESC
                LIMIT $limit
                """,
                {"product": product, "limit": limit},
            )

        runs = parse_rows(rows)

    return {"runs": runs}


@router.post("/trigger/{engine_name}")
async def sentinel_trigger(
    engine_name: str,
    product: str = Query(default="product:default"),
    user=Depends(get_current_user),
):
    """Manually trigger an engine run. Returns the engine_run ID for polling."""
    entry = get_engine(engine_name)
    if entry is None:
        raise HTTPException(status_code=404, detail=f"Engine '{engine_name}' not found")

    if _scheduler is None:
        raise HTTPException(status_code=503, detail="Scheduler not initialized")

    async with pool.connection() as db:
        result = await _scheduler.execute_engine(engine_name, product, db=db)

    return result


@router.put("/schedule/{engine_name}")
async def update_schedule(
    engine_name: str,
    body: ScheduleUpdate,
    product: str = Query(default="product:default"),
    user=Depends(get_current_user),
):
    """Update the cron schedule and/or enabled state for an engine.

    Merges with any existing override — fields not included in the request
    body retain their current values. Immediately applies the change to the
    running scheduler.
    """
    entry = get_engine(engine_name)
    if entry is None:
        raise HTTPException(status_code=404, detail=f"Engine '{engine_name}' not registered")

    # Validate cron if provided
    if body.cron is not None:
        valid, reason = _validate_cron(body.cron)
        if not valid:
            raise HTTPException(status_code=422, detail=f"Invalid cron: {reason}")

    async with pool.connection() as db:
        # Read existing override to merge
        existing_rows = await db.query(
            """
            SELECT cron, enabled FROM engine_schedule_override
            WHERE product = <record>$product AND engine = $engine
            LIMIT 1
            """,
            {"product": product, "engine": engine_name},
        )
        existing = parse_one(existing_rows) or {}

        # Merge: request fields override existing, keep existing where not specified
        merged_cron = body.cron if body.cron is not None else existing.get("cron")
        merged_enabled = body.enabled if body.enabled is not None else existing.get("enabled", True)

        # Upsert override
        await db.query(
            """
            UPSERT engine_schedule_override
              SET product = <record>$product,
                  engine = $engine,
                  cron = $cron,
                  enabled = $enabled
              WHERE product = <record>$product AND engine = $engine
            """,
            {
                "product": product,
                "engine": engine_name,
                "cron": merged_cron,
                "enabled": merged_enabled,
            },
        )

    # Apply to running scheduler
    if _scheduler is not None and _scheduler.running:
        effective_cron = merged_cron or entry["cron"]
        if not merged_enabled:
            _scheduler.disable_engine(engine_name)
        else:
            _scheduler.reschedule_engine(engine_name, effective_cron)

    return {
        "status": "ok",
        "engine": engine_name,
        "cron": merged_cron,
        "enabled": merged_enabled,
    }
