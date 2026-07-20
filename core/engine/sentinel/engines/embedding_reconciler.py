"""Backfills embeddings for insights written in degraded mode (needs_embedding=true).

Runs on the sentinel schedule. Idempotent: clears needs_embedding once the vector
is written. This is the ONLY best-effort component retained in the memory write
path — the common path is fully atomic (see atomic_capture_write).
"""

from __future__ import annotations

import logging

from core.engine.core.db import parse_rows, pool
from core.engine.embedding.base import get_embedder
from core.engine.sentinel.registry import register_engine

logger = logging.getLogger(__name__)


async def reconcile_missing_embeddings(limit: int = 200) -> int:
    """Backfill embedding vectors for ANY embedding-less active insight.

    Path-agnostic: catches insights regardless of which write path created them —
    degraded-mode captures (needs_embedding=true) AND insights written by paths
    that never embed at all (sentinel write_engine_insight, consolidator,
    seed_generator, bootstrap, specialty_broadcast). Without this, those insights
    are permanently invisible to ace_search. Queries `embedding = NONE` (up to
    `limit`), embeds in one batch, writes the vectors back and clears any
    degraded flag. Global (not product-scoped). Empty-content rows are excluded
    (nothing to embed) so they don't get re-scanned every run. Returns the count
    backfilled.

    Connection discipline: the pooled connection is NOT held across embedding
    inference. We fetch ids+content, release the connection, run the (blocking)
    model over the whole batch, then reacquire to write. Holding a connection
    across many slow inferences would risk the lease watchdog reclaiming it
    mid-loop (LEASE_TTL) and starving the pool.
    """
    embedder = get_embedder()
    if embedder.dimensions == 0:
        return 0

    # --- fetch, then release the connection before inference ---
    async with pool.connection() as db:
        rows = parse_rows(
            await db.query(
                "SELECT id, content, domain_path, insight_type, tags FROM insight "
                "WHERE embedding = NONE AND status = 'active' AND content != NONE AND content != '' "
                "LIMIT $lim",
                {"lim": limit},
            )
        )

    from core.engine.core.config import settings

    pending = []  # (id_str, embed_text)
    for row in rows:
        content = row.get("content") or ""
        if not content:
            logger.warning("insight %s has needs_embedding=true but empty content — skipping", row.get("id"))
            continue
        # Contextual chunk enrichment — embed the SAME [discipline · type · tags]-prefixed text the
        # synthesizer uses, so reconciler-fixed vectors stay consistent with freshly-captured ones.
        embed_text = content
        if settings.contextual_chunk_enrichment:
            from core.engine.capture.contextualize import contextualize_for_embedding

            embed_text = contextualize_for_embedding(
                content,
                domain_path=row.get("domain_path"),
                insight_type=row.get("insight_type"),
                tags=row.get("tags"),
            )
        pending.append((str(row["id"]), embed_text))
    if not pending:
        return 0

    # --- batch-embed off the pool (blocking inference happens here) ---
    try:
        vectors = await embedder.embed([c for _, c in pending])
    except Exception:
        logger.warning("embedding batch failed in reconciler — will retry next run", exc_info=True)
        return 0

    # --- reacquire to write the successful rows ---
    fixed = 0
    async with pool.connection() as db:
        for (id_str, _), vec in zip(pending, vectors):
            if not vec or len(vec) != embedder.dimensions:
                continue
            await db.query(
                "UPDATE <record>$id SET embedding = $emb, needs_embedding = false, updated_at = time::now()",
                {"id": id_str, "emb": vec},
            )
            fixed += 1
    return fixed


@register_engine(
    name="embedding_reconciler",
    cron="*/15 * * * *",
    description="Backfills embedding vectors for degraded-mode captures (every 15 min)",
)
async def run(product_id: str) -> dict:
    """Sentinel entry point — global sweep ignores product_id."""
    n = await reconcile_missing_embeddings()
    return {"reconciled": n}
