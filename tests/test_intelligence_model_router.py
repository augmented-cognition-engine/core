# tests/test_intelligence_model_router.py
"""Tests for model routing."""

from core.engine.runtime.model_config import route_model


def test_haiku_for_extraction():
    model = route_model("extraction")
    assert "haiku" in model


def test_haiku_for_code_analysis():
    model = route_model("code_analysis")
    assert "haiku" in model  # High-volume — Haiku is sufficient and avoids rate limits


def test_sonnet_for_architecture():
    """architecture_decision routes to Sonnet — Opus is opt-in only."""
    model = route_model("architecture_decision", classification={"complexity": "complex"})
    assert "sonnet" in model
    assert "opus" not in model


def test_ceiling_limits():
    model = route_model(
        "architecture_decision",
        classification={"complexity": "complex"},
        ceiling="sonnet",
    )
    assert "sonnet" in model
    assert "opus" not in model


def test_default_for_unknown():
    model = route_model("unknown_task_type")
    assert "sonnet" in model  # default to sonnet


def test_classifier_override():
    """Strong classifier signals bump to Sonnet; Opus requires explicit ceiling='opus'."""
    model = route_model(
        "code_analysis",
        classification={
            "complexity": "complex",
            "archetype": "researcher",
            "mode": "exploratory",
        },
    )
    assert "sonnet" in model  # capped at Sonnet by default ceiling
    assert "opus" not in model
