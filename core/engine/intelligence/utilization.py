"""Insight utilization tracking — per-insight load/attribution counters.

Updates the insight_utilization table after each task execution.
Records how many times each insight was loaded into context vs. actually
attributed in the output — enabling ROI scoring and stale insight pruning.
"""

from __future__ import annotations

import hashlib
import logging

from surrealdb import RecordID

from core.engine.core.db import parse_rows

logger = logging.getLogger(__name__)

_LIVE_SCORE_MIN_SAMPLES = 5


def _iu_record_id(product_id: str, insight_id: str) -> RecordID:
    """Deterministic RecordID for insight_utilization rows.

    Uses MD5 of "{product_id}|{insight_id}" truncated to 16 hex chars.
    Matches the gap_analyzer.py pattern for idempotent UPSERT.
    """
    slug = hashlib.md5(f"{product_id}|{insight_id}".encode()).hexdigest()[:16]
    return RecordID("insight_utilization", slug)


async def update_utilization(
    product_id: str,
    loaded_ids: list[str],
    attributed_ids: list[str],
    db,
) -> None:
    """Upsert insight_utilization records for all loaded insights.

    For each loaded insight:
      - Increments loaded_count by 1
      - If the insight was also attributed: increments attributed_count + sets last_attributed

    Uses RecordID-keyed UPSERT (same pattern as gap_analyzer.py) to avoid the
    SurrealDB v3 WHERE-clause silent no-op on first insert.

    Non-fatal: each insight is wrapped in its own try/except. Failures are logged
    as warnings but do not propagate — utilization tracking must never break task flow.

    Note: utilization_score stays at its DEFAULT 0.5 until Phase 4's
    compute_utilization_scores() nightly recomputation kicks in. See
    docs/superpowers/plans/2026-04-15-token-roi-phase4-feedback-loop.md Task 1.

    Args:
        product_id: The product record ID (e.g. "product:abc123")
        loaded_ids: All insight IDs that were injected into context
        attributed_ids: Insight IDs that were attributed in the output
        db: SurrealDB connection (already acquired — caller manages lifecycle)
    """
    if not loaded_ids:
        return

    attributed_set = set(attributed_ids)

    for insight_id in loaded_ids:
        try:
            rid = _iu_record_id(product_id, insight_id)
            is_attributed = insight_id in attributed_set
            if is_attributed:
                result = await db.query(
                    """
                    UPSERT $rid SET
                        insight = <record>$insight,
                        product = <record>$product,
                        loaded_count = IF loaded_count THEN loaded_count + 1 ELSE 1 END,
                        attributed_count = IF attributed_count THEN attributed_count + 1 ELSE 1 END,
                        last_attributed = time::now(),
                        updated_at = time::now()
                    """,
                    {"rid": rid, "insight": insight_id, "product": product_id},
                )
            else:
                result = await db.query(
                    """
                    UPSERT $rid SET
                        insight = <record>$insight,
                        product = <record>$product,
                        loaded_count = IF loaded_count THEN loaded_count + 1 ELSE 1 END,
                        updated_at = time::now()
                    """,
                    {"rid": rid, "insight": insight_id, "product": product_id},
                )
            await _maybe_update_live_score(rid, result, db)
        except Exception as exc:
            logger.warning(
                "update_utilization: failed for insight=%s product=%s: %s",
                insight_id,
                product_id,
                exc,
            )


async def _maybe_update_live_score(rid: RecordID, upsert_result, db) -> None:
    """Inline score recompute — runs after each UPSERT once samples are sufficient.

    Reads counters from the UPSERT result, computes attributed/loaded, writes
    utilization_score back. Only active once loaded_count >= _LIVE_SCORE_MIN_SAMPLES
    (matches the nightly compute threshold so behaviour is consistent).

    Failures are swallowed — score staleness is acceptable, task flow must not break.
    """
    try:
        rows = parse_rows(upsert_result)
        if not rows:
            return
        row = rows[0]
        loaded = int(row.get("loaded_count") or 0)
        if loaded < _LIVE_SCORE_MIN_SAMPLES:
            return
        attributed = int(row.get("attributed_count") or 0)
        score = round(attributed / loaded, 4)
        await db.query(
            "UPDATE $rid SET utilization_score = $score, updated_at = time::now()",
            {"rid": rid, "score": score},
        )
    except Exception as exc:
        logger.warning("live utilization_score update failed for %s: %s", rid, exc)


async def compute_utilization_scores(product_id: str, db) -> dict:
    rows = parse_rows(
        await db.query(
            """SELECT id, loaded_count, attributed_count
               FROM insight_utilization
               WHERE product = <record>$product AND loaded_count >= 5""",
            {"product": product_id},
        )
    )

    updated = 0
    low_utilization_count = 0

    for row in rows:
        rid = row["id"]
        loaded = int(row.get("loaded_count") or 0)
        attributed = int(row.get("attributed_count") or 0)
        score = round(attributed / loaded, 4)
        await db.query(
            "UPDATE $rid SET utilization_score = $score, updated_at = time::now()",
            {"rid": rid, "score": score},
        )
        updated += 1
        if score < 0.1 and loaded >= 10:
            low_utilization_count += 1

    return {"updated": updated, "low_utilization_count": low_utilization_count}
