# engine/api/conflicts.py
"""Conflict resolution API — list product conflicts, resolve with human decision.

GET /conflicts — list conflicts for the authenticated product (filterable by status)
POST /conflicts/{id}/resolve — resolve a conflict with a human action

Resolution types:
- keep_a: insight_a stays active, insight_b set to superseded
- keep_b: insight_b stays active, insight_a set to superseded
- keep_both: both stay active, conflict marked resolved
- merge: both originals superseded, new merged insight created
"""

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel

from core.engine.core.auth import get_current_user, verify_ownership
from core.engine.core.db import parse_one, parse_rows, pool

router = APIRouter(prefix="/conflicts", tags=["conflicts"])

VALID_RESOLUTION_TYPES = {"keep_a", "keep_b", "keep_both", "merge"}


class ConflictResolveRequest(BaseModel):
    resolution_type: str
    resolution: str
    merged_content: str | None = None


def _scoped_product(requested: str | None, user: dict) -> str:
    """Resolve conflict access to the authenticated product and fail closed on mismatch."""
    authenticated = str(user.get("product", ""))
    target = str(requested or authenticated)
    verify_ownership({"product": target}, user)
    return target


async def _claim_view(db, claim_id: object, product_id: str) -> dict:
    """Return one bounded, provenance-bearing claim view for conflict review."""
    if not claim_id:
        return {}
    claim_id = str(claim_id)
    row = parse_one(
        await db.query(
            """
            SELECT
                id, product, content, confidence, status, source_domain,
                source_product, source_observations, derivation_chain,
                last_confirmed, created_at, updated_at
            FROM ONLY <record>$id
            """,
            {"id": claim_id},
        )
    )
    if not row or str(row.get("product", "")) != product_id:
        return {"id": claim_id, "available": False}
    return {
        "id": claim_id,
        "available": True,
        "content": str(row.get("content", ""))[:10_000],
        "confidence": row.get("confidence"),
        "status": row.get("status"),
        "provenance": {
            "source_domain": row.get("source_domain"),
            "source_product": row.get("source_product"),
            "source_observations": row.get("source_observations") or [],
            "derivation_chain": row.get("derivation_chain") or [],
            "last_confirmed": row.get("last_confirmed"),
            "created_at": row.get("created_at"),
            "updated_at": row.get("updated_at"),
        },
    }


@router.get("")
async def list_conflicts(
    product: str | None = Query(default=None),
    status: str = Query(default="pending"),
    limit: int = Query(default=50, ge=1, le=200),
    user: dict = Depends(get_current_user),
):
    """List product-owned conflicts with claims, provenance, and required action."""
    product_id = _scoped_product(product, user)
    async with pool.connection() as db:
        result = await db.query(
            """
            SELECT
                id, insight_a, insight_b, conflicting_content,
                explanation, status, resolution_type, resolution,
                resolved_by, resolved_at, detected_by, created_at
            FROM conflict
            WHERE product = <record>$product AND status = $status
            ORDER BY created_at DESC
            LIMIT $limit
            """,
            {"product": product_id, "status": status, "limit": limit},
        )
        rows = parse_rows(result)

        enriched = []
        for conflict in rows:
            enriched_conflict = dict(conflict)

            claim_a = await _claim_view(db, conflict.get("insight_a"), product_id)
            claim_b = await _claim_view(db, conflict.get("insight_b"), product_id)
            enriched_conflict["product"] = product_id
            enriched_conflict["claims"] = [claim for claim in (claim_a, claim_b) if claim]
            enriched_conflict["attention"] = {
                "required": conflict.get("status") == "pending",
                "code": "contested_truth" if conflict.get("status") == "pending" else "conflict_resolved",
                "operational_state": "quarantined" if conflict.get("status") == "pending" else "resolved",
                "resolution_endpoint": f"/conflicts/{conflict.get('id')}/resolve",
                "allowed_actions": sorted(VALID_RESOLUTION_TYPES),
            }

            # Preserve the existing CLI response fields while the richer
            # claims[] contract becomes the canonical review representation.
            if claim_a.get("available"):
                enriched_conflict["insight_a_content"] = claim_a["content"]
                enriched_conflict["insight_a_confidence"] = claim_a.get("confidence") or 0
            if claim_b.get("available"):
                enriched_conflict["insight_b_content"] = claim_b["content"]
                enriched_conflict["insight_b_confidence"] = claim_b.get("confidence") or 0

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
    product_id = _scoped_product(None, user)

    async with pool.connection() as db:
        conflict_result = await db.query(
            "SELECT * FROM conflict WHERE id = <record>$id AND product = <record>$product LIMIT 1",
            {"id": conflict_id, "product": product_id},
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

        if body.resolution_type == "keep_a":
            if insight_a_id:
                await db.query("UPDATE <record>$id SET status = 'active'", {"id": insight_a_id})
            if insight_b_id:
                await db.query("UPDATE <record>$id SET status = 'superseded'", {"id": insight_b_id})

        elif body.resolution_type == "keep_b":
            if insight_b_id:
                await db.query("UPDATE <record>$id SET status = 'active'", {"id": insight_b_id})
            if insight_a_id:
                await db.query("UPDATE <record>$id SET status = 'superseded'", {"id": insight_a_id})

        elif body.resolution_type == "keep_both":
            if insight_a_id:
                await db.query("UPDATE <record>$id SET status = 'active'", {"id": insight_a_id})
            if insight_b_id:
                await db.query("UPDATE <record>$id SET status = 'active'", {"id": insight_b_id})

        elif body.resolution_type == "merge":
            if insight_a_id:
                await db.query("UPDATE <record>$id SET status = 'superseded'", {"id": insight_a_id})
            if insight_b_id:
                await db.query("UPDATE <record>$id SET status = 'superseded'", {"id": insight_b_id})

            ia_data = {}
            if insight_a_id:
                ia_result = await db.query(
                    "SELECT product, domain_path, domain, subdomain, specialty, tier FROM ONLY <record>$id",
                    {"id": insight_a_id},
                )
                ia_data = parse_one(ia_result) or {}

            await db.query(
                """
                CREATE insight SET
                    product = <record>$product,
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
