# engine/worker/processor.py
"""Observation processor — drains the pending observation queue."""

from __future__ import annotations

import asyncio
import logging
import os
import uuid

from core.engine.capture.leases import (
    DEFAULT_HEARTBEAT_SECONDS,
    DEFAULT_LEASE_SECONDS,
    ClaimedObservationV1,
    ObservationLeaseLost,
    ObservationLeaseV1,
    claim_next_observation,
    renew_observation_lease,
)
from core.engine.capture.lifecycle import MAX_PROCESSING_ATTEMPTS, process_observation_attempt
from core.engine.capture.synthesizer import Synthesizer
from core.engine.core.db import parse_rows, pool
from core.engine.embedding.base import get_embedder

logger = logging.getLogger(__name__)

_POLL_BATCH = 10
_MAX_DRAIN_BATCHES = 4
MAX_RETRIES = MAX_PROCESSING_ATTEMPTS
WORKER_INSTANCE_ID = os.environ.get("ACE_WORKER_INSTANCE_ID") or f"worker:{os.getpid()}:{uuid.uuid4().hex[:16]}"


async def fetch_pending(product_id: str = "product:platform") -> list[dict]:
    """Return pending or retry-eligible observations for exactly one product."""
    async with pool.connection() as db:
        result = await db.query(
            """
            SELECT * FROM observation
            WHERE product = <record>$product AND status = 'pending'
              AND (processing_state IS NONE OR processing_state IN ['pending', 'retryable_failed'])
              AND (next_retry_at IS NONE OR next_retry_at <= time::now())
            ORDER BY created_at ASC LIMIT $limit
            """,
            {"product": product_id, "limit": _POLL_BATCH},
        )
        return parse_rows(result)


async def process_observation(
    obs: dict,
    *,
    route: str = "worker",
    lease: ObservationLeaseV1 | None = None,
):
    """Process through the shared receipt/finalization lifecycle."""
    receipt = await process_observation_attempt(
        obs,
        db_pool=pool,
        route=route,
        synthesizer_factory=Synthesizer,
        scope_prevalidated=True,
        lease_id=lease.lease_id if lease else None,
        lease_owner=lease.owner_id if lease else None,
        lease_recovered=lease.recovered_attempt if lease else False,
    )
    logger.debug(
        "Observation %s finalized as %s",
        obs.get("id"),
        receipt.processing_state.value,
    )
    return receipt


async def claim_observation(
    product_id: str = "product:platform",
    *,
    owner_id: str = WORKER_INSTANCE_ID,
    lease_seconds: float = DEFAULT_LEASE_SECONDS,
) -> ClaimedObservationV1 | None:
    """Atomically claim one due product-owned observation."""
    return await claim_next_observation(
        pool,
        product_id=product_id,
        owner_id=owner_id,
        lease_seconds=lease_seconds,
    )


async def process_claimed_observation(
    claimed: ClaimedObservationV1,
    *,
    lease_seconds: float = DEFAULT_LEASE_SECONDS,
    heartbeat_seconds: float = DEFAULT_HEARTBEAT_SECONDS,
):
    """Process under a heartbeat and cancel immediately if the fence is lost."""
    if not 0 < heartbeat_seconds < lease_seconds:
        raise ValueError("heartbeat_seconds must be positive and shorter than lease_seconds")

    lease = claimed.lease
    processing = asyncio.create_task(
        process_observation(
            claimed.observation,
            route="worker_leased",
            lease=lease,
        )
    )
    try:
        while True:
            done, _pending = await asyncio.wait({processing}, timeout=heartbeat_seconds)
            if processing in done:
                return await processing
            try:
                lease = await renew_observation_lease(
                    pool,
                    lease,
                    lease_seconds=lease_seconds,
                )
            except Exception:
                processing.cancel()
                try:
                    await processing
                except asyncio.CancelledError:
                    pass
                raise
    except asyncio.CancelledError:
        processing.cancel()
        try:
            await processing
        except asyncio.CancelledError:
            pass
        raise


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
                await db.query(
                    "DELETE <record>$id WHERE product = <record>$product",
                    {"id": dup_id, "product": product_id},
                )
            merged += 1

        if duplicates:
            for keeper in seen.values():
                new_conf = min(1.0, float(keeper.get("confidence", 0.7)) + 0.05)
                async with pool.connection() as db:
                    await db.query(
                        "UPDATE <record>$id SET confidence = $conf WHERE product = <record>$product",
                        {"id": str(keeper["id"]), "conf": new_conf, "product": product_id},
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
                    "UPDATE <record>$id SET embedding = $vec WHERE product = <record>$product",
                    {"id": str(row["id"]), "vec": vec, "product": product_id},
                )

        logger.debug("Embedded %d insights", len(rows))
        return len(rows)

    except Exception as exc:
        logger.warning("Insight embedding failed: %s", exc)
        return 0


async def run_poll_cycle(
    product_id: str = "product:platform",
    *,
    owner_id: str = WORKER_INSTANCE_ID,
    lease_seconds: float = DEFAULT_LEASE_SECONDS,
    heartbeat_seconds: float = DEFAULT_HEARTBEAT_SECONDS,
) -> int:
    """Claim and process up to one bounded batch, one lease at a time."""
    from core.engine.worker.health import get_health_state

    processed = 0
    disciplines_seen: set[str] = set()
    for _ in range(_POLL_BATCH):
        claimed = await claim_observation(
            product_id,
            owner_id=owner_id,
            lease_seconds=lease_seconds,
        )
        if claimed is None:
            break
        get_health_state().record_lease_claim(recovered=claimed.lease.recovered_attempt)
        try:
            await process_claimed_observation(
                claimed,
                lease_seconds=lease_seconds,
                heartbeat_seconds=heartbeat_seconds,
            )
            processed += 1
            get_health_state().record_leased_outcome()
            obs = claimed.observation
            disc = obs.get("domain_path") or obs.get("discipline_hint", "")
            if disc:
                disciplines_seen.add(disc)
        except ObservationLeaseLost as exc:
            get_health_state().record_lease_loss(str(exc))
            logger.warning("Observation lease lost before finalization: %s", exc)
        except Exception as exc:
            get_health_state().record_error(str(exc))
            logger.warning("Leased observation processing failed: %s", exc)

    if not processed:
        return 0

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

    logger.info("poll_cycle: processed=%d signals=%d", processed, len(signals))
    return processed


async def run_drain_cycle(
    product_id: str = "product:platform",
    *,
    owner_id: str = WORKER_INSTANCE_ID,
    max_batches: int = _MAX_DRAIN_BATCHES,
) -> int:
    """Continuously drain a bounded number of batches without pre-claiming work."""
    if not 1 <= max_batches <= 100:
        raise ValueError("max_batches must be between 1 and 100")
    total = 0
    for _ in range(max_batches):
        count = await run_poll_cycle(product_id, owner_id=owner_id)
        total += count
        if count < _POLL_BATCH:
            break
        await asyncio.sleep(0)
    return total
