# engine/api/graph_edge_summary.py
"""Graph edge-summary API — lightweight edge counts grouped by type for a single node."""

from __future__ import annotations

import logging

from fastapi import APIRouter, Depends

from core.engine.core.auth import get_current_user
from core.engine.core.db import pool

logger = logging.getLogger(__name__)

router = APIRouter(tags=["graph-edge-summary"])

# ---------------------------------------------------------------------------
# Product edge tables (15)
# ---------------------------------------------------------------------------

_PRODUCT_EDGE_TABLES = [
    "realizes",
    "became",
    "led_to",
    "supersedes",
    "depends_on",
    "inspired_by",
    "affected",
    "quality_delta",
    "targets",
    "blocked_by",
    "improves",
    "specified_by",
    "fulfills",
    "derived_from",
    "loaded",
]


# ---------------------------------------------------------------------------
# GET /graph/edge-summary/{node_id}
# ---------------------------------------------------------------------------


@router.get("/graph/edge-summary/{node_id:path}")
async def graph_edge_summary(
    node_id: str,
    user: dict = Depends(get_current_user),
):
    """Return edge counts grouped by type for a single node.

    Scans 15 product edge tables and counts edges where the node appears as
    either source (in) or target (out). Only tables with at least one edge
    are included in the response.
    """
    edges: dict[str, int] = {}

    async with pool.connection() as db:
        for table in _PRODUCT_EDGE_TABLES:
            try:
                result = await db.query(
                    f"SELECT count() AS c FROM {table} WHERE in = <record>$id OR out = <record>$id GROUP ALL",
                    {"id": node_id},
                )
                # result may be [[{"c": n}]], [{"c": n}], or []
                rows = result if isinstance(result, list) else []
                count = 0
                for item in rows:
                    if isinstance(item, list):
                        for sub in item:
                            if isinstance(sub, dict):
                                count = int(sub.get("c", 0))
                    elif isinstance(item, dict):
                        count = int(item.get("c", 0))
                if count > 0:
                    edges[table] = count
            except Exception as exc:
                logger.debug("Edge summary query failed for table %s: %s", table, exc)

    return {"edges": edges, "total": sum(edges.values())}
