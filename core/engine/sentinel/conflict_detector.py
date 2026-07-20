# engine/sentinel/conflict_detector.py
"""Conflict detector engine — post-synthesis hook + daily sweep.

Detects contradictions between insights using a budget LLM semantic comparison.
Writes to the existing conflict table. Two modes:
1. Post-synthesis hook: compare new insights against existing in same subdomain.
2. Daily sweep: re-check active insights with confidence < 0.5.

Spec: docs/superpowers/specs/2026-03-21-phase3a-scheduler-signals.md §5
Cost: ~$0.001 per comparison via budget LLM.
"""

from __future__ import annotations

import logging
from itertools import combinations
from typing import Any

from core.engine.core.db import parse_rows
from core.engine.core.exceptions import ValidationError
from core.engine.sentinel.registry import register_engine

logger = logging.getLogger(__name__)

CONTRADICTION_PROMPT = """Compare these two statements and determine if they contradict each other.

Statement A: {content_a}

Statement B: {content_b}

Return JSON with:
- "contradicts": true or false
- "explanation": brief explanation of why they do or do not contradict"""


def _validate_conflict_inputs(content_a: str, content_b: str) -> None:
    """Validate that insight content strings are suitable for contradiction checking.

    Raises ValidationError if either content string is blank or exceeds the
    practical limit for a single LLM comparison (10,000 chars).  Long strings
    should be summarised before comparison; passing them raw wastes tokens and
    degrades comparison quality.
    """
    for label, text in (("content_a", content_a), ("content_b", content_b)):
        if not text or not text.strip():
            raise ValidationError(f"{label} must be non-empty")
        if len(text) > 10_000:
            raise ValidationError(f"{label} exceeds 10,000 char limit (got {len(text)})")


async def check_contradiction(
    content_a: str,
    content_b: str,
    llm: Any,
) -> dict[str, Any]:
    """Use budget LLM to check if two statements contradict each other.

    Returns: { contradicts: bool, explanation: str }
    Raises ValidationError if inputs are blank or too long.
    """
    _validate_conflict_inputs(content_a, content_b)
    prompt = CONTRADICTION_PROMPT.format(content_a=content_a, content_b=content_b)
    result = await llm.complete_json(prompt)
    return {
        "contradicts": bool(result.get("contradicts", False)),
        "explanation": result.get("explanation", ""),
    }


async def check_new_insights(
    new_insight_ids: list[str],
    product_id: str,
    db: Any,
    llm: Any,
) -> dict[str, Any]:
    """Post-synthesis hook: compare new insights against existing in same subdomain.

    For each new insight, query top 5 active insights in the same subdomain
    (by confidence DESC) and check for contradictions.
    """
    pairs_checked = 0
    conflicts_found = 0

    # Fetch new insights — convert string IDs to RecordID for SurrealDB v3
    from core.engine.core.db import parse_record_id

    record_ids = [
        parse_record_id(id_str) if isinstance(id_str, str) and ":" in id_str else id_str for id_str in new_insight_ids
    ]
    rows = await db.query(
        "SELECT * FROM insight WHERE id IN $ids",
        {"ids": record_ids},
    )
    new_insights = parse_rows(rows)

    for new_insight in new_insights:
        subdomain = new_insight.get("subdomain")
        if not subdomain:
            continue

        # Fetch top 5 existing active insights in same subdomain and product
        existing_rows = await db.query(
            """
            SELECT id, content, confidence FROM insight
            WHERE subdomain = $subdomain
              AND product = <record>$product
              AND status = 'active'
              AND id != <record>$new_id
            ORDER BY confidence DESC
            LIMIT 5
            """,
            {"subdomain": subdomain, "product": product_id, "new_id": str(new_insight["id"])},
        )
        existing = parse_rows(existing_rows)

        for existing_insight in existing:
            # Check if conflict already exists between these two
            conflict_check = await db.query(
                """
                SELECT id FROM conflict
                WHERE (insight_a = <record>$a AND insight_b = <record>$b)
                   OR (insight_a = <record>$b AND insight_b = <record>$a)
                LIMIT 1
                """,
                {"a": str(existing_insight["id"]), "b": str(new_insight["id"])},
            )
            existing_conflict = parse_rows(conflict_check)
            if existing_conflict:
                continue

            pairs_checked += 1
            result = await check_contradiction(
                content_a=existing_insight.get("content", ""),
                content_b=new_insight.get("content", ""),
                llm=llm,
            )

            if result["contradicts"]:
                await db.query(
                    """
                    CREATE conflict SET
                        insight_a = <record>$a,
                        insight_b = <record>$b,
                        explanation = $explanation,
                        status = 'open',
                        detected_by = 'conflict_detector',
                        created_at = time::now()
                    """,
                    {
                        "product": product_id,
                        "a": str(existing_insight["id"]),
                        "b": str(new_insight["id"]),
                        "explanation": result["explanation"],
                    },
                )
                conflicts_found += 1
                logger.info(f"Conflict found: {existing_insight['id']} vs {new_insight['id']}")

    return {
        "pairs_checked": pairs_checked,
        "conflicts_found": conflicts_found,
        "cost": pairs_checked * 0.001,
    }


