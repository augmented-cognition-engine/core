"""Tests for engine/orchestration/composition_scorer.py::score_lens_composition."""

from unittest.mock import patch

import pytest


@pytest.mark.unit
async def test_default_weights_when_no_signals():
    """With <min_signals lens-set rows in window, all weights = 1.0 and no injections."""
    from core.engine.orchestration import composition_scorer as cs

    async def _no_signals(*args, **kwargs):
        return []

    with patch.object(cs, "_query_lens_signals", _no_signals):
        scored = await cs.score_lens_composition(
            {"discipline": "architecture"},
            "product:platform",
        )
    assert scored.lens_weights == {}
    assert scored.injected_lenses == []
    assert scored.preferred_lens_set is None


@pytest.mark.unit
async def test_penalty_when_lens_has_poor_outcome():
    """A lens that produced consistently low outcome_confidence gets weight < 1.0."""
    from core.engine.orchestration import composition_scorer as cs

    fake_signals = [
        {
            "lens": "architecture",
            "lens_set": ["architecture"],
            "outcome_confidence": 0.2,
            "feedback": None,
            "utilization_rate": 0.5,
            "engagement_type": "deep_committee",
            "mode_confidence": 0.8,
            "created_at": "2026-05-20T00:00:00Z",
        }
        for _ in range(10)
    ]

    async def _signals(*args, **kwargs):
        return fake_signals

    with patch.object(cs, "_query_lens_signals", _signals):
        scored = await cs.score_lens_composition(
            {"discipline": "architecture"},
            "product:platform",
        )
    assert "architecture" in scored.lens_weights
    assert scored.lens_weights["architecture"] < 1.0


@pytest.mark.unit
async def test_inject_missing_but_effective_lens():
    """A high-performing lens not in the queried discipline base set should appear in injected_lenses."""
    from core.engine.orchestration import composition_scorer as cs

    fake_signals = [
        {
            "lens": "security",
            "lens_set": ["architecture", "security"],
            "outcome_confidence": 0.9,
            "feedback": "accepted",
            "utilization_rate": 0.7,
            "engagement_type": "deep_committee",
            "mode_confidence": 0.9,
            "created_at": "2026-05-20T00:00:00Z",
        }
        for _ in range(10)
    ]

    async def _signals(*args, **kwargs):
        return fake_signals

    with patch.object(cs, "_query_lens_signals", _signals):
        scored = await cs.score_lens_composition(
            {"discipline": "architecture"},
            "product:platform",
        )
    # security appears in history with high outcome — should be injected
    assert "security" in scored.injected_lenses


@pytest.mark.unit
async def test_preferred_lens_set_when_one_combination_dominates():
    """When a specific lens_set has ≥min_signals AND high mean outcome, expose it."""
    from core.engine.orchestration import composition_scorer as cs

    fake_signals = [
        {
            "lens": "architecture",
            "lens_set": ["architecture", "data"],
            "outcome_confidence": 0.85,
            "feedback": "accepted",
            "utilization_rate": 0.7,
            "engagement_type": "deep_committee",
            "mode_confidence": 0.9,
            "created_at": "2026-05-20T00:00:00Z",
        }
        for _ in range(6)
    ]

    async def _signals(*args, **kwargs):
        return fake_signals

    with patch.object(cs, "_query_lens_signals", _signals):
        scored = await cs.score_lens_composition(
            {"discipline": "architecture"},
            "product:platform",
        )
    assert scored.preferred_lens_set == ["architecture", "data"]
