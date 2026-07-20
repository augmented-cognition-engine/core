# engine/api/self_optimizer.py
"""Self-optimizer proposals API.

GET  /self-optimizer/proposals         — list proposals for org (filter by status, type)
POST /self-optimizer/proposals/{id}/approve  — approve + materialise skill or framework
POST /self-optimizer/proposals/{id}/dismiss  — dismiss proposal
"""

from __future__ import annotations

import re

from fastapi import APIRouter, Depends, HTTPException, Query

from core.engine.core.auth import get_current_user
from core.engine.core.db import parse_rows, pool

router = APIRouter(prefix="/self-optimizer", tags=["self-optimizer"])


def _slugify(name: str) -> str:
    """Convert a name to a URL-safe slug."""
    slug = name.lower().strip()
    slug = re.sub(r"[^a-z0-9]+", "-", slug)
    return slug.strip("-") or "proposal"


# ---------------------------------------------------------------------------
# GET /self-optimizer/proposals
# ---------------------------------------------------------------------------


@router.get("/proposals")
async def list_proposals(
    product: str = Query(default="product:default"),
    status: str | None = Query(default=None),
    type: str | None = Query(default=None),
    user: dict = Depends(get_current_user),
):
    """List self-optimizer proposals for an org, optionally filtered by status and/or type."""
    async with pool.connection() as db:
        if status and type:
            result = await db.query(
                """SELECT * FROM self_optimizer_proposal
                   WHERE product = <record>$product AND status = $status AND type = $type
                   ORDER BY created_at DESC""",
                {"product": product, "status": status, "type": type},
            )
        elif status:
            result = await db.query(
                """SELECT * FROM self_optimizer_proposal
                   WHERE product = <record>$product AND status = $status
                   ORDER BY created_at DESC""",
                {"product": product, "status": status},
            )
        elif type:
            result = await db.query(
                """SELECT * FROM self_optimizer_proposal
                   WHERE product = <record>$product AND type = $type
                   ORDER BY created_at DESC""",
                {"product": product, "type": type},
            )
        else:
            result = await db.query(
                """SELECT * FROM self_optimizer_proposal
                   WHERE product = <record>$product
                   ORDER BY created_at DESC""",
                {"product": product},
            )
        rows = parse_rows(result)
    return {"proposals": rows}


# ---------------------------------------------------------------------------
# POST /self-optimizer/proposals/{id}/approve
# ---------------------------------------------------------------------------


@router.post("/proposals/{proposal_id}/approve")
async def approve_proposal(
    proposal_id: str,
    product: str = Query(default="product:default"),
    user: dict = Depends(get_current_user),
):
    """Approve a proposal — sets status='approved' and materialises it as a skill or framework."""
    async with pool.connection() as db:
        result = await db.query(
            "SELECT * FROM ONLY <record>$id",
            {"id": proposal_id},
        )
        rows = parse_rows(result)

    if not rows:
        raise HTTPException(status_code=404, detail="Proposal not found")

    proposal = rows[0]

    if proposal.get("product") != product:
        raise HTTPException(status_code=403, detail="Proposal does not belong to this org")

    current_status = proposal.get("status", "pending")
    if current_status == "approved":
        raise HTTPException(status_code=409, detail="Proposal is already approved")
    if current_status == "dismissed":
        raise HTTPException(status_code=409, detail="Cannot approve a dismissed proposal")

    proposal_type = proposal.get("type")
    draft = proposal.get("draft") or {}
    name = proposal.get("name", "Untitled")
    description = proposal.get("description", "")

    created_record: dict | None = None

    async with pool.connection() as db:
        # Mark proposal approved
        await db.query(
            """UPDATE <record>$id SET
                   status = 'approved',
                   reviewed_at = time::now()""",
            {"id": proposal_id},
        )

        # Materialise based on type
        if proposal_type == "skill":
            slug = _slugify(name)
            jobs = draft.get("jobs") or []
            activation_signals = draft.get("activation_signals") or []
            domain_path = draft.get("domain_path")

            skill_result = await db.query(
                """CREATE skill SET
                       slug = $slug,
                       name = $name,
                       description = $description,
                       domain_path = $domain_path,
                       tier = 'custom',
                       jobs = $jobs,
                       activation_signals = $signals,
                       source = 'self_optimizer',
                       created_at = time::now()""",
                {
                    "product": product,
                    "slug": slug,
                    "name": name,
                    "description": description,
                    "domain_path": domain_path,
                    "jobs": jobs,
                    "signals": activation_signals,
                },
            )
            skill_rows = parse_rows(skill_result)
            created_record = skill_rows[0] if skill_rows else {"slug": slug, "status": "created"}

        elif proposal_type == "framework":
            slug = _slugify(name)
            system_prompt = draft.get("system_prompt", "")
            activation_signals = draft.get("activation_signals") or []
            family = draft.get("family", "custom")
            domain_path = draft.get("domain_path")

            fw_result = await db.query(
                """CREATE framework SET
                       slug = $slug,
                       name = $name,
                       family = $family,
                       tier = 'custom',
                       domain_path = $domain_path,
                       description = $description,
                       system_prompt = $prompt,
                       activation_signals = $signals,
                       source = 'self_optimizer',
                       created_at = time::now()""",
                {
                    "product": product,
                    "slug": slug,
                    "name": name,
                    "family": family,
                    "domain_path": domain_path,
                    "description": description,
                    "prompt": system_prompt,
                    "signals": activation_signals,
                },
            )
            fw_rows = parse_rows(fw_result)
            created_record = fw_rows[0] if fw_rows else {"slug": slug, "status": "created"}

    return {
        "proposal_id": proposal_id,
        "status": "approved",
        "type": proposal_type,
        "created": created_record,
    }


# ---------------------------------------------------------------------------
# POST /self-optimizer/proposals/{id}/dismiss
# ---------------------------------------------------------------------------


@router.post("/proposals/{proposal_id}/dismiss")
async def dismiss_proposal(
    proposal_id: str,
    product: str = Query(default="product:default"),
    user: dict = Depends(get_current_user),
):
    """Dismiss a proposal — sets status='dismissed'."""
    async with pool.connection() as db:
        result = await db.query(
            "SELECT * FROM ONLY <record>$id",
            {"id": proposal_id},
        )
        rows = parse_rows(result)

    if not rows:
        raise HTTPException(status_code=404, detail="Proposal not found")

    proposal = rows[0]

    if proposal.get("product") != product:
        raise HTTPException(status_code=403, detail="Proposal does not belong to this org")

    if proposal.get("status") == "dismissed":
        raise HTTPException(status_code=409, detail="Proposal is already dismissed")

    async with pool.connection() as db:
        await db.query(
            """UPDATE <record>$id SET
                   status = 'dismissed',
                   reviewed_at = time::now()""",
            {"id": proposal_id},
        )

    return {"proposal_id": proposal_id, "status": "dismissed"}
