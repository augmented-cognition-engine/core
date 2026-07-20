# engine/api/graph_health.py
"""Graph health-map API — node health data for bubble visualization."""

from __future__ import annotations

import logging
from typing import Literal

from fastapi import APIRouter, Depends, Query

from core.engine.core.auth import get_current_user
from core.engine.core.db import parse_rows, pool, serialize_record

logger = logging.getLogger(__name__)

router = APIRouter(tags=["graph-health"])

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

_EDGE_TABLES = [
    "inspired_by",
    "became",
    "specified_by",
    "fulfills",
    "led_to",
    "affected",
    "derived_from",
    "supersedes",
    "loaded",
    "quality_delta",
    "targets",
    "blocked_by",
    "realizes",
    "depends_on",
    "improves",
]


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


async def _count_edges(db, node_id: str) -> int:
    """Count edges across all 15 product edge tables for a given node."""
    total = 0
    for table in _EDGE_TABLES:
        try:
            result = await db.query(
                f"SELECT count() AS c FROM {table} WHERE in = <record>$id OR out = <record>$id GROUP ALL",
                {"id": node_id},
            )
            rows = parse_rows(result)
            if rows:
                total += rows[0].get("c", 0)
        except Exception as exc:
            logger.debug("Edge count failed for %s on %s: %s", table, node_id, exc)
    return total


# ---------------------------------------------------------------------------
# GET /graph/health-map
# ---------------------------------------------------------------------------


@router.get("/graph/health-map")
async def health_map(
    filter: Literal["all", "capabilities", "files", "high_risk"] = Query(default="all"),
    user: dict = Depends(get_current_user),
):
    """Return node health data for bubble visualization.

    Each node includes a health_score (0-1), edge_count, gap list, and layer.
    """
    product_id = user.get("product", "")
    nodes: list[dict] = []

    async with pool.connection() as db:
        # -------------------------------------------------------------------
        # Capabilities
        # -------------------------------------------------------------------
        if filter in ("all", "capabilities", "high_risk"):
            cap_result = await db.query(
                "SELECT * FROM capability WHERE product = <record>$product AND status != 'deprecated'",
                {"product": product_id},
            )
            capabilities = parse_rows(cap_result)

            # Fetch all quality rows for this org
            quality_result = await db.query(
                "SELECT * FROM capability_quality WHERE product = <record>$product",
                {"product": product_id},
            )
            quality_rows = parse_rows(quality_result)

            # Group quality scores by capability ID
            quality_by_cap: dict[str, list[dict]] = {}
            for qrow in quality_rows:
                cap_ref = qrow.get("capability", "")
                cap_id = str(serialize_record(cap_ref)) if cap_ref else ""
                if cap_id:
                    quality_by_cap.setdefault(cap_id, []).append(qrow)

            for cap in capabilities:
                cap_data = serialize_record(cap)
                cap_id = str(cap_data.get("id", ""))
                if not cap_id:
                    continue

                # Compute health_score = average of dimension scores
                q_rows = quality_by_cap.get(cap_id, [])
                if q_rows:
                    scores = [r.get("score", 0.0) for r in q_rows if isinstance(r.get("score"), (int, float))]
                    health_score = sum(scores) / len(scores) if scores else 0.0
                else:
                    health_score = 0.0

                # Find gaps: dimensions with score < 0.5
                gaps = []
                for qr in q_rows:
                    score = qr.get("score", 0.0)
                    if isinstance(score, (int, float)) and score < 0.5:
                        dim = qr.get("discipline", qr.get("dimension", ""))
                        if dim:
                            gaps.append(dim)

                edge_count = await _count_edges(db, cap_id)

                nodes.append(
                    {
                        "id": cap_id,
                        "label": cap_data.get("name", cap_data.get("slug", cap_id)),
                        "type": "capability",
                        "layer": "product",
                        "edge_count": edge_count,
                        "health_score": round(health_score, 2),
                        "gaps": gaps,
                        "details": {"status": cap_data.get("status", "unknown")},
                    }
                )

        # -------------------------------------------------------------------
        # Files
        # -------------------------------------------------------------------
        if filter in ("all", "files", "high_risk"):
            file_result = await db.query(
                "SELECT * FROM graph_file WHERE graph_id = <string>$gid ORDER BY change_frequency DESC LIMIT 50",
                {"gid": "default"},
            )
            files = parse_rows(file_result)

            # Find max change_frequency for normalization
            max_freq = 0.0
            for f in files:
                freq = f.get("change_frequency", 0.0)
                if isinstance(freq, (int, float)) and freq > max_freq:
                    max_freq = freq

            for f in files:
                f_data = serialize_record(f)
                f_id = str(f_data.get("id", ""))
                if not f_id:
                    continue

                freq = f_data.get("change_frequency", 0.0)
                if isinstance(freq, (int, float)) and max_freq > 0:
                    health_score = 1.0 - (freq / max_freq)
                else:
                    health_score = 0.5

                edge_count = await _count_edges(db, f_id)

                nodes.append(
                    {
                        "id": f_id,
                        "label": f_data.get("path", f_data.get("slug", f_id)),
                        "type": "graph_file",
                        "layer": "code",
                        "edge_count": edge_count,
                        "health_score": round(health_score, 2),
                        "gaps": [],
                        "details": {"language": f_data.get("language", "unknown")},
                    }
                )

        # -------------------------------------------------------------------
        # High-risk post-filter
        # -------------------------------------------------------------------
        if filter == "high_risk":
            nodes = [n for n in nodes if n["health_score"] < 0.4]

    return {"nodes": nodes}
