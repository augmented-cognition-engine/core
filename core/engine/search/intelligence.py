"""Production-bounded intelligence retrieval over SurrealDB.

This module is the single retrieval implementation shared by the in-process
MCP surface and the authenticated HTTP/thin-client surface.  It deliberately
keeps ranking policy, index compatibility, and degraded-state reporting out of
transport adapters so every supported caller sees the same result set.
"""

from __future__ import annotations

import time
from collections.abc import Awaitable, Callable
from typing import Any

from core.engine.core.config import settings
from core.engine.core.db import parse_rows
from core.engine.core.exceptions import ValidationError
from core.engine.embedding.base import INTELLIGENCE_EMBEDDING_DIMENSIONS, get_embedder

RETRIEVAL_CONTRACT_VERSION = "ace.rag-retrieval/v1"
RANKING_POLICY_VERSION = "ace.rag-ranking/rrf-v1"

_MAX_QUERY_LENGTH = 2_000
_MAX_LIMIT = 50
_MAX_TAGS = 20
_RRF_K = 60


def _validate_inputs(
    query: str,
    product_id: str,
    knowledge_type: str | None,
    tags: list[str] | None,
    limit: int,
) -> None:
    if not query or not query.strip():
        raise ValidationError("query must be non-empty")
    if len(query) > _MAX_QUERY_LENGTH:
        raise ValidationError(f"query too long: {len(query)} > {_MAX_QUERY_LENGTH}")
    if not product_id or ":" not in product_id:
        raise ValidationError(f"Invalid product_id: {product_id!r}")
    if knowledge_type is not None and (not knowledge_type.strip() or len(knowledge_type) > 100):
        raise ValidationError("knowledge_type must be 1-100 characters")
    if tags is not None:
        if not tags or len(tags) > _MAX_TAGS:
            raise ValidationError(f"tags must contain 1-{_MAX_TAGS} values")
        if any(not isinstance(tag, str) or not tag.strip() or len(tag) > 100 for tag in tags):
            raise ValidationError("each tag must be a non-empty string of at most 100 characters")
    if not 1 <= limit <= _MAX_LIMIT:
        raise ValidationError(f"limit must be in [1, {_MAX_LIMIT}], got {limit}")


def _query_filters(knowledge_type: str | None, tags: list[str] | None) -> tuple[str, str]:
    type_filter = "AND insight_type = $type" if knowledge_type else ""
    tag_filter = "AND tags CONTAINSANY $tags" if tags else ""
    return type_filter, tag_filter


def _query_params(
    *,
    product_id: str,
    query: str,
    candidate_limit: int,
    knowledge_type: str | None,
    tags: list[str] | None,
) -> dict[str, Any]:
    return {
        "product": product_id,
        "query": query,
        "limit": candidate_limit,
        **({"type": knowledge_type} if knowledge_type else {}),
        **({"tags": tags} if tags else {}),
    }


async def _authoritative_promotions(
    *,
    db_pool,
    product_id: str,
    query: str,
    knowledge_type: str | None,
    tags: list[str] | None,
    limit: int,
) -> tuple[list[dict[str, Any]], str | None]:
    """Return effective promoted memories without trusting legacy row status.

    Promotion state is append-only and receipt-governed.  Searching ordinary
    ``insight`` rows directly can otherwise revive a superseded or contested
    promotion, so those rows are excluded from the index queries and rebuilt
    from the authoritative projection here.
    """
    try:
        from core.engine.grounded_state.promotion import promoted_memory_as_insight, retrieve_promoted_memories

        memories = await retrieve_promoted_memories(pool=db_pool, product_id=product_id, limit=limit)
    except Exception as exc:
        return [], f"promotion_projection_failed:{type(exc).__name__}"

    needle = query.casefold()
    required_tags = set(tags or ())
    results: list[dict[str, Any]] = []
    for memory in memories:
        item = promoted_memory_as_insight(memory)
        if needle not in str(item.get("content", "")).casefold():
            continue
        if knowledge_type and item.get("insight_type") != knowledge_type:
            continue
        if required_tags and required_tags.isdisjoint(item.get("tags") or ()):
            continue
        item["lexical_score"] = 1.0
        results.append(item)
    return results, None


def reciprocal_rank_fusion(
    lexical_rows: list[dict[str, Any]],
    vector_rows: list[dict[str, Any]],
    *,
    limit: int,
    k: int = _RRF_K,
) -> list[dict[str, Any]]:
    """Fuse two ordered rankings with deterministic record-id tie-breaking."""
    scores: dict[str, float] = {}
    id_to_row: dict[str, dict[str, Any]] = {}

    for rows in (lexical_rows, vector_rows):
        for rank, row in enumerate(rows):
            record_id = str(row.get("id", ""))
            if not record_id:
                continue
            scores[record_id] = scores.get(record_id, 0.0) + 1 / (k + rank + 1)
            id_to_row.setdefault(record_id, row)

    ranked = sorted(scores, key=lambda record_id: (-scores[record_id], record_id))[:limit]
    return [
        {
            **id_to_row[record_id],
            "id": record_id,
            "score": round(scores[record_id], 6),
        }
        for record_id in ranked
    ]


