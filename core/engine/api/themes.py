"""REST API for themes — strategic bets between vision and initiatives."""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException

from core.engine.core.auth import get_current_user
from core.engine.core.db import pool
from core.engine.product.map import ProductMap
from core.engine.product.models import ThemeCreate

router = APIRouter(tags=["themes"])


@router.get("/themes")
async def list_themes(status: str = "active", user=Depends(get_current_user)):
    """List themes for the org."""
    product_id = user.get("product", "")
    pm = ProductMap(pool)
    themes = await pm.get_themes(product_id, status)
    return {"themes": themes, "count": len(themes)}


@router.post("/themes", status_code=201)
async def create_theme(body: ThemeCreate, user=Depends(get_current_user)):
    """Create a new theme."""
    product_id = user.get("product", "")
    pm = ProductMap(pool)
    theme = await pm.create_theme(body.model_dump(), product_id)
    return theme


@router.patch("/themes/{theme_id}")
async def update_theme(theme_id: str, body: dict, user=Depends(get_current_user)):
    """Update a theme's name, description, or status."""
    product_id = user.get("product", "")
    pm = ProductMap(pool)
    allowed = {k: v for k, v in body.items() if k in {"name", "description", "status"}}
    if not allowed:
        raise HTTPException(status_code=400, detail="No valid fields to update")
    theme = await pm.update_theme(theme_id, allowed, product_id)
    if theme is None:
        raise HTTPException(status_code=404, detail="Theme not found")
    return theme


@router.delete("/themes/{theme_id}")
async def archive_theme(theme_id: str, user=Depends(get_current_user)):
    """Archive a theme (status=archived)."""
    product_id = user.get("product", "")
    pm = ProductMap(pool)
    theme = await pm.update_theme(theme_id, {"status": "archived"}, product_id)
    if theme is None:
        raise HTTPException(status_code=404, detail="Theme not found")
    return theme
