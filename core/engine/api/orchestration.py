# engine/api/orchestration.py
"""Orchestration API — query persisted runs and events for debugging/replay."""

from __future__ import annotations

import logging

from fastapi import APIRouter, Depends

from core.engine.core.auth import get_current_user
from core.engine.core.db import parse_one, parse_rows, pool

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/orchestration", tags=["orchestration"])


@router.get("/runs")
async def list_runs(
    product: str = "product:default",
    source: str | None = None,
    limit: int = 20,
    user: dict = Depends(get_current_user),
):
    """List recent orchestration runs."""
    filters = "WHERE product = <record>$product"
    params: dict = {"product": product, "limit": limit}

    if source:
        filters += " AND source = $source"
        params["source"] = source

    async with pool.connection() as db:
        result = await db.query(
            f"SELECT * FROM orchestration_run {filters} ORDER BY created_at DESC LIMIT $limit",
            params,
        )
        rows = parse_rows(result)

    return {"runs": rows, "count": len(rows)}


@router.get("/runs/{run_id}")
async def get_run(run_id: str, user: dict = Depends(get_current_user)):
    """Get a single orchestration run with its events."""
    async with pool.connection() as db:
        run_result = await db.query(
            "SELECT * FROM orchestration_run WHERE run_id = $run_id LIMIT 1",
            {"run_id": run_id},
        )
        run = parse_one(run_result)

        events_result = await db.query(
            "SELECT * FROM orchestration_event WHERE run_id = $run_id ORDER BY created_at ASC",
            {"run_id": run_id},
        )
        event_rows = parse_rows(events_result)

    if not run:
        from fastapi import HTTPException

        raise HTTPException(status_code=404, detail="Run not found")

    return {"run": run, "events": event_rows, "event_count": len(event_rows)}
