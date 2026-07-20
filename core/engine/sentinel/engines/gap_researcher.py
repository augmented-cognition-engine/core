# engine/sentinel/engines/gap_researcher.py
"""Gap researcher engine — consume research queue, fill knowledge gaps with LLM.

Runs nightly at 3:30 AM (after failure analysis). Three input sources in
priority order:
  1. Queued research (research_queue, status='pending')
  2. Low-confidence tasks (self_assessment < 0.6, not rejected)
  3. Thin specialties (task_count > 5, fewer than 10 active insights)

All sources feed conduct_research(), which prompts the LLM to synthesize
findings into new insights.

Spec: docs/superpowers/specs/2026-03-21-phase3b-overnight-engines.md
"""

from __future__ import annotations

import logging

from core.engine.core.db import parse_rows, pool
from core.engine.core.exceptions import ValidationError
from core.engine.core.llm import llm
from core.engine.sentinel.engines import load_discipline_context, write_engine_insight
from core.engine.sentinel.registry import register_engine

logger = logging.getLogger(__name__)

SOURCE_DOMAIN = "sentinel.gap-researcher"

RESEARCH_PROMPT = """You are an expert knowledge researcher for an AI intelligence system.

Research the following topic and synthesize your findings into structured insights.

## Research Query
{query}

## Context
{context}

## Instructions
Synthesize your knowledge into 1-3 concrete findings. Each finding should be a standalone insight that could help an AI system perform better on related tasks.

For each finding, specify:
- content: The insight text (1-3 sentences, specific and actionable)
- insight_type: "fact" (established knowledge), "pattern" (best practice/approach), or "procedure" (step-by-step)
- confidence: 0.0-1.0 (how confident you are this is current and correct)
- tier: "specialty" (very specific), "subdomain" (broader), or "domain" (general)
- discipline: the discipline tag for this finding (e.g. "frontend", "devops", "backend")

Return JSON:
{{
  "findings": [
    {{
      "content": "...",
      "insight_type": "fact|pattern|procedure",
      "confidence": 0.0-1.0,
      "tier": "specialty|subdomain|domain",
      "discipline": "frontend|devops|backend|..."
    }}
  ]
}}"""


async def _conduct_research(
    db,
    product_id: str,
    query: str,
    context: str,
    source_task: str | None = None,
) -> tuple[int, list[str]]:
    """Run LLM research and write findings as insights.

    Returns:
        Tuple of (findings_count, list of created insight IDs).
    """
    prompt = RESEARCH_PROMPT.format(query=query, context=context)

    try:
        result = await llm.complete_json(prompt)
    except Exception:
        return 0, []

    findings = result.get("findings", [])
    insight_ids = []

    for finding in findings:
        content = finding.get("content", "")
        if not content:
            continue

        insight_id = await write_engine_insight(
            db,
            product_id=product_id,
            content=content,
            insight_type=finding.get("insight_type", "fact"),
            tier=finding.get("tier", "subdomain"),
            discipline=finding.get("discipline", finding.get("domain_path", "unknown")),
            source_domain=SOURCE_DOMAIN,
            confidence=finding.get("confidence", 0.6),
            tags=["auto-researched"],
            source_task=source_task,
        )

        if insight_id:
            insight_ids.append(insight_id)

    return len(findings), insight_ids


def _validate_gap_researcher_inputs(product_id: str, budget: int = 100) -> None:
    """Validate gap researcher inputs before querying the database.

    Raises ValidationError for malformed product_id or out-of-range budget
    so the engine fails fast with a clear error rather than running LLM
    calls against invalid data.
    """
    if not product_id or ":" not in product_id:
        raise ValidationError(f"Invalid product_id for gap-researcher: {product_id!r}")
    if not (0 <= budget <= 500):
        raise ValidationError(f"budget must be in [0, 500], got {budget}")


