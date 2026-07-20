# tests/test_engagement_models.py
"""Tests for SpinOutput and EngagementResult pydantic models."""

from __future__ import annotations

from core.engine.orchestrator.engagement_models import EngagementResult, SpinOutput


def test_spin_output_defaults():
    spin = SpinOutput(
        content="some content",
        handoff="pass to next",
        confidence=0.8,
        perspective="analyst",
    )
    assert spin.open_questions == []
    assert spin.specialties_used == []


def test_spin_output_full():
    spin = SpinOutput(
        content="detailed analysis",
        handoff="escalate to researcher",
        confidence=0.95,
        open_questions=["What is the root cause?", "Is this repeatable?"],
        perspective="sentinel",
        specialties_used=["risk-analysis", "pattern-detection"],
    )
    assert spin.content == "detailed analysis"
    assert spin.handoff == "escalate to researcher"
    assert spin.confidence == 0.95
    assert spin.open_questions == ["What is the root cause?", "Is this repeatable?"]
    assert spin.perspective == "sentinel"
    assert spin.specialties_used == ["risk-analysis", "pattern-detection"]


def test_engagement_result_single_spin():
    spin = SpinOutput(
        content="solo take",
        handoff="done",
        confidence=0.7,
        perspective="creator",
    )
    result = EngagementResult(
        spins=[spin],
        merged_output="solo take",
        perspectives_used=["creator"],
    )
    assert len(result.spins) == 1
    assert result.adversarial_resolution is None
    assert result.injected_perspectives == []
    assert result.engagement_rationale == ""


def test_engagement_result_multi_spin():
    spin_a = SpinOutput(
        content="analyst view",
        handoff="hand to creator",
        confidence=0.85,
        perspective="analyst",
    )
    spin_b = SpinOutput(
        content="creator view",
        handoff="done",
        confidence=0.9,
        perspective="creator",
    )
    result = EngagementResult(
        spins=[spin_a, spin_b],
        merged_output="analyst view + creator view combined",
        perspectives_used=["analyst", "creator"],
    )
    assert len(result.spins) == 2
    assert result.merged_output == "analyst view + creator view combined"
    assert result.perspectives_used == ["analyst", "creator"]
    assert result.adversarial_resolution is None


def test_engagement_result_adversarial():
    spin_pro = SpinOutput(
        content="pro argument",
        handoff="challenge this",
        confidence=0.8,
        perspective="advisor",
    )
    spin_con = SpinOutput(
        content="counter argument",
        handoff="resolve",
        confidence=0.75,
        perspective="sentinel",
    )
    result = EngagementResult(
        spins=[spin_pro, spin_con],
        merged_output="balanced synthesis of both positions",
        perspectives_used=["advisor", "sentinel"],
        adversarial_resolution="Both perspectives highlight valid trade-offs; recommend option A.",
        injected_perspectives=[{"label": "devil's advocate", "weight": 0.3}],
        engagement_rationale="Adversarial pattern selected due to high-stakes decision.",
    )
    assert result.adversarial_resolution == "Both perspectives highlight valid trade-offs; recommend option A."
    assert result.injected_perspectives == [{"label": "devil's advocate", "weight": 0.3}]
    assert result.engagement_rationale == "Adversarial pattern selected due to high-stakes decision."
