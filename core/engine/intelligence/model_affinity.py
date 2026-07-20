"""Per-model insight affinity tracking.

Extension to insight_utilization: a parallel table `insight_model_affinity` keyed
by (product, insight, model_class) records per-model load/attribution. Over time
this exposes which insights work best for which model class — Haiku thrives on
concrete examples, Sonnet on patterns, Opus on strategic framing.

The loader can then slice intelligence by the target model's affinity profile,
tailoring the snapshot to how the model actually consumes intelligence.
"""

from __future__ import annotations

import hashlib
import logging
import re

from surrealdb import RecordID

logger = logging.getLogger(__name__)

_AFFINITY_MIN_SAMPLES = 5


def normalize_model_class(model_id: str | None) -> str:
    """Collapse a specific model id into a family-level class for affinity bucketing.

    Examples:
        claude-opus-4-7            → opus
        claude-sonnet-4-6          → sonnet
        claude-haiku-4-5-20251001  → haiku
        gpt-4o                     → gpt
        gemini-2.5-pro             → gemini
    """
    if not model_id:
        return "unknown"
    mid = model_id.lower().strip()
    for family in ("opus", "sonnet", "haiku"):
        if family in mid:
            return family
    # Strip trailing version components to get a stable vendor prefix
    m = re.match(r"^([a-z]+)", mid)
    if m:
        return m.group(1)
    return "unknown"


def _affinity_record_id(product_id: str, insight_id: str, model_class: str) -> RecordID:
    slug = hashlib.md5(f"{product_id}|{insight_id}|{model_class}".encode()).hexdigest()[:16]
    return RecordID("insight_model_affinity", slug)


async def update_model_affinity(
    product_id: str,
    loaded_ids: list[str],
    attributed_ids: list[str],
    model_class: str,
    db,
) -> None:
    """Upsert per-model insight affinity counters.

    Mirrors update_utilization() but partitions by model_class so we can see,
    for the same insight, how it performs under different model families.
    """
    if not loaded_ids:
        return

    model_class = normalize_model_class(model_class)
    attributed_set = set(attributed_ids)

    for insight_id in loaded_ids:
        try:
            rid = _affinity_record_id(product_id, insight_id, model_class)
            is_attributed = insight_id in attributed_set
            if is_attributed:
                result = await db.query(
                    """UPSERT $rid SET
                       insight = <record>$insight,
                       product = <record>$product,
                       model_class = $model_class,
                       loaded_count = IF loaded_count THEN loaded_count + 1 ELSE 1 END,
                       attributed_count = IF attributed_count THEN attributed_count + 1 ELSE 1 END,
                       updated_at = time::now()""",
                    {
                        "rid": rid,
                        "insight": insight_id,
                        "product": product_id,
                        "model_class": model_class,
                    },
                )
            else:
                result = await db.query(
                    """UPSERT $rid SET
                       insight = <record>$insight,
                       product = <record>$product,
                       model_class = $model_class,
                       loaded_count = IF loaded_count THEN loaded_count + 1 ELSE 1 END,
                       updated_at = time::now()""",
                    {
                        "rid": rid,
                        "insight": insight_id,
                        "product": product_id,
                        "model_class": model_class,
                    },
                )
            await _maybe_update_affinity_score(rid, result, db)
        except Exception as exc:
            logger.warning(
                "update_model_affinity failed for insight=%s model=%s: %s",
                insight_id,
                model_class,
                exc,
            )


async def _maybe_update_affinity_score(rid: RecordID, upsert_result, db) -> None:
    """Inline affinity score recompute once the per-model sample size is sufficient."""
    try:
        from core.engine.core.db import parse_rows

        rows = parse_rows(upsert_result)
        if not rows:
            return
        row = rows[0]
        loaded = int(row.get("loaded_count") or 0)
        if loaded < _AFFINITY_MIN_SAMPLES:
            return
        attributed = int(row.get("attributed_count") or 0)
        score = round(attributed / loaded, 4)
        await db.query(
            "UPDATE $rid SET affinity_score = $score, updated_at = time::now()",
            {"rid": rid, "score": score},
        )
    except Exception as exc:
        logger.warning("affinity_score update failed for %s: %s", rid, exc)


async def get_model_affinity(db, product_id: str, model_class: str) -> dict[str, float]:
    """Return {insight_id: affinity_score} for one model class. Non-fatal on failure."""
    try:
        from core.engine.core.db import parse_rows

        model_class = normalize_model_class(model_class)
        rows = parse_rows(
            await db.query(
                """SELECT insight, affinity_score FROM insight_model_affinity
                   WHERE product = <record>$product
                     AND model_class = $model_class
                     AND affinity_score IS NOT NONE""",
                {"product": product_id, "model_class": model_class},
            )
        )
        return {str(r.get("insight", "")): float(r.get("affinity_score") or 0.0) for r in rows if r.get("insight")}
    except Exception as exc:
        logger.warning("get_model_affinity failed (non-fatal): %s", exc)
        return {}
