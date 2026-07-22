"""Loop-context loader — the read-side of the learning loop (L1 -> L3).

Before composition, the orchestration layer loads what the system already
knows: recent similar decisions (the ledger) and per-archetype calibration
for the classified discipline (written by the L9 reconciler). The result
rides into the composer inside the classification dict; the composer itself
stays stateless and DB-free.

Contract: fail-open. Any exception, missing table, or slow query returns {}
within ``deadline_s``. Composition must never degrade because this read had
a bad day.
"""

from __future__ import annotations

import asyncio
import logging
from typing import Any

logger = logging.getLogger(__name__)

DEFAULT_DEADLINE_S = 3.0
MAX_DECISIONS = 5

# Imported at module level so tests can patch them via
# "core.engine.orchestration.loop_context.find_similar_decisions" etc.
from core.engine.core.db import parse_rows, pool  # noqa: E402
from core.engine.product.decisions import find_similar_decisions, list_decisions  # noqa: E402


async def _gather_context(product_id: str, classification: dict) -> dict[str, Any]:
    """The raw reads. Separated so tests (and the deadline wrapper) can patch it."""
    thought = classification.get("thought") or classification.get("task") or ""
    discipline = classification.get("discipline") or ""

    async with pool.connection() as db:
        decisions = await find_similar_decisions(db, product_id, thought, limit=MAX_DECISIONS)
        calibration = parse_rows(
            await db.query(
                "SELECT archetype, calibration_score, sample_count FROM archetype_calibration "
                "WHERE product = <record>$product AND discipline = <string>$discipline",
                {"product": product_id, "discipline": discipline},
            )
        )
    if not decisions:
        # Jaccard-vs-title rarely matches free-form thoughts; recency is the
        # honest fallback — the ledger should always be in the room.
        # Called AFTER the pool block exits: list_decisions acquires its own
        # connection, and nesting would stall a single-connection pool until
        # the fail-open deadline.
        decisions = await list_decisions(
            product_id,
            outcome="accepted",
            limit=3,
        )
    return {"prior_decisions": decisions, "calibration": calibration}


def _shape(gathered: dict[str, Any]) -> dict[str, Any]:
    decisions = [
        {
            "title": d.get("title", ""),
            "rationale": (d.get("rationale") or "")[:280],
            "decision_type": d.get("decision_type", ""),
        }
        for d in gathered.get("prior_decisions", [])[:MAX_DECISIONS]
    ]
    calibration = {
        row["archetype"]: {
            "score": row.get("calibration_score"),
            "samples": row.get("sample_count", 0),
        }
        for row in gathered.get("calibration", [])
        if row.get("archetype")
    }
    if not decisions and not calibration:
        return {}
    return {"prior_decisions": decisions, "calibration": calibration}


async def load_loop_context(
    product_id: str,
    classification: dict,
    *,
    deadline_s: float = DEFAULT_DEADLINE_S,
) -> dict[str, Any]:
    """Load prior-decision + calibration context for this classification.

    Returns {} on ANY failure or timeout — never raises, never blocks past
    ``deadline_s``.
    """
    try:
        gathered = await asyncio.wait_for(_gather_context(product_id, classification), timeout=deadline_s)
        return _shape(gathered)
    except Exception:
        logger.debug("loop_context unavailable (fail-open)", exc_info=True)
        return {}
