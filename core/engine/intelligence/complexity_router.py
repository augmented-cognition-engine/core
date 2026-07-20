"""ComplexityRouter — determines the model tier for a reasoning loop task.

Hard rules fire first (keyword patterns → COMPLEX). Remaining tasks
are assessed via a cheap Haiku call. Falls back to MODERATE on error.
"""

from __future__ import annotations

import logging
from enum import Enum

from core.engine.runtime.model_config import MODEL_TIERS

logger = logging.getLogger(__name__)

_COMPLEX_KEYWORDS = frozenset(
    [
        "refactor",
        "migrate",
        "migration",
        "architecture",
        "multi-file",
        "across files",
        "rewrite",
        "redesign",
        "extract module",
        "split",
    ]
)


class ComplexityTier(str, Enum):
    SIMPLE = "simple"  # haiku executes,  sonnet reviews
    MODERATE = "moderate"  # sonnet executes, sonnet reviews
    COMPLEX = "complex"  # sonnet executes, opus reviews


TIER_EXECUTOR: dict[ComplexityTier, str] = {
    ComplexityTier.SIMPLE: MODEL_TIERS["haiku"],
    ComplexityTier.MODERATE: MODEL_TIERS["sonnet"],
    ComplexityTier.COMPLEX: MODEL_TIERS["sonnet"],
}

TIER_REVIEWER: dict[ComplexityTier, str] = {
    ComplexityTier.SIMPLE: MODEL_TIERS["sonnet"],
    ComplexityTier.MODERATE: MODEL_TIERS["sonnet"],
    ComplexityTier.COMPLEX: MODEL_TIERS["opus"],
}


class ComplexityRouter:
    """Routes tasks to a ComplexityTier based on hard rules + optional LLM assessment."""

    def _apply_hard_rules(self, task_description: str, discipline: str) -> ComplexityTier | None:
        lower = task_description.lower()
        if any(kw in lower for kw in _COMPLEX_KEYWORDS):
            return ComplexityTier.COMPLEX
        return None

    async def _llm_assess(self, task_description: str, discipline: str) -> ComplexityTier:
        from core.engine.core.llm import get_llm

        llm = get_llm()
        prompt = (
            f"Classify the complexity of this software task for discipline '{discipline}'.\n\n"
            f"Task: {task_description}\n\n"
            "Tiers:\n"
            "- simple: single function/file, no architectural decisions, trivial scope\n"
            "- moderate: multi-step implementation, some design choices, 1-3 files\n"
            "- complex: architectural decisions, multi-file refactor, performance-critical\n\n"
            'Return JSON: {"tier": "simple"|"moderate"|"complex"}'
        )
        result = await llm.complete_json(prompt, model=MODEL_TIERS["haiku"], max_tokens=64)
        tier_str = result.get("tier", "moderate").lower()
        try:
            return ComplexityTier(tier_str)
        except ValueError:
            return ComplexityTier.MODERATE

    async def assess(self, task_description: str, discipline: str) -> ComplexityTier:
        """Assess task complexity. Hard rules fire first; LLM fallback on remainder."""
        hard = self._apply_hard_rules(task_description, discipline)
        if hard is not None:
            logger.debug("ComplexityRouter hard rule → %s for: %.80s", hard, task_description)
            return hard
        try:
            tier = await self._llm_assess(task_description, discipline)
            logger.debug("ComplexityRouter LLM → %s for: %.80s", tier, task_description)
            return tier
        except Exception:
            logger.warning("ComplexityRouter LLM assessment failed; defaulting to MODERATE")
            return ComplexityTier.MODERATE
