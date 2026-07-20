"""Value model for the Foresight Engine — scores hypothetical product states.

Reads existing capability_quality scores from the DB and applies an in-memory
state_override before computing gap_score. No LLM calls. No DB writes.
"""

from __future__ import annotations

import logging
from collections import defaultdict

from core.engine.core.db import parse_rows
from core.engine.foresight.models import HypotheticalScore

logger = logging.getLogger(__name__)


async def score_hypothetical_state(
    product_id: str,
    state_override: dict[str, float],
    pool=None,
) -> HypotheticalScore:
    """Score a hypothetical product state.

    Args:
        product_id: SurrealDB record ID string (e.g. "product:platform").
        state_override: Maps capability record ID strings (e.g. "capability:auth")
            to hypothetical scores (0.0–1.0). Capability IDs not present in the DB
            are silently ignored. Scores outside [0, 1] are clamped.
        pool: SurrealDB connection pool. Defaults to the module-level pool.

    Returns:
        HypotheticalScore with gap_score, top_risks, capability_scores reflecting
        the patched state. gap_score=0.0 and empty collections when no
        capability_quality rows exist for the product.
    """
    if pool is None:
        from core.engine.core.db import pool as _pool

        pool = _pool

    async with pool.connection() as db:
        result = await db.query(
            "SELECT capability, dimension, score FROM capability_quality WHERE product = <record>$product",
            {"product": product_id},
        )
    rows = parse_rows(result)

    if not rows:
        return HypotheticalScore(gap_score=0.0, top_risks=[], capability_scores={})

    # Apply state_override — patch scores for matching capability IDs in-memory.
    # Each row is (capability_id_str, patched_score).
    patched: list[tuple[str, float]] = []
    for row in rows:
        cap_id = str(row.get("capability", ""))
        raw_score = float(row.get("score", 0.0))
        score = state_override.get(cap_id, raw_score)
        score = max(0.0, min(1.0, score))
        patched.append((cap_id, score))

    # Aggregate: mean score per capability across dimensions.
    cap_buckets: dict[str, list[float]] = defaultdict(list)
    for cap_id, score in patched:
        cap_buckets[cap_id].append(score)

    capability_scores: dict[str, float] = {cap_id: sum(scores) / len(scores) for cap_id, scores in cap_buckets.items()}

    gap_score = sum(capability_scores.values()) / len(capability_scores)

    # top_risks: capabilities below quality threshold, sorted ascending (worst first).
    # Capped at 5 — planner renders at most 3 branches; beyond 5 adds no signal.
    top_risks = [cap_id for cap_id, score in sorted(capability_scores.items(), key=lambda kv: kv[1]) if score < 0.6][:5]

    return HypotheticalScore(
        gap_score=round(gap_score, 4),
        top_risks=top_risks,
        capability_scores=capability_scores,
    )
