from __future__ import annotations

from unittest.mock import AsyncMock, patch

import pytest

from core.engine.intelligence.complexity_router import ComplexityRouter, ComplexityTier


def test_complexity_tier_values():
    assert ComplexityTier.SIMPLE == "simple"
    assert ComplexityTier.MODERATE == "moderate"
    assert ComplexityTier.COMPLEX == "complex"


def test_tier_model_map():
    from core.engine.intelligence.complexity_router import TIER_EXECUTOR, TIER_REVIEWER

    assert TIER_EXECUTOR[ComplexityTier.SIMPLE] == "claude-haiku-4-5-20251001"
    assert TIER_EXECUTOR[ComplexityTier.MODERATE] == "claude-sonnet-5"
    assert TIER_EXECUTOR[ComplexityTier.COMPLEX] == "claude-sonnet-5"
    assert TIER_REVIEWER[ComplexityTier.SIMPLE] == "claude-sonnet-5"
    assert TIER_REVIEWER[ComplexityTier.MODERATE] == "claude-sonnet-5"
    assert TIER_REVIEWER[ComplexityTier.COMPLEX] == "claude-opus-4-8"


@pytest.mark.parametrize(
    "keyword,expected_tier",
    [
        ("refactor the authentication module", ComplexityTier.COMPLEX),
        ("migrate database schema", ComplexityTier.COMPLEX),
        ("architecture decision for caching", ComplexityTier.COMPLEX),
        ("update across multi-file components", ComplexityTier.COMPLEX),
        ("add a docstring to this function", None),
    ],
)
def test_hard_rules(keyword, expected_tier):
    router = ComplexityRouter()
    tier = router._apply_hard_rules(keyword, "coding")
    assert tier == expected_tier


@pytest.mark.asyncio
async def test_assess_uses_hard_rule_without_llm_call():
    router = ComplexityRouter()
    with patch.object(router, "_llm_assess", new_callable=AsyncMock) as mock_llm:
        tier = await router.assess("refactor the entire auth module", "coding")
    assert tier == ComplexityTier.COMPLEX
    mock_llm.assert_not_called()


@pytest.mark.asyncio
async def test_assess_falls_back_to_moderate_on_llm_error():
    router = ComplexityRouter()
    with patch.object(router, "_llm_assess", new_callable=AsyncMock, side_effect=Exception("timeout")):
        tier = await router.assess("add docstring", "coding")
    assert tier == ComplexityTier.MODERATE
