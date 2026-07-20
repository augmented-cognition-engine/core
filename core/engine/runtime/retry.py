"""Retry policy — model-config-driven exponential backoff.

Retry parameters come from model_config.py (YAML-driven),
not hardcoded Claude Code constants. Different models have
different rate limit profiles.
"""

from __future__ import annotations

import random

RETRYABLE_CODES = {429, 500, 502, 503, 529}


class RetryPolicy:
    """Retry policy with model-aware configuration."""

    def __init__(
        self,
        max_retries: int = 3,
        base_delay_ms: int = 500,
        max_529_before_fallback: int = 3,
        fallback_model: str | None = None,
    ) -> None:
        self.max_retries = max_retries
        self.base_delay_ms = base_delay_ms
        self.max_529_before_fallback = max_529_before_fallback
        self.fallback_model = fallback_model

    @classmethod
    def from_model_config(cls, model: str) -> "RetryPolicy":
        """Create policy from model config. Falls back to defaults."""
        try:
            from core.engine.runtime.model_config import ModelConfig

            config = ModelConfig()
            model_cfg = config.get(model)
            return cls(
                max_retries=model_cfg.get("max_retries", 3),
                base_delay_ms=model_cfg.get("base_delay_ms", 500),
                max_529_before_fallback=model_cfg.get("max_529_before_fallback", 3),
                fallback_model=model_cfg.get("weak_model"),
            )
        except Exception:
            return cls()

    def should_retry(self, attempt: int, error_code: int) -> bool:
        if attempt > self.max_retries:
            return False
        return error_code in RETRYABLE_CODES

    def get_delay_ms(self, attempt: int) -> int:
        delay = self.base_delay_ms * (2 ** (attempt - 1))
        jitter = random.randint(0, delay // 4)
        return delay + jitter

    def should_fallback(self, consecutive_529: int) -> bool:
        return consecutive_529 >= self.max_529_before_fallback
