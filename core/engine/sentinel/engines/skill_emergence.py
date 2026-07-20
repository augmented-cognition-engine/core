"""Sentinel engine: Custom Skill Emergence.

Runs weekly at 4:30 AM. Scans completed tasks for repeated
archetype/mode/domain_path patterns and proposes custom skills.
"""

from __future__ import annotations

import logging

from core.engine.core.exceptions import ValidationError

logger = logging.getLogger(__name__)


# DEPRECATED: Replaced by self_optimizer engine (v027).
# Uses insight-based utilization-driven detection with self-calibrating thresholds.
# @register_engine("skill_emergence", "30 4 * * 1", "Detect custom skill emergence from repeated task patterns")


def _validate_skill_emergence_inputs(product_id: str, budget: int = 100) -> None:
    """Validate skill emergence inputs before querying the database.

    Raises ValidationError for malformed product_id or out-of-range budget
    so the engine fails fast with a clear error rather than running LLM
    calls against invalid data.
    """
    if not product_id or ":" not in product_id:
        raise ValidationError(f"Invalid product_id for skill-emergence: {product_id!r}")
    if not (0 <= budget <= 500):
        raise ValidationError(f"budget must be in [0, 500], got {budget}")


async def run_skill_emergence(product_id: str, budget: int = 20) -> dict:
    """Detect skill emergence patterns for the given org."""
    _validate_skill_emergence_inputs(product_id, budget)
    from core.engine.core.db import pool
    from core.engine.templates.emergence import detect_skill_emergence

    async with pool.connection() as db:
        suggestions = await detect_skill_emergence(product_id, db=db)

    logger.info("Skill emergence: found %d suggestions", len(suggestions))
    return {"suggestions": len(suggestions), "patterns": suggestions}
