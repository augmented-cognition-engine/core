"""ConfidenceGate — determines when a phase output warrants additional retrieval.

Fires when phase confidence falls below threshold or unresolved gaps exist.
Used by MultiPhaseExecutor to trigger mid-phase intelligence retrieval.
Non-prescriptive: callers decide what to do when the gate fires.
"""

from __future__ import annotations

from core.engine.cognition.phase_output import PhaseOutput

_DEFAULT_CONFIDENCE_THRESHOLD = 0.6
_MAX_RETRIEVAL_TERMS = 5


class ConfidenceGate:
    """Gate that fires when a PhaseOutput warrants additional retrieval."""

    def __init__(self, confidence_threshold: float = _DEFAULT_CONFIDENCE_THRESHOLD) -> None:
        self._threshold = confidence_threshold

    def should_retrieve(self, phase_output: PhaseOutput) -> bool:
        """Return True if additional intelligence retrieval is warranted.

        Fires when:
        - confidence < threshold (model is uncertain about its output)
        - gaps list is non-empty (model identified unresolved questions)
        """
        if phase_output.confidence < self._threshold:
            return True
        if phase_output.gaps:
            return True
        return False

    def retrieval_query(self, phase_output: PhaseOutput) -> list[str]:
        """Return search terms derived from the phase's open gaps.

        Caps at _MAX_RETRIEVAL_TERMS to avoid noise in intelligence queries.
        """
        return phase_output.gaps[:_MAX_RETRIEVAL_TERMS]
