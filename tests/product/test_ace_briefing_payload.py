import pytest

from core.engine.mcp.tools import ace_briefing_payload


@pytest.mark.asyncio
async def test_ace_briefing_payload_returns_payload_shape(db_pool):
    result = await ace_briefing_payload(product_id="product:platform")
    assert isinstance(result, dict)
    expected_keys = {
        "current_phase",
        "phase_floors",
        "pillar_scores",
        "top_recommendations",
        "blocked_patterns",
        "open_uncertainty_queries",
    }
    assert expected_keys.issubset(set(result.keys()))


@pytest.mark.asyncio
async def test_ace_briefing_payload_phase_floors_have_seven_pillars(db_pool):
    result = await ace_briefing_payload(product_id="product:platform")
    expected_pillars = {
        "experience",
        "interface",
        "logic",
        "state",
        "operations",
        "evolution",
        "trust",
    }
    assert set(result["phase_floors"].keys()) == expected_pillars
