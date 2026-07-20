# engine/api/velocity.py
"""REST API for developer velocity metrics."""

from __future__ import annotations

from fastapi import APIRouter, Depends

from core.engine.core.auth import get_current_user

router = APIRouter(tags=["velocity"])


@router.get("/velocity/{owner}/{repo}")
async def get_velocity(
    owner: str,
    repo: str,
    period_days: int = 30,
    user=Depends(get_current_user),
):
    """Get developer velocity metrics for a repository."""
    from core.engine.review.velocity import VelocityCalculator

    calc = VelocityCalculator()
    metrics = await calc.calculate(owner, repo, period_days)
    return metrics.model_dump()
