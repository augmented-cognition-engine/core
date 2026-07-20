"""Capability priority ranking for test generation.

Drives ace_generate_tests(mode='priority'): which capability should we write
tests for first?

Score = (1 - function_pct) × importance × (1 + decline_penalty)
"""

from __future__ import annotations

import logging

from core.engine.core.db import parse_rows, pool

logger = logging.getLogger(__name__)


async def rank_capabilities(product_id: str, limit: int = 10) -> list[dict]:
    """Return capabilities sorted by 'tests-most-needed' score.

    Capabilities with no coverage data rank higher than those with measured low coverage
    only if they have no functions tracked at all (genuinely unmeasured).
    """
    try:
        async with pool.connection() as db:
            rows = parse_rows(
                await db.query(
                    """SELECT cap.slug AS slug, cap.name AS name, cap.priority AS priority,
                    cc.function_pct AS function_pct, cc.untested_functions_count AS untested
                FROM capability AS cap
                LEFT JOIN capability_coverage AS cc ON cc.capability = cap.id
                WHERE cap.product = <record>$product
                """,
                    {"product": product_id},
                )
            )
    except Exception as exc:
        logger.debug("rank_capabilities: DB query failed: %s", exc)
        return []

    ranked: list[dict] = []
    for r in rows:
        pct = float(r.get("function_pct") or 0.0)
        priority = float(r.get("priority") or 0.5)
        untested = int(r.get("untested") or 0)

        if pct == 0.0 and untested == 0:
            score = priority * 0.7  # unmeasured — treat as moderately high priority
        else:
            score = (1.0 - pct) * priority + min(untested, 20) * 0.02

        ranked.append(
            {
                "slug": r.get("slug", ""),
                "name": r.get("name") or r.get("slug", ""),
                "function_pct": pct,
                "untested_count": untested,
                "score": round(score, 3),
            }
        )

    ranked.sort(key=lambda x: x["score"], reverse=True)
    return ranked[:limit]
