"""Token Intelligence API — serves ledger data to the portal dashboard."""

from __future__ import annotations

from fastapi import APIRouter, Depends, Query

from core.engine.api.auth_routes import get_current_user
from core.engine.intelligence.token_ledger import TokenLedger

router = APIRouter(prefix="/token-intelligence", tags=["token-intelligence"])
_ledger = TokenLedger()


@router.get("/summary")
async def get_summary(
    project: str = Query(...),
    days: int = Query(30, ge=1, le=365),
    user=Depends(get_current_user),
) -> dict:
    return await _ledger.get_summary(product_id=project, days=days)


@router.get("/passes")
async def get_passes(
    project: str = Query(...),
    days: int = Query(30, ge=1, le=365),
    user=Depends(get_current_user),
) -> list[dict]:
    return await _ledger.get_passes_by_discipline(product_id=project, days=days)


@router.get("/failures")
async def get_failures(
    project: str = Query(...),
    days: int = Query(30, ge=1, le=365),
    user=Depends(get_current_user),
) -> list[dict]:
    return await _ledger.get_failure_categories(product_id=project, days=days)


@router.get("/routing")
async def get_routing(
    project: str = Query(...),
    weeks: int = Query(12, ge=1, le=52),
    user=Depends(get_current_user),
) -> list[dict]:
    return await _ledger.get_weekly_trend(product_id=project, weeks=weeks)
