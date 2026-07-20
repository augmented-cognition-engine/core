# tests/test_intelligence_cascade.py
"""Tests for cascade model routing."""

from unittest.mock import AsyncMock, patch

import pytest

from core.engine.intelligence.cascade_router import (
    MODEL_ROUTING,
    MODEL_TIERS,
    TIER_ORDER,
    CascadeRouter,
    _get_threshold,
    _next_tier,
    get_escalation_rates,
    route_model,
)


def test_route_model_haiku_tasks():
    assert "haiku" in route_model("code_analysis")
    assert "haiku" in route_model("extraction")
    assert "haiku" in route_model("classification")


def test_route_model_sonnet_tasks():
    assert "sonnet" in route_model("code_review")
    assert "sonnet" in route_model("implementation")
    assert "sonnet" in route_model("spec_generation")


def test_route_model_formerly_opus_tasks_now_sonnet():
    """architecture_decision and risk_analysis route to Sonnet — Opus is opt-in only."""
    assert "sonnet" in route_model("architecture_decision")
    assert "sonnet" in route_model("risk_analysis")


def test_route_model_ceiling():
    model = route_model("architecture_decision", ceiling="sonnet")
    assert "sonnet" in model
    assert "opus" not in model


def test_route_model_classifier_override():
    """Strong classifier signals bump to Sonnet by default; Opus requires ceiling='opus'."""
    model = route_model(
        "code_analysis",
        classification={"complexity": "complex", "archetype": "researcher", "mode": "exploratory"},
    )
    assert "sonnet" in model  # capped at sonnet by default ceiling

    # Opus unlocked only with explicit ceiling
    opus_model = route_model(
        "code_analysis",
        classification={"complexity": "complex", "archetype": "researcher", "mode": "exploratory"},
        ceiling="opus",
    )
    assert "opus" in opus_model


def test_next_tier():
    assert _next_tier("haiku") == "sonnet"
    assert _next_tier("sonnet") == "opus"
    assert _next_tier("opus") == "fable"
    assert _next_tier("fable") is None


def test_threshold_defaults():
    assert _get_threshold("unknown_task", "haiku_to_sonnet") == 0.8
    # sonnet_to_opus removed from DEFAULT_THRESHOLDS — Opus is opt-in via ceiling, not threshold
    assert (
        _get_threshold("unknown_task", "sonnet_to_opus") == 0.8
    )  # falls back to DEFAULT_THRESHOLDS haiku_to_sonnet default


def test_threshold_overrides():
    assert _get_threshold("routing", "haiku_to_sonnet") == 0.85
    assert _get_threshold("verification_simple", "haiku_to_sonnet") == 0.9


def test_verification_complex_uses_default_threshold():
    """verification_complex has no custom threshold — it starts at Sonnet so haiku_to_sonnet never fires.
    Removing the dead entry means it falls back to the global default (0.8).
    """
    assert _get_threshold("verification_complex", "haiku_to_sonnet") == 0.8  # global default, not custom


def test_escalation_rates_empty():
    rates = get_escalation_rates()
    # Should return dict (may be empty or have prior test state)
    assert isinstance(rates, dict)


@pytest.mark.asyncio
async def test_cascade_high_confidence_no_escalation():
    """High confidence result should not escalate."""
    router = CascadeRouter()

    mock_result = {"result": {"purpose": "test"}, "confidence": 0.95}

    with patch("core.engine.core.llm.get_llm") as mock_llm:
        llm = AsyncMock()
        llm.complete_json = AsyncMock(return_value=mock_result)
        mock_llm.return_value = llm

        result = await router.call("code_analysis", "Analyze this file")
        assert result["confidence"] == 0.95
        assert "haiku" in result["tier"]
        assert not result["escalated"]
        assert len(result["tiers_used"]) == 1


@pytest.mark.asyncio
async def test_cascade_low_confidence_escalates():
    """Low confidence should escalate to next tier."""
    router = CascadeRouter()

    call_count = 0

    async def mock_complete_json(prompt, model=None):
        nonlocal call_count
        call_count += 1
        if call_count == 1:
            # First call (haiku) — low confidence
            return {"result": {"purpose": "maybe test?"}, "confidence": 0.5}
        else:
            # Second call (sonnet) — high confidence
            return {"result": {"purpose": "JWT validation"}, "confidence": 0.95}

    with patch("core.engine.core.llm.get_llm") as mock_llm:
        llm = AsyncMock()
        llm.complete_json = AsyncMock(side_effect=mock_complete_json)
        mock_llm.return_value = llm

        result = await router.call("code_analysis", "Analyze this file")
        assert result["escalated"]
        assert len(result["tiers_used"]) == 2
        assert result["tiers_used"] == ["haiku", "sonnet"]
        assert result["confidence"] == 0.95


@pytest.mark.asyncio
async def test_cascade_bulk_mode_no_escalation():
    """Bulk mode should accept low confidence without escalating."""
    router = CascadeRouter()

    mock_result = {"result": {"purpose": "test"}, "confidence": 0.3}

    with patch("core.engine.core.llm.get_llm") as mock_llm:
        llm = AsyncMock()
        llm.complete_json = AsyncMock(return_value=mock_result)
        mock_llm.return_value = llm

        result = await router.call("code_analysis", "Analyze this file", bulk_mode=True)
        assert not result["escalated"]
        assert result["confidence"] == 0.3
        assert len(result["tiers_used"]) == 1


@pytest.mark.asyncio
async def test_cascade_ceiling_prevents_escalation():
    """Ceiling should prevent going above the specified tier."""
    router = CascadeRouter(ceiling="haiku")

    mock_result = {"result": {"purpose": "test"}, "confidence": 0.3}

    with patch("core.engine.core.llm.get_llm") as mock_llm:
        llm = AsyncMock()
        llm.complete_json = AsyncMock(return_value=mock_result)
        mock_llm.return_value = llm

        result = await router.call("code_analysis", "Analyze this file")
        # Should NOT escalate because ceiling is haiku
        assert "haiku" in result["tier"]
        assert len(result["tiers_used"]) == 1


@pytest.mark.asyncio
async def test_cascade_passes_previous_attempt():
    """Escalated call should include the previous attempt as context."""
    router = CascadeRouter()

    prompts_received = []

    async def mock_complete_json(prompt, model=None):
        prompts_received.append(prompt)
        if len(prompts_received) == 1:
            return {"result": {"purpose": "weak"}, "confidence": 0.4}
        return {"result": {"purpose": "strong"}, "confidence": 0.95}

    with patch("core.engine.core.llm.get_llm") as mock_llm:
        llm = AsyncMock()
        llm.complete_json = AsyncMock(side_effect=mock_complete_json)
        mock_llm.return_value = llm

        await router.call("code_analysis", "Analyze this file")

        # Second prompt should reference the first attempt
        assert len(prompts_received) == 2
        assert "haiku" in prompts_received[1].lower() or "lower" in prompts_received[1].lower()
        assert "weak" in prompts_received[1]


def test_all_routing_keys_have_valid_tiers():
    """Every task type should map to a valid tier."""
    for task, tier in MODEL_ROUTING.items():
        assert tier in TIER_ORDER, f"{task} maps to invalid tier: {tier}"


def test_model_tiers_have_model_strings():
    """Every tier should have a model string."""
    for tier in TIER_ORDER:
        assert tier in MODEL_TIERS
        assert MODEL_TIERS[tier].startswith("claude-")
