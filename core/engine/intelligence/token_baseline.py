# engine/intelligence/token_baseline.py
"""Token baseline estimation from experiment data.

Baselines are populated by the domain research engine after experiments.
Fallback chain: discipline+complexity → discipline (any complexity) → None.
"""

from __future__ import annotations

import logging

from core.engine.core.db import parse_rows, pool

logger = logging.getLogger(__name__)


def _compute_savings_pct(control: int, variant: int) -> float:
    """Compute savings percentage: 1 - (variant / control). Guards against zero."""
    if control <= 0:
        return 0.0
    return max(0.0, 1.0 - (variant / control))


async def _query_baseline(discipline: str, complexity: str | None, product_id: str) -> list[dict]:
    """Query token_baseline table with optional complexity filter."""
    if complexity:
        query = """
            SELECT avg_tokens_control, avg_tokens_variant, discipline, complexity
            FROM token_baseline
            WHERE product = <record>$product
              AND discipline = <string>$discipline
              AND complexity = <string>$complexity
            LIMIT 1
        """
        params = {"product": product_id, "discipline": discipline, "complexity": complexity}
    else:
        query = """
            SELECT math::mean(avg_tokens_control) AS avg_tokens_control
            FROM token_baseline
            WHERE product = <record>$product
              AND discipline = <string>$discipline
            GROUP ALL
        """
        params = {"product": product_id, "discipline": discipline}
    async with pool.connection() as db:
        result = await db.query(query, params)
    return parse_rows(result)


async def estimate_baseline(
    discipline: str,
    complexity: str,
    product_id: str,
) -> int | None:
    """Estimate tokens a task would cost WITHOUT intelligence.

    Fallback chain: discipline+complexity → discipline (any complexity) → None.
    """
    import math as _math

    rows = await _query_baseline(discipline, complexity, product_id)
    val = rows[0].get("avg_tokens_control") if rows else None
    if val is not None and not (isinstance(val, float) and _math.isnan(val)):
        return int(val)

    rows = await _query_baseline(discipline, None, product_id)
    val = rows[0].get("avg_tokens_control") if rows else None
    if val is not None and not (isinstance(val, float) and _math.isnan(val)):
        return int(val)

    return None


async def update_baseline(
    discipline: str,
    complexity: str,
    product_id: str,
    control_tokens: int,
    variant_tokens: int,
) -> None:
    """Update baseline with new experiment data using running average."""
    savings_pct = _compute_savings_pct(control_tokens, variant_tokens)

    async with pool.connection() as db:
        await db.query(
            """
            UPSERT token_baseline
            SET
                discipline = <string>$discipline,
                complexity = <string>$complexity,
                avg_tokens_control = IF avg_tokens_control THEN
                    math::floor((avg_tokens_control * sample_count + $control) / (sample_count + 1))
                ELSE $control END,
                avg_tokens_variant = IF avg_tokens_variant THEN
                    math::floor((avg_tokens_variant * sample_count + $variant) / (sample_count + 1))
                ELSE $variant END,
                sample_count = IF sample_count THEN sample_count + 1 ELSE 1 END,
                savings_pct = $savings_pct,
                updated_at = time::now()
            WHERE product = <record>$product
              AND discipline = <string>$discipline
              AND complexity = <string>$complexity
            """,
            {
                "product": product_id,
                "discipline": discipline,
                "complexity": complexity,
                "control": control_tokens,
                "variant": variant_tokens,
                "savings_pct": savings_pct,
            },
        )