async def search_intelligence(
    query: str,
    product_id: str,
    *,
    knowledge_type: str | None = None,
    tags: list[str] | None = None,
    limit: int = 10,
    db_pool,
    embedder=None,
    reranker: Callable[[str, list[dict[str, Any]]], Awaitable[list[dict[str, Any]]]] | None = None,
) -> dict[str, Any]:
    """Run product-scoped BM25 + indexed-KNN retrieval with an explicit receipt."""
    _validate_inputs(query, product_id, knowledge_type, tags, limit)
    started = time.perf_counter()
    query = query.strip()
    candidate_limit = min(_MAX_LIMIT * 3, max(limit * 3, 20))
    # Capture once so filtering and the externally visible receipt cannot
    # disagree if settings are replaced or monkeypatched during an await.
    vector_max_distance = settings.rag_vector_max_distance
    type_filter, tag_filter = _query_filters(knowledge_type, tags)
    params = _query_params(
        product_id=product_id,
        query=query,
        candidate_limit=candidate_limit,
        knowledge_type=knowledge_type,
        tags=tags,
    )

    degraded_reasons: list[str] = []
    lexical_rows: list[dict[str, Any]] = []
    vector_rows: list[dict[str, Any]] = []
    vector_distance_omitted = 0
    vector_state = "unavailable"
    vector_reason = "embedding_disabled"
    configured_embedder = embedder or get_embedder()

    async with db_pool.connection() as db:
        lexical_rows = parse_rows(
            await db.query(
                f"""
                SELECT id, content, confidence, domain_path, observation_type,
                       insight_type, tags, source_kind, search::score(0) AS lexical_score
                FROM insight
                WHERE product = <record>$product AND status = 'active'
                  AND (source_kind IS NONE OR source_kind != 'grounded_promotion')
                  AND content @0@ $query
                  {type_filter}
                  {tag_filter}
                ORDER BY lexical_score DESC, confidence DESC, id ASC
                LIMIT $limit
                """,
                params,
            )
        )

        if configured_embedder.dimensions == 0:
            degraded_reasons.append("embedding_disabled")
        elif configured_embedder.dimensions != INTELLIGENCE_EMBEDDING_DIMENSIONS:
            vector_state = "degraded"
            vector_reason = "embedding_dimension_mismatch"
            degraded_reasons.append(vector_reason)
        else:
            try:
                vectors = await configured_embedder.embed([query])
                query_vector = vectors[0] if vectors else []
                if len(query_vector) != INTELLIGENCE_EMBEDDING_DIMENSIONS:
                    raise ValueError("embedder returned an incompatible query vector")

                # The KNN and effort values are validated integers embedded in
                # the operator because SurrealQL does not parameterize its K/EF
                # grammar. Product/type/tag predicates are pushed into KnnScan
                # by the pinned SurrealDB 3.2.x executor.
                effort = max(40, candidate_limit * 2)
                raw_vector_rows = parse_rows(
                    await db.query(
                        f"""
                        SELECT id, content, confidence, domain_path, observation_type,
                               insight_type, tags, source_kind,
                               vector::distance::knn() AS vector_distance
                        FROM insight
                        WHERE product = <record>$product AND status = 'active'
                          AND (source_kind IS NONE OR source_kind != 'grounded_promotion')
                          AND embedding <|{candidate_limit},{effort}|> $vec
                          {type_filter}
                          {tag_filter}
                        ORDER BY vector_distance ASC, confidence DESC, id ASC
                        LIMIT $limit
                        """,
                        {**params, "vec": query_vector},
                    )
                )
                vector_rows = [
                    row
                    for row in raw_vector_rows
                    if row.get("vector_distance") is not None and float(row["vector_distance"]) <= vector_max_distance
                ]
                vector_distance_omitted = len(raw_vector_rows) - len(vector_rows)
                vector_state = "complete"
                vector_reason = None
            except Exception as exc:  # vector retrieval is fail-open, but never silent
                vector_state = "degraded"
                vector_reason = f"vector_retrieval_failed:{type(exc).__name__}"
                degraded_reasons.append(vector_reason)

    promotions, promotion_reason = await _authoritative_promotions(
        db_pool=db_pool,
        product_id=product_id,
        query=query,
        knowledge_type=knowledge_type,
        tags=tags,
        limit=candidate_limit,
    )
    if promotion_reason:
        degraded_reasons.append(promotion_reason)
    lexical_rows = promotions + lexical_rows

    fused = reciprocal_rank_fusion(lexical_rows, vector_rows, limit=candidate_limit)
    rerank_state = "disabled"
    if reranker is not None and len(fused) > 1:
        try:
            fused = await reranker(query, fused)
            rerank_state = "complete"
        except Exception as exc:
            degraded_reasons.append(f"rerank_failed:{type(exc).__name__}")
            rerank_state = "degraded"
    results = fused[:limit]

    latency_ms = round((time.perf_counter() - started) * 1_000, 3)
    state = "degraded" if degraded_reasons else "complete"
    return {
        "results": results,
        "count": len(results),
        "query": query,
        "retrieval": {
            "contract_version": RETRIEVAL_CONTRACT_VERSION,
            "ranking_policy_version": RANKING_POLICY_VERSION,
            "state": state,
            "product_id": product_id,
            "limit": limit,
            "candidate_limit": candidate_limit,
            "signals": {
                "lexical": {"state": "complete", "candidates": len(lexical_rows), "ranking": "bm25"},
                "vector": {
                    "state": vector_state,
                    "reason": vector_reason,
                    "candidates": len(vector_rows),
                    "distance_omitted": vector_distance_omitted,
                    "index": "insight_hnsw",
                    "maximum_distance": vector_max_distance,
                },
                "promotion_projection": {
                    "state": "degraded" if promotion_reason else "complete",
                    "reason": promotion_reason,
                    "candidates": len(promotions),
                },
            },
            "embedding": {
                "provider": settings.embedding_provider,
                "model": settings.embedding_model,
                "dimensions": configured_embedder.dimensions,
                "required_dimensions": INTELLIGENCE_EMBEDDING_DIMENSIONS,
            },
            "fusion": {"method": "reciprocal_rank_fusion", "k": _RRF_K},
            "rerank": {"state": rerank_state},
            "degraded_reasons": degraded_reasons,
            "latency_ms": latency_ms,
        },
    }
