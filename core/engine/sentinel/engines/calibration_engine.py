"""Sentinel engine: Calibration — builds per-domain confidence calibration curves.

Runs weekly (Sunday 5 AM). Queries tasks with both self_assessment and
feedback_human from the last 90 days, computes calibration curves,
and UPSERTs the calibration table.
"""

from __future__ import annotations

import logging

from core.engine.core.db import pool
from core.engine.core.exceptions import ValidationError
from core.engine.intelligence.calibration import bucket_tasks, compute_calibration
from core.engine.sentinel.registry import register_engine

logger = logging.getLogger(__name__)


def _validate_calibration_inputs(product_id: str, budget: int = 100) -> None:
    """Validate calibration engine inputs before issuing DB queries.

    Raises ValidationError for malformed product_id or out-of-range budget
    to prevent the weekly calibration job from running against invalid data.
    """
    if not product_id or ":" not in product_id:
        raise ValidationError(f"Invalid product_id for calibration: {product_id!r}")
    if not (1 <= budget <= 500):
        raise ValidationError(f"budget must be in [1, 500], got {budget}")


@register_engine(
    name="calibration",
    cron="0 5 * * sun",
    description="Weekly calibration curves — compare predicted confidence vs actual outcomes (Sunday 5am)",
)
async def run_calibration(product_id: str, budget: int = 20) -> dict:
    """Build calibration curves from task history."""
    _validate_calibration_inputs(product_id, budget)
    async with pool.connection() as db:
        # Query tasks with a predicted confidence AND an actual outcome — either human feedback OR a
        # cross-model grader_score (keystone #1 payoff: grader_score un-starves calibration when no
        # human judged the task). ORDER BY field (created_at) is in SELECT per SurrealDB v3.
        result = await db.query(
            """
            SELECT discipline, self_assessment, feedback_human, grader_score, created_at
            FROM task
            WHERE product = <record>$product
              AND self_assessment IS NOT NONE
              AND (feedback_human IS NOT NONE OR grader_score IS NOT NONE)
              AND created_at > time::now() - 90d
            ORDER BY created_at DESC
            LIMIT 1000
            """,
            {"product": product_id},
        )
        rows = result[0] if result and isinstance(result[0], list) else (result or [])

        if not rows:
            return {"domains_calibrated": 0, "reason": "no_tasks_with_assessment_and_feedback"}

        # Compute calibration
        buckets = bucket_tasks(rows)

        # Provenance: how much of the signal is human-validated vs cross-model grader (honesty —
        # grader-only curves must never be presented as if humans validated them).
        all_samples = [s for domain in buckets.values() for samples in domain.values() for s in samples]
        human_samples = sum(1 for s in all_samples if s.get("source") == "human")
        grader_samples = sum(1 for s in all_samples if s.get("source") == "grader")

        calibration_data = compute_calibration(buckets)

        if not calibration_data:
            return {
                "domains_calibrated": 0,
                "reason": "insufficient_samples_per_bucket",
                "human_samples": human_samples,
                "grader_samples": grader_samples,
            }

        # UPSERT calibration table
        await db.query(
            """
            UPSERT calibration SET
                product = <record>$product,
                data = $data,
                updated_at = time::now()
            WHERE product = <record>$product
            """,
            {"product": product_id, "data": calibration_data},
        )

        # Compute summary for briefing
        worst_domain = None
        best_domain = None
        worst_miscal = 0.0
        best_miscal = 1.0

        for domain, domain_buckets in calibration_data.items():
            for bucket_data in domain_buckets.values():
                miscal = abs(bucket_data.get("miscalibration", 0.0))
                if miscal > worst_miscal:
                    worst_miscal = miscal
                    worst_domain = domain
                if miscal < best_miscal:
                    best_miscal = miscal
                    best_domain = domain

    logger.info("Calibration: %d domains calibrated", len(calibration_data))

    return {
        "domains_calibrated": len(calibration_data),
        "worst_domain": worst_domain,
        "worst_miscalibration": round(worst_miscal, 3),
        "best_domain": best_domain,
        "best_miscalibration": round(best_miscal, 3),
        "human_samples": human_samples,
        "grader_samples": grader_samples,
    }
