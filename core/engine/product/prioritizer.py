# engine/product/prioritizer.py
"""Product-layer slot machine — multi-dimensional scoring for what to work on next."""

import logging

from core.engine.core.db import parse_rows
from core.engine.core.exceptions import DatabaseError, PrioritizationError, ValidationError

logger = logging.getLogger(__name__)

PRIORITY_WEIGHTS = {"critical": 1.0, "important": 0.7, "nice_to_have": 0.3}


class ProductPrioritizer:
    """Multi-dimensional scoring for what to work on next."""

    def __init__(self, db_pool):
        self._pool = db_pool

    def _validate_product_id(self, product_id: str) -> None:
        """Validate product_id format before issuing DB queries.

        Raises ValidationError if the product_id is empty or missing the required
        colon-separated namespace prefix (e.g. 'product:platform').
        """
        if not product_id or ":" not in product_id:
            raise ValidationError(f"Invalid product_id: {product_id!r}")

    async def prioritize(self, product_id: str) -> list[dict]:
        """Score and rank work items by priority.

        Returns a list of dicts sorted by priority_score (desc). Each item has:
            type, capability_slug, dimension, current_score, gaps, priority_score

        Raises:
            ValidationError: If product_id is malformed.
            DatabaseError: On DB failure.
            PrioritizationError: If scoring produces no results.
        """
        self._validate_product_id(product_id)
        try:
            async with self._pool.connection() as db:
                cap_result = await db.query(
                    "SELECT * FROM capability WHERE product = <record>$product AND status != 'deprecated'",
                    {"product": product_id},
                )
                capabilities = parse_rows(cap_result)
                cap_by_id = {str(c["id"]): c for c in capabilities}

                gap_result = await db.query(
                    "SELECT * FROM capability_quality WHERE product = <record>$product AND score < 0.6 ORDER BY score",
                    {"product": product_id},
                )
                gaps = parse_rows(gap_result)
        except Exception as exc:
            raise DatabaseError(f"Failed to load prioritization data for {product_id}: {exc}") from exc

        scored = []
        for gap in gaps:
            cap_id = str(gap.get("capability", ""))
            cap = cap_by_id.get(cap_id, {})
            try:
                score = self._score(gap, cap)
            except Exception as exc:
                raise PrioritizationError(
                    f"Scoring failed for {cap.get('slug')}/{gap.get('dimension')}: {exc}"
                ) from exc
            scored.append(
                {
                    "type": "gap",
                    "capability_slug": cap.get("slug", "unknown"),
                    "dimension": gap.get("dimension", "unknown"),
                    "current_score": gap.get("score", 0),
                    "gaps": gap.get("gaps", []),
                    "priority_score": score,
                }
            )

        scored.sort(key=lambda x: x["priority_score"], reverse=True)
        logger.debug(
            "Prioritized %d gaps for product=%s (top: %s %.2f)",
            len(scored),
            product_id,
            scored[0]["capability_slug"] if scored else "none",
            scored[0]["priority_score"] if scored else 0.0,
        )
        return scored

    def _score(self, gap: dict, capability: dict) -> float:
        """Multi-dimensional scoring.
        - severity (0.45): lower quality score = higher severity
        - cap_priority (0.35): critical > important > nice_to_have
        - blast_radius (0.20): more gaps = more impact
        Weights sum to 1.0.

        All inputs are clamped to valid ranges to defend against bad DB data.
        """
        raw_score = gap.get("score", 0.5)
        quality_score = max(0.0, min(1.0, float(raw_score) if raw_score is not None else 0.5))
        severity = 1.0 - quality_score
        priority_key = capability.get("priority", "important")
        cap_priority = PRIORITY_WEIGHTS.get(priority_key, 0.5)
        gap_count = len(gap.get("gaps", []))
        blast_radius = min(1.0, gap_count / 5.0)
        score = (severity * 0.45) + (cap_priority * 0.35) + (blast_radius * 0.20)
        logger.debug(
            "Scored %s/%s: severity=%.2f cap_priority=%.2f blast=%.2f → %.3f",
            capability.get("slug", "?"),
            gap.get("dimension", "?"),
            severity,
            cap_priority,
            blast_radius,
            score,
        )
        return score
