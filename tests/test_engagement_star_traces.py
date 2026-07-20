# tests/test_engagement_star_traces.py
"""Tests for _spins_to_phase_traces — Gap 2 closure.

Verifies the engagement path builds non-empty phase_traces from SpinOutputs
so STaR writes carry real reasoning data instead of an empty list.
"""

from __future__ import annotations

import pytest

from core.engine.orchestration.executor import _spins_to_phase_traces
from core.engine.orchestrator.engagement_models import SpinOutput


def _spin(perspective: str, confidence: float, content: str = "output") -> SpinOutput:
    return SpinOutput(
        content=content,
        handoff="next...",
        confidence=confidence,
        open_questions=[],
        perspective=perspective,
        specialties_used=[],
    )


def test_spins_to_phase_traces_returns_one_entry_per_spin():
    spins = [_spin("practitioner", 0.85), _spin("analyst", 0.72)]
    traces = _spins_to_phase_traces(spins)
    assert len(traces) == 2


def test_spins_to_phase_traces_uses_perspective_as_phase_name():
    traces = _spins_to_phase_traces([_spin("strategist", 0.9)])
    assert traces[0]["phase_name"] == "strategist"


def test_spins_to_phase_traces_carries_confidence():
    traces = _spins_to_phase_traces([_spin("executor", 0.77)])
    assert traces[0]["confidence"] == pytest.approx(0.77)


def test_spins_to_phase_traces_carries_content():
    traces = _spins_to_phase_traces([_spin("analyst", 0.8, content="deep analysis here")])
    assert "deep analysis here" in traces[0]["output"]


def test_spins_to_phase_traces_empty_spins_returns_empty():
    assert _spins_to_phase_traces([]) == []
