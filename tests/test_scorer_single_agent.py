# tests/test_scorer_single_agent.py
from unittest.mock import patch

import pytest

from core.engine.orchestration.composition_scorer import score_composition


@pytest.mark.asyncio
async def test_single_perspective_still_adjusts():
    """Single-perspective task still gets weight adjustment."""
    signals = [{"perspectives": ["practitioner"], "feedback": "rejected", "utilization_rate": 0.05} for _ in range(10)]
    with patch("core.engine.orchestration.composition_scorer._query_signals", return_value=signals):
        result = await score_composition(
            classification={
                "discipline": "testing",
                "perspectives": ["practitioner"],
                "engagement": {"perspectives": ["practitioner"]},
                "specialties": [],
                "archetype": "analyst",
                "mode": "reactive",
            },
            product_id="product:default",
        )
    assert result.perspective_weights["practitioner"] < 1.0
    assert len(result.perspectives) == 1


@pytest.mark.asyncio
async def test_injection_promotes_to_multi():
    """Perspective injection on single-agent task adds a second perspective."""
    signals = [{"perspectives": ["practitioner"], "feedback": "accepted", "utilization_rate": 0.7} for _ in range(10)]
    with patch("core.engine.orchestration.composition_scorer._query_signals", return_value=signals):
        result = await score_composition(
            classification={
                "discipline": "security",
                "perspectives": ["theorist"],
                "engagement": {"perspectives": ["theorist"]},
                "specialties": [],
                "archetype": "analyst",
                "mode": "reactive",
            },
            product_id="product:default",
        )
    assert "practitioner" in result.perspectives
    assert len(result.perspectives) == 2


@pytest.mark.asyncio
async def test_no_injection_when_below_threshold():
    """Perspectives below threshold are NOT injected."""
    signals = [{"perspectives": ["practitioner"], "feedback": "accepted", "utilization_rate": 0.3} for _ in range(10)]
    with patch("core.engine.orchestration.composition_scorer._query_signals", return_value=signals):
        result = await score_composition(
            classification={
                "discipline": "security",
                "perspectives": ["theorist"],
                "engagement": {"perspectives": ["theorist"]},
                "specialties": [],
                "archetype": "analyst",
                "mode": "reactive",
            },
            product_id="product:default",
        )
    assert "practitioner" not in result.perspectives
