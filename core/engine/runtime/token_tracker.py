"""Per-conversation token tracking.

Tracks input/output tokens across turns. Provides:
- Context size estimation (for compaction decisions)
- Cost tracking (USD estimate)
- Compaction threshold detection
"""

from __future__ import annotations

AUTOCOMPACT_BUFFER = 13_000  # Same as Claude Code's AUTOCOMPACT_BUFFER_TOKENS

# Pricing per million tokens (Sonnet 4.6 default)
DEFAULT_INPUT_COST = 3.0
DEFAULT_OUTPUT_COST = 15.0
DEFAULT_CACHE_READ_COST = 0.3


class TokenTracker:
    """Track token usage across a conversation."""

    def __init__(
        self,
        context_window: int = 200_000,
        input_cost_per_m: float = DEFAULT_INPUT_COST,
        output_cost_per_m: float = DEFAULT_OUTPUT_COST,
    ) -> None:
        self._context_window = context_window
        self._input_cost = input_cost_per_m
        self._output_cost = output_cost_per_m
        self._turns: list[dict[str, int]] = []

    def record_turn(self, input_tokens: int, output_tokens: int) -> None:
        """Record token usage from one model call."""
        self._turns.append({"input": input_tokens, "output": output_tokens})

    @property
    def total_input(self) -> int:
        return sum(t["input"] for t in self._turns)

    @property
    def total_output(self) -> int:
        return sum(t["output"] for t in self._turns)

    @property
    def turn_count(self) -> int:
        return len(self._turns)

    @property
    def estimated_context_tokens(self) -> int:
        """Estimate current context size from last API response."""
        if not self._turns:
            return 0
        return self._turns[-1]["input"]

    @property
    def estimated_cost_usd(self) -> float:
        """Rough USD cost estimate."""
        return (self.total_input * self._input_cost + self.total_output * self._output_cost) / 1_000_000

    def should_compact(self) -> bool:
        """Check if context size exceeds compaction threshold."""
        threshold = self._context_window - AUTOCOMPACT_BUFFER
        return self.estimated_context_tokens >= threshold

    def estimate_tokens(self, messages: list) -> int:
        """Local token estimate from message content length.

        Uses ~4 chars/token approximation (English + code average).
        Not API-accurate — used for compaction marker display only.
        """
        total_chars = sum(len(getattr(m, "content", "") or "") for m in messages)
        return total_chars // 4

    def summary(self) -> dict:
        return {
            "turn_count": self.turn_count,
            "total_input": self.total_input,
            "total_output": self.total_output,
            "estimated_context": self.estimated_context_tokens,
            "estimated_cost_usd": round(self.estimated_cost_usd, 4),
        }
