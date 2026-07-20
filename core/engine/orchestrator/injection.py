# engine/orchestrator/injection.py
"""Proactive perspective injection — adds missing perspectives based on contextual signals.

Runs post-classification, before engagement execution. Lightweight DB queries only (no LLM).
"""

from __future__ import annotations

import logging

from core.engine.core.db import parse_rows, pool

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

_COMPLEXITY_ESCALATION_MAP = {
    "practitioner": "theorist",
    "theorist": "practitioner",
    "strategist": "practitioner",
    "operator": "strategist",
}
_RECENCY_THRESHOLD_DAYS = 7
_MAX_PERSPECTIVES = 4


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


async def inject_missing_perspectives(classification: dict, product_id: str) -> dict:
    """Add missing perspectives to *classification* based on contextual DB signals.

    Modifies and returns the classification dict (mutates engagement.perspectives
    and engagement.injected).  Three lightweight checks are run in order:

    1. Complexity escalation — complex task with a single perspective gets its
       complementary perspective added from _COMPLEXITY_ESCALATION_MAP.
    2. Recency gap — a perspective that has specialties but hasn't been used in
       the last 7 days is injected (max 1 per call from this check).
    3. Milestone proximity — any milestone due within 7 days triggers operator
       injection if operator is not already present.

    All DB queries are wrapped in try/except so injection failures never block
    task execution.
    """
    engagement = classification.setdefault("engagement", {})
    perspectives: list[str] = engagement.setdefault("perspectives", ["practitioner"])
    injected: list[dict] = engagement.setdefault("injected", [])

    # -----------------------------------------------------------------------
    # Check 1: Complexity escalation
    # -----------------------------------------------------------------------
    try:
        complexity = classification.get("complexity", "simple")
        if complexity == "complex" and len(perspectives) == 1:
            sole = perspectives[0]
            complement = _COMPLEXITY_ESCALATION_MAP.get(sole)
            if complement and complement not in perspectives and len(perspectives) < _MAX_PERSPECTIVES:
                perspectives.append(complement)
                injected.append(
                    {
                        "perspective": complement,
                        "reason": f"complexity escalation — '{sole}' needs '{complement}' for complex task",
                        "injected": True,
                    }
                )
                logger.debug(
                    "injection: complexity escalation added '%s' (sole=%s, org=%s)",
                    complement,
                    sole,
                    product_id,
                )
    except Exception as exc:
        logger.warning("injection: complexity escalation check failed (skipped): %s", exc)

    # -----------------------------------------------------------------------
    # Check 2: Recency gap
    # -----------------------------------------------------------------------
    try:
        async with pool.connection() as conn:
            task_rows = parse_rows(
                await conn.query(
                    """
                    SELECT perspective, count() AS cnt
                    FROM task
                    WHERE product = <record>$product
                      AND created_at > time::now() - <duration>$window
                    GROUP BY perspective
                    """,
                    {"product": product_id, "window": f"{_RECENCY_THRESHOLD_DAYS}d"},
                )
            )
        recently_used: set[str] = {r["perspective"] for r in task_rows if r.get("perspective")}

        async with pool.connection() as conn:
            specialty_rows = parse_rows(
                await conn.query(
                    """
                    SELECT perspective
                    FROM specialty
                    WHERE product IN [$product, "product:platform"]
                    GROUP BY perspective
                    """,
                    {"product": product_id},
                )
            )
        perspectives_with_specialties: set[str] = {r["perspective"] for r in specialty_rows if r.get("perspective")}

        injected_from_recency = 0
        for perspective in perspectives_with_specialties:
            if injected_from_recency >= 1:
                break
            if perspective in perspectives:
                continue
            if perspective in recently_used:
                continue
            if len(perspectives) >= _MAX_PERSPECTIVES:
                break
            perspectives.append(perspective)
            injected.append(
                {
                    "perspective": perspective,
                    "reason": f"recency gap — '{perspective}' has specialties but no recent usage",
                    "injected": True,
                }
            )
            injected_from_recency += 1
            logger.debug(
                "injection: recency gap added '%s' (org=%s)",
                perspective,
                product_id,
            )
    except Exception as exc:
        logger.warning("injection: recency gap check failed (skipped): %s", exc)

    # -----------------------------------------------------------------------
    # Check 3: Milestone proximity
    # -----------------------------------------------------------------------
    try:
        async with pool.connection() as conn:
            milestone_rows = parse_rows(
                await conn.query(
                    """
                    SELECT id, title, due
                    FROM milestone
                    WHERE product = <record>$product
                      AND due <= time::now() + <duration>$window
                      AND due >= time::now()
                    LIMIT 10
                    """,
                    {"product": product_id, "window": f"{_RECENCY_THRESHOLD_DAYS}d"},
                )
            )
        if milestone_rows and "operator" not in perspectives:
            if len(perspectives) < _MAX_PERSPECTIVES:
                perspectives.append("operator")
                injected.append(
                    {
                        "perspective": "operator",
                        "reason": f"milestone proximity — {len(milestone_rows)} milestone(s) due within {_RECENCY_THRESHOLD_DAYS} days",
                        "injected": True,
                    }
                )
                logger.debug(
                    "injection: milestone proximity added 'operator' (%d milestones, org=%s)",
                    len(milestone_rows),
                    product_id,
                )
    except Exception as exc:
        logger.warning("injection: milestone proximity check failed (skipped): %s", exc)

    return classification
