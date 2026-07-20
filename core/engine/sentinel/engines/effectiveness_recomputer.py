"""Sentinel engine: Effectiveness Recomputer.

Runs twice daily at 06:30 and 18:30. Recomputes effectiveness scores per
(pillar, discipline) by reading outcome_observations over the 30-day rolling
window and persisting new rows to the effectiveness_score table.

The 30-minute offset from the outcome_sweeper (which runs at 0 */4 * * *)
ensures that window-expired 'open → ignored' transitions land before the
recomputer reads them, so ignored observations are correctly counted.
"""

from __future__ import annotations

import logging

from core.engine.sentinel.registry import register_engine

logger = logging.getLogger(__name__)


@register_engine(
    "effectiveness_recomputer",
    "30 6,18 * * *",
    "Recompute effectiveness scores per (pillar, discipline) twice daily",
)
async def run_effectiveness_recomputer(product_id: str = "product:platform") -> dict:
    """Compute and persist effectiveness scores for the product."""
    from core.engine.learning.effectiveness import compute_effectiveness_scores, persist_scores

    scores = await compute_effectiveness_scores(product_id)
    await persist_scores(scores)
    logger.info(
        "effectiveness_recomputer: %d score(s) written for %s",
        len(scores),
        product_id,
    )
    return {"scores_computed": len(scores), "product_id": product_id}
