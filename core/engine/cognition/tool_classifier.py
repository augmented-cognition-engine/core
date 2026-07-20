# engine/cognition/tool_classifier.py
"""ToolClassifier — resolves ToolSpec slots to tool slugs (advisory binding).

Direct mirror of FrameworkClassifier, against the tool_perf table:
1. Explicit spec.slug → return it.
2. Learned: query tool_perf for the best tool given
   (cognitive_function, task_type, discipline, meta_skill); blend by sample count.
3. Static: spec.fallback_slug when learned data is sparse.

Blending curve matches FrameworkClassifier:
  <5 samples → static; 5-19 → transitional; 20+ → mature.
"""

from __future__ import annotations

import logging

from core.engine.cognition.models import ToolSpec
from core.engine.core.db import parse_rows, pool

logger = logging.getLogger(__name__)

_COLD_START_THRESHOLD = 5
_MATURE_THRESHOLD = 20
_MATURE_WEIGHT = 0.9
_TRANSITIONAL_WEIGHT = 0.7


class ToolClassifier:
    """Resolves a ToolSpec to a concrete tool slug."""

    def _blend_weight(self, sample_count: int) -> float:
        if sample_count < _COLD_START_THRESHOLD:
            return 0.0
        if sample_count >= _MATURE_THRESHOLD:
            return _MATURE_WEIGHT
        return _TRANSITIONAL_WEIGHT

    async def resolve_tool(
        self,
        spec: ToolSpec,
        task_type: str,
        discipline: str,
        product_id: str,
        cognitive_function: str = "",
        meta_skill: str = "",
    ) -> str:
        """Resolve one ToolSpec to the best tool slug (explicit → learned → fallback)."""
        if spec.slug:
            return spec.slug

        learned_slug = await self._query_learned(
            cognitive_function=cognitive_function,
            task_type=task_type,
            discipline=discipline,
            product_id=product_id,
            meta_skill=meta_skill,
        )
        if learned_slug:
            return learned_slug
        return spec.fallback_slug

    async def _query_learned(
        self,
        cognitive_function: str,
        task_type: str,
        discipline: str,
        product_id: str,
        meta_skill: str,
    ) -> str | None:
        """Query tool_perf for the best-performing tool slug. None on cold start / error."""
        try:
            async with pool.connection() as db:
                rows = await db.query(
                    """
                    SELECT tool_slug,
                           math::mean(outcome_score) AS avg_score,
                           count() AS sample_count
                    FROM tool_perf
                    WHERE product = <record>$product
                      AND cognitive_function = $cognitive_function
                      AND (meta_skill = $meta_skill OR meta_skill = '')
                      AND (task_type = $task_type OR task_type = '')
                      AND (discipline = $discipline OR discipline = '')
                      AND outcome_score >= 0
                    GROUP BY tool_slug
                    ORDER BY avg_score DESC
                    LIMIT 1
                    """,
                    {
                        "product": product_id,
                        "cognitive_function": cognitive_function,
                        "meta_skill": meta_skill,
                        "task_type": task_type,
                        "discipline": discipline,
                    },
                )
                parsed = parse_rows(rows)
                if not parsed:
                    return None
                top = parsed[0]
                if self._blend_weight(top.get("sample_count", 0)) == 0.0:
                    return None  # cold start — use static fallback
                return top.get("tool_slug")
        except Exception as exc:
            logger.debug("tool_perf query failed (non-fatal): %s", exc)
            return None
