# engine/sentinel/engines/knowledge_verifier.py
"""Knowledge verifier engine — verify stale insights against LLM knowledge.

Runs nightly at 4:00 AM. Finds stale insights using category-dependent
staleness thresholds, plus low-confidence insights. Uses LLM to verify
each against its training data.

Three outcomes:
  - confirmed: boost confidence +0.3 (max 1.0), update last_confirmed
  - updated: create new insight, mark old as contradicted
  - cannot_verify: decay confidence -0.1 (min 0.0)

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
SOURCE_DOMAIN = "sentinel.knowledge-verifier"

VERIFICATION_THRESHOLDS: dict[str, int] = {
    "version": 14,
    "personnel": 30,
    "pricing": 30,
    "regulation": 90,
    "process": 180,
    "fact": 90,
    "decision": 365,
}

DEFAULT_THRESHOLD = 90


def _validate_verifier_inputs(product_id: str, budget: int = 100) -> None:
    """Validate knowledge verifier inputs before querying stale insights.

    Raises ValidationError for malformed product_id or budget out of range
    so the nightly verifier job fails fast instead of running LLM calls
    against every insight in an invalid product's graph.
    """
    if not product_id or ":" not in product_id:
        raise ValidationError(f"Invalid product_id for knowledge verifier: {product_id!r}")
    if not (1 <= budget <= 500):
        raise ValidationError(f"budget must be in [1, 500], got {budget}")


VERIFICATION_PROMPT = """You are a knowledge verification expert for an AI intelligence system.

Verify whether the following insight is still accurate and current.

## Insight
Content: {content}
Created: {created_at}
Last confirmed: {last_confirmed}
Tags: {tags}
Current confidence: {confidence}

## Instructions
Based on your knowledge, determine one of three outcomes:

1. "confirmed" — The insight is still accurate. No changes needed.
2. "updated" — The insight is outdated or partially wrong. Provide the corrected version.
3. "cannot_verify" — You cannot determine accuracy (e.g., company-specific data, real-time info).

If outcome is "updated", provide the corrected content and your confidence level.

Return JSON:
{{
  "outcome": "confirmed|updated|cannot_verify",
  "explanation": "Why you reached this conclusion",
  "updated_content": "only if outcome is updated — the corrected insight text",
  "confidence": 0.0-1.0 (only if outcome is updated — confidence in the correction)
}}"""


def get_threshold_for_tags(tags: list[str]) -> int:
    """Return the smallest verification threshold from an insight's tags.

    If no recognized category tag is found, returns DEFAULT_THRESHOLD (90 days).
    Uses the smallest threshold because the most time-sensitive category wins.
    """
    thresholds = [VERIFICATION_THRESHOLDS[tag] for tag in tags if tag in VERIFICATION_THRESHOLDS]
    return min(thresholds) if thresholds else DEFAULT_THRESHOLD


@register_engine(
    name="knowledge_verifier",
    cron="0 4 * * *",
    description="Verify stale insights against LLM knowledge",
)
async def run_knowledge_verifier(product_id: str, budget: int = 20) -> dict:
    """Verify stale and low-confidence insights.

    Args:
        product_id: Organization to verify insights for.
        budget: Maximum LLM calls per run (default 20).

    Returns:
        Dict with counts: candidates, confirmed, updated, cannot_verify.
    """
    _validate_verifier_inputs(product_id, budget)
    confirmed = 0
    updated = 0
    cannot_verify = 0
    llm_calls = 0

    async with pool.connection() as db:
        stale_result = await db.query(
            """
            SELECT *
            FROM insight
            WHERE product = <record>$product
                AND status = 'active'
                AND last_confirmed < time::now() - 14d
            ORDER BY last_confirmed ASC
            LIMIT 200
            """,
            {"product": product_id},
        )
        stale_rows = parse_rows(stale_result)

        low_conf_result = await db.query(
            """
            SELECT *
            FROM insight
            WHERE product = <record>$product
                AND status = 'active'
                AND confidence < 0.5
                AND last_confirmed < time::now() - 30d
            ORDER BY confidence ASC
            LIMIT 50
            """,
            {"product": product_id},
        )
        low_conf_rows = parse_rows(low_conf_result)

        # Deduplicate
        seen_ids: set[str] = set()
        candidates: list[dict] = []

        for insight in stale_rows:
            insight_id = str(insight.get("id", ""))
            if insight_id not in seen_ids:
                seen_ids.add(insight_id)
                candidates.append(insight)

        for insight in low_conf_rows:
            insight_id = str(insight.get("id", ""))
            if insight_id not in seen_ids:
                seen_ids.add(insight_id)
                candidates.append(insight)

        total_candidates = len(candidates)

        for insight in candidates:
            if llm_calls >= budget:
                break

            insight_id = str(insight.get("id", ""))
            content = insight.get("content", "")
            tags = insight.get("tags", [])
            confidence = insight.get("confidence", 0.5)
            created_at = str(insight.get("created_at", ""))
            last_confirmed = str(insight.get("last_confirmed", ""))

            insight_discipline = next(
                (t for t in tags if t not in VERIFICATION_THRESHOLDS and t not in ("auto-verified", "auto-researched")),
                "",
            )
            intel = await load_discipline_context(insight_discipline, product_id) if insight_discipline else ""

            prompt = VERIFICATION_PROMPT.format(
                content=content,
                created_at=created_at,
                last_confirmed=last_confirmed,
                tags=str(tags),
                confidence=confidence,
            )
            if intel:
                prompt = f"{prompt}\n\n{intel}"

            try:
                verification = await llm.complete_json(prompt)
            except Exception:
                continue

            llm_calls += 1
            outcome = verification.get("outcome", "cannot_verify")

            if outcome == "confirmed":
                new_confidence = min(1.0, confidence + 0.3)
                await db.query(
                    """
                    UPDATE type::record($insight_id) SET
                        last_confirmed = time::now(),
                        confidence = $new_confidence
                    """,
                    {"insight_id": insight_id, "new_confidence": new_confidence},
                )
                confirmed += 1

            elif outcome == "updated":
                updated_content = verification.get("updated_content", content)
                new_confidence = verification.get("confidence", 0.8)
                # Use discipline tag if present, fall back to domain_path for legacy insights
                existing_tags = insight.get("tags", [])
                discipline = next(
                    (t for t in existing_tags if t not in VERIFICATION_THRESHOLDS and t != "auto-verified"),
                    insight.get("domain_path", "unknown"),
                )
                tier = insight.get("tier", "subdomain")

                new_id = await write_engine_insight(
                    db,
                    product_id=product_id,
                    content=updated_content,
                    insight_type=insight.get("insight_type", "fact"),
                    tier=tier,
                    discipline=discipline,
                    source_domain=SOURCE_DOMAIN,
                    confidence=new_confidence,
                    tags=[*[t for t in tags if t != "auto-verified"], "auto-verified"],
                )

                await db.query(
                    """
                    UPDATE type::record($insight_id) SET
                        status = 'contradicted',
                        contradicted_by = type::record($new_id)
                    """,
                    {"insight_id": insight_id, "new_id": new_id},
                )
                updated += 1

            else:  # cannot_verify
                new_confidence = max(0.0, confidence - 0.1)
                await db.query(
                    """
                    UPDATE type::record($insight_id) SET
                        confidence = $new_confidence
                    """,
                    {"insight_id": insight_id, "new_confidence": new_confidence},
                )
                cannot_verify += 1

    return {
        "candidates": total_candidates,
        "confirmed": confirmed,
        "updated": updated,
        "cannot_verify": cannot_verify,
    }
