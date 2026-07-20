"""REST API for the product awareness layer — capabilities, vision, health, quality."""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException

from core.engine.core.auth import get_current_user
from core.engine.core.db import parse_one, parse_rows, pool
from core.engine.product.acceptance import AcceptanceVerifier
from core.engine.product.feedback_handler import FeedbackHandler
from core.engine.product.map import ProductMap
from core.engine.product.models import CapabilityCreate, CapabilityUpdate, QualityAssessment, VisionCreate
from core.engine.product.spec_generator import SpecGenerator
from core.engine.product.spec_models import AgentFeedbackCreate

router = APIRouter(tags=["product"])


# ------------------------------------------------------------------
# Capabilities
# ------------------------------------------------------------------


@router.get("/product/capabilities")
async def list_capabilities(status: str | None = None, project: str | None = None, user=Depends(get_current_user)):
    """List all capabilities for the org, optionally filtered by status and/or project."""
    product_id = user.get("product", "")
    pm = ProductMap(pool)
    capabilities = await pm.get_capabilities(product_id, status, project)
    return {"capabilities": capabilities, "count": len(capabilities)}


@router.get("/product/capabilities/{slug}")
async def get_capability(slug: str, user=Depends(get_current_user)):
    """Get a single capability with quality dimensions, dependencies, and realized files."""
    product_id = user.get("product", "")
    pm = ProductMap(pool)
    cap = await pm.get_capability(slug, product_id)
    if cap is None:
        raise HTTPException(status_code=404, detail=f"Capability '{slug}' not found")
    return cap


@router.post("/product/capabilities", status_code=201)
async def create_capability(body: CapabilityCreate, user=Depends(get_current_user)):
    """Create or upsert a capability."""
    product_id = user.get("product", "")
    pm = ProductMap(pool)
    cap = await pm.upsert_capability(body.model_dump(), product_id)
    return cap


@router.patch("/product/capabilities/{slug}")
async def update_capability(slug: str, body: CapabilityUpdate, user=Depends(get_current_user)):
    """Update fields on an existing capability."""
    product_id = user.get("product", "")
    pm = ProductMap(pool)

    # Verify it exists
    existing = await pm.get_capability(slug, product_id)
    if existing is None:
        raise HTTPException(status_code=404, detail=f"Capability '{slug}' not found")

    # Merge update into existing data, excluding unset fields
    data = {**existing, **{k: v for k, v in body.model_dump().items() if v is not None}}
    data["slug"] = slug
    updated = await pm.upsert_capability(data, product_id)
    return updated


@router.delete("/product/capabilities/{slug}")
async def archive_capability(slug: str, user=Depends(get_current_user)):
    """Archive a capability by setting its status to deprecated."""
    product_id = user.get("product", "")
    pm = ProductMap(pool)

    existing = await pm.get_capability(slug, product_id)
    if existing is None:
        raise HTTPException(status_code=404, detail=f"Capability '{slug}' not found")

    data = {**existing, "slug": slug, "status": "deprecated"}
    await pm.upsert_capability(data, product_id)
    return {"slug": slug, "status": "deprecated"}


# ------------------------------------------------------------------
# Vision
# ------------------------------------------------------------------


@router.get("/product/vision")
async def get_vision(user=Depends(get_current_user)):
    """Get the active product vision."""
    product_id = user.get("product", "")
    pm = ProductMap(pool)
    vision = await pm.get_vision(product_id)
    if vision is None:
        return {"active": False, "message": "No active vision set"}
    return vision


@router.post("/product/vision", status_code=201)
async def set_vision(body: VisionCreate, user=Depends(get_current_user)):
    """Set a new product vision, superseding the previous one."""
    product_id = user.get("product", "")
    pm = ProductMap(pool)
    vision = await pm.set_vision(body.model_dump(), product_id)
    return vision


# ------------------------------------------------------------------
# Health summary
# ------------------------------------------------------------------


@router.get("/product/health")
async def get_health(project: str | None = None, user=Depends(get_current_user)):
    """Return aggregate quality summary across all capabilities, optionally filtered by project."""
    product_id = user.get("product", "")
    pm = ProductMap(pool)
    summary = await pm.health_summary(product_id, project)
    return summary


# ------------------------------------------------------------------
# Quality assessment
# ------------------------------------------------------------------


@router.post("/product/capabilities/{slug}/quality", status_code=201)
async def assess_quality(slug: str, body: QualityAssessment, user=Depends(get_current_user)):
    """Record or update a quality assessment for a capability dimension."""
    product_id = user.get("product", "")
    pm = ProductMap(pool)

    # Verify capability exists
    existing = await pm.get_capability(slug, product_id)
    if existing is None:
        raise HTTPException(status_code=404, detail=f"Capability '{slug}' not found")

    result = await pm.update_quality(slug, body.dimension, body.model_dump(), product_id)
    return result


