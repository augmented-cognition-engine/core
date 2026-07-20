"""Code search API — semantic + hybrid search endpoint."""

from __future__ import annotations

from fastapi import APIRouter, Depends, Query

from core.engine.core.auth import get_current_user
from core.engine.search.hybrid import hybrid_search

router = APIRouter(tags=["search"])


@router.get("/search/code")
async def search_code(
    q: str = Query(..., description="Search query"),
    limit: int = Query(10, ge=1, le=50),
    user=Depends(get_current_user),
):
    """Search code by semantic similarity + structural signals."""
    product_id = user.get("product", "")
    results = await hybrid_search(q, product_id, limit=limit)
    return {"results": results, "total": len(results), "query": q}
