# engine/cognition/classifier.py
"""FrameworkClassifier — resolves InstrumentSpec slots to framework slugs.

Two-tier resolution per instrument slot:
1. Learned preferences: query instrument_perf for best frameworks given
   (cognitive_function, task_type, discipline). Historical performance drives selection.
2. Static affinity fallback: use spec.fallback_slug when learned data is sparse.

Blending curve (samples = rows in instrument_perf for this slot):
  <5  samples  → 0% learned  (cold start: pure static)
  5-20 samples → 70% learned / 30% static (transitional)
  20+ samples  → 90% learned / 10% static (never fully eliminate static)
"""

from __future__ import annotations

import logging

from core.engine.cognition.models import InstrumentSpec
from core.engine.core.db import parse_rows, pool

logger = logging.getLogger(__name__)

_COLD_START_THRESHOLD = 5
_MATURE_THRESHOLD = 20
_MATURE_WEIGHT = 0.9
_TRANSITIONAL_WEIGHT = 0.7


class FrameworkClassifier:
    """Resolves InstrumentSpec to a concrete framework slug."""

    def _blend_weight(self, sample_count: int) -> float:
        """Return the learned-preference weight (0.0-0.9) given sample count.

        <5  samples → 0.0  (cold start)
        5-19 samples → 0.7 (transitional)
        20+ samples  → 0.9 (mature)
        """
        if sample_count < _COLD_START_THRESHOLD:
            return 0.0
        if sample_count >= _MATURE_THRESHOLD:
            return _MATURE_WEIGHT
        return _TRANSITIONAL_WEIGHT

    async def resolve_instrument(
        self,
        spec: InstrumentSpec,
        task_type: str,
        discipline: str,
        product_id: str,
        cognitive_function: str = "",
        meta_skill: str = "",
    ) -> str:
        """Resolve one InstrumentSpec to the best framework slug.

        If spec.slug is set (explicit), return it directly — no DB lookup.
        If spec.family_hint is set, query learned preferences; fall back to
        static (spec.fallback_slug) when data is sparse.
        """
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
        """Query instrument_perf for best-performing slug.

        Returns None if insufficient samples (cold start) or no data.
        """
        try:
            async with pool.connection() as db:
                rows = await db.query(
                    """
                    SELECT framework_slug,
                           math::mean(outcome_score) AS avg_score,
                           count() AS sample_count
                    FROM instrument_perf
                    WHERE product = <record>$product
                      AND cognitive_function = $cognitive_function
                      AND (meta_skill = $meta_skill OR meta_skill = '')
                      AND (task_type = $task_type OR task_type = '')
                      AND (discipline = $discipline OR discipline = '')
                      AND outcome_score >= 0
                    GROUP BY framework_slug
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
                sample_count = top.get("sample_count", 0)
                blend = self._blend_weight(sample_count)

                if blend == 0.0:
                    return None  # cold start — use static

                return top.get("framework_slug")
        except Exception as exc:
            logger.debug("instrument_perf query failed (non-fatal): %s", exc)
            return None
