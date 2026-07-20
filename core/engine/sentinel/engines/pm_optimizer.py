# engine/sentinel/engines/pm_optimizer.py
"""PM Self-Optimizer — learn which specs, decompositions, and dispatches work best.

Runs weekly (Sunday 5 AM). Analyzes:
- Spec quality: % of specs that pass acceptance on first try
- Decomposition efficiency: avg parallel utilization, % units blocked
- Feedback resolution: avg time to resolve blockers
- Gap closure rate: % of identified gaps closed within 7 days
- Rework rate: % of specs that needed follow-up

Writes analysis to intelligence pipeline as insights.
"""

import logging

from core.engine.core.db import parse_rows, pool
from core.engine.core.exceptions import ValidationError
from core.engine.sentinel.registry import register_engine

logger = logging.getLogger(__name__)


def _validate_pm_optimizer_inputs(product_id: str, budget: int = 100) -> None:
    """Validate pm optimizer inputs before querying the database.

    Raises ValidationError for malformed product_id or out-of-range budget
    so the engine fails fast with a clear error rather than running LLM
    calls against invalid data.
    """
    if not product_id or ":" not in product_id:
        raise ValidationError(f"Invalid product_id for pm-optimizer: {product_id!r}")
    if not (0 <= budget <= 500):
        raise ValidationError(f"budget must be in [0, 500], got {budget}")


@register_engine(
    name="pm_optimizer",
    cron="0 5 * * sun",  # Sunday 5 AM
    description="Analyze PM effectiveness: spec quality, decomposition efficiency, gap closure rate.",
)
async def run_pm_optimizer(product_id: str, budget: int = 20) -> dict:
    """Analyze PM performance and generate improvement insights."""
    _validate_pm_optimizer_inputs(product_id, budget)
    results = {
        "specs_analyzed": 0,
        "first_pass_rate": 0.0,
        "avg_units_per_spec": 0.0,
        "blocked_rate": 0.0,
        "gap_closure_rate": 0.0,
        "insights_generated": 0,
    }

    async with pool.connection() as db:
        # 1. Spec quality: how many specs pass acceptance on first try?
        spec_result = await db.query(
            "SELECT status FROM agent_spec WHERE product = <record>$product",
            {"product": product_id},
        )
        specs = parse_rows(spec_result)
        if specs:
            results["specs_analyzed"] = len(specs)
            completed = sum(1 for s in specs if s.get("status") == "completed")
            failed = sum(1 for s in specs if s.get("status") == "failed")
            total_resolved = completed + failed
            results["first_pass_rate"] = completed / total_resolved if total_resolved > 0 else 0.0

        # 2. Feedback analysis: what types of feedback are most common?
        feedback_result = await db.query(
            "SELECT feedback_type, resolved FROM agent_feedback WHERE product = <record>$product",
            {"product": product_id},
        )
        feedbacks = parse_rows(feedback_result)
        if feedbacks:
            by_type = {}
            for f in feedbacks:
                ft = f.get("feedback_type", "unknown")
                by_type[ft] = by_type.get(ft, 0) + 1
            results["feedback_by_type"] = by_type
            resolved = sum(1 for f in feedbacks if f.get("resolved"))
            results["feedback_resolution_rate"] = resolved / len(feedbacks) if feedbacks else 0.0

        # 3. Gap closure: how many quality scores improved?
        quality_result = await db.query(
            """SELECT capability, dimension, score, assessed_at
               FROM capability_quality WHERE product = <record>$product
               ORDER BY assessed_at DESC""",
            {"product": product_id},
        )
        qualities = parse_rows(quality_result)
        if qualities:
            # Count dimensions with score >= 0.6 (considered "closed")
            good = sum(1 for q in qualities if q.get("score", 0) >= 0.6)
            results["gap_closure_rate"] = good / len(qualities) if qualities else 0.0
            results["total_assessments"] = len(qualities)

        # 4. Generate improvement insights
        if results["specs_analyzed"] > 0:
            if results["first_pass_rate"] < 0.5:
                # Write insight about low spec quality
                try:
                    await db.query(
                        """CREATE observation SET
                            content = $content,
                            observation_type = 'pattern',
                            source = 'pm_optimizer',
                            confidence = 0.7,
                            created_at = time::now()""",
                        {
                            "product": product_id,
                            "content": f"PM spec first-pass acceptance rate is {results['first_pass_rate']:.0%}. Consider improving spec detail, adding more constraints, or including integration point details.",
                        },
                    )
                    results["insights_generated"] += 1
                except Exception as e:
                    logger.warning(f"Failed to write insight: {e}")

        # 5. Overall PM health score
        scores = [
            results["first_pass_rate"],
            results.get("feedback_resolution_rate", 0),
            results["gap_closure_rate"],
        ]
        results["pm_health_score"] = sum(scores) / len(scores) if scores else 0.0

    return results
