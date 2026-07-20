"""Sentinel engine: Idea Incubator.

Runs overnight at 2:45 AM. Queries all ideas in 'open', 'incubating',
'captured', 'qualifying', or 'proposed' status, runs incubate_idea()
for each (max 20 per org per run), and posts research results to each
idea's conversation thread.
"""

from __future__ import annotations

import logging

from core.engine.core.exceptions import ValidationError
from core.engine.sentinel.registry import register_engine

logger = logging.getLogger(__name__)

MAX_IDEAS_PER_RUN = 20


def _validate_idea_incubator_inputs(product_id: str, budget: int = 100) -> None:
    """Validate idea incubator inputs before querying the database.

    Raises ValidationError for malformed product_id or out-of-range budget
    so the engine fails fast with a clear error rather than running LLM
    calls against invalid data.
    """
    if not product_id or ":" not in product_id:
        raise ValidationError(f"Invalid product_id for idea-incubator: {product_id!r}")
    if not (0 <= budget <= 500):
        raise ValidationError(f"budget must be in [0, 500], got {budget}")


@register_engine("idea_incubator", "45 2 * * *", "Incubate ideas overnight — research, brief, connections")
async def run_idea_incubator(product_id: str, budget: int = 20) -> dict:
    """Incubate all open/unprocessed ideas for the given org."""
    _validate_idea_incubator_inputs(product_id, budget)
    from core.engine.core.db import pool
    from core.engine.ideas.incubate import incubate_idea

    incubated = 0
    failed = 0

    async with pool.connection() as db:
        result = await db.query(
            """
            SELECT * FROM idea
            WHERE product = <record>$product
                AND (status = 'open' OR status = 'incubating' OR status = 'captured'
                     OR status = 'qualifying' OR status = 'proposed')
            ORDER BY created_at ASC
            LIMIT $limit
            """,
            {"product": product_id, "limit": min(budget, MAX_IDEAS_PER_RUN)},
        )
        rows = result[0] if result and isinstance(result[0], list) else (result or [])

    for idea in rows:
        try:
            await incubate_idea(idea, product_id)
            incubated += 1
        except Exception as exc:
            logger.warning("Failed to incubate idea %s: %s", idea.get("id"), exc)
            failed += 1

    logger.info("Idea incubator: incubated=%d, failed=%d", incubated, failed)
    return {"incubated": incubated, "failed": failed, "total": len(rows)}
