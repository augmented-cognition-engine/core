# engine/sentinel/engines/overthinking_observer.py
"""overthinking_observer — daily aggregator of cost-aware composition signals.

Aggregates composition_signal rows where overthinking_flag=true over a 14-day
window, grouped by (discipline, model_used). When ≥10 events exist for a
(discipline, model) pair, emits an ace_insight row recommending model
reconsideration.

Source: OckBench "overthinking tax" framing (https://arxiv.org/abs/2511.05722) —
smaller models can cost more in total when they emit longer chains than the
default model would.
"""

from __future__ import annotations

import logging

from core.engine.core.db import parse_rows, pool
from core.engine.sentinel.registry import register_engine

logger = logging.getLogger(__name__)

INSIGHT_THRESHOLD = 10  # min events in window before emitting an insight
WINDOW_DAYS = 14


@register_engine(
    name="overthinking_observer",
    cron="0 5 * * *",  # 5am daily
    description="Aggregate overthinking-flagged composition signals; emit insights when (discipline, model) pairs exceed threshold.",
)
async def run_overthinking_observer(product_id: str) -> dict:
    """Aggregate flagged signals and emit ace_insight rows for outliers."""
    async with pool.connection() as db:
        agg = await db.query(
            f"""
            SELECT discipline, model_used,
                   count() AS n,
                   math::sum(cost_usd) AS total_cost,
                   math::sum(estimated_alternative_cost_usd) AS total_alt_cost
            FROM composition_signal
            WHERE product = <record>$product
              AND overthinking_flag = true
              AND created_at > time::now() - {WINDOW_DAYS}d
            GROUP BY discipline, model_used
            """,
            {"product": product_id},
        )
        # parse_rows handles v3 flat list and v2 [[...]] nested list.
        # SurrealDB also returns [{result: [...]}] envelopes in some clients;
        # unwrap if the first row looks like an envelope rather than data.
        _raw = parse_rows(agg)
        if _raw and isinstance(_raw[0], dict) and "result" in _raw[0] and "discipline" not in _raw[0]:
            rows = parse_rows(_raw[0]["result"])
        else:
            rows = _raw

        emitted = 0
        for row in rows:
            n = int(row.get("n", 0) or 0)
            if n < INSIGHT_THRESHOLD:
                continue
            discipline = row.get("discipline") or "unknown"
            model_used = row.get("model_used") or "unknown"
            total_cost = float(row.get("total_cost", 0.0) or 0.0)
            total_alt = float(row.get("total_alt_cost", 0.0) or 0.0)
            content = (
                f"discipline '{discipline}' on model '{model_used}' produced {n} overthinking events "
                f"in the last {WINDOW_DAYS} days — total ${total_cost:.2f} vs ${total_alt:.2f} on the "
                f"alternative model. Consider routing this discipline to the default tier."
            )
            await db.query(
                """
                CREATE ace_insight SET
                    product = <record>$product,
                    source = 'overthinking_observer',
                    content = $content,
                    tags = ['cost', 'overthinking', $discipline, $model_used],
                    confidence = 0.75,
                    created_at = time::now()
                """,
                {
                    "product": product_id,
                    "content": content,
                    "discipline": discipline,
                    "model_used": model_used,
                },
            )
            emitted += 1
            logger.info(
                "overthinking_observer emitted insight: %s/%s n=%d",
                discipline,
                model_used,
                n,
            )

    return {"status": "completed", "insights_emitted": emitted, "groups_examined": len(rows)}
