"""REST API for quality gates — evaluate, approve, reject, list pending."""

from __future__ import annotations

from fastapi import APIRouter, Depends
from pydantic import BaseModel

from core.engine.core.auth import get_current_user
from core.engine.core.db import parse_one, pool
from core.engine.pm.gate_engine import GateEngine

router = APIRouter(tags=["gates"])


class ApproveRequest(BaseModel):
    rationale: str = ""


class RejectRequest(BaseModel):
    reason: str


@router.post("/gates/{entity_type}/{entity_id}/evaluate")
async def evaluate_gate(entity_type: str, entity_id: str, user=Depends(get_current_user)):
    """Evaluate a gate transition — returns risk assessment."""
    product_id = user.get("product", "")
    ge = GateEngine(pool)
    current_state = await _current_gate_state(entity_type, entity_id)
    result = await ge.evaluate_gate(entity_type, entity_id, current_state, "", product_id)
    return result


@router.post("/gates/{entity_type}/{entity_id}/approve")
async def approve_gate(
    entity_type: str,
    entity_id: str,
    body: ApproveRequest,
    user=Depends(get_current_user),
):
    """PM approves a pending gate."""
    product_id = user.get("product", "")
    user_id = user.get("sub", "user:default")

    ge = GateEngine(pool)
    gate_state = await _current_gate_state(entity_type, entity_id)
    result = await ge.approve_gate(entity_type, entity_id, gate_state, body.rationale, product_id, user_id)
    return result


@router.post("/gates/{entity_type}/{entity_id}/reject")
async def reject_gate(
    entity_type: str,
    entity_id: str,
    body: RejectRequest,
    user=Depends(get_current_user),
):
    """PM rejects a pending gate with reason."""
    product_id = user.get("product", "")
    user_id = user.get("sub", "user:default")

    ge = GateEngine(pool)
    gate_state = await _current_gate_state(entity_type, entity_id)
    result = await ge.reject_gate(entity_type, entity_id, gate_state, body.reason, product_id, user_id)
    return result


@router.get("/gates/pending")
async def list_pending_gates(user=Depends(get_current_user)):
    """List all entities waiting for human review."""
    product_id = user.get("product", "")
    ge = GateEngine(pool)
    gates = await ge.list_pending(product_id)
    return {"gates": gates, "count": len(gates)}


async def _current_gate_state(entity_type: str, entity_id: str) -> str:
    """Read the entity's current status to determine which gate it's at."""
    async with pool.connection() as db:
        result = await db.query("SELECT status FROM <record>$id", {"id": entity_id})
        entity = parse_one(result)
        return entity.get("status", "") if entity else ""
