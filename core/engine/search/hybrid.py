"""Hybrid search — combines semantic similarity with graph-structural signals."""

from __future__ import annotations

import logging

from core.engine.core.db import parse_rows, pool
from core.engine.core.exceptions import ValidationError
from core.engine.search.semantic import semantic_search

logger = logging.getLogger(__name__)

SEMANTIC_WEIGHT = 0.5
STRUCTURAL_WEIGHT = 0.3
RECENCY_WEIGHT = 0.2
_MAX_QUERY_LEN = 2000
_MAX_LIMIT = 200


def _validate_search_inputs(query: str, product_id: str, limit: int) -> None:
    """Validate hybrid search inputs at the system boundary.

    Raises ValidationError for empty queries, oversized inputs, malformed
    product_id, or out-of-range limit — preventing DB queries with inputs
    that would either crash or silently return garbage results.
    """
    if not query or not query.strip():
        raise ValidationError("query must be non-empty")
    if len(query) > _MAX_QUERY_LEN:
        raise ValidationError(f"query too long: {len(query)} > {_MAX_QUERY_LEN}")
    if not product_id or ":" not in product_id:
        raise ValidationError(f"Invalid product_id: {product_id!r}")
    if not (1 <= limit <= _MAX_LIMIT):
        raise ValidationError(f"limit must be in [1, {_MAX_LIMIT}], got {limit}")


async def hybrid_search(query: str, product_id: str, limit: int = 20) -> list[dict]:
    """Search code using both semantic and structural signals."""
    _validate_search_inputs(query, product_id, limit)
    semantic_results = await semantic_search(query, product_id, limit=limit * 2)

    if not semantic_results:
        return await _keyword_fallback(query, product_id, limit)

    file_ids = [r["id"] for r in semantic_results]

    structural_scores = {}
    async with pool.connection() as db:
        for file_id in file_ids:
            score = 0.0
            reasons = []

            deps = parse_rows(
                await db.query(
                    "SELECT count() AS cnt FROM imports WHERE out = <record>$fid GROUP ALL",
                    {"fid": file_id},
                )
            )
            dep_count = deps[0].get("cnt", 0) if deps else 0
            if dep_count > 5:
                score += 0.3
                reasons.append(f"structural: {dep_count} dependents")

            cochanges = parse_rows(
                await db.query(
                    "SELECT count() AS cnt FROM related_to WHERE in = <record>$fid OR out = <record>$fid GROUP ALL",
                    {"fid": file_id},
                )
            )
            if cochanges and cochanges[0].get("cnt", 0) > 0:
                score += 0.2
                reasons.append("structural: co-changes with other files")

            caps = parse_rows(
                await db.query(
                    "SELECT count() AS cnt FROM realizes WHERE in = <record>$fid GROUP ALL",
                    {"fid": file_id},
                )
            )
            if caps and caps[0].get("cnt", 0) > 0:
                score += 0.2
                reasons.append("structural: realizes a capability")

            structural_scores[file_id] = {"score": min(score, 1.0), "reasons": reasons}

    results = []
    for r in semantic_results:
        fid = r["id"]
        sem = r["score"]
        struct = structural_scores.get(fid, {}).get("score", 0.0)
        reasons = structural_scores.get(fid, {}).get("reasons", [])

        if sem > 0.3:
            reasons.insert(0, f"semantic: {sem:.2f} similarity")

        final = (SEMANTIC_WEIGHT * sem) + (STRUCTURAL_WEIGHT * struct) + (RECENCY_WEIGHT * 0.5)

        results.append(
            {
                "type": r["type"],
                "path": r["path"],
                "id": fid,
                "score": round(final, 4),
                "semantic_score": round(sem, 4),
                "structural_score": round(struct, 4),
                "match_reasons": reasons,
            }
        )

    results.sort(key=lambda r: r["score"], reverse=True)
    return results[:limit]


async def _keyword_fallback(query: str, product_id: str, limit: int) -> list[dict]:
    """Simple keyword search when embeddings unavailable."""
    terms = query.lower().split()
    if not terms:
        return []

    async with pool.connection() as db:
        rows = parse_rows(
            await db.query(
                "SELECT id, path, name FROM graph_file WHERE string::lowercase(path) CONTAINS $term ORDER BY path LIMIT $lim",
                {"term": terms[0], "lim": limit},
            )
        )

    return [
        {
            "type": "file",
            "path": r.get("path", ""),
            "id": str(r.get("id", "")),
            "score": 0.5,
            "semantic_score": 0.0,
            "structural_score": 0.0,
            "match_reasons": ["keyword: path match"],
        }
        for r in rows
    ]
