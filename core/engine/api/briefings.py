# engine/api/briefings.py
"""Briefing API — versioned intelligence briefings with diff + permalinks.

GET  /briefings               — list briefings for an org
GET  /briefings/latest        — most recent briefing
GET  /briefings/{id}          — single briefing by ID (any version, forever)
GET  /briefings/{a}/diff/{b}  — structured diff between two versions
POST /briefings/{id}/subscribe — subscribe email to future briefings
GET  /briefings/{id}/permalink — public permalink (no auth if is_public=True)
"""

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, ConfigDict

from core.engine.core.auth import get_current_user
from core.engine.core.db import parse_one, parse_rows, pool
from core.engine.product.briefing_diff import BriefingDiff, diff_briefings

router = APIRouter(prefix="/briefings", tags=["briefings"])


class BriefingResponse(BaseModel):
    model_config = ConfigDict(extra="allow")

    content: str | dict | None = None
    period: str = ""
    metrics: dict = {}
    created_at: str | None = None
    superseded_by: str | None = None
    is_public: bool = False


class BriefingListResponse(BaseModel):
    briefings: list[dict] = []


class SubscribeRequest(BaseModel):
    email: str


class SubscribeResponse(BaseModel):
    subscribed: bool
    briefing_id: str
    email: str


@router.get("", response_model=BriefingListResponse)
async def list_briefings(
    product: str = Query(...),
    limit: int = Query(default=10, ge=1, le=100),
    project: str | None = None,
    user: dict = Depends(get_current_user),
):
    """List briefings for an org, most recent first."""
    project_clause = ""
    if project:
        # decision:6vacauzia2jc46hpvms8 — `= (SELECT VALUE ... LIMIT 1)` returns
        # empty in SurrealDB v3 (subquery yields 1-element array, not scalar).
        project_clause = " AND project IN (SELECT VALUE id FROM project WHERE product = <record>$product AND slug = <string>$project)"
    async with pool.connection() as db:
        result = await db.query(
            f"""
            SELECT id, period, metrics, created_at, superseded_by, is_public
            FROM briefing
            WHERE product = <record>$product{project_clause}
            ORDER BY created_at DESC
            LIMIT $limit
            """,
            {"product": product, "limit": limit, "project": project},
        )
        rows = parse_rows(result)
    return {"briefings": rows}


@router.get("/latest")
async def get_latest_briefing(
    product: str = Query(...),
    project: str | None = None,
    user: dict = Depends(get_current_user),
):
    """Get the most recent briefing for an org."""
    project_clause = ""
    if project:
        # decision:6vacauzia2jc46hpvms8 — `= (SELECT VALUE ... LIMIT 1)` returns
        # empty in SurrealDB v3 (subquery yields 1-element array, not scalar).
        project_clause = " AND project IN (SELECT VALUE id FROM project WHERE product = <record>$product AND slug = <string>$project)"
    async with pool.connection() as db:
        result = await db.query(
            f"""
            SELECT *
            FROM briefing
            WHERE product = <record>$product{project_clause}
            ORDER BY created_at DESC
            LIMIT 1
            """,
            {"product": product, "project": project},
        )
        rows = parse_rows(result)

    if not rows:
        raise HTTPException(status_code=404, detail="No briefings found")
    return rows[0]


@router.get("/{briefing_id}/diff/{other_briefing_id}", response_model=BriefingDiff)
async def get_briefing_diff(
    briefing_id: str,
    other_briefing_id: str,
    user: dict = Depends(get_current_user),
):
    """Structured diff between two briefing versions (older → newer by created_at)."""
    async with pool.connection() as db:
        result_a = await db.query("SELECT * FROM ONLY <record>$id", {"id": briefing_id})
        result_b = await db.query("SELECT * FROM ONLY <record>$id", {"id": other_briefing_id})
        row_a = parse_one(result_a)
        row_b = parse_one(result_b)

    if not row_a:
        raise HTTPException(status_code=404, detail=f"Briefing {briefing_id} not found")
    if not row_b:
        raise HTTPException(status_code=404, detail=f"Briefing {other_briefing_id} not found")

    return diff_briefings(row_a, row_b)


@router.post("/{briefing_id}/subscribe", response_model=SubscribeResponse)
async def subscribe_to_briefing(
    briefing_id: str,
    body: SubscribeRequest,
    user: dict = Depends(get_current_user),
):
    """Subscribe an email address to receive future briefings for this product."""
    async with pool.connection() as db:
        row = parse_one(await db.query("SELECT id, product FROM ONLY <record>$id", {"id": briefing_id}))
        if not row:
            raise HTTPException(status_code=404, detail="Briefing not found")

        await db.query(
            """
            CREATE briefing_subscription SET
                briefing_id = <record>$briefing_id,
                email = $email,
                product = $product,
                created_at = time::now()
            """,
            {"briefing_id": briefing_id, "email": body.email, "product": row.get("product", "")},
        )

    return SubscribeResponse(subscribed=True, briefing_id=briefing_id, email=body.email)


@router.get("/{briefing_id}/permalink")
async def get_permalink(briefing_id: str):
    """Public permalink — no auth required; returns 401 if is_public is not True."""
    async with pool.connection() as db:
        row = parse_one(
            await db.query(
                "SELECT id, is_public, content, created_at FROM ONLY <record>$id",
                {"id": briefing_id},
            )
        )

    if not row:
        raise HTTPException(status_code=404, detail="Briefing not found")
    if not row.get("is_public", False):
        raise HTTPException(status_code=401, detail="Briefing is not public")

    return {
        "briefing_id": briefing_id,
        "created_at": str(row.get("created_at", "")),
        "content": row.get("content", {}),
        "public": True,
    }


@router.get("/{briefing_id}")
async def get_briefing(
    briefing_id: str,
    product: str = Query(...),
    user: dict = Depends(get_current_user),
):
    """Get a single briefing by ID — returns the briefing exactly as it existed at that ID."""
    async with pool.connection() as db:
        result = await db.query(
            "SELECT * FROM ONLY <record>$id",
            {"id": briefing_id},
        )
        rows = parse_rows(result)

    if not rows:
        raise HTTPException(status_code=404, detail="Briefing not found")
    return rows[0]
