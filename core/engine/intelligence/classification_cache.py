# engine/intelligence/classification_cache.py
"""Classification cache — semantic lookup + UPSERT store.

Caches task classification results by semantic similarity of the task
description.  On lookup, fetches up to _MAX_FETCH entries for the product
and finds the closest match using client-side cosine similarity.

Returns the cached result if best_sim >= LOW_THRESHOLD.
Stores new results with an md5-based RecordID to enable idempotent UPSERT.

All failures are non-fatal — lookup returns None, store is silent.
"""

from __future__ import annotations

import hashlib
import logging
from typing import Any

from core.engine.core.db import parse_record_id, parse_rows, pool
from core.engine.embedding.base import get_embedder
from core.engine.search.semantic import cosine_similarity_batch

logger = logging.getLogger(__name__)

HIGH_THRESHOLD = 0.90
LOW_THRESHOLD = 0.75
_MAX_FETCH = 200


def _md5_slug(text: str) -> str:
    return hashlib.md5(text.strip().lower().encode()).hexdigest()


async def lookup(description: str, product_id: str) -> dict[str, Any] | None:
    """Semantic lookup: returns cached classification result or None.

    Returns None if embedder is unavailable (dimensions==0).
    On hit: increments hit_count (best-effort).
    """
    result, _ = await lookup_with_entry(description, product_id)
    return result


async def lookup_with_entry(
    description: str,
    product_id: str,
) -> tuple[dict[str, Any] | None, str | None]:
    """Semantic lookup returning (result, entry_id) or (None, None) on miss."""
    embedder = get_embedder()
    if embedder.dimensions == 0:
        return None, None

    # Embed query
    try:
        vecs = await embedder.embed([description])
        query_vec: list[float] = vecs[0] if vecs else []
    except Exception as exc:
        logger.warning("classification_cache: embed failed (non-fatal): %s", exc)
        return None, None

    if not query_vec:
        return None, None

    # Fetch candidate entries
    try:
        async with pool.connection() as db:
            rows_raw = await db.query(
                """SELECT id, description_embedding, result, hit_count, created_at
                   FROM classification_cache
                   WHERE product = <record>$product
                   ORDER BY created_at DESC
                   LIMIT $limit""",
                {"product": product_id, "limit": _MAX_FETCH},
            )
            entries = parse_rows(rows_raw)
    except Exception as exc:
        logger.warning("classification_cache: fetch failed (non-fatal): %s", exc)
        return None, None

    if not entries:
        return None, None

    # Build candidate vectors
    valid: list[tuple[dict, list[float]]] = []
    for entry in entries:
        emb = entry.get("description_embedding")
        if emb and len(emb) == embedder.dimensions:
            valid.append((entry, emb))

    if not valid:
        return None, None

    candidate_vecs = [v for _, v in valid]
    sims = cosine_similarity_batch(query_vec, candidate_vecs)

    best_idx = max(range(len(sims)), key=lambda i: sims[i])
    best_sim = sims[best_idx]

    if best_sim < LOW_THRESHOLD:
        return None, None

    best_entry = valid[best_idx][0]
    entry_id = str(best_entry.get("id", ""))

    # Increment hit_count (best-effort)
    try:
        async with pool.connection() as db:
            await db.query(
                "UPDATE $rid SET hit_count = IF hit_count THEN hit_count + 1 ELSE 1 END",
                {"rid": parse_record_id(entry_id)},
            )
    except Exception as exc:
        logger.debug("classification_cache: hit_count increment failed (non-fatal): %s", exc)

    result = best_entry.get("result")
    if not isinstance(result, dict):
        return None, None

    return result, entry_id


async def store(description: str, result: dict[str, Any], product_id: str) -> None:
    """UPSERT a classification result keyed by md5 of description.

    Embedding is generated for future similarity lookups.
    hit_count and created_at are preserved on update.
    """
    embedder = get_embedder()
    if embedder.dimensions == 0:
        return

    try:
        vecs = await embedder.embed([description])
        emb: list[float] = vecs[0] if vecs else []
    except Exception as exc:
        logger.warning("classification_cache: store embed failed (non-fatal): %s", exc)
        emb = []

    slug = _md5_slug(description)

    try:
        from surrealdb import RecordID

        rid = RecordID("classification_cache", slug)
        async with pool.connection() as db:
            await db.query(
                """UPSERT $rid SET
                   product            = <record>$product,
                   description        = $description,
                   description_embedding = $embedding,
                   result             = $result,
                   hit_count          = IF hit_count THEN hit_count ELSE 0 END,
                   created_at         = IF created_at THEN created_at ELSE time::now() END""",
                {
                    "rid": rid,
                    "product": product_id,
                    "description": description,
                    "embedding": emb if emb else None,
                    "result": result,
                },
            )
    except Exception as exc:
        logger.warning("classification_cache: store upsert failed (non-fatal): %s", exc)


async def on_zero_utilization_hit(entry_id: str) -> None:
    """Increment consecutive_zero_utilization counter; DELETE entry at 3."""
    try:
        rid = parse_record_id(entry_id)
        async with pool.connection() as db:
            await db.query(
                """UPDATE $rid SET
                    consecutive_zero_utilization = IF consecutive_zero_utilization
                        THEN consecutive_zero_utilization + 1
                        ELSE 1
                    END,
                    updated_at = time::now()
                """,
                {"rid": rid},
            )
            rows = parse_rows(
                await db.query(
                    "SELECT consecutive_zero_utilization FROM $rid",
                    {"rid": rid},
                )
            )
            if rows and int(rows[0].get("consecutive_zero_utilization") or 0) >= 3:
                await db.query("DELETE $rid", {"rid": rid})
                logger.info(
                    "Invalidated stale cache entry %s (3+ consecutive zero-utilization hits)",
                    entry_id,
                )
    except Exception as exc:
        logger.warning("on_zero_utilization_hit failed (non-fatal): %s", exc)


async def on_utilization_hit(entry_id: str) -> None:
    """Reset consecutive_zero_utilization counter to 0."""
    try:
        rid = parse_record_id(entry_id)
        async with pool.connection() as db:
            await db.query(
                "UPDATE $rid SET consecutive_zero_utilization = 0, updated_at = time::now()",
                {"rid": rid},
            )
    except Exception as exc:
        logger.warning("on_utilization_hit failed (non-fatal): %s", exc)
