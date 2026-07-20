"""Error recovery waterfall — one-shot guards prevent death spirals.

Recovery actions are informed by model config rather than hardcoded.
The nudge text and escalation targets adapt to the model's capabilities.
"""

from __future__ import annotations

MAX_OUTPUT_RECOVERY_LIMIT = 3


class ErrorRecovery:
    """Manages error recovery state with one-shot guards."""

    def __init__(self, model: str = "claude-sonnet-4-6") -> None:
        self._model = model
        self.has_attempted_compact = False
        self.max_output_recovery_count = 0

    def try_compact(self) -> bool:
        if self.has_attempted_compact:
            return False
        self.has_attempted_compact = True
        return True

    def try_max_output_recovery(self) -> bool:
        if self.max_output_recovery_count >= MAX_OUTPUT_RECOVERY_LIMIT:
            return False
        self.max_output_recovery_count += 1
        return True

    def get_recovery_nudge(self) -> str:
        """Generate nudge appropriate for the model and ACE's context."""
        return (
            "Output limit reached. Continue directly from where you stopped. "
            "No recap, no apology. If the task has multiple parts, "
            "focus on the most important remaining piece."
        )

    def get_escalated_max_tokens(self) -> int:
        """Get escalated max_tokens from model config."""
        try:
            from core.engine.runtime.model_config import ModelConfig

            config = ModelConfig()
            model_cfg = config.get(self._model)
            return min(model_cfg.get("max_tokens", 8192) * 2, 128000)
        except Exception:
            return 16384

    def reset(self) -> None:
        self.has_attempted_compact = False
        self.max_output_recovery_count = 0
