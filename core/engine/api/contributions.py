"""Contributions dashboard API — /portal/contributions/{product_id}."""

from __future__ import annotations

from fastapi import APIRouter, Depends

from core.engine.api._portal_security import verify_product_access
from core.engine.contributions.aggregator import compute_contributions
from core.engine.core.db import pool

router = APIRouter(prefix="/portal/contributions", tags=["contributions"])


@router.get("/{product_id}")
async def get_contributions(product_id: str, user=Depends(verify_product_access)) -> dict:
    return await compute_contributions(pool, product_id)
