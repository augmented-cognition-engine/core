"""Tests for _dominant_agent heuristic in forecaster."""

from core.engine.foresight.forecaster import _dominant_agent


def test_empty_perspectives_returns_ace_ghost():
    assert _dominant_agent([]) == "ace"
    assert _dominant_agent(None) == "ace"


def test_picks_highest_confidence():
    perspectives = [
        {"archetype": "pm", "contribution_summary": "x", "confidence": 0.6},
        {"archetype": "skeptic", "contribution_summary": "y", "confidence": 0.9},
        {"archetype": "advisor", "contribution_summary": "z", "confidence": 0.7},
    ]
    assert _dominant_agent(perspectives) == "skeptic"


def test_tie_breaks_on_option_label_match():
    perspectives = [
        {"archetype": "pm", "contribution_summary": "proposed JWT", "confidence": 0.8},
        {"archetype": "skeptic", "contribution_summary": "flagged cookies", "confidence": 0.8},
    ]
    assert _dominant_agent(perspectives, option_label="JWT") == "pm"
    assert _dominant_agent(perspectives, option_label="cookies") == "skeptic"


def test_falls_back_to_first_when_tied_with_no_match():
    perspectives = [
        {"archetype": "pm", "contribution_summary": "abc", "confidence": 0.7},
        {"archetype": "skeptic", "contribution_summary": "def", "confidence": 0.7},
    ]
    assert _dominant_agent(perspectives, option_label="zzz") == "pm"


def test_handles_missing_confidence():
    perspectives = [
        {"archetype": "pm", "contribution_summary": "x"},
        {"archetype": "skeptic", "contribution_summary": "y", "confidence": 0.5},
    ]
    # Missing confidence is treated as 0; skeptic should win
    assert _dominant_agent(perspectives) == "skeptic"
