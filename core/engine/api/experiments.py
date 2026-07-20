"""REST API for experiment log — view A/B test results."""

from __future__ import annotations

from fastapi import APIRouter, Depends, Query

from core.engine.core.auth import get_current_user
from core.engine.core.db import parse_one, parse_rows, pool

router = APIRouter(prefix="/experiments", tags=["experiments"])


@router.get("")
async def list_experiments(
    product: str = Query(...),
    domain: str | None = None,
    experiment_type: str | None = None,
    significant_only: bool = False,
    limit: int = Query(default=50, le=200),
    user=Depends(get_current_user),
):
    """List experiment results with filtering."""
    conditions = ["product = <record>$product"]
    params: dict = {"product": product, "limit": limit}

    if domain:
        conditions.append("domain = $domain")
        params["domain"] = domain
    if experiment_type:
        conditions.append("experiment_type = $etype")
        params["etype"] = experiment_type
    if significant_only:
        conditions.append("significant = true")

    where = " AND ".join(conditions)

    async with pool.connection() as db:
        result = await db.query(
            f"SELECT * FROM experiment_log WHERE {where} ORDER BY created_at DESC LIMIT $limit",
            params,
        )
        rows = parse_rows(result)

    return {"experiments": rows, "count": len(rows)}


@router.get("/summary")
async def experiment_summary(product: str = Query(...), user=Depends(get_current_user)):
    """Aggregate experiment summary."""
    async with pool.connection() as db:
        total_result = await db.query(
            "SELECT count() AS n FROM experiment_log WHERE product = <record>$product GROUP ALL",
            {"product": product},
        )
        total_row = parse_one(total_result)
        total = total_row.get("n", 0) if total_row else 0

        winners_result = await db.query(
            "SELECT count() AS n FROM experiment_log WHERE product = <record>$product AND committed = true GROUP ALL",
            {"product": product},
        )
        winners_row = parse_one(winners_result)
        winners = winners_row.get("n", 0) if winners_row else 0

        avg_result = await db.query(
            "SELECT math::mean(improvement) AS avg_imp FROM experiment_log WHERE product = <record>$product AND significant = true GROUP ALL",
            {"product": product},
        )
        avg_row = parse_one(avg_result)
        avg_improvement = avg_row.get("avg_imp", 0) if avg_row else 0

        by_type = await db.query(
            """
            SELECT experiment_type, count() AS count, math::sum(IF committed THEN 1 ELSE 0 END) AS committed_count
            FROM experiment_log WHERE product = <record>$product
            GROUP BY experiment_type
            """,
            {"product": product},
        )
        type_rows = parse_rows(by_type)

    return {
        "total_experiments": total,
        "winners_committed": winners,
        "avg_improvement": round(float(avg_improvement or 0), 4),
        "by_type": type_rows,
    }
