# engine/api/ecosystem.py
"""REST API for ecosystem and project hierarchy."""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from core.engine.core.auth import get_current_user
from core.engine.core.db import pool
from core.engine.product.ecosystem import EcosystemManager
from core.engine.product.portfolio import get_cross_product_alerts, get_portfolio_summary, get_project_badges

router = APIRouter(tags=["ecosystem"])


# ------------------------------------------------------------------
# Ecosystems
# ------------------------------------------------------------------


@router.get("/ecosystems")
async def list_ecosystems(user=Depends(get_current_user)):
    """List all ecosystems for the org."""
    product_id = user.get("product", "")
    em = EcosystemManager(pool)
    ecosystems = await em.get_ecosystems(product_id)
    return {"ecosystems": ecosystems, "count": len(ecosystems)}


@router.get("/ecosystems/{slug}")
async def get_ecosystem(slug: str, user=Depends(get_current_user)):
    """Get an ecosystem with its projects."""
    product_id = user.get("product", "")
    em = EcosystemManager(pool)
    eco = await em.get_ecosystem(slug, product_id)
    if not eco:
        raise HTTPException(status_code=404, detail="Ecosystem not found")
    return eco


@router.post("/ecosystems", status_code=201)
async def create_ecosystem(body: dict, user=Depends(get_current_user)):
    """Create or upsert an ecosystem."""
    product_id = user.get("product", "")
    em = EcosystemManager(pool)
    return await em.create_ecosystem(body, product_id)


# ------------------------------------------------------------------
# Projects
# ------------------------------------------------------------------


@router.get("/projects")
async def list_projects(ecosystem: str | None = None, user=Depends(get_current_user)):
    """List projects for the org, optionally filtered by ecosystem slug."""
    product_id = user.get("product", "")
    em = EcosystemManager(pool)
    projects = await em.get_projects(product_id, ecosystem)
    return {"projects": projects, "count": len(projects)}


# ------------------------------------------------------------------
# Portfolio (multi-product workspace)
# ------------------------------------------------------------------


@router.get("/projects/portfolio")
async def portfolio(user=Depends(get_current_user)):
    """Portfolio summary cards for the tower view."""
    product_id = user.get("product", "")
    projects = await get_portfolio_summary(product_id)
    return {"projects": projects, "count": len(projects)}


@router.get("/projects/alerts")
async def cross_product_alerts(user=Depends(get_current_user)):
    """Cross-product alerts for the tower view."""
    product_id = user.get("product", "")
    alerts = await get_cross_product_alerts(product_id)
    return {"alerts": alerts, "count": len(alerts)}


@router.get("/projects/badges")
async def badges(user=Depends(get_current_user)):
    """Badge data for all products — consumed by the product rail."""
    product_id = user.get("product", "")
    user_id = user.get("sub", "")
    badge_data = await get_project_badges(product_id, user_id)
    return {"badges": badge_data}


class OnboardProjectRequest(BaseModel):
    repo_path: str | None = None
    git_url: str | None = None
    name: str | None = None
    description: str | None = None
    ecosystem_slug: str | None = None
    active_disciplines: list[str] | None = None


@router.post("/projects/onboard", status_code=201)
async def onboard_project(body: OnboardProjectRequest, user=Depends(get_current_user)):
    """Onboard a new project — create record and optionally trigger scan."""
    product_id = user.get("product", "")
    em = EcosystemManager(pool)

    # Derive slug from name or repo path
    name = body.name or (body.repo_path or "").split("/")[-1] or "unnamed"
    slug = name.lower().replace(" ", "-").replace("_", "-")

    project_data = {
        "name": name,
        "slug": slug,
        "description": body.description or "",
        "repo_path": body.repo_path,
        "active_disciplines": body.active_disciplines or [],
    }

    if body.ecosystem_slug:
        project_data["ecosystem_slug"] = body.ecosystem_slug

    project = await em.create_project(project_data, product_id)
    return {"project": project, "slug": slug}


@router.get("/projects/{slug}")
async def get_project(slug: str, user=Depends(get_current_user)):
    """Get a project with its capabilities."""
    product_id = user.get("product", "")
    em = EcosystemManager(pool)
    project = await em.get_project(slug, product_id)
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")
    return project


@router.post("/projects", status_code=201)
async def create_project(body: dict, user=Depends(get_current_user)):
    """Create or upsert a project."""
    product_id = user.get("product", "")
    em = EcosystemManager(pool)
    return await em.create_project(body, product_id)


# ------------------------------------------------------------------
# Hierarchy
# ------------------------------------------------------------------


@router.get("/hierarchy")
async def get_hierarchy(user=Depends(get_current_user)):
    """Full hierarchy tree: ecosystems → projects → capability counts."""
    product_id = user.get("product", "")
    em = EcosystemManager(pool)
    return await em.get_hierarchy(product_id)
