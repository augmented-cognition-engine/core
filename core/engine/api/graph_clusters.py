# engine/api/graph_clusters.py
"""Graph cluster API — community detection via Louvain algorithm."""

from __future__ import annotations

import logging
from datetime import datetime, timezone

from fastapi import APIRouter, Depends

from core.engine.core.auth import get_current_user
from core.engine.core.db import pool, serialize_record
from core.engine.graph.cluster import build_graph, compute_inter_cluster_edges, detect_clusters

logger = logging.getLogger(__name__)

router = APIRouter(tags=["graph-clusters"])

# ---------------------------------------------------------------------------
# Edge tables — product (15) + code (13) = 28
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

_CODE_EDGE_TABLES = [
    "imports",
    "tests",
    "implements",
    "informed_by",
    "solves",
    "causes",
    "breaks",
    "reverts",
    "decomposes",
    "assigned_to",
    "produced",
    "related_to",
    "evolved_from",
]

_ALL_EDGE_TABLES = _PRODUCT_EDGE_TABLES + _CODE_EDGE_TABLES


# ---------------------------------------------------------------------------
# GET /graph/clusters
# ---------------------------------------------------------------------------


@router.get("/graph/clusters")
async def graph_clusters(user: dict = Depends(get_current_user)):
    """Fetch all edges from both graph systems, run Louvain community detection.

    Scans 28 edge tables (15 product + 13 code), builds an undirected graph,
    and returns detected clusters with inter-cluster edge counts.
    """
    edges: list[dict] = []

    async with pool.connection() as db:
        for table in _ALL_EDGE_TABLES:
            try:
                result = await db.query(f"SELECT in, out FROM {table} LIMIT 500")
                rows = result if isinstance(result, list) else []
                # SurrealDB query returns list-of-lists or list-of-dicts
                for row in rows:
                    if isinstance(row, dict):
                        src = str(serialize_record(row.get("in", "")))
                        tgt = str(serialize_record(row.get("out", "")))
                        if src and tgt and src != "None" and tgt != "None":
                            edges.append({"from": src, "to": tgt, "type": table})
                    elif isinstance(row, list):
                        # SurrealDB may return list of result sets
                        for item in row:
                            if isinstance(item, dict):
                                src = str(serialize_record(item.get("in", "")))
                                tgt = str(serialize_record(item.get("out", "")))
                                if src and tgt and src != "None" and tgt != "None":
                                    edges.append({"from": src, "to": tgt, "type": table})
            except Exception as exc:
                logger.debug("Edge query failed for table %s: %s", table, exc)

    g = build_graph(edges)
    clusters = detect_clusters(g)
    inter_edges = compute_inter_cluster_edges(g, clusters)

    return {
        "clusters": clusters,
        "inter_cluster_edges": inter_edges,
        "computed_at": datetime.now(timezone.utc).isoformat(),
    }
