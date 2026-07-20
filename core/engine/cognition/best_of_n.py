"""BestOfNSampler — ranks PhaseCandidate objects by combined confidence + evaluator score.

Pure module: no I/O, no LLM calls. Used by MultiPhaseExecutor to select the
best candidate when lazy branching fires on uncertain phases.

Ranking formula: 0.6 × confidence + 0.4 × score
- Unscored candidates (score=0.0): ranked by confidence alone
- A high-score, lower-confidence candidate can beat a high-confidence, unscored one
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import TYPE_CHECKING

from core.engine.cognition.phase_output import PhaseOutput

if TYPE_CHECKING:
    from core.engine.cognition.phase_evaluator import EvaluationResult

_WEIGHT_CONFIDENCE = 0.6
_WEIGHT_SCORE = 0.4


@dataclass
class PhaseCandidate:
    """A single candidate output from one LLM call for a phase.

    output: raw LLM response string (PhaseOutput JSON or fallback plain text)
    phase_output: parsed PhaseOutput (confidence, evidence, gaps)
    score: PhaseEvaluator score 0.0-1.0; 0.0 means unscored (not a bad score)
    evaluation_result: full EvaluationResult if evaluated; None if unscored
    """

    output: str
    phase_output: PhaseOutput
    score: float = field(default=0.0)
    evaluation_result: EvaluationResult | None = field(default=None)


class BestOfNSampler:
    """Selects the best PhaseCandidate by weighted confidence + evaluator score."""

    def select_best(self, candidates: list[PhaseCandidate]) -> PhaseCandidate:
        """Return the highest-ranked candidate.

        Raises ValueError if candidates is empty.
        """
        if not candidates:
            raise ValueError("candidates must be non-empty")
        if len(candidates) == 1:
            return candidates[0]
        return max(
            candidates,
            key=lambda c: _WEIGHT_CONFIDENCE * c.phase_output.confidence + _WEIGHT_SCORE * c.score,
        )
