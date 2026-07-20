"""Bootstrap helper — research scaffolded specialties using their description.

Shared helper used by gap_researcher and specialty_deepener to handle
cold-start specialties (task_count=0, insight_count=0, status='scaffolded').
Generates seed insights from the specialty's description via budget LLM.
"""

from __future__ import annotations

import logging

from core.engine.core.config import settings
from core.engine.core.db import parse_record_id, parse_rows, pool
from core.engine.core.llm import llm

logger = logging.getLogger(__name__)


async def research_specialty_by_description(
    specialty: dict,
    product_id: str,
) -> dict:
    """Bootstrap a scaffolded specialty using its description.

    Generates seed insights via budget LLM based on the specialty's
    description and discipline context. Writes insights with specialty
    record link. Sets bootstrapped=true when threshold is met.

    Returns: {"insights_created": int, "bootstrapped": bool}
    """
    spec_id = specialty.get("id")
    slug = specialty.get("slug", "unknown")
    description = specialty.get("description", slug)
    name = specialty.get("name", slug)
    min_threshold = specialty.get("min_threshold", 5)

    try:
        result = await llm.complete_json(
            f"""You are bootstrapping knowledge for the specialty: "{name}"

Description: {description}

Generate {min_threshold} foundational insights for this specialty.
Each insight should be a well-established fact, pattern, or principle
that a practitioner in this area would consider essential knowledge.

For each insight:
- content: the insight (1-2 sentences, specific and actionable)
- confidence: 0.7-0.95 (these are established knowledge, not speculation)
- insight_type: fact | pattern | convention | discovery

Return JSON: {{"insights": [...]}}""",
            model=settings.llm_budget_model,
        )
    except Exception as exc:
        logger.warning("Bootstrap LLM call failed for %s: %s", slug, exc)
        return {"insights_created": 0, "bootstrapped": False}

    raw_insights = result.get("insights", [])
    if not isinstance(raw_insights, list):
        return {"insights_created": 0, "bootstrapped": False}

    created = 0
    async with pool.connection() as db:
        for ins in raw_insights[: min_threshold + 2]:  # slight overshoot OK
            content = ins.get("content", "")
            if not content or len(content) < 3:
                continue
            confidence = max(0.5, min(0.95, float(ins.get("confidence", 0.7))))
            insight_type = ins.get("insight_type", "fact")
            if insight_type not in ("fact", "pattern", "convention", "discovery"):
                insight_type = "fact"

            try:
                rows = parse_rows(
                    await db.query(
                        """CREATE insight SET
                        product = <record>$product, content = $content,
                        insight_type = $type, tier = 'specialty',
                        confidence = $conf, specialty = $spec,
                        source_domain = $slug, status = 'active',
                        clearance = 'open',
                        created_at = time::now(), updated_at = time::now(),
                        last_confirmed = time::now()""",
                        {
                            "product": product_id,
                            "content": content,
                            "type": insight_type,
                            "conf": confidence,
                            "spec": parse_record_id(str(spec_id)) if spec_id else None,
                            "slug": slug,
                        },
                    )
                )
                if rows:
                    created += 1
            except Exception as exc:
                logger.warning("Failed to create bootstrap insight for %s: %s", slug, exc)

        # Update insight count and check bootstrapped threshold
        bootstrapped = False
        if created > 0:
            try:
                await db.query(
                    "UPDATE <record>$id SET insight_count += $n",
                    {"id": str(spec_id), "n": created},
                )
                # Check if threshold met
                check = parse_rows(
                    await db.query(
                        "SELECT insight_count, min_threshold FROM <record>$id",
                        {"id": str(spec_id)},
                    )
                )
                if check:
                    count = check[0].get("insight_count", 0)
                    threshold = check[0].get("min_threshold", 5)
                    if count >= threshold:
                        await db.query(
                            "UPDATE <record>$id SET bootstrapped = true, status = 'active'",
                            {"id": str(spec_id)},
                        )
                        bootstrapped = True
            except Exception as exc:
                logger.warning("Failed to update specialty %s after bootstrap: %s", slug, exc)

    logger.info("Bootstrapped %s: %d insights, bootstrapped=%s", slug, created, bootstrapped)
    return {"insights_created": created, "bootstrapped": bootstrapped}
