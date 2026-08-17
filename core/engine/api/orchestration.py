# engine/api/orchestration.py
"""Orchestration API — query persisted runs and events for debugging/replay."""

from __future__ import annotations

import logging

from fastapi import APIRouter, Depends, HTTPException

from core.engine.core.auth import get_current_user
from core.engine.core.db import parse_one, parse_rows, pool

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/orchestration", tags=["orchestration"])


def _authenticated_product(user: dict, requested: str | None = None) -> str:
    product = user.get("product")
    if not isinstance(product, str) or not product.startswith("product:") or len(product) <= 8:
        raise HTTPException(status_code=404, detail="Not found")
    # Preserve the historical default query value as "use my product" while
    # preventing an explicit product selector from crossing the token fence.
    if requested not in (None, "product:default", product):
        raise HTTPException(status_code=404, detail="Not found")
    return product


@router.get("/runs")
async def list_runs(
    product: str = "product:default",
    source: str | None = None,
    limit: int = 20,
    user: dict = Depends(get_current_user),
):
    """List recent orchestration runs."""
    product = _authenticated_product(user, product)
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
    product = _authenticated_product(user)
    async with pool.connection() as db:
        run_result = await db.query(
            "SELECT * FROM orchestration_run WHERE product = <record>$product AND run_id = $run_id LIMIT 1",
            {"product": product, "run_id": run_id},
        )
        run = parse_one(run_result)

        events_result = await db.query(
            "SELECT * FROM orchestration_event WHERE product = <record>$product "
            "AND run_id = $run_id ORDER BY created_at ASC",
            {"product": product, "run_id": run_id},
        )
        event_rows = parse_rows(events_result)

    if not run:
        raise HTTPException(status_code=404, detail="Run not found")

    return {"run": run, "events": event_rows, "event_count": len(event_rows)}
