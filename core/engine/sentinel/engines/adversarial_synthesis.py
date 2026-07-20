"""Sentinel engine: Adversarial Synthesis — challenge high-confidence beliefs.

Runs weekly (Wednesday 5 AM). For each domain with high-confidence insights:
1. Generate plausible counter-arguments via budget LLM
2. Evaluate each challenge's validity (0.0-1.0)
3. Valid challenges (> 0.6) → conflict record for human review
4. ALL results logged to experiment_log (valid + invalid)

This is ACE's self-immune system. It prevents institutional blind spots
by questioning the most confident, oldest beliefs.
"""

from __future__ import annotations

import logging

from core.engine.core.config import settings
from core.engine.core.db import pool
from core.engine.core.exceptions import ValidationError
from core.engine.core.llm import llm
from core.engine.sentinel.registry import register_engine

logger = logging.getLogger(__name__)

CONFIDENCE_THRESHOLD = 0.8
VALID_CHALLENGE_THRESHOLD = 0.6
MAX_INSIGHTS_PER_DOMAIN = 20

CHALLENGE_PROMPT = """This insight is held with {confidence} confidence: '{content}'.

Generate a plausible counter-argument or scenario where this insight would be wrong, outdated, or harmful. Be specific and realistic, not contrarian for its own sake.

Return JSON: {{"contradiction": "your specific counter-argument"}}"""

EVALUATE_PROMPT = """Original belief: '{content}' (confidence: {confidence}).
Challenge: '{contradiction}'.

Score 0.0-1.0:
- 0.0 = baseless, generic, or contrarian for no reason
- 0.5 = legitimate concern worth noting but doesn't invalidate
- 1.0 = invalidates the belief entirely

Return JSON: {{"score": <float>, "reasoning": "brief explanation"}}"""


def _validate_adversarial_synthesis_inputs(product_id: str, budget: int = 100) -> None:
    """Validate adversarial synthesis inputs before querying the database.

    Raises ValidationError for malformed product_id or out-of-range budget
    so the engine fails fast with a clear error rather than running LLM
    calls against invalid data.
    """
    if not product_id or ":" not in product_id:
        raise ValidationError(f"Invalid product_id for adversarial-synthesis: {product_id!r}")
    if not (0 <= budget <= 500):
        raise ValidationError(f"budget must be in [0, 500], got {budget}")


