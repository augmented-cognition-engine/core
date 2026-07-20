"""TALE-style per-task token budget + BATS-style per-build call budget.

Pure functions. Derive caps from classification's complexity and mode.
Soft caps — LLM may emit less; this prevents runaway long chains.

Sources:
  - TALE (https://arxiv.org/abs/2412.18547): per-task token budget by complexity
  - BATS (https://arxiv.org/abs/2511.17006): per-build call budget
"""

from __future__ import annotations

from typing import Any


def estimate_token_budget(classification: dict[str, Any]) -> int:
    """TALE-style per-phase token cap derived from classification.

    Returns max_tokens for one LLM call. Multi-phase recipes get this cap
    per phase, not per task — the composer scales by composition.depth
    implicitly (each phase is its own call).

    Defaults to moderate (2048) on unknown values — never blows up.
    """
    complexity = classification.get("complexity", "moderate")
    mode = classification.get("mode", "deliberative")

    if complexity == "simple":
        return 1024 if mode == "deliberative" else 512
    if complexity == "complex":
        return 6144 if mode == "deliberative" else 4096
    # moderate (and unknown fall-through)
    return 2048


def estimate_call_budget(classification: dict[str, Any]) -> int:
    """BATS-style call-count budget per build path.

    Returns max total LLM calls across `from_request_with_team`. When
    exceeded, the risk pass is skipped (synthesis still runs).

    Defaults to moderate (8) on unknown values.
    """
    complexity = classification.get("complexity", "moderate")
    return {"simple": 4, "moderate": 8, "complex": 16}.get(complexity, 8)
