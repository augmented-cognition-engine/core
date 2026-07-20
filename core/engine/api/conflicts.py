# engine/api/conflicts.py
"""Conflict resolution API — list conflicts, resolve with human decision.

GET /conflicts — list conflicts for an org (filterable by status)
POST /conflicts/{id}/resolve — resolve a conflict with a human action

Resolution types:
- keep_a: insight_a stays active, insight_b set to superseded
- keep_b: insight_b stays active, insight_a set to superseded
- keep_both: both stay active, conflict marked resolved
- merge: both originals superseded, new merged insight created
"""

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel

from core.engine.core.auth import get_current_user
from core.engine.core.db import parse_one, parse_rows, pool

router = APIRouter(prefix="/conflicts", tags=["conflicts"])

VALID_RESOLUTION_TYPES = {"keep_a", "keep_b", "keep_both", "merge"}


class ConflictResolveRequest(BaseModel):
    resolution_type: str
    resolution: str
    merged_content: str | None = None


@router.get("")
async def list_conflicts(
    product: str = Query(...),
    status: str = Query(default="pending"),
    limit: int = Query(default=50, ge=1, le=200),
    user: dict = Depends(get_current_user),
):
    """List conflicts for an org, filterable by status."""
    async with pool.connection() as db:
        result = await db.query(
            """
            SELECT
                id, insight_a, insight_b, conflicting_content,
                explanation, status, resolution_type, resolution,
                resolved_by, resolved_at, created_at
            FROM conflict
            WHERE product = <record>$product AND status = $status
            ORDER BY created_at DESC
            LIMIT $limit
            """,
            {"product": product, "status": status, "limit": limit},
        )
        rows = parse_rows(result)

        enriched = []
        for conflict in rows:
            enriched_conflict = dict(conflict)

            if conflict.get("insight_a"):
                ia = await db.query(
                    "SELECT content, confidence FROM ONLY <record>$id",
                    {"id": conflict["insight_a"]},
                )
                ia_rows = parse_rows(ia)
                if ia_rows:
                    enriched_conflict["insight_a_content"] = ia_rows[0].get("content", "")
                    enriched_conflict["insight_a_confidence"] = ia_rows[0].get("confidence", 0)

            if conflict.get("insight_b"):
                ib = await db.query(
                    "SELECT content, confidence FROM ONLY <record>$id",
                    {"id": conflict["insight_b"]},
                )
                ib_rows = parse_rows(ib)
                if ib_rows:
                    enriched_conflict["insight_b_content"] = ib_rows[0].get("content", "")
                    enriched_conflict["insight_b_confidence"] = ib_rows[0].get("confidence", 0)

            enriched.append(enriched_conflict)

    return {"conflicts": enriched}


@router.post("/{conflict_id}/resolve")
async def resolve_conflict(
    conflict_id: str,
    body: ConflictResolveRequest,
    user: dict = Depends(get_current_user),
):
    """Resolve a conflict with a human decision."""
    if body.resolution_type not in VALID_RESOLUTION_TYPES:
        raise HTTPException(
            status_code=400,
            detail=f"Invalid resolution_type. Must be one of: {', '.join(sorted(VALID_RESOLUTION_TYPES))}",
        )

    if body.resolution_type == "merge" and not body.merged_content:
        raise HTTPException(
            status_code=400,
            detail="merged_content is required for resolution_type 'merge'",
        )

    user_id = user.get("sub", "user:default")

    async with pool.connection() as db:
        conflict_result = await db.query(
            "SELECT * FROM ONLY <record>$id",
            {"id": conflict_id},
        )
        conflict = parse_one(conflict_result)

        if not conflict:
            raise HTTPException(status_code=404, detail="Conflict not found")

        if conflict.get("status") == "resolved":
            raise HTTPException(status_code=409, detail="Conflict already resolved")

        insight_a_id = conflict.get("insight_a")
        insight_b_id = conflict.get("insight_b")

        await db.query(
            """
            UPDATE <record>$id SET
                status = 'resolved',
                resolution_type = $resolution_type,
                resolution = $resolution,
                resolved_by = $user,
                resolved_at = time::now()
            """,
            {
                "id": conflict_id,
                "resolution_type": body.resolution_type,
                "resolution": body.resolution,
                "user": user_id,
            },
        )

        if body.resolution_type == "keep_a" and insight_b_id:
            await db.query("UPDATE <record>$id SET status = 'superseded'", {"id": insight_b_id})

        elif body.resolution_type == "keep_b" and insight_a_id:
            await db.query("UPDATE <record>$id SET status = 'superseded'", {"id": insight_a_id})

        elif body.resolution_type == "keep_both":
            pass

        elif body.resolution_type == "merge":
            if insight_a_id:
                await db.query("UPDATE <record>$id SET status = 'superseded'", {"id": insight_a_id})
            if insight_b_id:
                await db.query("UPDATE <record>$id SET status = 'superseded'", {"id": insight_b_id})

            ia_data = {}
            if insight_a_id:
                ia_result = await db.query(
                    "SELECT org, domain_path, domain, subdomain, specialty, tier FROM ONLY <record>$id",
                    {"id": insight_a_id},
                )
                ia_data = parse_one(ia_result) or {}

            await db.query(
                """
                CREATE insight SET
                    content = $content,
                    insight_type = 'fact',
                    tier = $tier,
                    domain_path = $domain_path,
                    domain = $domain,
                    subdomain = $subdomain,
                    specialty = $specialty,
                    confidence = 0.8,
                    source_domain = 'human.conflict-resolution',
                    tags = ['merged', 'conflict-resolution'],
                    status = 'active',
                    clearance = 'open',
                    created_at = time::now()
                """,
                {
                    "product": ia_data.get("product", conflict.get("product")),
                    "content": body.merged_content,
                    "tier": ia_data.get("tier", "domain"),
                    "domain_path": ia_data.get("domain_path", ""),
                    "domain": ia_data.get("domain"),
                    "subdomain": ia_data.get("subdomain"),
                    "specialty": ia_data.get("specialty"),
                },
            )

        updated = await db.query("SELECT * FROM ONLY <record>$id", {"id": conflict_id})
        updated_record = parse_one(updated)

    return updated_record if updated_record else {"id": conflict_id, "status": "resolved"}
