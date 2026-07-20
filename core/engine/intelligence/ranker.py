# engine/intelligence/ranker.py
"""Relevance ranker — scores insights by task relevance + utilization + confidence.

always_on_score = 0.4 × task_relevance + 0.3 × utilization_score + 0.3 × confidence

All DB operations are best-effort (non-fatal).  Falls back to confidence sort
when the embedder is unavailable (dimensions == 0).
"""

from __future__ import annotations

import logging
from typing import Any

from core.engine.core.db import parse_record_ids, parse_rows, pool
from core.engine.embedding.base import get_embedder
from core.engine.search.semantic import cosine_similarity_batch

logger = logging.getLogger(__name__)

# Score weights
_W_RELEVANCE = 0.4
_W_UTILIZATION = 0.3
_W_CONFIDENCE = 0.3


def _score(task_relevance: float, utilization_score: float, confidence: float) -> float:
    return _W_RELEVANCE * task_relevance + _W_UTILIZATION * utilization_score + _W_CONFIDENCE * confidence


def _sort_by_score(insights: list[dict]) -> list[dict]:
    return sorted(insights, key=lambda x: x.get("_score", 0.0), reverse=True)


async def rank_insights(
    snapshot: dict[str, Any],
    task_description: str,
    product_id: str,
) -> dict[str, Any]:
    """Rank insights in snapshot by always_on_score.

    Mutates and returns snapshot.  All failures are non-fatal — worst case
    the snapshot is returned unchanged (sorted by confidence).
    """
    embedder = get_embedder()

    # Fast path: no embedding capability — sort by confidence only
    if embedder.dimensions == 0:
        for key in ("insights", "specialty_insights", "org_insights"):
            items = snapshot.get(key, [])
            if items:
                for item in items:
                    item.setdefault("_score", item.get("confidence", 0.0))
                snapshot[key] = sorted(items, key=lambda x: x.get("confidence", 0.0), reverse=True)
        return snapshot

    # Embed the task description
    try:
        task_vecs = await embedder.embed([task_description])
        task_vec: list[float] = task_vecs[0] if task_vecs else []
    except Exception as exc:
        logger.warning("ranker: embed failed (non-fatal): %s", exc)
        task_vec = []

    # Fetch stored insight embeddings and utilization scores
    all_insights: list[dict] = list(snapshot.get("insights", []))
    insight_ids = [str(i.get("id", "")) for i in all_insights if i.get("id")]

    embedding_map: dict[str, list[float]] = {}
    utilization_map: dict[str, float] = {}

    if insight_ids:
        try:
            async with pool.connection() as db:
                _emb_rows = await db.query(
                    "SELECT id, embedding FROM insight WHERE id IN $ids",
                    {"ids": parse_record_ids(insight_ids)},
                )
                for row in parse_rows(_emb_rows):
                    emb = row.get("embedding")
                    rid = str(row.get("id", ""))
                    if emb and rid:
                        embedding_map[rid] = emb

                _util_rows = await db.query(
                    """SELECT insight, utilization_score, created_at
                       FROM insight_utilization
                       WHERE insight IN $ids
                       ORDER BY created_at DESC
                       LIMIT 200""",
                    {"ids": parse_record_ids(insight_ids)},
                )
                for row in parse_rows(_util_rows):
                    rid = str(row.get("insight", ""))
                    score = row.get("utilization_score")
                    if rid and score is not None:
                        utilization_map[rid] = float(score)
        except Exception as exc:
            logger.warning("ranker: DB fetch failed (non-fatal): %s", exc)

    def _annotate_and_score(items: list[dict]) -> list[dict]:
        """Annotate each insight with _vec and _score, then sort."""
        if not items:
            return items

        # Build list of (insight, embedding) pairs
        vecs: list[list[float] | None] = []
        for item in items:
            rid = str(item.get("id", ""))
            vec = embedding_map.get(rid)
            item["_vec"] = vec  # inject for compressor reuse (None if unavailable)
            vecs.append(vec)

        # Batch cosine similarity for items that have embeddings + we have task_vec
        if task_vec:
            valid_indices = [i for i, v in enumerate(vecs) if v is not None and len(v) == embedder.dimensions]
            valid_vecs = [vecs[i] for i in valid_indices]
            if valid_vecs:
                sims = cosine_similarity_batch(task_vec, valid_vecs)
                sim_map = {valid_indices[i]: sims[i] for i in range(len(valid_indices))}
            else:
                sim_map = {}
        else:
            sim_map = {}

        for idx, item in enumerate(items):
            rid = str(item.get("id", ""))
            task_relevance = float(sim_map.get(idx, 0.5))
            utilization = utilization_map.get(rid, 0.5)
            confidence = float(item.get("confidence", 0.5))
            item["_score"] = _score(task_relevance, utilization, confidence)

        return _sort_by_score(items)

    # Rank all three insight lists
    for key in ("insights", "specialty_insights", "org_insights"):
        items = snapshot.get(key, [])
        if items:
            snapshot[key] = _annotate_and_score(list(items))

    return snapshot
