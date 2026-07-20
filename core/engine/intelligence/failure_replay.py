"""Failure replay — counterfactual detector for repeat failures.

When a task fails VerificationGate with gap patterns resembling a prior failure,
the system failed to learn from its own memory. This module surfaces that
signal so the briefing can highlight it and humans (or sentinel engines) can
investigate why the memory didn't prevent the repeat.

Full LLM replay (re-running a task with failure_memory injected to see if it
would pass now) is an expensive future extension. The detector here is cheap —
it runs on every failure and answers: "have we seen this pattern before?"
"""

from __future__ import annotations

import logging

logger = logging.getLogger(__name__)

_REPEAT_OVERLAP_THRESHOLD = 0.5


def _tokenize_gaps(gaps: list[str]) -> set[str]:
    return {g.strip().lower() for g in gaps if g and g.strip()}


def _gap_overlap(a: list[str], b: list[str]) -> float:
    """Jaccard over the set of gap entries (case-normalized)."""
    sa, sb = _tokenize_gaps(a), _tokenize_gaps(b)
    if not sa or not sb:
        return 0.0
    return len(sa & sb) / len(sa | sb)


async def detect_repeat_failures(
    db,
    product_id: str,
    discipline: str,
    gaps: list[str],
    threshold: float = _REPEAT_OVERLAP_THRESHOLD,
    lookback_limit: int = 100,
) -> list[dict]:
    """Return prior failure_memory rows whose gap set matches above threshold.

    Args:
        db: SurrealDB connection
        product_id: Scope to one product
        discipline: Same-discipline failures only (cross-discipline overlap is noise)
        gaps: Gap list from the new failure
        threshold: Jaccard threshold (default 0.5)
        lookback_limit: Max prior failures to scan

    Returns the matching prior rows. Non-fatal — [] on any failure.
    """
    try:
        from core.engine.core.db import parse_rows

        rows = parse_rows(
            await db.query(
                """SELECT id, task_summary, gaps, created_at
                   FROM failure_memory
                   WHERE product = <record>$product AND discipline = $discipline
                   ORDER BY created_at DESC
                   LIMIT $limit""",
                {"product": product_id, "discipline": discipline, "limit": lookback_limit},
            )
        )
        return [row for row in rows if _gap_overlap(gaps, row.get("gaps") or []) >= threshold]
    except Exception as exc:
        logger.warning("detect_repeat_failures failed (non-fatal): %s", exc)
        return []


async def record_repeat_failure(
    db,
    bus,
    product_id: str,
    new_failure_id: str,
    repeat_of_ids: list[str],
) -> None:
    """Flag a new failure_memory row as a repeat + emit the learning-failure event.

    Updates the row's `repeat_of` field (SCHEMALESS table → schema-free) and emits
    failure.repeat_detected so the briefing can surface it.
    Non-fatal.
    """
    try:
        await db.query(
            "UPDATE <record>$id SET repeat_of = $repeat_of, is_repeat = true",
            {"id": new_failure_id, "repeat_of": repeat_of_ids},
        )
    except Exception as exc:
        logger.warning("record_repeat_failure UPDATE failed (non-fatal): %s", exc)

    try:
        await bus.emit(
            "failure.repeat_detected",
            {
                "product_id": product_id,
                "new_failure_id": new_failure_id,
                "repeat_of": repeat_of_ids,
            },
        )
    except Exception as exc:
        logger.debug("failure.repeat_detected emit failed (non-fatal): %s", exc)
