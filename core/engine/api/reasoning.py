# engine/api/reasoning.py
"""Reasoning framework API — list frameworks, get details, view performance.

GET /frameworks — list frameworks (filter by family, tier)
GET /frameworks/{slug} — get a single framework
GET /framework-perf — performance stats per framework
"""

from fastapi import APIRouter, Depends, HTTPException, Query

from core.engine.core.auth import get_current_user
from core.engine.core.db import parse_rows, pool

router = APIRouter(tags=["reasoning"])


@router.get("/frameworks")
async def list_frameworks(
    product: str = Query(default="product:default"),
    family: str | None = Query(default=None),
    tier: str | None = Query(default=None),
    user: dict = Depends(get_current_user),
):
    """List frameworks — built-in + org-specific."""
    async with pool.connection() as db:
        where = "(product IS NONE OR product = <record>$product)"
        if family and tier:
            where += " AND family = <string>$family AND tier = <string>$tier"
        elif family:
            where += " AND family = <string>$family"
        elif tier:
            where += " AND tier = <string>$tier"
        result = await db.query(
            f"SELECT * FROM framework WHERE {where} ORDER BY family, name",
            {"product": product, "family": family, "tier": tier},
        )
        rows = parse_rows(result)
    return {"frameworks": rows}


@router.get("/frameworks/{slug}")
async def get_framework(slug: str, user: dict = Depends(get_current_user)):
    """Get a single framework by slug."""
    async with pool.connection() as db:
        result = await db.query(
            "SELECT * FROM framework WHERE slug = <string>$slug LIMIT 1",
            {"slug": slug},
        )
        rows = parse_rows(result)
    if not rows:
        raise HTTPException(status_code=404, detail="Framework not found")
    return rows[0]


@router.get("/framework-perf")
async def get_framework_perf(
    product: str = Query(default="product:default"),
    user: dict = Depends(get_current_user),
):
    """Get performance stats for frameworks."""
    async with pool.connection() as db:
        result = await db.query(
            """
            SELECT framework, task_count, accept_rate, avg_score, last_used
            FROM framework_perf
            WHERE product = <record>$product
            ORDER BY task_count DESC
            """,
            {"product": product},
        )
        rows = parse_rows(result)
    return {"performance": rows}
