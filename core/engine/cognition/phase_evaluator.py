"""PhaseEvaluator — LLM-based scorer for cognitive phase outputs.

Evaluates a PhaseOutput against the RecipePhase's must_not/must_verify constraints.
Returns a float score 0.0–1.0. Non-fatal: returns 0.5 (neutral) on any error.

Close-call zone [0.35, 0.65]: instead of escalating to a stronger advisor model,
we run 2 additional Haiku samples in parallel and average all 3 scores.
Uncorrelated failure modes → more reliable than one expensive opinion.

Used by MultiPhaseExecutor's lazy branching to rank N candidates.
"""

from __future__ import annotations

import logging

from pydantic import BaseModel, Field

from core.engine.cognition.models import RecipePhase
from core.engine.cognition.phase_output import PhaseOutput
from core.engine.cognition.self_consistency import (
    aggregate_scores,
    disagreement,
    most_conservative,
    sample_structured,
)
from core.engine.core.llm import get_llm

logger = logging.getLogger(__name__)

_CLOSE_CALL_LOW = 0.35
_CLOSE_CALL_HIGH = 0.65
_SELF_CONSISTENCY_SAMPLES = 2  # additional samples beyond the primary (total = 3)

_EVALUATION_PROMPT = """\
You are evaluating the quality of a single cognitive phase output.

## Task
{task}

## Phase Function
{cognitive_function}

## Output to Evaluate
{output}

## Self-Reported Confidence
{confidence}

## Constitutional Constraints

MUST NOT (each violation reduces score by 0.25):
{must_not}

MUST VERIFY (each satisfied item increases score by 0.1):
{must_verify}

## Scoring Instructions
Start at 0.5.
- Subtract 0.25 for each MUST NOT constraint visibly violated.
- Add 0.1 for each MUST VERIFY item clearly satisfied.
- Add 0.1 if the output has strong evidence (specific facts, not vague claims).
- Add 0.1 if no critical gaps remain unaddressed.
- Clamp final score to [0.0, 1.0].

Return JSON: {{"score": 0.0-1.0, "reasoning": "one sentence explaining the score", "violated_constraints": ["exact MUST NOT text that was violated", ...]}}"""


class EvaluationResult(BaseModel):
    score: float = Field(ge=0.0, le=1.0)
    reasoning: str
    violated_constraints: list[str] = Field(default_factory=list)
    # Self-consistency spread across close-call samples (0.0 = stable verdict).
    # Defaults to 0.0 for confident (non-close-call) evaluations.
    disagreement: float = Field(default=0.0, ge=0.0, le=1.0)


class PhaseEvaluator:
    """Evaluates a phase output against constitutional constraints using an LLM critic.

    Primary evaluation uses the budget model (Haiku). When score lands in the
    close-call zone [0.35, 0.65], self-consistency sampling runs 2 additional
    Haiku calls in parallel and averages all 3 scores. Uncorrelated failure modes
    across samples produce more reliable scores than escalating to a stronger model.

    advisor_model param accepted for backward compat but ignored — self-consistency
    is always used for close calls regardless of this setting.
    """

    def __init__(self, advisor_model: str | None = None) -> None:
        # advisor_model kept for backward compat; self-consistency is used instead
        if advisor_model:
            logger.debug(
                "PhaseEvaluator: advisor_model=%r ignored — using self-consistency sampling instead",
                advisor_model,
            )

    async def evaluate(
        self,
        task: str,
        phase_output: PhaseOutput,
        phase: RecipePhase,
    ) -> EvaluationResult:
        """Score the phase output, returning full EvaluationResult.

        Uses budget model (Haiku) for primary evaluation.
        On close calls, runs 2 additional Haiku samples (self-consistency).
        Returns neutral EvaluationResult (score=0.5) on any error — never raises.
        """
        try:
            must_not_text = "\n".join(f"  - {c}" for c in phase.must_not) or "  (none)"
            must_verify_text = "\n".join(f"  - {c}" for c in phase.must_verify) or "  (none)"
            prompt = _EVALUATION_PROMPT.format(
                task=task,
                cognitive_function=phase.cognitive_function,
                output=phase_output.output[:500],
                confidence=phase_output.confidence,
                must_not=must_not_text,
                must_verify=must_verify_text,
            )
            llm = get_llm()
            from core.engine.core.config import settings

            primary: EvaluationResult = await llm.complete_structured(
                prompt, schema=EvaluationResult, model=settings.llm_budget_model
            )

            # Self-consistency on close calls: sample 2 more times, average all 3
            if _CLOSE_CALL_LOW <= primary.score <= _CLOSE_CALL_HIGH:
                extra = await sample_structured(
                    prompt,
                    EvaluationResult,
                    model=settings.llm_budget_model,
                    n=_SELF_CONSISTENCY_SAMPLES,
                )
                all_samples = [primary, *extra]
                avg_score = aggregate_scores(all_samples, "score")
                dis = disagreement(all_samples, "score")
                # The sample spread is a self-consistency honesty signal: when the
                # same model disagrees with itself on a close call, the verdict is
                # unstable — discount the score so the (often inflated) signal that
                # feeds best-of-N selection and downstream learning is more honest.
                adjusted = round(avg_score * (1.0 - 0.2 * dis), 4)
                # Take the most conservative violation set (most cautious verdict)
                canonical = most_conservative(all_samples) or primary
                return canonical.model_copy(
                    update={
                        "score": adjusted,
                        "disagreement": round(dis, 4),
                        "reasoning": (
                            f"self-consistency ({len(all_samples)} samples, avg={avg_score:.2f}, "
                            f"disagreement={dis:.2f}): {canonical.reasoning}"
                        ),
                    }
                )

            return primary
        except Exception as exc:
            logger.warning("PhaseEvaluator failed (non-fatal): %s", exc)
            return EvaluationResult(score=0.5, reasoning="evaluation error")
