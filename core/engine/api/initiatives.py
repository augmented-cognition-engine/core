# engine/api/initiatives.py
"""REST API for initiative lifecycle management."""

from __future__ import annotations

import re

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field, field_validator

from core.engine.core.auth import get_current_user
from core.engine.core.db import parse_one, parse_rows, pool

router = APIRouter(tags=["initiatives"])


# --- Request/Response models ---


class CreateInitiativeRequest(BaseModel):
    title: str
    description: str
    workspace_id: str | None = None  # deprecated, ignored
    priority: str = "medium"
    cost_budget: float | None = None
    git_base_branch: str | None = Field(default=None, max_length=200)
    product_id: str | None = None  # optional override; must be in same tenant

    @field_validator("git_base_branch")
    @classmethod
    def validate_branch(cls, v: str | None) -> str | None:
        if v is not None:
            if not re.fullmatch(r"[a-zA-Z0-9._/\-]+", v):
                raise ValueError("git_base_branch contains invalid characters")
            if ".." in v:
                raise ValueError("git_base_branch must not contain '..'")
        return v

    success_criteria: list[str] | None = None


class ApproveRejectRequest(BaseModel):
    feedback: str | None = None


# --- Routes ---


@router.post("/initiatives", status_code=201)
async def create_initiative(body: CreateInitiativeRequest, user=Depends(get_current_user)):
    """Create a new initiative.

    product_id in body overrides JWT product — must belong to the same tenant.
    """
    from core.engine.pm.tracker import InitiativeTracker

    user_product_id = user["product"]
    target_product_id = user_product_id

    if body.product_id and body.product_id != user_product_id:
        # Validate the override product belongs to the same tenant
        async with pool.connection() as db:
            t_result = await db.query(
                "SELECT tenant FROM product WHERE id = <record>$product LIMIT 1",
                {"product": user_product_id},
            )
            t_rows = parse_rows(t_result)
            user_tenant = str(t_rows[0]["tenant"]) if t_rows and t_rows[0].get("tenant") else None

            p_result = await db.query(
                "SELECT tenant FROM product WHERE id = <record>$product LIMIT 1",
                {"product": body.product_id},
            )
            p_rows = parse_rows(p_result)
            target_tenant = str(p_rows[0]["tenant"]) if p_rows and p_rows[0].get("tenant") else None

        if not user_tenant or user_tenant != target_tenant:
            raise HTTPException(status_code=403, detail="Product not in your tenant")
        target_product_id = body.product_id

    tracker = InitiativeTracker(db_pool=pool)
    result = await tracker.create_initiative(
        title=body.title,
        description=body.description,
        product_id=target_product_id,
        user_id=user["sub"],
        priority=body.priority,
        cost_budget=body.cost_budget,
        git_base_branch=body.git_base_branch,
        success_criteria=body.success_criteria,
    )
    return result


