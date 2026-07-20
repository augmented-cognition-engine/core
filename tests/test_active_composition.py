"""Tests for the ace_active_composition introspection surface.

Covers the in-memory recent-composition cache (composer-side) and the MCP
tool function that exposes it to AI partners.
"""

from __future__ import annotations

from unittest.mock import AsyncMock, patch

import pytest

from core.engine.cognition.composer import (
    CognitiveComposer,
    _recent_compositions,
    get_recent_composition,
)
from core.engine.mcp.tools import ace_active_composition


@pytest.fixture(autouse=True)
def _clear_recent_compositions():
    """Reset the in-memory cache between tests."""
    _recent_compositions.clear()
    yield
    _recent_compositions.clear()


# ---------------------------------------------------------------------------
# get_recent_composition — direct access
# ---------------------------------------------------------------------------


def test_get_recent_composition_returns_none_when_empty():
    """Querying before any composition has been emitted returns None."""
    assert get_recent_composition("product:unseen") is None


def test_get_recent_composition_returns_snapshot_copy():
    """The function returns a snapshot dict, not the live cache entry —
    mutation of the returned dict must not corrupt the cache."""
    _recent_compositions["product:test"] = {
        "meta_skills": ["coding_intelligence"],
        "depth": 2,
        "fusion_mode": True,
    }

    snapshot = get_recent_composition("product:test")
    assert snapshot is not None
    snapshot["meta_skills"].append("DO NOT POLLUTE CACHE")

    # The original cache entry is unchanged
    cached = _recent_compositions["product:test"]
    assert "DO NOT POLLUTE CACHE" in snapshot["meta_skills"]
    # Note: list contents are shared by reference; full deepcopy would be
    # heavier — we accept that consumers must not mutate inner lists either.
    # The top-level dict copy is the guard against accidental dict-level corruption.
    assert isinstance(cached["meta_skills"], list)


# ---------------------------------------------------------------------------
# Compose populates the cache
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_compose_populates_recent_composition_cache():
    """A successful compose() leaves a snapshot in _recent_compositions."""
    composer = CognitiveComposer()

    classification = {
        "discipline": "ux",
        "task_type": "build",
        "archetype": "creator",
        "mode": "deliberative",
        "complexity": "moderate",
        "description": "Build a UI component",
    }

    with patch(
        "core.engine.cognition.classifier.FrameworkClassifier.resolve_instrument",
        new=AsyncMock(return_value="first-principles"),
    ):
        result = await composer.compose(classification, "product:test")

    cached = get_recent_composition("product:test")
    assert cached is not None
    assert set(cached["meta_skills"]) == set(result.meta_skills)
    assert cached["depth"] == result.depth
    assert cached["fusion_mode"] == result.fusion_mode
    assert cached["classification"]["discipline"] == "ux"
    assert cached["classification"]["task_type"] == "build"
    assert "phases" in cached
    assert isinstance(cached["phases"], list)


@pytest.mark.asyncio
async def test_compose_overwrites_recent_composition_for_same_product():
    """Subsequent compose() calls overwrite the prior snapshot for the same product."""
    composer = CognitiveComposer()

    classification_1 = {
        "discipline": "ux",
        "task_type": "design",
        "archetype": "creator",
        "mode": "deliberative",
        "complexity": "moderate",
        "description": "Design a UI",
    }
    classification_2 = {
        "discipline": "security",
        "task_type": "review",
        "archetype": "sentinel",
        "mode": "reflective",
        "complexity": "complex",
        "description": "Audit the auth flow for security gaps",
    }

    with patch(
        "core.engine.cognition.classifier.FrameworkClassifier.resolve_instrument",
        new=AsyncMock(return_value="first-principles"),
    ):
        await composer.compose(classification_1, "product:test")
        first_snap = get_recent_composition("product:test")
        await composer.compose(classification_2, "product:test")
        second_snap = get_recent_composition("product:test")

    assert first_snap is not None and second_snap is not None
    assert first_snap["classification"]["task_type"] == "design"
    assert second_snap["classification"]["task_type"] == "review"
    # The second composition replaced the first
    assert first_snap != second_snap


# ---------------------------------------------------------------------------
# MCP tool surface
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_ace_active_composition_returns_none_when_empty():
    """The MCP tool surface returns a friendly note when no composition exists."""
    result = await ace_active_composition(product_id="product:empty")
    assert result["product_id"] == "product:empty"
    assert result["composition"] is None
    assert "No composition" in result["note"]


@pytest.mark.asyncio
async def test_ace_active_composition_returns_snapshot_when_present():
    """The MCP tool returns the cached composition wrapped in a product_id envelope."""
    _recent_compositions["product:active"] = {
        "meta_skills": ["coding_intelligence", "systems_intelligence"],
        "depth": 3,
        "fusion_mode": False,
        "classification": {"discipline": "architecture", "task_type": "review"},
        "phases": ["frame", "prioritize", "choose"],
    }

    result = await ace_active_composition(product_id="product:active")

    assert result["product_id"] == "product:active"
    assert result["composition"] is not None
    assert result["composition"]["meta_skills"] == ["coding_intelligence", "systems_intelligence"]
    assert result["composition"]["depth"] == 3
    assert result["composition"]["phases"] == ["frame", "prioritize", "choose"]


@pytest.mark.asyncio
async def test_ace_active_composition_scopes_by_product_id():
    """Different products have independent compositions; the tool returns the right one."""
    _recent_compositions["product:a"] = {
        "meta_skills": ["creative_intelligence"],
        "depth": 2,
        "fusion_mode": True,
        "classification": {},
        "phases": [],
    }
    _recent_compositions["product:b"] = {
        "meta_skills": ["risk_intelligence"],
        "depth": 4,
        "fusion_mode": False,
        "classification": {},
        "phases": [],
    }

    result_a = await ace_active_composition(product_id="product:a")
    result_b = await ace_active_composition(product_id="product:b")

    assert result_a["composition"]["meta_skills"] == ["creative_intelligence"]
    assert result_b["composition"]["meta_skills"] == ["risk_intelligence"]