@register_engine(
    name="adversarial_synthesis",
    cron="0 5 * * wed",
    description="Weekly adversarial challenge of high-confidence beliefs (Wednesday 5am)",
)
async def run_adversarial_synthesis(product_id: str, budget: int = 20) -> dict:
    """Challenge high-confidence insights with adversarial counter-arguments."""
    insights_challenged = 0
    valid_challenges = 0
    conflicts_created = 0
    domains_processed = 0

    _validate_adversarial_synthesis_inputs(product_id, budget)
    async with pool.connection() as db:
        # Get distinct disciplines with high-confidence insights
        discipline_result = await db.query(
            """
            SELECT tags FROM insight
            WHERE product = <record>$product
              AND status = 'active'
              AND confidence > $threshold
            """,
            {"product": product_id, "threshold": CONFIDENCE_THRESHOLD},
        )
        discipline_rows = (
            discipline_result[0]
            if discipline_result and isinstance(discipline_result[0], list)
            else (discipline_result or [])
        )

        # Collect unique non-system tag values to use as discipline groupings
        _seen_disciplines: set[str] = set()
        _system_tags = {"auto-correction", "auto-researched", "auto-verified", "experiment"}
        discipline_list = []
        for row in discipline_rows:
            for tag in row.get("tags") or []:
                if tag not in _system_tags and not tag.startswith(("competitor:", "signal:", "framework-")):
                    if tag not in _seen_disciplines:
                        _seen_disciplines.add(tag)
                        discipline_list.append(tag)

        if not discipline_list:
            return {"insights_challenged": 0, "valid_challenges": 0, "conflicts_created": 0, "domains_processed": 0}

        # Process each discipline (up to budget)
        for discipline in discipline_list[:budget]:
            domains_processed += 1

            # Get top insights: oldest high-confidence first (most worth challenging)
            insight_result = await db.query(
                """
                SELECT id, content, confidence, org, created_at
                FROM insight
                WHERE product = <record>$product
                  AND tags CONTAINS $discipline
                  AND status = 'active'
                  AND confidence > $threshold
                ORDER BY confidence DESC, created_at ASC
                LIMIT $limit
                """,
                {
                    "product": product_id,
                    "discipline": discipline,
                    "threshold": CONFIDENCE_THRESHOLD,
                    "limit": MAX_INSIGHTS_PER_DOMAIN,
                },
            )
            insights = (
                insight_result[0] if insight_result and isinstance(insight_result[0], list) else (insight_result or [])
            )

            for insight in insights:
                insight_id = str(insight.get("id", ""))
                content = insight.get("content", "")
                confidence = insight.get("confidence", 0.0)

                if not content:
                    continue

                insights_challenged += 1

                try:
                    # Step 1: Generate challenge
                    challenge_result = await llm.complete_json(
                        CHALLENGE_PROMPT.format(content=content[:500], confidence=confidence),
                        model=settings.llm_budget_model,
                    )
                    contradiction = challenge_result.get("contradiction", "")

                    if not contradiction:
                        continue

                    # Step 2: Evaluate challenge
                    eval_result = await llm.complete_json(
                        EVALUATE_PROMPT.format(
                            content=content[:500],
                            confidence=confidence,
                            contradiction=contradiction[:500],
                        ),
                        model=settings.llm_budget_model,
                    )
                    score = float(eval_result.get("score", 0.0))
                    reasoning = eval_result.get("reasoning", "")

                    is_valid = score > VALID_CHALLENGE_THRESHOLD

                    # Step 3: If valid, create conflict record
                    if is_valid:
                        try:
                            await db.query(
                                """
                                CREATE conflict SET
                                    insight_a = $insight_id,
                                    explanation = $explanation,
                                    status = 'open',
                                    detected_by = 'adversarial_synthesis',
                                    created_at = time::now()
                                """,
                                {
                                    "product": product_id,
                                    "insight_id": insight_id,
                                    "explanation": f"Adversarial challenge (score: {score:.2f}): {contradiction}",
                                },
                            )
                            conflicts_created += 1
                            valid_challenges += 1
                        except Exception as exc:
                            logger.warning("Failed to create conflict for %s: %s", insight_id, exc)
                    else:
                        valid_challenges += 0  # explicit: invalid

                    # Step 4: Log ALL results to experiment_log
                    await db.query(
                        """
                        CREATE experiment_log SET
                            domain = $discipline,
                            experiment_type = 'adversarial',
                            control_description = $insight_content,
                            variant_description = $contradiction,
                            control_mean = $confidence,
                            variant_mean = $score,
                            improvement = $score,
                            p_value = 0.0,
                            significant = $is_valid,
                            committed = $is_valid,
                            details = $details,
                            created_at = time::now()
                        """,
                        {
                            "product": product_id,
                            "discipline": discipline,
                            "insight_content": content[:500],
                            "contradiction": contradiction[:500],
                            "confidence": confidence,
                            "score": score,
                            "is_valid": is_valid,
                            "details": {
                                "insight_id": insight_id,
                                "challenge": contradiction,
                                "evaluation_score": score,
                                "reasoning": reasoning,
                            },
                        },
                    )

                except Exception as exc:
                    logger.warning("Adversarial challenge failed for %s: %s", insight_id, exc)

    logger.info(
        "Adversarial synthesis: challenged=%d, valid=%d, conflicts=%d, domains=%d",
        insights_challenged,
        valid_challenges,
        conflicts_created,
        domains_processed,
    )
    return {
        "insights_challenged": insights_challenged,
        "valid_challenges": valid_challenges,
        "conflicts_created": conflicts_created,
        "domains_processed": domains_processed,
    }
