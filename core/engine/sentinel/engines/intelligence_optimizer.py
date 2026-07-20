# engine/sentinel/engines/intelligence_optimizer.py
from __future__ import annotations

import logging

from core.engine.core.db import parse_rows, pool
from core.engine.intelligence.utilization import compute_utilization_scores
from core.engine.sentinel.engines import write_engine_insight
from core.engine.sentinel.registry import register_engine

logger = logging.getLogger(__name__)


async def _aggregate_ab_results(product_id: str, db) -> dict:
    """Count A/B results from last 30 days, compute intelligence_premium."""
    rows = parse_rows(
        await db.query(
            """SELECT judge_preference FROM ab_result
               WHERE product = <record>$product
                 AND created_at > time::now() - 30d""",
            {"product": product_id},
        )
    )
    counts: dict[str, int] = {"treatment": 0, "control": 0, "tie": 0}
    for row in rows:
        pref = row.get("judge_preference", "tie")
        if pref in counts:
            counts[pref] += 1

    total = counts["treatment"] + counts["control"] + counts["tie"]
    premium = round(counts["treatment"] / total, 4) if total > 0 else 0.0

    return {**counts, "total": total, "intelligence_premium": premium}


@register_engine(
    name="intelligence_optimizer",
    cron="0 4 * * *",
    description="Recompute utilization scores, aggregate A/B baseline results, write findings insight.",
)
async def run_intelligence_optimizer(product_id: str, budget: int = 50) -> dict:
    """Nightly intelligence delivery optimizer."""
    results: dict = {}

    async with pool.connection() as db:
        results["utilization"] = await compute_utilization_scores(product_id, db)
        results["ab"] = await _aggregate_ab_results(product_id, db)

    util = results["utilization"]
    ab = results["ab"]
    premium_pct = f"{ab['intelligence_premium']:.0%}"
    target_met = ab["intelligence_premium"] >= 0.70 if ab["total"] >= 5 else None
    target_label = (
        "above target" if target_met is True else "below 70% target" if target_met is False else "insufficient data"
    )

    content = (
        f"Intelligence delivery health (intelligence_optimizer nightly run): "
        f"intelligence_premium={premium_pct} ({ab['total']} A/B comparisons — {target_label}). "
        f"Utilization scores updated for {util['updated']} insights"
        + (
            f", {util['low_utilization_count']} low-utilization (< 10% after 10+ loads)."
            if util["low_utilization_count"]
            else "."
        )
    )

    try:
        async with pool.connection() as db:
            await write_engine_insight(
                db,
                product_id=product_id,
                content=content,
                insight_type="pattern",
                tier="product",
                discipline="observability",
                source_domain="sentinel.intelligence_optimizer",
                confidence=0.85,
                tags=["intelligence_roi", "observability", "utilization"],
            )
    except Exception as exc:
        logger.warning("intelligence_optimizer: insight write failed (non-fatal): %s", exc)

    logger.info(
        "intelligence_optimizer complete: utilization_updated=%d, ab_total=%d, premium=%s",
        util["updated"],
        ab["total"],
        premium_pct,
    )
    return results
