"""Tests for the ace_product_pulse MCP tool."""

import pytest


@pytest.mark.integration
async def test_product_pulse_returns_top_items_with_rationale(monkeypatch):
    """The tool returns a dict with `items` (list of {title, source, rationale})."""
    from extensions.reference.tools import product_pulse

    async def _fake_health(product_id):
        return {"status": "yellow", "focus": "consolidate the importer story"}

    async def _fake_recent_decisions(product_id, limit=5):
        return [
            {"title": "Migrate auth", "rationale": "compliance"},
            {"title": "Sunset importer", "rationale": "tech-debt"},
        ]

    async def _fake_pending_gaps(product_id, limit=5):
        return [{"title": "No retention metrics", "score": 0.0}]

    monkeypatch.setattr(product_pulse, "_load_product_health", _fake_health)
    monkeypatch.setattr(product_pulse, "_load_recent_decisions", _fake_recent_decisions)
    monkeypatch.setattr(product_pulse, "_load_pending_gaps", _fake_pending_gaps)

    result = await product_pulse.ace_product_pulse(product_id="product:platform")
    assert "items" in result
    assert isinstance(result["items"], list)
    assert 1 <= len(result["items"]) <= 5
    for item in result["items"]:
        assert {"title", "source", "rationale"}.issubset(item.keys())
