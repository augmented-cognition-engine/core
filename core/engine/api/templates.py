"""REST API for template management."""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from core.engine.core.auth import get_current_user
from core.engine.core.db import parse_rows, pool

router = APIRouter(prefix="/templates", tags=["templates"])


class CreateTemplateRequest(BaseModel):
    name: str
    description: str
    domain_path: str
    milestones: list[dict] = []
    variables: list[dict] = []


class InstantiateRequest(BaseModel):
    variables: dict[str, str] = {}
    workspace_id: str | None = None


@router.get("")
async def list_templates(product: str | None = None, user=Depends(get_current_user)):
    """List templates for org."""
    product_id = product or user.get("product", "")
    async with pool.connection() as db:
        result = await db.query(
            "SELECT * FROM template WHERE product = <record>$product ORDER BY created_at DESC",
            {"product": product_id},
        )
        rows = parse_rows(result)
    return {"templates": rows}


@router.get("/{template_id}")
async def get_template(template_id: str, user=Depends(get_current_user)):
    """Get template detail."""
    async with pool.connection() as db:
        result = await db.query("SELECT * FROM ONLY <record>$id", {"id": template_id})
        rows = parse_rows(result)
    if not rows:
        raise HTTPException(status_code=404, detail="Template not found")
    return rows[0]


@router.post("", status_code=201)
async def create_template(body: CreateTemplateRequest, user=Depends(get_current_user)):
    """Create a new template."""
    async with pool.connection() as db:
        result = await db.query(
            """
            CREATE template SET
                name = $name,
                description = $description,
                domain_path = $domain_path,
                milestones = $milestones,
                variables = $variables,
                created_by = $user
            """,
            {
                "product": user.get("product", ""),
                "name": body.name,
                "description": body.description,
                "domain_path": body.domain_path,
                "milestones": body.milestones,
                "variables": body.variables,
                "user": user["sub"],
            },
        )
        rows = parse_rows(result)
    return rows[0] if rows else {"name": body.name, "status": "created"}


@router.post("/{template_id}/instantiate")
async def instantiate_template_endpoint(
    template_id: str,
    body: InstantiateRequest,
    user=Depends(get_current_user),
):
    """Instantiate a template with variable values — creates an initiative."""
    async with pool.connection() as db:
        result = await db.query("SELECT * FROM ONLY <record>$id", {"id": template_id})
        rows = parse_rows(result)
    if not rows:
        raise HTTPException(status_code=404, detail="Template not found")

    from core.engine.templates.instantiate import TemplateVariableError, instantiate_template

    try:
        return await instantiate_template(
            playbook=rows[0],
            variables=body.variables,
            user_id=user["sub"],
            product_id=user.get("product", ""),
            workspace_id=body.workspace_id,
        )
    except TemplateVariableError as e:
        raise HTTPException(status_code=400, detail=str(e))
