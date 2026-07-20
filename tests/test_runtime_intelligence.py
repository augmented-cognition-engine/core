# tests/test_runtime_intelligence.py
"""Tests for the pre-turn intelligence layer."""

from unittest.mock import AsyncMock, patch

import pytest

from core.engine.runtime.intelligence import IntelligenceLayer


@pytest.mark.asyncio
async def test_classify_returns_discipline():
    layer = IntelligenceLayer(product_id="product:test")
    with patch("core.engine.runtime.intelligence.classify_task", new_callable=AsyncMock) as mock_classify:
        mock_classify.return_value = {
            "discipline": "security",
            "archetype": "analyst",
            "mode": "deliberative",
            "complexity": "moderate",
            "perspective": "practitioner",
            "specialties": ["owasp-top-10"],
            "org_context": [],
            "engagement": {"perspectives": ["practitioner"], "adversarial_pair": None, "rationale": ""},
        }
        result = await layer.classify("review this code for SQL injection")
        assert result["discipline"] == "security"
        assert result["archetype"] == "analyst"


@pytest.mark.asyncio
async def test_load_intelligence_returns_context():
    layer = IntelligenceLayer(product_id="product:test")
    classification = {
        "discipline": "security",
        "archetype": "analyst",
        "mode": "deliberative",
        "specialties": ["owasp-top-10"],
        "org_context": [],
    }
    with patch("core.engine.runtime.intelligence.load_intelligence", new_callable=AsyncMock) as mock_load:
        mock_load.return_value = {
            "insights": [
                {"insight_type": "pattern", "content": "Always use parameterized queries", "confidence": 0.95},
            ],
            "recent_signals": [],
        }
        context = await layer.load(classification)
        assert "parameterized queries" in context
        mock_load.assert_called_once()


@pytest.mark.asyncio
async def test_classify_and_load():
    """Full pipeline: classify then load."""
    layer = IntelligenceLayer(product_id="product:test")
    with patch("core.engine.runtime.intelligence.classify_task", new_callable=AsyncMock) as mock_c:
        mock_c.return_value = {
            "discipline": "testing",
            "archetype": "executor",
            "mode": "procedural",
            "specialties": [],
            "org_context": [],
            "complexity": "simple",
            "perspective": "practitioner",
            "engagement": {"perspectives": ["practitioner"], "adversarial_pair": None, "rationale": ""},
        }
        with patch("core.engine.runtime.intelligence.load_intelligence", new_callable=AsyncMock) as mock_l:
            mock_l.return_value = {"insights": [], "recent_signals": []}
            classification, context = await layer.classify_and_load("write unit tests")
            assert classification["discipline"] == "testing"
            assert isinstance(context, str)


@pytest.mark.asyncio
async def test_cache_persists_across_calls():
    """Intelligence cache should persist within a session."""
    layer = IntelligenceLayer(product_id="product:test")
    layer._intel_cache["security"] = "cached security intelligence"
    result = layer.get_cached("security")
    assert result == "cached security intelligence"


def test_clear_cache():
    layer = IntelligenceLayer(product_id="product:test")
    layer._intel_cache["security"] = "cached"
    layer.clear_cache()
    assert layer.get_cached("security") is None
