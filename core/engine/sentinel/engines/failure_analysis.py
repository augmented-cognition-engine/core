# engine/sentinel/engines/failure_analysis.py
"""Failure analysis engine — analyze today's failures, write corrections.

Runs nightly at 3:00 AM. Finds rejected/low-scored tasks from the past 24h,
uses LLM to diagnose root cause, writes correction insights, and queues
research for knowledge gaps it cannot self-correct.

Root cause taxonomy:
  - knowledge_gap: Didn't know a relevant fact
  - wrong_assumption: Believed something incorrect
  - framework_mismatch: Used wrong approach
  - other: Unclear

Spec: docs/superpowers/specs/2026-03-21-phase3b-overnight-engines.md
"""

from __future__ import annotations

from core.engine.core.db import parse_rows, pool
from core.engine.core.exceptions import ValidationError
from core.engine.core.llm import llm
from core.engine.intelligence.calibration import effective_confidence
from core.engine.sentinel.engines import queue_research, write_engine_insight
from core.engine.sentinel.registry import register_engine

SOURCE_DOMAIN = "sentinel.failure-analysis"

ANALYSIS_PROMPT = """You are an expert failure analyst for an AI intelligence system.

A task was completed but received negative feedback. Analyze the failure.

## Task
Description: {description}
Discipline: {discipline}
Output produced: {output}
Feedback: {feedback_human} (score: {feedback_score}, self-assessment: {self_assessment})
Intelligence loaded: {intelligence_loaded}

## Instructions
Diagnose the root cause. Classify into exactly one failure_type:
- "knowledge_gap": The system didn't know a relevant fact
- "wrong_assumption": The system believed something incorrect
- "framework_mismatch": The system used the wrong approach/methodology
- "other": Unclear root cause

Write a correction that would prevent this failure in the future.
If the failure reveals a knowledge gap that needs deeper research, set should_research=true and provide a research_query.

Return JSON:
{{
  "failure_type": "knowledge_gap|wrong_assumption|framework_mismatch|other",
  "root_cause": "Brief explanation of what went wrong",
  "correction": "The corrected knowledge/approach to use in the future",
  "confidence": 0.0-1.0,
  "should_research": true|false,
  "research_query": "optional — only if should_research is true"
}}"""


def _build_correction_tags(failure_type: str) -> list[str]:
    """Build tags list for a correction insight based on failure type."""
    tags = ["auto-correction", failure_type]
    if failure_type == "framework_mismatch":
        tags.append("framework-issue")
    return tags


def _validate_failure_analysis_inputs(product_id: str, budget: int = 100) -> None:
    """Validate failure analysis inputs before querying the database.

    Raises ValidationError for malformed product_id or out-of-range budget
    so the engine fails fast with a clear error rather than running LLM
    calls against invalid data.
    """
    if not product_id or ":" not in product_id:
        raise ValidationError(f"Invalid product_id for failure-analysis: {product_id!r}")
    if not (0 <= budget <= 500):
        raise ValidationError(f"budget must be in [0, 500], got {budget}")


@register_engine(
    name="failure_analysis",
    cron="0 3 * * *",
    description="Analyze today's failures, write corrections, queue research",
)
async def run_failure_analysis(product_id: str, budget: int = 20) -> dict:
    """Analyze today's rejected/low-scored tasks and write corrections.

    Args:
        product_id: Organization to analyze failures for.
        budget: Maximum LLM calls per run (default 20).

    Returns:
        Dict with counts: failures_analyzed, corrections_written, research_queued.
    """
    failures_analyzed = 0
    corrections_written = 0
    research_queued = 0
    llm_calls = 0

    _validate_failure_analysis_inputs(product_id, budget)
    async with pool.connection() as db:
        result = await db.query(
            """
            SELECT *
            FROM task
            WHERE product = <record>$product
                AND completed_at > time::now() - 1d
                AND (
                    feedback_human = 'rejected'
                    OR feedback_score < 0.5
                    OR (calibrated_assessment ?? self_assessment) < 0.4
                )
            ORDER BY feedback_score ASC
            LIMIT $limit
            """,
            {"product": product_id, "limit": budget},
        )

        rows = parse_rows(result)
        if not rows:
            return {
                "failures_analyzed": 0,
                "corrections_written": 0,
                "research_queued": 0,
            }

        for task in rows:
            if llm_calls >= budget:
                break

            task_id = str(task.get("id", ""))
            description = task.get("description", "")
            discipline = task.get("discipline", task.get("domain_path", "unknown"))
            output = task.get("output", "")
            feedback_human = task.get("feedback_human", "unknown")
            feedback_score = task.get("feedback_score", 0.0)
            # The confidence the system actually trusts: calibrated when present, else raw.
            self_assessment = effective_confidence(task)
            intelligence_loaded = task.get("intelligence_loaded", [])

            prompt = ANALYSIS_PROMPT.format(
                description=description,
                discipline=discipline,
                output=output[:2000],
                feedback_human=feedback_human,
                feedback_score=feedback_score,
                self_assessment=self_assessment,
                intelligence_loaded=str(intelligence_loaded)[:500],
            )

            try:
                analysis = await llm.complete_json(prompt)
            except Exception:
                continue

            llm_calls += 1
            failures_analyzed += 1

            failure_type = analysis.get("failure_type", "other")
            correction_text = analysis.get("correction", "")
            confidence = analysis.get("confidence", 0.5)
            tags = _build_correction_tags(failure_type)

            insight_id = await write_engine_insight(
                db,
                product_id=product_id,
                content=correction_text,
                insight_type="correction",
                tier="subdomain",
                discipline=discipline,
                source_domain=SOURCE_DOMAIN,
                confidence=confidence,
                tags=tags,
                source_task=task_id,
            )

            if insight_id:
                corrections_written += 1

            should_research = analysis.get("should_research", False)
            if should_research:
                research_query = analysis.get(
                    "research_query",
                    f"Research needed for: {analysis.get('root_cause', description)}",
                )
                rq_id = await queue_research(
                    db,
                    product_id=product_id,
                    query=research_query,
                    context=f"Failure analysis of {task_id}: {analysis.get('root_cause', '')}",
                    priority="high",
                    source="failure-analysis",
                    related_task=task_id,
                )
                if rq_id:
                    research_queued += 1

    return {
        "failures_analyzed": failures_analyzed,
        "corrections_written": corrections_written,
        "research_queued": research_queued,
    }
