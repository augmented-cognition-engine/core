# engine/worker/signals.py
"""Signal extractor — reads recent insights and produces SignalEmission objects.

Runs at the end of run_poll_cycle (after dedup + embed). Queries DB directly
for what landed this cycle rather than taking processed/deduped/embedded as args.
This decouples extraction from processing and makes the extractor testable independently.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass

logger = logging.getLogger(__name__)

SIGNAL_THRESHOLDS: dict[str, float] = {
    "intelligence_classified": 0.7,
}


@dataclass
class SignalEmission:
    kind: str
    product_id: str
    payload: dict
    confidence: float


async def extract_signals(product_id: str) -> list[SignalEmission]:
    """Read recent insights and produce SignalEmission objects.

    Gate: returns [] immediately when worker_canvas_bridge_enabled is off.
    Threshold: only emits intelligence_classified when confidence > 0.7.
    Dedup: skips disciplines already emitted within the last 24 hours.
    """
    from core.engine.core.db import parse_rows, pool
    from core.engine.worker.feature_flag import is_worker_canvas_bridge_enabled

    if not await is_worker_canvas_bridge_enabled(pool, product_id):
        return []

    async with pool.connection() as db:
        insight_rows = parse_rows(
            await db.query(
                """SELECT id, domain_path, source_domain, confidence, content, created_at
                   FROM insight
                   WHERE product = <record>$pid
                     AND created_at > time::now() - 5m
                   ORDER BY created_at DESC LIMIT 50""",
                {"pid": product_id},
            )
        )
        # Read recent worker_signal rows (24h) for dedup
        recent_signals = parse_rows(
            await db.query(
                """SELECT kind, payload FROM worker_signal
                   WHERE product = <record>$pid
                     AND emitted_at > time::now() - 1d""",
                {"pid": product_id},
            )
        )

    seen_disciplines = {
        s["payload"].get("discipline") for s in recent_signals if s.get("kind") == "intelligence_classified"
    }

    signals: list[SignalEmission] = []
    threshold = SIGNAL_THRESHOLDS["intelligence_classified"]
    for row in insight_rows:
        confidence = float(row.get("confidence", 0.0))
        if confidence <= threshold:
            continue
        # Use domain_path as the discipline slug (source_domain is the fallback)
        discipline = row.get("domain_path") or row.get("source_domain")
        if not discipline or discipline in seen_disciplines:
            continue
        signals.append(
            SignalEmission(
                kind="intelligence_classified",
                product_id=product_id,
                payload={
                    "discipline": discipline,
                    "summary": (row.get("content") or "")[:200],
                    "observation_id": str(row.get("id", "")),
                },
                confidence=confidence,
            )
        )
        seen_disciplines.add(discipline)

    return signals
