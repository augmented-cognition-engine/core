# engine/cognition/plan_evaluator.py
"""PlanEvaluator — scores decomposition plans by quality using LLM judgment.

Primary evaluation uses llm_budget_model (Haiku).
Close-call zone [0.35, 0.65]: self-consistency sampling runs 2 additional
Haiku calls in parallel and averages all 3 scores — cheaper and more reliable
than escalating to a stronger advisor model.
Returns 0.5 on any LLM failure (non-fatal).
"""

from __future__ import annotations

import logging

from pydantic import BaseModel, Field

from core.engine.cognition.self_consistency import aggregate_scores, sample_structured
from core.engine.core.config import settings
from core.engine.core.llm import get_llm

logger = logging.getLogger(__name__)

_CLOSE_CALL_LOW = 0.35
_CLOSE_CALL_HIGH = 0.65
_SELF_CONSISTENCY_SAMPLES = 2  # additional samples beyond the primary (total = 3)


class PlanScore(BaseModel):
    score: float = Field(ge=0.0, le=1.0)
    reasoning: str


class PlanEvaluator:
    """Scores a decomposition plan using LLM judgment.

    advisor_model param accepted for backward compat but ignored — self-consistency
    is always used for close calls regardless of this setting.
    """

    def __init__(self, advisor_model: str | None = None) -> None:
        # advisor_model kept for backward compat; self-consistency is used instead
        if advisor_model:
            logger.debug(
                "PlanEvaluator: advisor_model=%r ignored — using self-consistency sampling instead",
                advisor_model,
            )

    async def evaluate(self, spec: dict, units: list) -> float:
        """Score a decomposition plan (0.0–1.0). Returns 0.5 on failure."""
        objective = spec.get("objective", "")
        unit_summaries = "\n".join(
            f"- [{getattr(u, 'archetype', '?')}/{getattr(u, 'mode', '?')}] "
            f"{getattr(u, 'title', '?')}: {getattr(u, 'description', '')}"
            for u in units
        )
        dep_count = sum(len(getattr(u, "depends_on", [])) for u in units)

        prompt = (
            f"Rate the quality of this decomposition plan (0.0–1.0).\n\n"
            f"Objective: {objective}\n\n"
            f"Work units:\n{unit_summaries}\n\n"
            f"Total dependency edges: {dep_count}\n\n"
            f"Score criteria:\n"
            f"- Units have clear, non-overlapping scope\n"
            f"- Dependencies minimized (maximize parallelism)\n"
            f"- Archetype and mode match the work type\n"
            f"- Plan covers the objective\n\n"
            f"Return score (0.0–1.0) and brief reasoning."
        )

        try:
            llm = get_llm()
            primary = await llm.complete_structured(prompt, schema=PlanScore, model=settings.llm_budget_model)
            score = primary.score

            # Self-consistency on close calls: sample 2 more times, average all 3
            if _CLOSE_CALL_LOW <= score <= _CLOSE_CALL_HIGH:
                extra = await sample_structured(
                    prompt,
                    PlanScore,
                    model=settings.llm_budget_model,
                    n=_SELF_CONSISTENCY_SAMPLES,
                )
                all_samples = [primary, *extra]
                score = aggregate_scores(all_samples, "score")

            return score
        except Exception as exc:
            logger.warning("PlanEvaluator failed (non-fatal): %s", exc)
            return 0.5