@router.get("/initiatives")
async def list_initiatives(
    status: str | None = None,
    project: str | None = None,
    all_products: bool = False,
    product_id: str | None = None,  # filter to a specific engagement (tenant-validated)
    user=Depends(get_current_user),
):
    """List initiatives.

    - all_products=true     → tenant-wide
    - product_id=<id>       → specific engagement (must be in same tenant)
    - default               → user's own product from JWT
    """
    from core.engine.pm.tracker import InitiativeTracker

    user_product_id = user.get("product", "")
    tracker = InitiativeTracker(db_pool=pool)

    # Resolve which product to filter by, validating tenant membership
    if product_id and product_id != user_product_id:
        async with pool.connection() as db:
            t1 = await db.query("SELECT tenant FROM product WHERE id = <record>$p LIMIT 1", {"p": user_product_id})
            t2 = await db.query("SELECT tenant FROM product WHERE id = <record>$p LIMIT 1", {"p": product_id})
            r1 = parse_rows(t1)
            r2 = parse_rows(t2)
            if not r1 or not r2 or r1[0].get("tenant") != r2[0].get("tenant"):
                raise HTTPException(status_code=403, detail="Product not in your tenant")
        # Treat as single-product fetch (not all_products)
        results = await tracker.list_initiatives(product_id=product_id, status=status, project=project)
        return {"initiatives": results if isinstance(results, list) else []}

    # Replace the local product_id variable for the rest of the function
    resolved_product_id = user_product_id

    if all_products:
        async with pool.connection() as db:
            t_result = await db.query(
                "SELECT tenant FROM product WHERE id = <record>$product LIMIT 1",
                {"product": resolved_product_id},
            )
            t_rows = parse_rows(t_result)
            if not t_rows or not t_rows[0].get("tenant"):
                return {"initiatives": []}
            tenant = str(t_rows[0]["tenant"])

            p_result = await db.query(
                "SELECT id, name FROM product WHERE tenant = <record>$tenant AND id != product:platform",
                {"tenant": tenant},
            )
            products = parse_rows(p_result)
            product_name_map = {str(p["id"]): p.get("name", "") for p in products}

            clause = """
                SELECT id, title, status, assignee, updated_at, product
                FROM initiative
                WHERE product INSIDE (SELECT VALUE id FROM product WHERE tenant = <record>$tenant AND id != product:platform)
            """
            params: dict = {"tenant": tenant}
            if status:
                clause += " AND status = $status"
                params["status"] = status
            clause += " ORDER BY updated_at DESC LIMIT 200"

            result = await db.query(clause, params)
            rows = parse_rows(result)
            for r in rows:
                r["product_name"] = product_name_map.get(str(r.get("product", "")), "")
        return {"initiatives": rows}

    results = await tracker.list_initiatives(product_id=resolved_product_id, status=status, project=project)
    return {"initiatives": results if isinstance(results, list) else []}


@router.get("/initiatives/{initiative_id}")
async def get_initiative(initiative_id: str, product: str | None = None, user=Depends(get_current_user)):
    """Get initiative detail with milestones and work items."""
    from core.engine.pm.tracker import InitiativeTracker

    product_id = product or user.get("product", "")
    tracker = InitiativeTracker(db_pool=pool)
    result = await tracker.get_initiative(initiative_id=initiative_id, product_id=product_id)
    if not result:
        raise HTTPException(status_code=404, detail="Initiative not found")
    return result


class PatchInitiativeRequest(BaseModel):
    status: str | None = None
    assignee: str | None = Field(default=None, max_length=200)


@router.patch("/initiatives/{initiative_id}")
async def patch_initiative(initiative_id: str, body: PatchInitiativeRequest, user=Depends(get_current_user)):
    """Update initiative status or assignee.

    Ownership is tenant-level: a consultant can update any initiative whose
    product belongs to their tenant, regardless of which product their JWT is
    scoped to.
    """
    user_product_id = user.get("product", "")
    updates: list[str] = []
    params: dict = {"id": initiative_id}

    if body.status is not None:
        allowed = {"planning", "active", "paused", "blocked", "complete", "cancelled"}
        if body.status not in allowed:
            raise HTTPException(status_code=422, detail=f"Invalid status '{body.status}'")
        updates.append("status = $status")
        params["status"] = body.status

    if body.assignee is not None:
        updates.append("assignee = $assignee")
        params["assignee"] = body.assignee

    if not updates:
        raise HTTPException(status_code=422, detail="No fields to update")

    set_clause = ", ".join(updates)
    try:
        async with pool.connection() as db:
            # Resolve caller's tenant
            t_result = await db.query(
                "SELECT tenant FROM product WHERE id = <record>$p LIMIT 1",
                {"p": user_product_id},
            )
            t_rows = parse_rows(t_result)
            tenant = str(t_rows[0]["tenant"]) if t_rows and t_rows[0].get("tenant") else None
            if not tenant:
                raise HTTPException(status_code=403, detail="Cannot resolve tenant")

            # Verify the initiative's product belongs to the caller's tenant
            # SurrealDB v3: two-step (SELECT then UPDATE) because WHERE <record>$param
            # and time::now() in SET both silently return [] with parameterized record IDs.
            check = await db.query(
                """SELECT id FROM initiative
                   WHERE id = <record>$id
                   AND product INSIDE (SELECT VALUE id FROM product WHERE tenant = <record>$tenant)
                   LIMIT 1""",
                {"id": initiative_id, "tenant": tenant},
            )
            if not parse_rows(check):
                raise HTTPException(status_code=404, detail="Initiative not found")

            result = await db.query(
                f"UPDATE <record>$id SET {set_clause} RETURN AFTER",
                params,
            )
            row = parse_one(result)
            if not row:
                raise HTTPException(status_code=404, detail="Initiative not found")
    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(status_code=422, detail="Invalid initiative id") from exc
    return row


