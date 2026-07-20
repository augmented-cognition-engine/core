# engine/api/efficiency.py
"""Efficiency endpoints — token savings, composition effectiveness, baselines."""

from __future__ import annotations

import logging

from fastapi import APIRouter, Depends, Query

from core.engine.core.auth import get_current_user
from core.engine.core.db import parse_rows, pool

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/efficiency", tags=["efficiency"])


async def _query_efficiency_summary(product_id: str, days: int = 7) -> dict:
    async with pool.connection() as db:
        result = await db.query(
            f"""
            SELECT
                math::sum(token_total) AS total_tokens,
                math::sum(estimated_tokens_saved) AS estimated_saved,
                count() AS task_count
            FROM composition_signal
            WHERE product = <record>$product
              AND created_at > time::now() - {days}d
            GROUP ALL
            """,
            {"product": product_id},
        )
        rows = parse_rows(result)
        return rows[0] if rows else {"total_tokens": 0, "estimated_saved": 0, "task_count": 0}


async def _query_top_compositions(product_id: str, discipline: str | None, limit: int) -> list[dict]:
    where = "WHERE product = <record>$product AND feedback = 'accepted'"
    params: dict = {"product": product_id, "limit": limit}
    if discipline:
        where += " AND discipline = <string>$discipline"
        params["discipline"] = discipline
    async with pool.connection() as db:
        result = await db.query(
            f"""
            SELECT
                discipline,
                perspectives,
                engagement_type,
                count() AS count,
                math::mean(token_total) AS avg_tokens,
                math::mean(utilization_rate) AS avg_utilization
            FROM composition_signal
            {where}
            GROUP BY discipline, perspectives, engagement_type
            ORDER BY count DESC
            LIMIT $limit
            """,
            params,
        )
        return parse_rows(result)


async def _query_baselines(product_id: str) -> list[dict]:
    async with pool.connection() as db:
        result = await db.query(
            """
            SELECT discipline, complexity, avg_tokens_control, avg_tokens_variant,
                   sample_count, savings_pct
            FROM token_baseline
            WHERE product = <record>$product
            ORDER BY savings_pct DESC
            """,
            {"product": product_id},
        )
        return parse_rows(result)


@router.get("")
async def get_efficiency_summary(
    user: dict = Depends(get_current_user),
):
    """Token savings summary: this_week/this_month/all_time."""
    product_id = user.get("product", "product:default")
    week = await _query_efficiency_summary(product_id, 7)
    month = await _query_efficiency_summary(product_id, 30)
    all_time = await _query_efficiency_summary(product_id, 36500)
    return {
        "this_week": week,
        "this_month": month,
        "all_time": all_time,
        "total_tokens": all_time.get("total_tokens", 0),
        "estimated_saved": all_time.get("estimated_saved", 0),
    }


@router.get("/compositions")
async def get_top_compositions(
    discipline: str | None = Query(None),
    limit: int = Query(10, ge=1, le=50),
    user: dict = Depends(get_current_user),
):
    """Top compositions ranked by acceptance rate + token efficiency."""
    product_id = user.get("product", "product:default")
    compositions = await _query_top_compositions(product_id, discipline, limit)
    return {"compositions": compositions}


@router.get("/baselines")
async def get_baselines(
    user: dict = Depends(get_current_user),
):
    """Current baseline estimates per discipline x complexity."""
    product_id = user.get("product", "product:default")
    baselines = await _query_baselines(product_id)
    return {"baselines": baselines}
