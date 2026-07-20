# engine/review/capture.py
"""Auto-capture review decisions into ACE's decision graph.

Every review run generates decisions: discipline selection, judge verdicts,
quality gate results, and autofix outcomes. These are captured as observations
and decisions in the graph for future intelligence.
"""

from __future__ import annotations

import logging

from core.engine.core.db import pool

logger = logging.getLogger(__name__)


async def capture_review_decisions(
    pr_title: str,
    disciplines: list[str],
    synthesis_summary: str,
    findings_count: int,
    findings_before_judge: int,
    findings_after_judge: int,
    pass_quality_gate: bool,
    gate_failures: list[str],
    discipline_scores: dict[str, float],
    autofix_result: dict | None = None,
    source: str = "local",
    product_id: str = "product:platform",
) -> None:
    """Fire-and-forget capture of review decisions into the graph.

    Captures as observations (fast, no LLM) that the synthesizer
    will promote to insights overnight.
    """
    try:
        async with pool.connection() as db:
            # 1. Discipline selection decision
            await db.query(
                """
                CREATE observation SET
                    product = <record>$product,
                    content = $content,
                    observation_type = 'decision',
                    confidence = 0.9,
                    domain_hint = 'code_conventions',
                    discipline_hint = 'architecture',
                    synthesized = false,
                    created_at = time::now()
                """,
                {
                    "product": product_id,
                    "content": f"Review of '{pr_title}' selected disciplines: {', '.join(disciplines)}. Source: {source}.",
                },
            )

            # 2. Judge synthesis decision
            if findings_before_judge > 0:
                filtered = findings_before_judge - findings_after_judge
                await db.query(
                    """
                    CREATE observation SET
                        product = <record>$product,
                        content = $content,
                        observation_type = 'pattern',
                        confidence = 0.85,
                        domain_hint = 'code_conventions',
                        discipline_hint = 'architecture',
                        synthesized = false,
                        created_at = time::now()
                    """,
                    {
                        "product": product_id,
                        "content": (
                            f"Review judge: {findings_before_judge} raw findings → "
                            f"{findings_after_judge} after synthesis ({filtered} merged/discarded). "
                            f"{synthesis_summary}"
                        ),
                    },
                )

            # 3. Quality gate verdict
            gate_status = "PASSED" if pass_quality_gate else "FAILED"
            gate_detail = f"Failures: {', '.join(gate_failures)}" if gate_failures else "All checks passed"
            scores_text = (
                ", ".join(f"{d}={s:.0%}" for d, s in sorted(discipline_scores.items()))
                if discipline_scores
                else "no scores"
            )

            await db.query(
                """
                CREATE observation SET
                    product = <record>$product,
                    content = $content,
                    observation_type = 'decision',
                    confidence = 0.95,
                    domain_hint = 'testing',
                    discipline_hint = 'testing',
                    synthesized = false,
                    created_at = time::now()
                """,
                {
                    "product": product_id,
                    "content": (
                        f"Quality gate {gate_status} for '{pr_title}': "
                        f"{findings_count} findings. {gate_detail}. Scores: {scores_text}."
                    ),
                },
            )

            # 4. Autofix decision
            if autofix_result is not None:
                fix_type = autofix_result.get("type", "unknown")
                files_fixed = autofix_result.get("files_fixed", 0)
                await db.query(
                    """
                    CREATE observation SET
                        product = <record>$product,
                        content = $content,
                        observation_type = 'decision',
                        confidence = 0.9,
                        domain_hint = 'devops',
                        discipline_hint = 'devops',
                        synthesized = false,
                        created_at = time::now()
                    """,
                    {
                        "product": product_id,
                        "content": f"Autofix for '{pr_title}': {files_fixed} files fixed via {fix_type}.",
                    },
                )

    except Exception as exc:
        logger.debug("Review decision capture failed (best-effort): %s", exc)