@router.post("/initiatives/{initiative_id}/activate")
async def activate_initiative(initiative_id: str, product: str | None = None, user=Depends(get_current_user)):
    """Activate a planning-stage initiative. Triggers milestone decomposition."""
    from core.engine.pm.tracker import InitiativeTracker

    product_id = product or user.get("product", "")
    tracker = InitiativeTracker(db_pool=pool)
    result = await tracker.activate_initiative(initiative_id=initiative_id, product_id=product_id)
    return result


@router.post("/initiatives/{initiative_id}/pause")
async def pause_initiative(initiative_id: str, product: str | None = None, user=Depends(get_current_user)):
    """Pause a running initiative."""
    from core.engine.pm.tracker import InitiativeTracker

    product_id = product or user.get("product", "")
    tracker = InitiativeTracker(db_pool=pool)
    result = await tracker.pause_initiative(initiative_id=initiative_id, product_id=product_id)
    return result


@router.post("/initiatives/{initiative_id}/cancel")
async def cancel_initiative(initiative_id: str, product: str | None = None, user=Depends(get_current_user)):
    """Cancel an initiative. Cleans up branches and locks."""
    from core.engine.pm.tracker import InitiativeTracker

    product_id = product or user.get("product", "")
    tracker = InitiativeTracker(db_pool=pool)
    result = await tracker.cancel_initiative(initiative_id=initiative_id, product_id=product_id)
    return result


@router.get("/initiatives/{initiative_id}/milestones")
async def list_milestones(initiative_id: str, product: str | None = None, user=Depends(get_current_user)):
    """List milestones for an initiative with status and work items."""
    product_id = product or user.get("product", "")
    async with pool.connection() as db:
        result = await db.query(
            """
            SELECT * FROM milestone
            WHERE initiative = $init_id AND product = <record>$product
            ORDER BY sequence ASC
            """,
            {"init_id": initiative_id, "product": product_id},
        )
        rows = parse_rows(result)

        # Load work items for each milestone
        for ms in rows:
            ms_id = ms.get("id", "")
            wi_result = await db.query(
                """
                SELECT * FROM work_item
                WHERE milestone = $ms_id AND product = <record>$product
                ORDER BY parallel_group ASC
                """,
                {"ms_id": ms_id, "product": product_id},
            )
            wi_rows = parse_rows(wi_result)
            ms["work_items_detail"] = wi_rows

        return {"milestones": rows}


@router.post("/initiatives/{initiative_id}/decompose")
async def decompose_initiative(initiative_id: str, user=Depends(get_current_user)):
    """Trigger SmartDecomposer. Transitions: planning -> decomposing -> ready."""
    from core.engine.pm.tracker import InitiativeTracker

    product_id = user.get("product", "")
    tracker = InitiativeTracker(db_pool=pool)
    initiative = await tracker.get_initiative(initiative_id, product_id)
    if not initiative:
        raise HTTPException(status_code=404, detail="Initiative not found")

    if initiative.get("status") not in ("planning",):
        raise HTTPException(status_code=400, detail=f"Cannot decompose from state '{initiative['status']}'")

    spec_id = initiative.get("spec_id") or initiative.get("source_spec")
    if not spec_id:
        # Defensive guard: refuse to advance an initiative to "ready" without a
        # spec to decompose against. The prior behavior wrote a placeholder
        # plan_data ({"note": "manual decomposition needed"}) and flipped
        # status to ready anyway — the same lazy fast-path class as the
        # qualify bug. Without a real plan, "ready" carries no actionable
        # meaning and downstream activation has nothing to dispatch.
        raise HTTPException(
            status_code=400,
            detail="Cannot decompose: initiative has no linked spec (spec_id / source_spec).",
        )

    async with pool.connection() as db:
        await db.query(
            "UPDATE <record>$id SET status = 'decomposing', decomposed_at = time::now()",
            {"id": initiative_id},
        )

    from core.engine.cognition.plan_evaluator import PlanEvaluator
    from core.engine.core.config import settings as _settings
    from core.engine.product.smart_decompose import SmartDecomposer

    decomposer = SmartDecomposer(
        pool,
        plan_evaluator=PlanEvaluator(advisor_model=_settings.llm_model),
        branch_count=3,
    )
    plan = await decomposer.decompose(str(spec_id), product_id)
    plan_data = plan.to_dict() if hasattr(plan, "to_dict") else str(plan)

    async with pool.connection() as db:
        await db.query(
            "UPDATE <record>$id SET status = 'ready', ready_at = time::now()",
            {"id": initiative_id},
        )

    return {"initiative_id": initiative_id, "status": "ready", "plan": plan_data}


