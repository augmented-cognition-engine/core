"""Safety limits — max turns, cost ceiling, execution guards.

Prevents runaway loops and unexpected costs.
"""

from __future__ import annotations

from pydantic import BaseModel


class SafetyLimits(BaseModel):
    """Configurable safety boundaries for a runtime session."""

    max_turns: int = 100
    max_cost_usd: float | None = None

    def check_turn(self, turn_count: int) -> tuple[bool, str]:
        if turn_count > self.max_turns:
            return False, f"Reached max_turns limit ({self.max_turns})"
        return True, ""

    def check_cost(self, cost_usd: float) -> tuple[bool, str]:
        if self.max_cost_usd is not None and cost_usd > self.max_cost_usd:
            return False, f"Cost ${cost_usd:.4f} exceeds budget ${self.max_cost_usd:.4f}"
        return True, ""
