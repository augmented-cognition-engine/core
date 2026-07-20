# engine/api/onboarding.py
"""Onboarding API — scaffold project + specialties from a description.

POST /onboarding
  Body: {"role_description": "...", "project_description": "...", "repo_path": "..."}
  Auth: JWT required
  201: {"project": {...}, "specialties_created": N, "specialties": [...]}
  409: already onboarded
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from core.engine.core.auth import get_current_user
from core.engine.core.db import parse_rows, pool
from core.engine.onboarding.scaffolder import (
    needs_onboarding,
    scaffold_project,
    scaffold_specialties,
)
from core.engine.product.capability_mapper import CapabilityMapper

router = APIRouter(prefix="/onboarding", tags=["onboarding"])


class OnboardingRequest(BaseModel):
    role_description: str
    project_description: str | None = None
    repo_path: str | None = None


@router.post("", status_code=201)
async def onboard(
    body: OnboardingRequest,
    user: dict = Depends(get_current_user),
):
    """Scaffold project and specialties for an org.

    - If project_description is provided, creates the project and activates disciplines.
    - Always scaffolds specialties from role_description.
    - Returns 409 if the org is already onboarded (has projects and specialties).
    """
    product_id: str = user.get("product", "product:default")

    if not await needs_onboarding(product_id):
        raise HTTPException(status_code=409, detail="Already onboarded")

    project: dict = {}
    if body.project_description:
        project = await scaffold_project(body.project_description, product_id, repo_path=body.repo_path)

    specialties = await scaffold_specialties(body.role_description, product_id)

    return {
        "project": project,
        "specialties_created": len(specialties),
        "specialties": specialties,
    }


@router.get("/status")
async def onboarding_status(
    user: dict = Depends(get_current_user),
):
    """Check if org needs onboarding. Single source of truth."""
    product_id: str = user.get("product", "product:default")

    async with pool.connection() as db:
        cap_result = await db.query(
            "SELECT count() FROM capability WHERE product = <record>$product GROUP ALL",
            {"product": product_id},
        )
        caps = parse_rows(cap_result)
        cap_count = caps[0].get("count", 0) if caps else 0

        proj_result = await db.query(
            "SELECT id FROM project WHERE product = <record>$product LIMIT 1",
            {"product": product_id},
        )
        projects = parse_rows(proj_result)
        has_project = len(projects) > 0

        # Check org-level onboarding flag
        org_result = await db.query(
            "SELECT onboarding_complete FROM <record>$product",
            {"product": product_id},
        )
        org_row = parse_rows(org_result)
        onboarding_complete = bool(org_row[0].get("onboarding_complete")) if org_row else False

    return {
        "needs_onboarding": not onboarding_complete and cap_count == 0 and not has_project,
        "capabilities_count": cap_count,
        "has_project": has_project,
    }


class GreenfieldRequest(BaseModel):
    description: str


class CompleteRequest(BaseModel):
    create_initiative: bool = False
    initiative_title: str | None = None
    initiative_description: str | None = None
    capability_slug: str | None = None
    path: str = "existing"  # "existing" | "greenfield"


@router.post("/greenfield")
async def onboarding_greenfield(
    body: GreenfieldRequest,
    user: dict = Depends(get_current_user),
):
    """Generate capability map from project description (greenfield path)."""
    product_id: str = user.get("product", "product:default")
    mapper = CapabilityMapper(pool)
    result = await mapper.bootstrap_from_intent(body.description, product_id)
    return result


@router.post("/complete")
async def onboarding_complete(
    body: CompleteRequest,
    user: dict = Depends(get_current_user),
):
    """Mark onboarding complete, optionally create first initiative."""
    product_id: str = user.get("product", "product:default")
    initiative_id = None

    async with pool.connection() as db:
        # Create initiative if requested
        if body.create_initiative and body.initiative_title:
            result = await db.query(
                """CREATE initiative SET
                    title = $title,
                    description = $desc,
                    status = 'active',
                    source = 'onboarding',
                    created_at = time::now()""",
                {
                    "product": product_id,
                    "title": body.initiative_title,
                    "desc": body.initiative_description or "",
                },
            )
            rows = parse_rows(result)
            if rows:
                initiative_id = str(rows[0].get("id", ""))

        # Mark onboarding complete on org
        await db.query(
            "UPDATE <record>$product SET onboarding_complete = true",
            {"product": product_id},
        )

    # Run existing scaffolders if first project for this org
    if await needs_onboarding(product_id):
        if body.path == "greenfield" and body.initiative_title:
            await scaffold_project(body.initiative_title, product_id)
        await scaffold_specialties("general software development", product_id)

    return {
        "initiative_id": initiative_id,
        "onboarding_complete": True,
    }