async def sweep(
    product_id: str,
    db: Any,
    llm: Any,
    max_comparisons: int = 100,
) -> dict[str, Any]:
    """Daily sweep: re-check active insights with confidence < 0.5.

    Compares pairwise within the same subdomain. Budget: max_comparisons.
    Skips pairs already in the conflict table.
    """
    pairs_checked = 0
    pairs_skipped = 0
    conflicts_found = 0

    # Fetch low-confidence active insights
    rows = await db.query(
        """
        SELECT id, content, subdomain, confidence FROM insight
        WHERE product = <record>$product
          AND status = 'active'
          AND confidence < 0.5
        ORDER BY subdomain, confidence ASC
        """,
        {"product": product_id},
    )
    insights = parse_rows(rows)

    # Group by subdomain
    by_subdomain: dict[str, list[dict]] = {}
    for insight in insights:
        sd = str(insight.get("subdomain", ""))
        by_subdomain.setdefault(sd, []).append(insight)

    for subdomain, group in by_subdomain.items():
        for a, b in combinations(group, 2):
            if pairs_checked >= max_comparisons:
                break

            # Check if conflict already exists
            conflict_check = await db.query(
                """
                SELECT id FROM conflict
                WHERE (insight_a = <record>$a AND insight_b = <record>$b)
                   OR (insight_a = <record>$b AND insight_b = <record>$a)
                LIMIT 1
                """,
                {"a": str(a["id"]), "b": str(b["id"])},
            )
            existing = parse_rows(conflict_check)
            if existing:
                pairs_skipped += 1
                continue

            pairs_checked += 1
            result = await check_contradiction(
                content_a=a.get("content", ""),
                content_b=b.get("content", ""),
                llm=llm,
            )

            if result["contradicts"]:
                await db.query(
                    """
                    CREATE conflict SET
                        insight_a = <record>$a_id,
                        insight_b = <record>$b_id,
                        explanation = $explanation,
                        status = 'open',
                        detected_by = 'conflict_detector',
                        created_at = time::now()
                    """,
                    {
                        "product": product_id,
                        "a_id": str(a["id"]),
                        "b_id": str(b["id"]),
                        "explanation": result["explanation"],
                    },
                )
                conflicts_found += 1

        if pairs_checked >= max_comparisons:
            break

    logger.info(f"Conflict sweep: checked={pairs_checked}, skipped={pairs_skipped}, found={conflicts_found}")
    return {
        "pairs_checked": pairs_checked,
        "pairs_skipped": pairs_skipped,
        "conflicts_found": conflicts_found,
        "cost": pairs_checked * 0.001,
    }


@register_engine(
    name="conflict_detector",
    cron="30 2 * * *",
    description="Daily contradiction sweep across low-confidence insights",
)
async def run(product_id: str) -> dict:
    """Execute conflict detector daily sweep.

    Uses budget LLM for semantic comparison. Max 100 comparisons per sweep.
    """
    from core.engine.core.db import pool
    from core.engine.core.llm import get_llm

    llm = get_llm()

    async with pool.connection() as db:
        return await sweep(product_id=product_id, db=db, llm=llm)
