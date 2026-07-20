"""Sentinel engine: Template Detector.

Runs weekly at 4:00 AM. Scans completed initiatives for structural
similarity clusters and proposes templates.
"""

from __future__ import annotations

import logging

from core.engine.core.exceptions import ValidationError
from core.engine.sentinel.registry import register_engine

logger = logging.getLogger(__name__)


def _validate_template_detector_inputs(product_id: str, budget: int = 100) -> None:
    """Validate template detector inputs before querying the database.

    Raises ValidationError for malformed product_id or out-of-range budget
    so the engine fails fast with a clear error rather than running LLM
    calls against invalid data.
    """
    if not product_id or ":" not in product_id:
        raise ValidationError(f"Invalid product_id for template-detector: {product_id!r}")
    if not (0 <= budget <= 500):
        raise ValidationError(f"budget must be in [0, 500], got {budget}")


@register_engine("template_detector", "0 4 * * mon", "Detect template candidates from completed initiatives")
async def run_template_detector(product_id: str, budget: int = 20) -> dict:
    """Detect template candidates for the given org."""
    _validate_template_detector_inputs(product_id, budget)
    from core.engine.core.db import pool
    from core.engine.templates.suggest import detect_template_candidates

    async with pool.connection() as db:
        drafts = await detect_template_candidates(product_id, db=db)

    logger.info("Template detector: found %d candidates", len(drafts))
    return {"candidates": len(drafts), "drafts": drafts}
