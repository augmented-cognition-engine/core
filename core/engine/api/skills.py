# engine/api/skills.py
"""Skills API — CRUD for skill definitions.

GET /skills — list skills (filter by domain_path, tier)
GET /skills/{slug} — get a single skill
POST /skills — create a custom skill
PUT /skills/{slug} — update a skill
DELETE /skills/{slug} — delete a custom skill (not built-in)
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel

from core.engine.core.auth import get_current_user
from core.engine.core.db import parse_rows, pool

router = APIRouter(prefix="/skills", tags=["skills"])


class JobRequest(BaseModel):
    name: str
    archetype: str
    mode: str
    frameworks: list[str] = []
    output_format: str = "prose"
    description: str = ""


class SkillCreateRequest(BaseModel):
    slug: str
    name: str
    description: str
    domain_path: str | None = None
    jobs: list[JobRequest]
    activation_signals: list[str] = []


class SkillUpdateRequest(BaseModel):
    name: str | None = None
    description: str | None = None
    domain_path: str | None = None
    jobs: list[JobRequest] | None = None
    activation_signals: list[str] | None = None


@router.get("")
async def list_skills(
    product: str = Query(default="product:default"),
    domain_path: str | None = Query(default=None),
    tier: str | None = Query(default=None),
    user: dict = Depends(get_current_user),
):
    """List skills — built-in + org-specific. Filter by domain_path or tier."""
    async with pool.connection() as db:
        where = "(org IS NONE OR product = <record>$product)"
        if domain_path and tier:
            where += " AND domain_path = <string>$dp AND tier = <string>$tier"
        elif domain_path:
            where += " AND domain_path = <string>$dp"
        elif tier:
            where += " AND tier = <string>$tier"
        result = await db.query(
            f"SELECT * FROM skill WHERE {where} ORDER BY name",
            {"product": product, "dp": domain_path, "tier": tier},
        )
        rows = parse_rows(result)
    return {"skills": rows}


@router.get("/{slug}")
async def get_skill(slug: str, user: dict = Depends(get_current_user)):
    """Get a single skill by slug."""
    async with pool.connection() as db:
        result = await db.query(
            "SELECT * FROM skill WHERE slug = <string>$slug LIMIT 1",
            {"slug": slug},
        )
        rows = parse_rows(result)
    if not rows:
        raise HTTPException(status_code=404, detail="Skill not found")
    return rows[0]


@router.post("", status_code=201)
async def create_skill(
    body: SkillCreateRequest,
    product: str = Query(default="product:default"),
    user: dict = Depends(get_current_user),
):
    """Create a custom skill."""
    async with pool.connection() as db:
        result = await db.query(
            """
            CREATE skill SET
                product = <record>$product,
                slug = $slug,
                name = $name,
                description = $description,
                domain_path = $domain_path,
                tier = 'custom',
                jobs = $jobs,
                activation_signals = $signals,
                created_at = time::now()
            """,
            {
                "product": product,
                "slug": body.slug,
                "name": body.name,
                "description": body.description,
                "domain_path": body.domain_path,
                "jobs": [j.model_dump() for j in body.jobs],
                "signals": body.activation_signals,
            },
        )
        rows = parse_rows(result)
    return rows[0] if rows else {"slug": body.slug, "status": "created"}


@router.put("/{slug}")
async def update_skill(
    slug: str,
    body: SkillUpdateRequest,
    user: dict = Depends(get_current_user),
):
    """Update a skill's fields."""
    updates = []
    params: dict = {"slug": slug}

    if body.name is not None:
        updates.append("name = $name")
        params["name"] = body.name
    if body.description is not None:
        updates.append("description = $description")
        params["description"] = body.description
    if body.domain_path is not None:
        updates.append("domain_path = $domain_path")
        params["domain_path"] = body.domain_path
    if body.jobs is not None:
        updates.append("jobs = $jobs")
        params["jobs"] = [j.model_dump() for j in body.jobs]
    if body.activation_signals is not None:
        updates.append("activation_signals = $signals")
        params["signals"] = body.activation_signals

    if not updates:
        raise HTTPException(status_code=400, detail="No fields to update")

    set_clause = ", ".join(updates)

    async with pool.connection() as db:
        result = await db.query(
            f"UPDATE skill SET {set_clause} WHERE slug = <string>$slug",
            params,
        )
        rows = parse_rows(result)
    if not rows:
        raise HTTPException(status_code=404, detail="Skill not found")
    return rows[0]


@router.delete("/{slug}")
async def delete_skill(slug: str, user: dict = Depends(get_current_user)):
    """Delete a custom skill. Cannot delete built-in skills."""
    async with pool.connection() as db:
        # Check if built-in
        check = await db.query(
            "SELECT tier FROM skill WHERE slug = <string>$slug LIMIT 1",
            {"slug": slug},
        )
        check_rows = parse_rows(check)
        if not check_rows:
            raise HTTPException(status_code=404, detail="Skill not found")
        if check_rows[0].get("tier") == "built-in":
            raise HTTPException(status_code=403, detail="Cannot delete built-in skills")

        await db.query("DELETE skill WHERE slug = <string>$slug", {"slug": slug})
    return {"deleted": slug}
