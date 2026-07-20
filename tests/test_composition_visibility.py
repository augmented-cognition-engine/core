"""Tests for L3 composition visibility — emit_composition_selected canvas event.

When CognitiveComposer.compose() produces a composition, it should emit a
canvas event so the Living Canvas (and any AI partners observing the substrate)
can see which meta-skills self-nominated for the current task.
"""

from __future__ import annotations

from unittest.mock import AsyncMock, patch

import pytest

from core.engine.cognition.composer import CognitiveComposer
from core.engine.events.canvas import (
    LivingCanvasEventType,
    emit_composition_selected,
)

# ---------------------------------------------------------------------------
# emit_composition_selected — direct API
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_emit_composition_selected_payload_shape():
    """The canvas event carries the meta-skills + depth + fusion_mode + classification slice."""
    emitted: list = []

    async def _capture(event_type, payload):
        emitted.append((event_type, payload))

    with patch("core.engine.events.canvas.bus.emit", new=AsyncMock(side_effect=_capture)):
        await emit_composition_selected(
            product_id="product:test",
            meta_skills=["creative_intelligence", "coding_intelligence"],
            depth=3,
            fusion_mode=False,
            classification={
                "task_type": "build",
                "discipline": "ux",
                "mode": "deliberative",
                "archetype": "creator",
                "complexity": "moderate",
                "confidence": 0.9,  # this should NOT appear in the payload
            },
        )

    assert len(emitted) == 1
    event_type, payload_dict = emitted[0]
    assert event_type == "canvas.composition.selected"
    assert payload_dict["event_type"] == LivingCanvasEventType.COMPOSITION_SELECTED.value
    inner = payload_dict["payload"]
    assert inner["meta_skills"] == ["creative_intelligence", "coding_intelligence"]
    assert inner["depth"] == 3
    assert inner["fusion_mode"] is False
    assert inner["classification"]["task_type"] == "build"
    assert inner["classification"]["discipline"] == "ux"
    # Confidence should NOT leak — payload is compact
    assert "confidence" not in inner["classification"]


@pytest.mark.asyncio
async def test_emit_composition_selected_no_classification():
    """Calling without classification still produces a valid event."""
    emitted: list = []

    async def _capture(event_type, payload):
        emitted.append((event_type, payload))

    with patch("core.engine.events.canvas.bus.emit", new=AsyncMock(side_effect=_capture)):
        await emit_composition_selected(
            product_id="product:test",
            meta_skills=["coding_intelligence"],
            depth=1,
            fusion_mode=True,
        )

    inner = emitted[0][1]["payload"]
    assert "classification" not in inner
    assert inner["meta_skills"] == ["coding_intelligence"]


@pytest.mark.asyncio
async def test_emit_composition_selected_provenance_is_classifier():
    """Composition events are attributed to the ACE classifier, not user."""
    emitted: list = []

    async def _capture(event_type, payload):
        emitted.append((event_type, payload))

    with patch("core.engine.events.canvas.bus.emit", new=AsyncMock(side_effect=_capture)):
        await emit_composition_selected(
            product_id="product:test",
            meta_skills=["coding_intelligence", "creative_intelligence"],
            depth=2,
            fusion_mode=True,
        )

    provenance = emitted[0][1]["provenance"]
    assert provenance["source"] == "ace_classifier"
    assert "2 meta-skill" in provenance["rationale"]


# ---------------------------------------------------------------------------
# Integration: CognitiveComposer.compose() emits the event
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_composer_compose_emits_composition_selected_event():
    """When compose() succeeds, it fires a canvas.composition.selected event.

    This is the load-bearing test for L3 visibility: the orchestra becomes
    legible because every selection produces an observable event.
    """
    composer = CognitiveComposer()

    classification = {
        "discipline": "ux",
        "task_type": "build",
        "archetype": "creator",
        "mode": "deliberative",
        "complexity": "moderate",
        "description": "Build a new UI component with strong visual hierarchy",
    }

    emitted: list = []

    async def _capture(event_type, payload):
        emitted.append((event_type, payload))

    with patch(
        "core.engine.cognition.classifier.FrameworkClassifier.resolve_instrument",
        new=AsyncMock(return_value="first-principles"),
    ):
        with patch("core.engine.events.canvas.bus.emit", new=AsyncMock(side_effect=_capture)):
            result = await composer.compose(classification, "product:test")

    # The composition itself should be valid
    assert result.meta_skills
    assert result.depth >= 1

    # Look for the composition.selected event among all emissions
    composition_events = [e for e in emitted if e[0] == "canvas.composition.selected"]
    assert len(composition_events) == 1, f"Expected 1 composition.selected event, got {len(composition_events)}"

    payload = composition_events[0][1]["payload"]
    assert set(payload["meta_skills"]) == set(result.meta_skills)
    assert payload["depth"] == result.depth
    assert payload["fusion_mode"] == result.fusion_mode
    assert payload["classification"]["task_type"] == "build"


@pytest.mark.asyncio
async def test_composer_compose_failure_does_not_crash_on_event_emit():
    """If the event emit fails, compose() still returns a valid composition."""
    composer = CognitiveComposer()

    classification = {
        "discipline": "ux",
        "task_type": "build",
        "archetype": "creator",
        "mode": "deliberative",
        "complexity": "moderate",
        "description": "Build a UI",
    }

    with patch(
        "core.engine.cognition.classifier.FrameworkClassifier.resolve_instrument",
        new=AsyncMock(return_value="first-principles"),
    ):
        with patch("core.engine.events.canvas.bus.emit", new=AsyncMock(side_effect=RuntimeError("bus down"))):
            result = await composer.compose(classification, "product:test")

    # Composition should still be returned despite bus failure
    assert result is not None
    assert result.meta_skills