@router.post("/initiatives/{initiative_id}/start")
async def start_initiative(initiative_id: str, user=Depends(get_current_user)):
    """Start a ready initiative. Transitions: ready -> active."""
    from core.engine.pm.tracker import InitiativeTracker

    product_id = user.get("product", "")
    tracker = InitiativeTracker(db_pool=pool)
    result = await tracker.activate_initiative(initiative_id, product_id)
    if "error" in result:
        raise HTTPException(status_code=400, detail=result["error"])
    return result


@router.post("/initiatives/{initiative_id}/review")
async def review_initiative(initiative_id: str, user=Depends(get_current_user)):
    """Transition initiative to review. Transitions: completing -> review."""
    from core.engine.pm.tracker import InitiativeTracker

    product_id = user.get("product", "")
    tracker = InitiativeTracker(db_pool=pool)
    initiative = await tracker.get_initiative(initiative_id, product_id)
    if not initiative:
        raise HTTPException(status_code=404, detail="Initiative not found")

    if initiative.get("status") != "completing":
        raise HTTPException(status_code=400, detail=f"Cannot review from state '{initiative['status']}'")

    async with pool.connection() as db:
        await db.query(
            "UPDATE <record>$id SET status = 'review', reviewed_at = time::now()",
            {"id": initiative_id},
        )

    from core.engine.events.bus import bus

    await bus.emit(
        "gate.pending",
        {
            "entity_type": "initiative",
            "entity_id": initiative_id,
            "gate_state": "review",
            "product_id": product_id,
        },
    )

    return {"initiative_id": initiative_id, "status": "review"}


@router.post("/initiatives/{initiative_id}/complete")
async def complete_initiative_review(initiative_id: str, user=Depends(get_current_user)):
    """PM approves completion. Transitions: review -> completed."""
    product_id = user.get("product", "")
    user_id = user.get("sub", "user:default")

    from core.engine.pm.gate_engine import GateEngine

    ge = GateEngine(pool)
    result = await ge.approve_gate("initiative", initiative_id, "review", "Quality acceptable", product_id, user_id)
    return result


@router.post("/milestones/{milestone_id}/approve")
async def approve_milestone(milestone_id: str, product: str | None = None, user=Depends(get_current_user)):
    """Approve a milestone gate. Triggers next milestone decomposition."""
    from core.engine.pm.approvals import ApprovalManager

    product_id = product or user.get("product", "")
    approvals = ApprovalManager(db_pool=pool)
    result = await approvals.approve_milestone(
        milestone_id=milestone_id,
        approver_id=user["sub"],
        product_id=product_id,
    )
    return result


@router.post("/milestones/{milestone_id}/reject")
async def reject_milestone(
    milestone_id: str,
    body: ApproveRejectRequest,
    product: str | None = None,
    user=Depends(get_current_user),
):
    """Reject a milestone with feedback. Returns to previous work."""
    from core.engine.pm.approvals import ApprovalManager

    product_id = product or user.get("product", "")
    approvals = ApprovalManager(db_pool=pool)
    result = await approvals.reject_milestone(
        milestone_id=milestone_id,
        rejector_id=user["sub"],
        feedback=body.feedback or "",
        product_id=product_id,
    )
    return result
