"""Token budget — auto-continue with ACE-tuned thresholds.

ACE's intelligence-loaded prompts are larger than vanilla prompts
(discipline context, session memory, graph nodes). The thresholds
account for this: higher completion threshold because more tokens
are "productive" context, not filler.
"""

from __future__ import annotations

# ACE's prompts include intelligence context (~5-15K tokens extra)
# so we use a slightly higher threshold than Claude Code's 0.9
COMPLETION_THRESHOLD = 0.85

# ACE turns tend to produce more substantive output (intelligence-informed)
# so the diminishing returns threshold is higher
DIMINISHING_DELTA = 800


class TokenBudget:
    """Manages token budget for auto-continuation."""

    def __init__(self, total: int | None = None) -> None:
        self.total = total
        self._continuations: list[int] = []

    def record_continuation(self, tokens_at_check: int) -> None:
        self._continuations.append(tokens_at_check)

    def should_continue(self, current_tokens: int) -> str:
        if self.total is None or self.total <= 0:
            return "stop"

        if len(self._continuations) >= 3:
            deltas = [self._continuations[i] - self._continuations[i - 1] for i in range(1, len(self._continuations))]
            if len(deltas) >= 2 and all(d < DIMINISHING_DELTA for d in deltas[-2:]):
                return "stop"

        if current_tokens < self.total * COMPLETION_THRESHOLD:
            return "continue"

        return "stop"

    def get_nudge_message(self, current_tokens: int) -> str:
        pct = int((current_tokens / self.total) * 100) if self.total else 0
        return (
            f"Budget {pct}% used ({current_tokens:,} / {self.total:,}). "
            f"Continue — focus on the most impactful remaining work."
        )
