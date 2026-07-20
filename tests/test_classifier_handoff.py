"""Tests for classifier handoff integration. Mocks the LLM call so tests
are deterministic — set discipline_confidence in the mocked response and
assert the handoff flag flows through."""

from __future__ import annotations

import pytest


@pytest.mark.asyncio
async def test_classifier_attaches_handoff_when_confidence_low(monkeypatch):
    """When the LLM's discipline_confidence < 0.4, classify_task attaches
    handoff_recommended=True and suggested_external_tool='Claude'."""
    from core.engine.cognition.handoff import HANDOFF_DEFAULT_TOOL
    from core.engine.orchestrator import classifier as classifier_mod

    fake_low_confidence = {
        "discipline": "ux",
        "discipline_confidence": 0.2,  # below threshold
        "archetype": "executor",
        "archetype_confidence": 0.7,
        "mode": "reactive",
        "mode_confidence": 0.7,
        "complexity": "simple",
        "complexity_confidence": 0.7,
        "perspective": "operator",
        "perspective_confidence": 0.7,
        "task_type": "implement",
        "task_type_confidence": 0.7,
        "quality_bar": "draft",
        "quality_bar_confidence": 0.7,
        "specialties": [],
        "org_context": [],
        "engagement": {"perspectives": ["executor"], "adversarial_pair": None, "rationale": "x"},
    }

    async def fake_complete_json(*args, **kwargs):
        return fake_low_confidence

    # Patch the LLM provider's complete_json
    monkeypatch.setattr(classifier_mod.llm, "complete_json", fake_complete_json)
    # Patch the catalog/corrections loaders to return empty strings (no DB call)

    async def empty_str(*args, **kwargs):
        return ""

    monkeypatch.setattr(classifier_mod, "_load_specialty_catalog", empty_str)
    monkeypatch.setattr(classifier_mod, "_load_routing_corrections", empty_str)

    result = await classifier_mod.classify_task("write me a poem about cats")
    assert result.get("handoff_recommended") is True
    assert result.get("suggested_external_tool") == HANDOFF_DEFAULT_TOOL


@pytest.mark.asyncio
async def test_classifier_omits_handoff_when_confidence_high(monkeypatch):
    """When discipline_confidence >= 0.4, handoff_recommended is False (or absent)."""
    from core.engine.orchestrator import classifier as classifier_mod

    fake_high_confidence = {
        "discipline": "security",
        "discipline_confidence": 0.92,  # well above threshold
        "archetype": "sentinel",
        "archetype_confidence": 0.85,
        "mode": "deliberative",
        "mode_confidence": 0.8,
        "complexity": "moderate",
        "complexity_confidence": 0.8,
        "perspective": "practitioner",
        "perspective_confidence": 0.8,
        "task_type": "review",
        "task_type_confidence": 0.85,
        "quality_bar": "production",
        "quality_bar_confidence": 0.8,
        "specialties": [],
        "org_context": [],
        "engagement": {"perspectives": ["sentinel"], "adversarial_pair": None, "rationale": "x"},
    }

    async def fake_complete_json(*args, **kwargs):
        return fake_high_confidence

    async def empty_str(*args, **kwargs):
        return ""

    monkeypatch.setattr(classifier_mod.llm, "complete_json", fake_complete_json)
    monkeypatch.setattr(classifier_mod, "_load_specialty_catalog", empty_str)
    monkeypatch.setattr(classifier_mod, "_load_routing_corrections", empty_str)

    result = await classifier_mod.classify_task("audit our auth middleware for OWASP issues")
    assert result.get("handoff_recommended") is False
    assert result.get("suggested_external_tool") is None
