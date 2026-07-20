"""Sentinel engine: Task Grading — cross-model grade recent ungraded task outputs to un-starve calibration.

Runs Saturday 4am (before Sunday-5am calibration). For each recent task that has an output and a
predicted confidence but NO human feedback and NO grade yet, grade the output with the cross-model peer
(keystone #1) against a generic rubric and write grader_score + grader_source. The calibration engine
then consumes grader_score as the "actual" outcome (human feedback still wins). OFF THE HOT PATH — this
adds zero latency to live orchestration.

Gated on a configured cross-model peer: a Claude-grades-Claude score is same-family and does NOT
un-starve calibration (it would reintroduce the inflation keystone #1 removed), so the engine no-ops
when settings.cross_model_grader_host is unset.
"""

from __future__ import annotations

import logging

from core.engine.core.config import settings
from core.engine.core.db import pool
from core.engine.core.exceptions import ValidationError
from core.engine.sentinel.registry import register_engine
from core.engine.verification.grader import make_grader

logger = logging.getLogger(__name__)

# Generic holistic rubric — arbitrary tasks carry no spec. This is a CALIBRATION signal (relative
# miscalibration trends in aggregate), not a quality gate, so an unbiased-but-noisy generic grade is fine.
_GENERIC_RUBRIC = [
    "The output directly addresses the stated task",
    "The output is correct and free of obvious errors",
    "The output is complete — no key part of the ask is missing",
    "The output is clear and usable",
]


def _validate_inputs(product_id: str, budget: int) -> None:
    """Validate inputs before issuing DB queries / LLM calls."""
    if not product_id or ":" not in product_id:
        raise ValidationError(f"Invalid product_id for task grading: {product_id!r}")
    if not (1 <= budget <= 200):
        raise ValidationError(f"budget must be in [1, 200], got {budget}")


@register_engine(
    name="task_grading",
    cron="0 4 * * sat",  # Saturday 4am — BEFORE Sunday-5am calibration so fresh grades feed the curve
    description="Cross-model grade recent ungraded task outputs → un-starve calibration (Sat 4am)",
)
async def run_task_grading(product_id: str, budget: int = 25) -> dict:
    """Grade recent ungraded task outputs with the cross-model peer; write grader_score + grader_source.

    Returns a summary dict. Non-fatal per task: one bad grade is logged and skipped, never aborts the batch.
    """
    _validate_inputs(product_id, budget)

    # Gate: only a genuinely cross-family grade un-starves calibration. No peer → no-op (behavior
    # identical to before this engine existed).
    if not getattr(settings, "cross_model_grader_host", None):
        return {"graded": 0, "reason": "no_cross_model_peer"}

    # FAIL-CLOSED grader: a down peer must RAISE (→ skip the task), never silently fall back to a
    # same-family Claude grade that would be mislabeled cross_model and re-poison calibration.
    grader = make_grader(allow_fallback=False)
    peer_model = getattr(settings, "cross_model_grader_model", "cross_model")
    source = f"cross_model:{peer_model}"

    graded = 0
    async with pool.connection() as db:
        # Recent tasks with a predicted confidence + an output, but no human verdict and no grade yet.
        # ORDER BY field (created_at) is in SELECT per SurrealDB v3; budget is a validated int (inlined,
        # like calibration_engine's literal LIMIT, to avoid parameterized-LIMIT pitfalls).
        result = await db.query(
            f"""
            SELECT id, description, output, created_at FROM task
            WHERE product = <record>$product
              AND output IS NOT NONE
              AND self_assessment IS NOT NONE
              AND feedback_human IS NONE
              AND grader_score IS NONE
              AND created_at > time::now() - 90d
            ORDER BY created_at DESC
            LIMIT {budget}
            """,
            {"product": product_id},
        )
        rows = result[0] if result and isinstance(result[0], list) else (result or [])

        if not rows:
            return {"graded": 0, "reason": "no_ungraded_tasks"}

        for row in rows:
            tid = row.get("id")
            description = row.get("description") or ""
            output = row.get("output") or ""
            if not tid or not description or not output:
                continue
            try:
                grade = await grader.evaluate(task=description, rubric=_GENERIC_RUBRIC, artifact=output)
                # evaluate() never raises — it returns {"score": 0.0, "error": ...} on failure (incl. a
                # fail-closed peer outage). Skip those: a 0.0-on-error is a sentinel, not a real "task
                # failed" outcome, and persisting it would manufacture overconfidence in the curve.
                score = grade.get("score")
                if grade.get("error") or not isinstance(score, (int, float)) or isinstance(score, bool):
                    logger.warning("task_grading: skipping %s — grade unavailable (%s)", tid, grade.get("error"))
                    continue
                # Mirror the executor's canonical UPDATE-by-record pattern (executor.py:808).
                await db.query(
                    "UPDATE <record>$tid SET grader_score = $score, grader_source = $source",
                    {"tid": str(tid), "score": float(score), "source": source},
                )
                graded += 1
            except Exception as exc:
                logger.warning("task_grading: failed to grade %s (non-fatal): %s", tid, exc)

    logger.info("task_grading: graded %d tasks (source=%s)", graded, source)
    return {"graded": graded, "source": source}
