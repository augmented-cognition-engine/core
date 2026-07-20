"""Tests for voice surface registry."""

from __future__ import annotations

import pytest


def test_registry_has_8_surfaces():
    from core.engine.voice.surfaces import REGISTRY

    assert len(REGISTRY) == 8


def test_registry_has_required_fields():
    from core.engine.voice.surfaces import REGISTRY

    expected_names = {
        "briefing",
        "proactive_line",
        "discord",
        "in_app",
        "session_start",
        "journey_templates",
        "onboarding_copy",
        "drawer",
    }
    actual = {s.name for s in REGISTRY}
    assert actual == expected_names
    for surface in REGISTRY:
        assert isinstance(surface.enforce_at_write, bool)
        assert callable(surface.sample_provider)


def test_enforce_at_write_marks_static_surfaces():
    """journey_templates, onboarding_copy, and drawer are static surfaces CI can gate.

    drawer was briefly flipped to enforce_at_write=False (decision:rre2nyrpv0fih7y69ujr)
    while still aliasing _briefing_samples. That decision was resolved by introducing
    engine/voice/static_copy_extractor.py which scans partner-voice/ TSX components
    for static chrome strings — drawer is back as a write-gated surface.
    """
    from core.engine.voice.surfaces import REGISTRY

    static_surfaces = {s.name for s in REGISTRY if s.enforce_at_write}
    assert static_surfaces == {"journey_templates", "onboarding_copy", "drawer"}


@pytest.mark.asyncio
async def test_fixture_samples_returns_journey_templates():
    """journey_templates sample provider returns the canvas + bus topic templates."""
    from core.engine.voice.surfaces import REGISTRY

    surface = next(s for s in REGISTRY if s.name == "journey_templates")
    samples = await surface.sample_provider("product:platform")
    assert len(samples) > 0
    assert any("we" in s.lower() for s in samples)


@pytest.mark.asyncio
async def test_fixture_samples_returns_onboarding_copy():
    from core.engine.voice.surfaces import REGISTRY

    surface = next(s for s in REGISTRY if s.name == "onboarding_copy")
    samples = await surface.sample_provider("product:platform")
    # Opening + closing + 4*(prompt + ack) = 10
    assert len(samples) == 10
