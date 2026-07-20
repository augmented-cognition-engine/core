"""Static per-model token cost rates.

Used by composition_signal_hook (F: overthinking-tax surfacing) to compute
actual cost and the cost of running on an alternative model. Rates are
$/million-tokens, hand-maintained — there is no live API for these.

Add a model: register its (input_rate, output_rate, alternative) in MODEL_RATES.
"""

from __future__ import annotations

# Per-million-token rates in USD. Maintained from Anthropic public pricing.
# (input_rate_per_million, output_rate_per_million)
MODEL_RATES: dict[str, tuple[float, float]] = {
    "claude-haiku-4-5-20251001": (0.80, 4.00),
    # Sonnet 5 introductory pricing through 2026-08-31; re-audit afterward.
    "claude-sonnet-5": (2.00, 10.00),
    "claude-opus-4-8": (5.00, 25.00),
    "claude-fable-5": (10.00, 50.00),
    "claude-sonnet-4-6": (3.00, 15.00),
    "claude-opus-4-6": (15.00, 75.00),
    "gpt-5.6-luna": (1.00, 6.00),
    "gpt-5.6-terra": (2.50, 15.00),
    "gpt-5.6-sol": (5.00, 30.00),
}

# Alternative routing: which model would we route to for a cost comparison?
# Used by F to compute "would running on the next tier have cost less in total?"
MODEL_ALTERNATIVES: dict[str, str] = {
    "claude-haiku-4-5-20251001": "claude-sonnet-5",
    "claude-sonnet-5": "claude-opus-4-8",
    "claude-opus-4-8": "claude-fable-5",
    "gpt-5.6-luna": "gpt-5.6-terra",
    "gpt-5.6-terra": "gpt-5.6-sol",
    # Compatibility chain for historical receipts.
    "claude-sonnet-4-6": "claude-opus-4-6",
}


def cost_for_call(model: str, input_tokens: int, output_tokens: int) -> float:
    """Cost in USD for one LLM call. Unknown models return 0.0 (no false alarms)."""
    rates = MODEL_RATES.get(model)
    if rates is None:
        return 0.0
    input_rate, output_rate = rates
    return (input_tokens * input_rate + output_tokens * output_rate) / 1_000_000


def alternative_model_for(model: str) -> str | None:
    """Return the next-tier model name for cost comparison, or None if no tier above."""
    return MODEL_ALTERNATIVES.get(model)
