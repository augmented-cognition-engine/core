# tests/test_model_config.py
"""Regression tests for engine/runtime/model_config.py.

Sentinel: Opus is opt-in only. Default ceiling is 'sonnet'.
Any task routing to Opus without an explicit ceiling="opus" is a regression.
"""

import pytest

from core.engine.runtime.model_config import MODEL_TIERS, TASK_ROUTING, route_model

SONNET = MODEL_TIERS["sonnet"]
HAIKU = MODEL_TIERS["haiku"]
OPUS = MODEL_TIERS["opus"]
FABLE = MODEL_TIERS["fable"]

# Tasks that were previously routed to Opus — must now return Sonnet by default
_FORMERLY_OPUS_TASKS = [
    "architecture_decision",
    "ambiguity_resolution",
    "cross_system_design",
    "risk_analysis",
    "complex_refactor",
]


@pytest.mark.parametrize("task_type", _FORMERLY_OPUS_TASKS)
def test_formerly_opus_tasks_route_to_sonnet_by_default(task_type):
    """Sentinel: formerly-Opus tasks must not produce Opus without explicit opt-in."""
    result = route_model(task_type)
    assert result == SONNET, (
        f"task_type={task_type!r} returned {result!r} — Opus is opt-in only; default ceiling must cap at Sonnet"
    )


def test_opus_reachable_via_ceiling_and_classifier_signals():
    """Opus is reachable when ceiling='opus' AND classifier signals are strong."""
    # Two Opus signals + ceiling='opus' → Opus
    classification = {"complexity": "complex", "archetype": "researcher"}
    result = route_model("implementation_simple", classification=classification, ceiling="opus")
    assert result == OPUS, "Strong classifier signals + ceiling='opus' should reach Opus tier"


def test_fable_is_a_distinct_explicit_frontier_ceiling():
    assert FABLE == "claude-fable-5"
    assert route_model("ambiguity_resolution", ceiling="fable") == OPUS


def test_default_ceiling_caps_at_sonnet():
    """route_model() with no ceiling argument must never return Opus."""
    for task_type in TASK_ROUTING:
        result = route_model(task_type)
        assert result != OPUS, (
            f"task_type={task_type!r} returned Opus without ceiling='opus' — default ceiling must be 'sonnet'"
        )


def test_haiku_tasks_unaffected():
    """Reader tasks must still resolve to Haiku."""
    haiku_tasks = ["classification", "extraction", "commit_message", "tool_summary"]
    for task in haiku_tasks:
        assert route_model(task) == HAIKU, f"{task!r} should still route to Haiku"


def test_classifier_signals_cannot_exceed_sonnet_without_ceiling():
    """Strong classifier signals (2+ Opus signals) must be capped at Sonnet by default."""
    classification = {"complexity": "complex", "archetype": "researcher"}
    result = route_model("implementation_simple", classification=classification)
    assert result != OPUS, (
        "Classifier signals bumped to Opus without ceiling='opus' — default ceiling must cap escalations at Sonnet"
    )


def test_classifier_signals_reach_opus_with_explicit_ceiling():
    """With ceiling='opus', strong signals must be allowed to escalate to Opus."""
    classification = {"complexity": "complex", "archetype": "researcher"}
    result = route_model("implementation_simple", classification=classification, ceiling="opus")
    assert result == OPUS


def test_ambiguity_resolution_unlocks_opus_with_ceiling():
    """ambiguity_resolution maps to 'opus' tier intentionally — input disambiguation is highest-stakes.
    Default ceiling caps it at Sonnet; callers must pass ceiling=settings.llm_reasoning_model to unlock.
    """
    # Default ceiling → Sonnet (safe)
    assert route_model("ambiguity_resolution") == SONNET
    # Explicit Opus ceiling → Opus (opt-in)
    assert route_model("ambiguity_resolution", ceiling="opus") == OPUS
