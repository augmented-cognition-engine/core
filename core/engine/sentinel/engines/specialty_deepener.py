# engine/sentinel/engines/specialty_deepener.py
"""Specialty deepener engine — find thin specialties, queue research topics.

Runs at 4:30 AM on Mon + Thu. Identifies specialties that are "thin" — high
task count but low insight count (task_count > insight_count * 2). Uses LLM
to identify top research topics, then queues them for the gap researcher to
process on the next overnight cycle.

Does NOT write insights directly. Only writes to research_queue.

Spec: docs/superpowers/specs/2026-03-21-phase3b-overnight-engines.md
"""

from __future__ import annotations

import logging

from core.engine.core.db import parse_rows, pool
from core.engine.core.exceptions import ValidationError
from core.engine.core.llm import llm
from core.engine.sentinel.engines import load_discipline_context, queue_research
from core.engine.sentinel.registry import register_engine

logger = logging.getLogger(__name__)

SOURCE_DOMAIN = "sentinel.specialty-deepener"
TOPICS_TO_QUEUE = 3

DEEPENER_PROMPT = """You are an expert knowledge strategist for an AI intelligence system.

A specialty area is "thin" — the system handles many tasks in this area but has very few knowledge insights. Identify what knowledge is missing.

## Specialty
Name: {specialty_name}
Tasks handled: {task_count}
Current insights: {insight_count}

## Existing Specialty Insights
{existing_insights}

{discipline_context}

## Instructions
Based on the specialty name and all available knowledge above, identify the top 5 topics where additional knowledge would be most valuable. Focus on:
- Foundational knowledge that would apply to many tasks
- Common patterns and best practices
- Recent developments or changes in the field
- Gaps visible from what IS known (existing insights)

Return JSON:
{{
  "topics": [
    {{
      "query": "Specific research question to investigate",
      "context": "Why this topic is important for this specialty"
    }}
  ]
}}"""


def is_thin_specialty(task_count: int, insight_count: int) -> bool:
    """Determine if a specialty is thin (needs deepening).

    A specialty is thin when:
    - task_count > 3 (minimum activity threshold)
    - task_count > insight_count * 2 (twice as many tasks as insights)
    """
    return task_count > 3 and task_count > insight_count * 2


def _validate_specialty_deepener_inputs(product_id: str, budget: int = 100) -> None:
    """Validate specialty deepener inputs before querying the database.

    Raises ValidationError for malformed product_id or out-of-range budget
    so the engine fails fast with a clear error rather than running LLM
    calls against invalid data.
    """
    if not product_id or ":" not in product_id:
        raise ValidationError(f"Invalid product_id for specialty-deepener: {product_id!r}")
    if not (0 <= budget <= 500):
        raise ValidationError(f"budget must be in [0, 500], got {budget}")


@register_engine(
    name="specialty_deepener",
    cron="30 4 * * mon,thu",
    description="Find thin specialties, queue research topics for gap researcher",
)
async def run_specialty_deepener(product_id: str, budget: int = 20) -> dict:
    """Find thin specialties and queue research topics.

    Args:
        product_id: Organization to analyze specialties for.
        budget: Maximum LLM calls per run (default 20).

    Returns:
        Dict with counts: thin_specialties_found, research_queued.
    """
    thin_specialties_found = 0
    research_queued = 0
    llm_calls = 0
    results: dict = {}

    _validate_specialty_deepener_inputs(product_id, budget)
    async with pool.connection() as db:
        # Bootstrap path: scaffolded specialties with zero task activity
        try:
            from core.engine.sentinel.engines.bootstrap import research_specialty_by_description

            scaffolded = parse_rows(
                await db.query(
                    """SELECT * FROM specialty
                   WHERE product = <record>$product AND bootstrapped = false AND status = 'scaffolded'
                   ORDER BY
                     CASE priority WHEN 'core' THEN 0 WHEN 'adjacent' THEN 1 ELSE 2 END,
                     created_at ASC
                   LIMIT $limit""",
                    {"product": product_id, "limit": max(1, budget // 2)},
                )
            )

            bootstrap_count = 0
            for spec in scaffolded:
                if bootstrap_count >= budget // 2:
                    break
                result = await research_specialty_by_description(spec, product_id)
                bootstrap_count += result.get("insights_created", 0)

            results["bootstrapped_specialties"] = len(scaffolded)
            results["bootstrap_insights"] = bootstrap_count
        except Exception as exc:
            logger.warning("Bootstrap path failed: %s", exc)

        spec_result = await db.query(
            """
            SELECT id, slug, name, task_count,
                   (SELECT count() FROM insight
                    WHERE (specialty = $parent.id OR tags CONTAINS $parent.slug)
                      AND status = 'active'
                    GROUP ALL)[0].count AS insight_count
            FROM specialty
            WHERE product = <record>$product AND task_count > 3
            ORDER BY task_count DESC
            """,
            {"product": product_id},
        )
        spec_rows = parse_rows(spec_result)

        thin_specs = [
            s
            for s in spec_rows
            if is_thin_specialty(
                task_count=s.get("task_count", 0),
                insight_count=s.get("insight_count") or 0,
            )
        ]

        thin_specialties_found = len(thin_specs)

        for spec in thin_specs:
            if llm_calls >= budget:
                break

            spec_name = spec.get("name", spec.get("slug", "unknown"))
            spec_slug = spec.get("slug", "unknown")
            task_count = spec.get("task_count", 0)
            insight_count = spec.get("insight_count") or 0

            insights_result = await db.query(
                """
                SELECT content, confidence
                FROM insight
                WHERE (specialty = $spec_id OR tags CONTAINS $slug)
                    AND status = 'active'
                ORDER BY confidence DESC
                LIMIT 10
                """,
                {"spec_id": spec.get("id"), "slug": spec_slug},
            )
            insight_rows = parse_rows(insights_result)
            existing_text = "\n".join(f"- {i.get('content', '')}" for i in insight_rows) if insight_rows else "(none)"

            spec_discipline = spec_slug.replace("-", "_")
            discipline_context = await load_discipline_context(spec_discipline, product_id)

            prompt = DEEPENER_PROMPT.format(
                specialty_name=spec_name,
                task_count=task_count,
                insight_count=insight_count,
                existing_insights=existing_text,
                discipline_context=discipline_context,
            )

            try:
                result = await llm.complete_json(prompt)
            except Exception:
                continue

            llm_calls += 1

            topics = result.get("topics", [])

            for topic in topics[:TOPICS_TO_QUEUE]:
                topic_query = topic.get("query", "")
                topic_context = topic.get("context", "")

                if not topic_query:
                    continue

                rq_id = await queue_research(
                    db,
                    product_id=product_id,
                    query=topic_query,
                    context=f"Specialty deepener ({spec_name}): {topic_context}",
                    priority="medium",
                    source="specialty-deepener",
                )

                if rq_id:
                    research_queued += 1

    results.update(
        {
            "thin_specialties_found": thin_specialties_found,
            "research_queued": research_queued,
        }
    )
    return results