@register_engine(
    name="gap_researcher",
    cron="30 3 * * *",
    description="Fill knowledge gaps from research queue + low-confidence tasks",
)
async def run_gap_researcher(product_id: str, budget: int = 20) -> dict:
    """Consume research queue and identify knowledge gaps.

    Args:
        product_id: Organization to research for.
        budget: Maximum LLM calls per run (default 20).

    Returns:
        Dict with counts: research_conducted, insights_written, queue_completed.
    """
    research_conducted = 0
    insights_written = 0
    queue_completed = 0
    llm_calls = 0

    results: dict = {}

    _validate_gap_researcher_inputs(product_id, budget)
    async with pool.connection() as db:
        # Bootstrap path: scaffolded specialties with zero task activity
        try:
            from core.engine.sentinel.engines.bootstrap import research_specialty_by_description

            scaffolded = parse_rows(
                await db.query(
                    """SELECT *, array::find_index(['core', 'adjacent', 'peripheral'], priority) AS priority_sort
                   FROM specialty
                   WHERE product = <record>$product AND bootstrapped = false AND status = 'scaffolded'
                   ORDER BY priority_sort ASC, created_at ASC
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

        # Source 1: Pending research queue items (highest priority)
        rq_result = await db.query(
            """
            SELECT * FROM research_queue
            WHERE product = <record>$product AND status = 'pending'
            ORDER BY created_at ASC
            LIMIT $limit
            """,
            {"product": product_id, "limit": budget},
        )
        rq_rows = parse_rows(rq_result)

        # Source 2: Low-confidence tasks from today
        lc_result = await db.query(
            """
            SELECT discipline, description, id
            FROM task
            WHERE product = <record>$product
                AND completed_at > time::now() - 1d
                AND (calibrated_assessment ?? self_assessment) < 0.6
                AND (feedback_human IS NONE OR feedback_human != 'rejected')
            LIMIT $limit
            """,
            {"product": product_id, "limit": budget},
        )
        lc_rows = parse_rows(lc_result)

        # Source 3: Thin specialties
        ts_result = await db.query(
            """
            SELECT id, slug, name, task_count,
                   (SELECT count() FROM insight WHERE specialty = $parent.id AND status = 'active' GROUP ALL)[0].count AS insight_count
            FROM specialty
            WHERE product = <record>$product AND task_count > 5
            """,
            {"product": product_id},
        )
        ts_rows = parse_rows(ts_result)
        thin_specialties = [s for s in ts_rows if (s.get("insight_count") or 0) < 10]

        # Process Source 1: Research queue items
        for item in rq_rows:
            if llm_calls >= budget:
                break

            item_id = str(item.get("id", ""))
            query = item.get("query", "")
            context = item.get("context", "")
            related_task = item.get("related_task")

            item_discipline = item.get("discipline", "")
            if item_discipline:
                intel = await load_discipline_context(item_discipline, product_id)
                if intel:
                    context = f"{context}\n\n{intel}" if context else intel

            count, ids = await _conduct_research(
                db,
                product_id,
                query,
                context,
                source_task=str(related_task) if related_task else None,
            )

            llm_calls += 1
            research_conducted += 1
            insights_written += len(ids)

            await db.query(
                """
                UPDATE type::record($item_id) SET
                    status = 'completed',
                    completed_at = time::now()
                """,
                {"item_id": item_id},
            )
            queue_completed += 1

        # Process Source 2: Low-confidence tasks
        for task in lc_rows:
            if llm_calls >= budget:
                break

            discipline = task.get("discipline", task.get("domain_path", "unknown"))
            description = task.get("description", "")
            task_id = str(task.get("id", ""))

            query = f"What knowledge is needed to confidently handle: {description}"
            intel = await load_discipline_context(discipline, product_id)
            context = f"Low-confidence task in {discipline}. Self-assessment was below 0.6."
            if intel:
                context = f"{context}\n\n{intel}"

            count, ids = await _conduct_research(
                db,
                product_id,
                query,
                context,
                source_task=task_id,
            )

            llm_calls += 1
            research_conducted += 1
            insights_written += len(ids)

        # Process Source 3: Thin specialties
        for spec in thin_specialties:
            if llm_calls >= budget:
                break

            spec_name = spec.get("name", spec.get("slug", "unknown"))
            spec_slug = spec.get("slug", "unknown")

            query = f"Key knowledge areas for the specialty: {spec_name}"
            intel = await load_discipline_context(spec_slug, product_id)
            context = f"Thin specialty {spec_slug}: {spec.get('task_count', 0)} tasks but only {spec.get('insight_count', 0)} insights."
            if intel:
                context = f"{context}\n\n{intel}"

            count, ids = await _conduct_research(db, product_id, query, context)

            llm_calls += 1
            research_conducted += 1
            insights_written += len(ids)

    results.update(
        {
            "research_conducted": research_conducted,
            "insights_written": insights_written,
            "queue_completed": queue_completed,
        }
    )
    return results