# ------------------------------------------------------------------
# Agent Specs
# ------------------------------------------------------------------


@router.post("/product/specs", status_code=201)
async def create_spec(body: dict, user=Depends(get_current_user)):
    """Create an agent spec from a gap, idea, or human request.

    Body options:
    - {source: "gap", gap: {...}, capability_slug: "auth"} → SpecGenerator.from_gap
    - {source: "idea", idea: {...}} → SpecGenerator.from_idea
    - {source: "human", request: "add rate limiting"} → SpecGenerator.from_request
    """
    product_id = user.get("product", "")
    gen = SpecGenerator(pool)

    source = body.get("source", "human")
    if source == "gap":
        result = await gen.from_gap(body.get("gap", {}), body.get("capability_slug", ""), product_id)
    elif source == "idea":
        result = await gen.from_idea(body.get("idea", {}), product_id)
    else:
        result = await gen.from_request(body.get("request", ""), product_id)

    if "error" in result:
        raise HTTPException(status_code=400, detail=result["error"])
    return result


@router.get("/product/specs")
async def list_specs(status: str | None = None, project: str | None = None, user=Depends(get_current_user)):
    """List agent specs, optionally filtered by status and/or project."""
    product_id = user.get("product", "")
    project_clause = ""
    if project:
        # decision:6vacauzia2jc46hpvms8 — `= (SELECT VALUE ... LIMIT 1)` returns
        # empty in SurrealDB v3 (subquery yields 1-element array, not scalar).
        project_clause = " AND project IN (SELECT VALUE id FROM project WHERE product = <record>$product AND slug = <string>$project)"
    async with pool.connection() as db:
        if status:
            result = await db.query(
                f"SELECT * FROM agent_spec WHERE product = <record>$product AND status = <string>$status{project_clause} ORDER BY created_at DESC",
                {"product": product_id, "status": status, "project": project},
            )
        else:
            result = await db.query(
                f"SELECT * FROM agent_spec WHERE product = <record>$product{project_clause} ORDER BY created_at DESC",
                {"product": product_id, "project": project},
            )
        specs = parse_rows(result)
    return {"specs": specs, "count": len(specs)}


@router.patch("/product/specs/{spec_id}")
async def update_spec(spec_id: str, body: dict, user=Depends(get_current_user)):
    """Update a spec (e.g., approve it, change status)."""
    allowed_fields = {"status", "objective", "acceptance_criteria", "constraints", "context"}
    updates = {k: v for k, v in body.items() if k in allowed_fields}
    if not updates:
        raise HTTPException(status_code=400, detail="No valid fields to update")

    # Build SET clause
    set_parts = [f"{k} = ${k}" for k in updates]
    set_parts.append("updated_at = time::now()")
    set_clause = ", ".join(set_parts)

    async with pool.connection() as db:
        result = await db.query(
            f"UPDATE <record>$spec_id SET {set_clause}",
            {"spec_id": spec_id, **updates},
        )
        spec = parse_one(result)
    if not spec:
        raise HTTPException(status_code=404, detail="Spec not found")
    return spec


@router.post("/product/specs/{spec_id}/verify")
async def verify_spec(spec_id: str, user=Depends(get_current_user)):
    """Trigger acceptance verification for a spec."""
    product_id = user.get("product", "")
    verifier = AcceptanceVerifier(pool)
    result = await verifier.verify(spec_id, product_id)
    if "error" in result:
        raise HTTPException(status_code=400, detail=result["error"])
    return result


# ------------------------------------------------------------------
# Agent Feedback
# ------------------------------------------------------------------


@router.post("/product/feedback", status_code=201)
async def submit_feedback(body: dict, user=Depends(get_current_user)):
    """Submit agent feedback to the PM."""
    product_id = user.get("product", "")
    feedback = AgentFeedbackCreate(**body)
    handler = FeedbackHandler(pool)
    result = await handler.handle(feedback, product_id)
    return result


@router.post("/product/seed-best-practices")
async def seed_best_practices(
    discipline: str | None = None,
    user=Depends(get_current_user),
):
    """Generate best practice insights for all (or one) discipline.

    This calls the LLM for each specialty to generate 3-5 actionable practices.
    Idempotent — skips specialties that already have enough practices.
    """
    product_id = user.get("product", "")
    from core.engine.product.seed_generator import BestPracticeSeedGenerator

    generator = BestPracticeSeedGenerator(pool)

    if discipline:
        from core.engine.product.seed_packs import SEED_STRUCTURE

        config = SEED_STRUCTURE.get(discipline)
        if not config:
            raise HTTPException(status_code=404, detail=f"Unknown discipline: {discipline}")
        total = 0
        for specialty_slug in config["specialties"]:
            created = await generator.generate_for_specialty(specialty_slug, discipline, product_id)
            total += len(created)
        return {"discipline": discipline, "created": total}
    else:
        result = await generator.generate_all(product_id)
        return result
