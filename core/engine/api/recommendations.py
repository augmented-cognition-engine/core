# engine/api/recommendations.py
"""Recommendations API — actionable insights from graph analysis.

GET  /recommendations              — get recommendations for the project
POST /recommendations/{id}/dismiss — dismiss a recommendation
POST /recommendations/{id}/execute — execute a recommendation as a task
"""

from __future__ import annotations

import logging

from fastapi import APIRouter, Depends, HTTPException, Query

from core.engine.core.auth import get_current_user
from core.engine.core.db import parse_one, pool

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/recommendations", tags=["recommendations"])


@router.get("")
async def get_recommendations(
    graph_id: str = Query("default"),
    limit: int = Query(8, ge=1, le=20),
    user: dict = Depends(get_current_user),
) -> dict:
    """Get actionable recommendations for the project."""
    from core.engine.graph.recommendations import generate_recommendations

    try:
        recs = await generate_recommendations(graph_id=graph_id, limit=limit)
    except Exception as exc:
        logger.error("Recommendation generation failed: %s", exc)
        recs = []

    return {"recommendations": recs, "count": len(recs)}


@router.post("/{rec_id}/dismiss")
async def dismiss_recommendation(
    rec_id: str,
    user: dict = Depends(get_current_user),
) -> dict:
    """Dismiss a recommendation so it doesn't show again."""
    from core.engine.graph.recommendations import dismiss

    dismiss(rec_id)
    return {"id": rec_id, "status": "dismissed"}


@router.post("/{rec_id}/execute")
async def execute_recommendation(
    rec_id: str,
    graph_id: str = Query("default"),
    user: dict = Depends(get_current_user),
) -> dict:
    """Execute a recommendation by creating a task with the action_prompt.

    Returns the created task queue item ID.
    """
    from core.engine.graph.recommendations import generate_recommendations

    # Find the recommendation by ID
    recs = await generate_recommendations(graph_id=graph_id, limit=20)
    target = None
    for r in recs:
        if r["id"] == rec_id:
            target = r
            break

    if not target:
        raise HTTPException(status_code=404, detail="Recommendation not found")

    action_prompt = target.get("action_prompt", "")
    if not action_prompt:
        raise HTTPException(status_code=400, detail="Recommendation has no action prompt")

    title = target.get("title", "ACE recommendation")
    product = user.get("product", "product:default")

    # Create a task in the queue for the runner to pick up
    async with pool.connection() as db:
        result = await db.query(
            """
            CREATE task_queue SET
                product = <record>$product,
                title = $title,
                description = $description,
                priority = 50,
                source = 'recommendation',
                status = 'queued',
                metadata = { recommendation_id: $rec_id, recommendation_type: $rec_type },
                created_at = time::now()
            """,
            {
                "product": product,
                "title": title,
                "description": action_prompt,
                "rec_id": rec_id,
                "rec_type": target.get("type", "suggestion"),
            },
        )

        # Parse the created record
        item = parse_one(result) or {}

    task_id = str(item.get("id", ""))

    return {
        "id": rec_id,
        "status": "executing",
        "task_id": task_id,
        "title": title,
    }
