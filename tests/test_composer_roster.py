"""Tests for CognitiveComposer roster output.

The roster field on CognitiveComposition lets the canvas frontend
materialize the agent-presence overlay on session open.
"""

from unittest.mock import AsyncMock, patch

import pytest

from core.engine.cognition.composer import (
    ARCHETYPE_COLOR_HINTS,
    ARCHETYPE_IDLE_ZONES,
    CognitiveComposer,
    _build_roster,
)


@pytest.fixture
def composer():
    return CognitiveComposer()


def test_build_roster_from_engagement_perspectives():
    classification = {
        "engagement": {"perspectives": ["analyst", "advisor"]},
    }
    roster = _build_roster(classification)
    assert len(roster) == 2
    assert {r["archetype"] for r in roster} == {"analyst", "advisor"}
    for entry in roster:
        assert "color_hint" in entry
        assert "idle_zone_hint" in entry


def test_build_roster_falls_back_to_single_archetype_when_no_perspectives():
    classification = {"archetype": "executor"}
    roster = _build_roster(classification)
    assert roster == [
        {
            "archetype": "executor",
            "color_hint": ARCHETYPE_COLOR_HINTS["executor"],
            "idle_zone_hint": ARCHETYPE_IDLE_ZONES["executor"],
        }
    ]


def test_build_roster_empty_when_no_archetypes():
    assert _build_roster({}) == []


def test_build_roster_caps_at_five():
    classification = {
        "engagement": {
            "perspectives": ["analyst", "advisor", "sentinel", "creator", "executor", "extra"],
        }
    }
    assert len(_build_roster(classification)) == 5


def test_build_roster_filters_falsy_entries():
    classification = {"engagement": {"perspectives": ["analyst", None, "", "advisor"]}}
    roster = _build_roster(classification)
    assert [r["archetype"] for r in roster] == ["analyst", "advisor"]


def test_build_roster_unknown_archetype_uses_neutral_hints():
    classification = {"engagement": {"perspectives": ["made_up_role"]}}
    roster = _build_roster(classification)
    assert roster[0] == {
        "archetype": "made_up_role",
        "color_hint": "neutral",
        "idle_zone_hint": "center",
    }


@pytest.mark.asyncio
async def test_compose_returns_roster_on_composition(composer):
    classification = {
        "discipline": "architecture",
        "task_type": "implement",
        "mode": "deliberative",
        "complexity": "moderate",
        "engagement": {"perspectives": ["analyst", "advisor"]},
    }
    with patch.object(composer._classifier, "resolve_instrument", new=AsyncMock(return_value="constraint-theory")):
        result = await composer.compose(classification, "product:test")
    assert hasattr(result, "roster")
    assert isinstance(result.roster, list)
    assert len(result.roster) == 2
    assert {r["archetype"] for r in result.roster} == {"analyst", "advisor"}


@pytest.mark.asyncio
async def test_compose_returns_empty_roster_when_classification_has_none(composer):
    classification = {
        "discipline": "architecture",
        "task_type": "code",
        "mode": "reactive",
        "complexity": "simple",
    }
    with patch.object(composer._classifier, "resolve_instrument", new=AsyncMock(return_value="first-principles")):
        result = await composer.compose(classification, "product:test")
    assert result.roster == []
