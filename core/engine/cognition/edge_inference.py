"""Edge inference — derive causal links between journey_event rows.

Runs as a periodic sentinel sweeper (every 5 minutes); journey API may also
trigger on-demand inference if the latest sweeper run is stale (>5 min).

Inference rules look at journey_event timing + payload + provenance to infer
causal edges. The reasoning_edge UNIQUE index makes inference idempotent —
duplicate writes silently skip.
"""

from __future__ import annotations

import logging
import math
from typing import Any

logger = logging.getLogger(__name__)


# Inference rule definitions. Each rule produces edges where to_event matches
# `to_topic` and there exists a from_event with `from_topic` within the window
# AND the predicate (payload similarity check) holds.
_RULES = [
    {
        "from_topic": "gap.detected",
        "to_topic": "canvas.score.changed",
        "edge_type": "triggered",
        "window_minutes": 60,
        "predicate": lambda f, t: f["payload"].get("pillar") == t["payload"].get("pillar"),
    },
    {
        "from_topic": "canvas.recommendation.shifted",
        "to_topic": "canvas.thread.committed",
        "edge_type": "triggered",
        "window_minutes": 60 * 24,
        "predicate": lambda f, t: f["payload"].get("topic") == t["payload"].get("topic"),
    },
    {
        "from_topic": "canvas.thread.resolved",
        "to_topic": "canvas.decision.captured",
        "edge_type": "triggered",
        "window_minutes": 60,
        "predicate": lambda f, t: True,
    },
    {
        "from_topic": "canvas.score.changed",
        "to_topic": "canvas.recommendation.shifted",
        "edge_type": "triggered",
        "window_minutes": 60,
        "predicate": lambda f, t: f["payload"].get("pillar") == t["payload"].get("pillar"),
    },
]

# 5th edge type `informed_by_star_trace` is reserved in the v101 ASSERT enum but
# not emitted by edge_inference in v1. Reason: reasoning_edge.from_event is
# record<journey_event> but star_trace rows don't have corresponding
# journey_event mirrors. AC3's "matched proven pattern" link in the expanded
# card already renders directly from composition_trace.star_trace_id (no edge
# required). Future Phase B: emit a journey_event mirror when a star_trace is
# loaded by the briefing engine, then this rule activates.


async def infer_edges_for_product(pool: Any, product_id: str) -> list[dict]:
    """Compute new edges for a product, write to reasoning_edge. Return list of new edges.

    Idempotent: existing (from_event, to_event, edge_type) tuples skip via UNIQUE index.
    """
    from core.engine.core.db import parse_rows

    new_edges: list[dict] = []

    async with pool.connection() as db:
        # Pull recent journey_event rows for this product (last 30 days, capped 5000)
        rows = parse_rows(
            await db.query(
                "SELECT id, topic, payload, occurred_at FROM journey_event "
                "WHERE product = <record>$pid AND occurred_at > time::now() - 30d "
                "ORDER BY occurred_at ASC LIMIT 5000",
                {"pid": product_id},
            )
        )

        # Bucket events by topic for fast lookup
        by_topic: dict[str, list[dict]] = {}
        for r in rows:
            by_topic.setdefault(r["topic"], []).append(r)

        for rule in _RULES:
            from_events = by_topic.get(rule["from_topic"], [])
            to_events = by_topic.get(rule["to_topic"], [])
            for to_ev in to_events:
                for from_ev in from_events:
                    if from_ev["occurred_at"] >= to_ev["occurred_at"]:
                        continue
                    delta_min = (to_ev["occurred_at"] - from_ev["occurred_at"]).total_seconds() / 60
                    if delta_min > rule["window_minutes"]:
                        continue
                    if not rule["predicate"](from_ev, to_ev):
                        continue
                    # Confidence decays with time gap (inverse log)
                    conf = max(0.5, 1.0 - (math.log1p(delta_min) / math.log(rule["window_minutes"] + 1)))
                    edge = {
                        "from_event": str(from_ev["id"]),
                        "to_event": str(to_ev["id"]),
                        "edge_type": rule["edge_type"],
                        "confidence": round(conf, 2),
                        "product": product_id,
                    }
                    try:
                        result = await db.query(
                            "CREATE reasoning_edge SET from_event=<record>$f, to_event=<record>$t, "
                            "edge_type=$et, confidence=$c, product=<record>$pid",
                            {
                                "f": edge["from_event"],
                                "t": edge["to_event"],
                                "et": edge["edge_type"],
                                "c": edge["confidence"],
                                "pid": product_id,
                            },
                        )
                        # SurrealDB returns UNIQUE-index violations as a string error in the
                        # result (no exception raised). Detect and skip those duplicates.
                        if isinstance(result, str):
                            logger.debug("reasoning_edge skipped (duplicate): %s", result)
                            continue
                        new_edges.append(edge)
                    except Exception as exc:
                        # Defensive: if the SDK does raise (future versions), still skip.
                        logger.debug("reasoning_edge skipped (likely duplicate): %s", exc)

    return new_edges
