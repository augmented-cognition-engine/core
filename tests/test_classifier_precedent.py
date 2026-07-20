# tests/test_classifier_precedent.py
"""Tests for apply_precedent_tiebreaker — the L5 classifier tie-breaker.

Spec §6.4 + TODO-12. Pure-function tests; no DB or LLM.
"""

from __future__ import annotations

from datetime import datetime, timezone

from core.engine.orchestrator.classifier import apply_precedent_tiebreaker
from core.engine.orchestrator.context import TieredDecision


def _td_cap(decision_id: str, discipline_hint: str | None) -> TieredDecision:
    """Factory for a capability-tier TieredDecision in tests."""
    return TieredDecision(
        decision_id=decision_id,
        title="t",
        rationale="r",
        decision_type="architecture",
        discipline_hint=discipline_hint,
        affected_capabilities=["auth"],
        created_at=datetime.now(timezone.utc),
        tier="capability",
        relevance_score=0.95,
        outcome="accepted",
        status=None,
        affected_capabilities_confidence=None,
    )


# -----------------------------------------------------------------------------
# Non-firing paths — guardrails first
# -----------------------------------------------------------------------------


def test_high_confidence_classification_not_overridden():
    """Classifier discipline_confidence >= 0.6 → no override applied (strictly additive)."""
    classifier_out = {"discipline": "testing", "discipline_confidence": 0.9}
    classification = {"recent_decisions": [_td_cap("decision:abc", "architecture")]}
    result = apply_precedent_tiebreaker(classifier_out, classification)
    assert result["discipline"] == "testing"
    assert "discipline_tiebreaker" not in result


def test_no_capability_tier_decision_no_override():
    """Even with low confidence, if recent_decisions has no capability-tier
    rows, the override doesn't fire."""
    discipline_decision = TieredDecision(
        decision_id="decision:disc",
        title="t",
        rationale="r",
        decision_type="architecture",
        discipline_hint="architecture",
        affected_capabilities=[],
        created_at=datetime.now(timezone.utc),
        tier="discipline",
        relevance_score=0.7,
        outcome="accepted",
        status=None,
        affected_capabilities_confidence=None,
    )
    classifier_out = {"discipline": "testing", "discipline_confidence": 0.4}
    classification = {"recent_decisions": [discipline_decision]}
    result = apply_precedent_tiebreaker(classifier_out, classification)
    assert result["discipline"] == "testing"
    assert "discipline_tiebreaker" not in result


def test_precedent_without_discipline_hint_no_override():
    """Cap-tier decision with discipline_hint=None doesn't provide an override
    signal, so the function returns unchanged classifier output."""
    classifier_out = {"discipline": "testing", "discipline_confidence": 0.3}
    classification = {"recent_decisions": [_td_cap("decision:abc", None)]}
    result = apply_precedent_tiebreaker(classifier_out, classification)
    assert result["discipline"] == "testing"
    assert "discipline_tiebreaker" not in result


def test_multi_turn_guard_skips_when_precedent_used_last_turn():
    """TODO-12: precedent already fired last turn → don't re-fire.

    Prevents ossifying a weak classification into a steady-state echo.
    """
    classifier_out = {"discipline": "testing", "discipline_confidence": 0.3}
    classification = {"recent_decisions": [_td_cap("decision:repeat", "architecture")]}
    task_meta = {"tiebreaker_history_last_turn": ["decision:repeat"]}
    result = apply_precedent_tiebreaker(classifier_out, classification, task_meta)
    assert result["discipline"] == "testing"
    assert "discipline_tiebreaker" not in result


# -----------------------------------------------------------------------------
# Firing path
# -----------------------------------------------------------------------------


def test_low_confidence_with_capability_precedent_overrides_discipline():
    classifier_out = {"discipline": "testing", "discipline_confidence": 0.4}
    classification = {"recent_decisions": [_td_cap("decision:abc", "architecture")]}
    result = apply_precedent_tiebreaker(classifier_out, classification)
    assert result["discipline"] == "architecture"
    assert result["discipline_tiebreaker"] == "decision:abc"
    assert result["tiebreaker_history"] == ["decision:abc"]


def test_override_does_not_mutate_input():
    classifier_out = {"discipline": "testing", "discipline_confidence": 0.4}
    classification = {"recent_decisions": [_td_cap("decision:abc", "architecture")]}
    result = apply_precedent_tiebreaker(classifier_out, classification)
    # Original input unchanged
    assert classifier_out["discipline"] == "testing"
    # Returned dict is a new object with the override
    assert result is not classifier_out
    assert result["discipline"] == "architecture"


def test_low_confidence_no_recent_decisions_no_override():
    """Empty recent_decisions list → no precedent → no override even on low conf."""
    classifier_out = {"discipline": "testing", "discipline_confidence": 0.3}
    classification = {"recent_decisions": []}
    result = apply_precedent_tiebreaker(classifier_out, classification)
    assert result["discipline"] == "testing"


def test_history_field_accumulates():
    """Successive tie-breaker fires on different precedents accumulate history."""
    classifier_out = {
        "discipline": "testing",
        "discipline_confidence": 0.3,
        "tiebreaker_history": ["decision:earlier"],
    }
    classification = {"recent_decisions": [_td_cap("decision:new", "architecture")]}
    result = apply_precedent_tiebreaker(classifier_out, classification)
    assert result["tiebreaker_history"] == ["decision:earlier", "decision:new"]
