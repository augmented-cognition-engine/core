# engine/api/graph_search.py
"""Graph search API — cross-table node search."""

from __future__ import annotations

import logging

from fastapi import APIRouter, Depends, Query

from core.engine.core.auth import get_current_user
from core.engine.core.db import parse_rows, pool, serialize_record

logger = logging.getLogger(__name__)

router = APIRouter(tags=["graph-search"])

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

_LAYER_MAP = {
    "capability": "product",
    "initiative": "work",
    "decision": "product",
    "graph_file": "code",
    "idea": "work",
}

# (table, search_fields, label_field)
_SEARCH_TABLES: list[tuple[str, list[str], str]] = [
    ("capability", ["name", "slug"], "name"),
    ("initiative", ["title", "slug"], "title"),
    ("decision", ["title", "slug"], "title"),
    ("graph_file", ["path", "name"], "name"),
    ("idea", ["title"], "title"),
]


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _relevance_score(label: str, query: str) -> int:
    """Score relevance: 0 = exact, 1 = starts_with, 2 = contains."""
    label_lower = label.lower()
    query_lower = query.lower()
    if label_lower == query_lower:
        return 0
    if label_lower.startswith(query_lower):
        return 1
    return 2


# ---------------------------------------------------------------------------
# GET /graph/search
# ---------------------------------------------------------------------------


@router.get("/graph/search")
async def graph_search(
    q: str = Query(..., min_length=1, max_length=100),
    user: dict = Depends(get_current_user),
):
    """Search across capability, initiative, decision, graph_file, and idea tables.

    Returns up to 10 results sorted by relevance (exact > starts_with > contains).
    """
    results: list[dict] = []

    async with pool.connection() as db:
        for table, fields, label_field in _SEARCH_TABLES:
            # Build WHERE clause: string::lowercase(field) CONTAINS string::lowercase($q)
            conditions = " OR ".join(f"string::lowercase({f}) CONTAINS string::lowercase($q)" for f in fields)
            query = f"SELECT * FROM {table} WHERE ({conditions}) LIMIT 5"

            try:
                raw = await db.query(query, {"q": q})
                for row in parse_rows(raw):
                    data = serialize_record(row)
                    node_id = str(data.get("id", ""))
                    label = str(data.get(label_field, "") or data.get("slug", "") or node_id)
                    results.append(
                        {
                            "id": node_id,
                            "label": label,
                            "layer": _LAYER_MAP.get(table, "unknown"),
                            "type": table,
                            "_score": _relevance_score(label, q),
                        }
                    )
            except Exception as exc:
                logger.debug("Search query failed for table %s: %s", table, exc)

    # Sort by relevance, then take top 10
    results.sort(key=lambda r: r["_score"])
    results = results[:10]

    # Strip internal _score field
    for r in results:
        r.pop("_score", None)

    return {"results": results}
