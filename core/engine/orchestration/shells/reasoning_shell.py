"""ReasoningShell — multi-pass executor/reviewer reasoning loop.

Executor and reviewer are always different models (key invariant).
Failures are captured to the knowledge graph via FailureClassifier.
Opus escalation fires only after max_passes exhausted.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field

from pydantic import BaseModel

from core.engine.intelligence.complexity_router import TIER_EXECUTOR, TIER_REVIEWER, ComplexityTier
from core.engine.intelligence.failure_classifier import FailureCategory
from core.engine.runtime.model_config import MODEL_TIERS

logger = logging.getLogger(__name__)

_DISCIPLINE_CONFIG: dict[str, dict] = {
    "coding": {"max_passes": 3, "confidence_threshold": 0.85},
    "brainstorming": {"max_passes": 2, "confidence_threshold": 0.70},
    "design": {"max_passes": 2, "confidence_threshold": 0.75},
}
_DEFAULT_CONFIG = {"max_passes": 3, "confidence_threshold": 0.85}

_REVIEW_PROMPT_TEMPLATE = """\
Task: {task}

Output to review:
{output}

Evaluate this output. Return JSON matching the schema exactly.
- passed: true if output fully satisfies the task
- confidence: 0.0-1.0
- failure_category: one of {categories} or null if passed
- issues: list of specific actionable problems (empty if passed)
"""


class ReviewResult(BaseModel):
    passed: bool
    confidence: float
    failure_category: FailureCategory | None = None
    issues: list[str] = field(default_factory=list)

    model_config = {"use_enum_values": False}


@dataclass
class PassRecord:
    output: str
    review: ReviewResult
    executor_model: str
    reviewer_model: str
    pass_number: int


@dataclass
class ReasoningResult:
    output: str
    passes: list[PassRecord]
    escalated: bool
    tier: ComplexityTier

    @property
    def pass_count(self) -> int:
        return len(self.passes)


class ReasoningShell:
    """Coordinates the executor/reviewer loop for a single task."""

    def __init__(self, llm=None, failure_classifier=None) -> None:
        from core.engine.core.llm import get_llm
        from core.engine.intelligence.failure_classifier import FailureClassifier

        self._llm = llm or get_llm()
        self._failure_classifier = failure_classifier or FailureClassifier()

    def _get_config(self, discipline: str) -> dict:
        return _DISCIPLINE_CONFIG.get(discipline, _DEFAULT_CONFIG)

    async def run(
        self,
        task_description: str,
        discipline: str,
        tier: ComplexityTier,
        product_id: str = "product:platform",
    ) -> ReasoningResult:
        cfg = self._get_config(discipline)
        max_passes: int = cfg["max_passes"]
        threshold: float = cfg["confidence_threshold"]
        executor_model = TIER_EXECUTOR[tier]
        reviewer_model = TIER_REVIEWER[tier]
        categories = [c.value for c in FailureCategory]
        passes: list[PassRecord] = []
        prior_issues: list[str] = []

        for i in range(max_passes):
            prompt = self._assemble_prompt(task_description, prior_issues)
            output = await self._llm.complete(prompt, model=executor_model)

            review_prompt = _REVIEW_PROMPT_TEMPLATE.format(
                task=task_description,
                output=output,
                categories=categories,
            )
            review: ReviewResult = await self._llm.complete_structured(
                review_prompt,
                schema=ReviewResult,
                model=reviewer_model,
            )

            record = PassRecord(
                output=output,
                review=review,
                executor_model=executor_model,
                reviewer_model=reviewer_model,
                pass_number=i + 1,
            )
            passes.append(record)

            if review.passed or review.confidence >= threshold:
                return ReasoningResult(output=output, passes=passes, escalated=False, tier=tier)

            if review.failure_category:
                await self._failure_classifier.capture(
                    discipline=discipline,
                    task_type="execution",
                    category=review.failure_category,
                    issues=review.issues,
                    product_id=product_id,
                )
            prior_issues = review.issues

        # Exhausted — escalate to Opus
        logger.warning("ReasoningShell: %d passes exhausted for %s, escalating", max_passes, discipline)
        opus_output = await self._escalate_to_opus(task_description, passes, discipline, product_id)
        passes.append(
            PassRecord(
                output=opus_output,
                review=ReviewResult(passed=True, confidence=1.0),
                executor_model=MODEL_TIERS["opus"],
                reviewer_model=MODEL_TIERS["opus"],
                pass_number=len(passes) + 1,
            )
        )
        return ReasoningResult(output=opus_output, passes=passes, escalated=True, tier=tier)

    async def _escalate_to_opus(
        self, task_description: str, passes: list[PassRecord], discipline: str, product_id: str
    ) -> str:
        last_output = passes[-1].output if passes else ""
        prompt = f"{task_description}\n\nPrevious attempt (needs improvement):\n{last_output}\n\nProduce the best possible version."
        opus_output = await self._llm.complete(prompt, model=MODEL_TIERS["opus"])
        await self._failure_classifier.capture_opus_success(
            discipline=discipline,
            task_type="execution",
            sonnet_output=last_output,
            opus_output=opus_output,
            product_id=product_id,
        )
        return opus_output

    @staticmethod
    def _assemble_prompt(task_description: str, prior_issues: list[str]) -> str:
        if not prior_issues:
            return task_description
        issues_block = "\n".join(f"- {issue}" for issue in prior_issues)
        return f"{task_description}\n\nPrevious attempt had these specific issues to fix:\n{issues_block}\n\nAddress all of the above issues in your response."
