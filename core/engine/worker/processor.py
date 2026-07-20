# engine/worker/processor.py
"""Observation processor — drains the pending observation queue."""

from __future__ import annotations

import logging

from core.engine.capture.synthesizer import Synthesizer
from core.engine.core.db import parse_rows, pool
from core.engine.embedding.base import get_embedder

logger = logging.getLogger(__name__)

_POLL_BATCH = 10
MAX_RETRIES = 3


async def fetch_pending(product_id: str = "product:platform") -> list[dict]:
    """Return up to _POLL_BATCH pending observations."""
    async with pool.connection() as db:
        result = await db.query(
            """
            SELECT * FROM observation
            WHERE product = <record>$product AND status = 'pending'
            ORDER BY created_at ASC LIMIT $limit
            """,
            {"product": product_id, "limit": _POLL_BATCH},
        )
        return parse_rows(result)


async def process_observation(obs: dict) -> None:
    """Synthesize a single observation and update its status."""
    obs_id = str(obs.get("id", ""))
    product_id = str(obs.get("product", "product:platform"))

    try:
        synth = Synthesizer(product_id=product_id, workspace_id=None, batch_size=1)
        synth._db_pool = pool  # required for _write_insight to flush to DB
        await synth.add_observation(obs)
        await synth.flush()

        async with pool.connection() as db:
            await db.query(
                "UPDATE <record>$id SET status = 'processed', processed_at = time::now()",
                {"id": obs_id},
            )
        logger.debug("Processed observation %s", obs_id)

    except Exception as exc:
        current_retries = int(obs.get("retry_count") or 0)
        next_retries = current_retries + 1
        exhausted = next_retries >= MAX_RETRIES
        logger.warning(
            "Failed to process observation %s (retry %d/%d): %s",
            obs_id,
            next_retries,
            MAX_RETRIES,
            exc,
        )
        try:
            async with pool.connection() as db:
                if exhausted:
                    await db.query(
                        "UPDATE <record>$id SET status = 'failed', retry_count = $rc, last_error = $err",
                        {"id": obs_id, "rc": next_retries, "err": str(exc)[:500]},
                    )
                else:
                    await db.query(
                        "UPDATE <record>$id SET retry_count = $rc, last_error = $err",
                        {"id": obs_id, "rc": next_retries, "err": str(exc)[:500]},
                    )
        except Exception:
            pass


async def dedup_insights(product_id: str, discipline: str) -> int:
    """Merge near-duplicate insights in the given discipline.

    Finds insights sharing the same first 60 characters (same core claim).
    Keeps highest-confidence, boosts by 5%, deletes duplicates.
    Returns count of merges performed.
    """
    merged = 0
    try:
        async with pool.connection() as db:
            rows = parse_rows(
                await db.query(
                    """
                SELECT id, content, confidence,
                    string::slice(content, 0, 60) AS prefix
                FROM insight
                WHERE product = <record>$product AND status = 'active'
                  AND (domain_path = $disc OR discipline_hint = $disc)
                ORDER BY confidence DESC
                """,
                    {"product": product_id, "disc": discipline},
                )
            )

        seen: dict[str, dict] = {}
        duplicates: list[str] = []
        for row in rows:
            prefix = row.get("prefix", "").strip().lower()
            if not prefix:
                continue
            rid = str(row.get("id", ""))
            if prefix in seen:
                duplicates.append(rid)
            else:
                seen[prefix] = row

        for dup_id in duplicates:
            async with pool.connection() as db:
                await db.query("DELETE <record>$id", {"id": dup_id})
            merged += 1

        if duplicates:
            for keeper in seen.values():
                new_conf = min(1.0, float(keeper.get("confidence", 0.7)) + 0.05)
                async with pool.connection() as db:
                    await db.query(
                        "UPDATE <record>$id SET confidence = $conf",
                        {"id": str(keeper["id"]), "conf": new_conf},
                    )

    except Exception as exc:
        logger.warning("Dedup failed for %s/%s: %s", product_id, discipline, exc)

    return merged


async def embed_new_insights(product_id: str, limit: int = 20) -> int:
    """Find insights without embeddings and generate them via get_embedder().

    Returns count of insights embedded. Skips if embedder is noop (dimensions==0)
    or if embedding generation fails.
    """
    embedder = get_embedder()
    if embedder.dimensions == 0:
        return 0

    try:
        async with pool.connection() as db:
            rows = parse_rows(
                await db.query(
                    """
                    SELECT id, content, domain_path, insight_type, tags FROM insight
                    WHERE product = <record>$product
                      AND status = 'active'
                      AND embedding IS NONE
                    LIMIT $limit
                    """,
                    {"product": product_id, "limit": limit},
                )
            )

        if not rows:
            return 0

        # Contextual chunk enrichment — embed the SAME [discipline · type · tags]-prefixed text the
        # synthesizer/reconciler use. This worker runs in the hot path and pre-empts the reconciler (it
        # sets a non-NONE embedding), so it MUST enrich too or degraded-mode insights stay unenriched.
        from core.engine.core.config import settings

        def _embed_text(r: dict) -> str:
            content = r.get("content", "") or ""
            if not settings.contextual_chunk_enrichment:
                return content
            from core.engine.capture.contextualize import contextualize_for_embedding

            return contextualize_for_embedding(
                content,
                domain_path=r.get("domain_path"),
                insight_type=r.get("insight_type"),
                tags=r.get("tags"),
            )

        texts = [_embed_text(r) for r in rows]
        vectors = await embedder.embed(texts)

        async with pool.connection() as db:
            for row, vec in zip(rows, vectors):
                await db.query(
                    "UPDATE <record>$id SET embedding = $vec",
                    {"id": str(row["id"]), "vec": vec},
                )

        logger.debug("Embedded %d insights", len(rows))
        return len(rows)

    except Exception as exc:
        logger.warning("Insight embedding failed: %s", exc)
        return 0


async def run_poll_cycle(product_id: str = "product:platform") -> int:
    """Fetch and process one batch. Returns count processed."""
    pending = await fetch_pending(product_id)
    if not pending:
        return 0

    disciplines_seen: set[str] = set()
    for obs in pending:
        await process_observation(obs)
        disc = obs.get("domain_path") or obs.get("discipline_hint", "")
        if disc:
            disciplines_seen.add(disc)

    for disc in disciplines_seen:
        await dedup_insights(product_id, disc)

    # Generate embeddings for any new insights
    await embed_new_insights(product_id)

    # Extract signals from what landed this cycle — extractor queries DB directly.
    # Returns [] immediately when worker_canvas_bridge_enabled flag is off.
    from core.engine.worker.signals import extract_signals

    signals = await extract_signals(product_id)

    # Emit signals to canvas bus (persist-first, fire-and-forget emit).
    from core.engine.worker.bus_bridge import emit_signals_to_bus

    await emit_signals_to_bus(signals)

    logger.info("poll_cycle: processed=%d signals=%d", len(pending), len(signals))
    return len(pending)
