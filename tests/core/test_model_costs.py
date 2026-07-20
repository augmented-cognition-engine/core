"""Tests for engine/core/model_costs.py — static per-model token cost rates."""

import pytest


@pytest.mark.unit
def test_cost_for_call_haiku_simple():
    """Haiku cost: 1000 input + 500 output tokens at the documented rate."""
    from core.engine.core.model_costs import cost_for_call

    cost = cost_for_call("claude-haiku-4-5-20251001", input_tokens=1000, output_tokens=500)
    # $0.80/M input, $4.00/M output → 1000*0.8/1e6 + 500*4.0/1e6 = 0.0008 + 0.002 = 0.0028
    assert abs(cost - 0.0028) < 1e-6


@pytest.mark.unit
def test_cost_for_call_sonnet():
    """Sonnet cost: 1000 input + 500 output tokens."""
    from core.engine.core.model_costs import cost_for_call

    cost = cost_for_call("claude-sonnet-5", input_tokens=1000, output_tokens=500)
    # $2.00/M input, $10.00/M output → 0.002 + 0.005 = 0.007
    assert abs(cost - 0.007) < 1e-6


@pytest.mark.unit
def test_cost_for_call_unknown_model_returns_zero():
    """Unknown model rates default to 0 (no false alarms)."""
    from core.engine.core.model_costs import cost_for_call

    cost = cost_for_call("claude-bogus-1", input_tokens=1000, output_tokens=500)
    assert cost == 0.0


@pytest.mark.unit
def test_alternative_model_routing():
    """alternative_model_for returns the next-tier model for cost comparison."""
    from core.engine.core.model_costs import alternative_model_for

    # Haiku's alternative is Sonnet (default model for ACE)
    assert alternative_model_for("claude-haiku-4-5-20251001") == "claude-sonnet-5"
    # Sonnet's alternative is Opus (reasoning model)
    assert alternative_model_for("claude-sonnet-5") == "claude-opus-4-8"
    # Unknown model has no alternative
    assert alternative_model_for("claude-bogus-1") is None
