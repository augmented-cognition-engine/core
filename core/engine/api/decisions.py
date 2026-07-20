# engine/api/decisions.py
"""REST API for PM decisions."""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from core.engine.core.auth import get_current_user
from core.engine.core.db import parse_one, pool
from core.engine.product.decisions import (
    create_decision,
    get_decision,
    list_decisions,
    supersede_decision,
)


class CreateDecisionRequest(BaseModel):
    title: str
    decision_type: str
    rationale: str
    alternatives: list[str] | None = None
    source: str | None = None
    source_session: str | None = None
    affected_capabilities: list[str] | None = None
    led_to_ids: list[str] | None = None


router = APIRouter(tags=["decisions"])


@router.post("/decisions", status_code=201)
async def post_decision(body: CreateDecisionRequest, user=Depends(get_current_user)):
    """Create a new PM decision."""
    product_id = user.get("product", "")

    result = await create_decision(
        title=body.title,
        decision_type=body.decision_type,
        rationale=body.rationale,
        product_id=product_id,
        alternatives=body.alternatives,
        source=body.source,
        source_session=body.source_session,
        affected_capabilities=body.affected_capabilities,
        led_to_ids=body.led_to_ids,
    )
    return result


@router.get("/decisions")
async def get_decisions(
    decision_type: str | None = None,
    outcome: str | None = None,
    limit: int = 50,
    user=Depends(get_current_user),
):
    """List decisions with optional filters."""
    product_id = user.get("product", "")
    decisions = await list_decisions(product_id, decision_type=decision_type, outcome=outcome, limit=limit)
    return {"decisions": decisions, "count": len(decisions)}


@router.get("/decisions/{decision_id:path}")
async def get_decision_by_id(decision_id: str, user=Depends(get_current_user)):
    """Get a single decision with its connected edges."""
    decision = await get_decision(decision_id)
    if not decision:
        raise HTTPException(404, f"Decision '{decision_id}' not found")
    return decision


@router.put("/decisions/{decision_id:path}")
async def update_decision(decision_id: str, body: dict, user=Depends(get_current_user)):
    """Update a decision (e.g., mark as superseded)."""
    product_id = user.get("product", "")

    if body.get("superseded_by"):
        result = await supersede_decision(
            old_id=decision_id,
            title=body.get("title", ""),
            decision_type=body.get("decision_type", ""),
            rationale=body.get("rationale", ""),
            product_id=product_id,
        )
        return result

    allowed = {"outcome", "rationale", "alternatives"}
    updates = {k: v for k, v in body.items() if k in allowed}
    if not updates:
        raise HTTPException(400, "No updatable fields provided")

    set_parts = [f"{k} = ${k}" for k in updates]
    set_clause = ", ".join(set_parts)

    async with pool.connection() as db:
        result = await db.query(
            f"UPDATE <record>$id SET {set_clause}",
            {"id": decision_id, **updates},
        )
        return parse_one(result) or {"id": decision_id, "updated": True}
