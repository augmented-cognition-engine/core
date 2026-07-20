# engine/sentinel/engines/perspective_gaps.py
"""Perspective gap detector engine — surface underused perspectives in briefing.

Runs daily at 5:00 AM. Compares perspectives used in tasks over the last 7 days
against perspectives available in specialties. For each unused perspective, uses
the budget LLM to generate 2-3 specific questions framed from that angle, so the
briefing layer can surface them proactively.

The task.perspective field was introduced in v026. Tasks created before that
migration may have perspective=None — those are filtered out gracefully.

Spec: docs/superpowers/specs/2026-03-25-part-a-perspective-and-dual-graphs.md
"""

from __future__ import annotations

from core.engine.core.config import settings
from core.engine.core.db import parse_rows, pool
from core.engine.core.exceptions import ValidationError
from core.engine.core.llm import llm
from core.engine.sentinel.registry import register_engine

SOURCE_DOMAIN = "sentinel.perspective-gap-detector"

GAP_PROMPT = """You are an expert strategic thinker helping an AI system broaden its perspective repertoire.

The system has been handling tasks recently but has NOT used the "{perspective}" perspective at all in the past 7 days.

## Recent task context (to understand the work domain)
{task_context}

## Instructions
Generate 2-3 specific, actionable questions that a person holding the "{perspective}" perspective would ask about this work. These questions should:
- Be concrete and grounded in the actual tasks described above
- Reveal blind spots or dimensions that other perspectives might miss
- Be immediately useful if posed to a practitioner in this domain

Return JSON:
{{
  "questions": [
    "Question 1?",
    "Question 2?",
    "Question 3?"
  ]
}}"""


def _validate_perspective_gaps_inputs(product_id: str, budget: int = 100) -> None:
    """Validate perspective gaps inputs before querying the database.

    Raises ValidationError for malformed product_id or out-of-range budget
    so the engine fails fast with a clear error rather than running LLM
    calls against invalid data.
    """
    if not product_id or ":" not in product_id:
        raise ValidationError(f"Invalid product_id for perspective-gaps: {product_id!r}")
    if not (0 <= budget <= 500):
        raise ValidationError(f"budget must be in [0, 500], got {budget}")


@register_engine(
    name="perspective_gap_detector",
    cron="0 5 * * *",
    description="Detect underused perspectives and surface in briefing",
)
async def run_perspective_gap_detector(product_id: str, budget: int = 20) -> dict:
    """Detect perspectives available but unused in recent tasks and generate prompts.

    Args:
        product_id: Organization to analyze perspective usage for.
        budget: Maximum LLM calls per run (default 20). Each call handles one gap.

    Returns:
        Dict with: gaps_found, gap_details, perspectives_used, perspectives_available.
        gap_details is a list of {perspective, unused_days, prompt} dicts.
    """
    gap_details: list[dict] = []
    perspectives_used: set[str] = set()
    perspectives_available: set[str] = set()
    llm_calls = 0

    _validate_perspective_gaps_inputs(product_id, budget)
    try:
        async with pool.connection() as db:
            # 1. Query task table for perspectives used in last 7 days
            usage_result = await db.query(
                """
                SELECT perspective, count() AS count
                FROM task
                WHERE product = <record>$product
                    AND created_at > time::now() - 7d
                    AND perspective != NONE
                GROUP BY perspective
                """,
                {"product": product_id},
            )
            usage_rows = parse_rows(usage_result)

            # Collect used perspectives — filter None defensively for pre-v026 rows
            for row in usage_rows:
                p = row.get("perspective")
                if p is not None:
                    perspectives_used.add(p)

            # 2. Query specialty for available perspectives
            # decision:17xtwojp9b4d3qcgsocz — prior shape was malformed
            # (`FROM specialty AND status IN [...]` with no WHERE). SurrealDB v3
            # silently parses that as zero-match and returns [{'perspective': None}]
            # instead of raising a parse error. Adding explicit WHERE.
            avail_result = await db.query(
                """
                SELECT perspective
                FROM specialty
                WHERE status IN ['active', 'scaffolded']
                GROUP BY perspective
                """,
                {"product": product_id},
            )
            avail_rows = parse_rows(avail_result)

            for row in avail_rows:
                p = row.get("perspective")
                if p is not None:
                    perspectives_available.add(p)

            # 3. Find gaps: available but not used
            gap_perspectives = sorted(perspectives_available - perspectives_used)
            total_gaps = len(gap_perspectives)

            # 4. For each gap (up to budget): fetch context + generate questions
            for perspective in gap_perspectives:
                if llm_calls >= budget:
                    break

                # Get recent task descriptions for context
                ctx_result = await db.query(
                    """
                    SELECT description, created_at
                    FROM task
                    WHERE product = <record>$product
                        AND created_at > time::now() - 7d
                    ORDER BY created_at DESC
                    LIMIT 10
                    """,
                    {"product": product_id},
                )
                ctx_rows = parse_rows(ctx_result)
                task_context = (
                    "\n".join(f"- {r.get('description', '')}" for r in ctx_rows if r.get("description"))
                    if ctx_rows
                    else "(no recent tasks)"
                )

                prompt = GAP_PROMPT.format(
                    perspective=perspective,
                    task_context=task_context,
                )

                try:
                    response = await llm.complete_json(
                        prompt,
                        model=settings.llm_budget_model,
                    )
                except Exception:
                    continue

                llm_calls += 1

                questions = response.get("questions", [])
                combined_prompt = " | ".join(q for q in questions if q)

                gap_details.append(
                    {
                        "perspective": perspective,
                        "unused_days": 7,
                        "prompt": combined_prompt,
                    }
                )

    except Exception:
        return {
            "gaps_found": 0,
            "gap_details": [],
            "perspectives_used": set(),
            "perspectives_available": set(),
        }

    return {
        "gaps_found": total_gaps,
        "gap_details": gap_details,
        "perspectives_used": perspectives_used,
        "perspectives_available": perspectives_available,
    }
