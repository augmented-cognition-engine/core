# tests/test_ace_roadmap_tool.py
from unittest.mock import AsyncMock, patch

import pytest

import core.engine.mcp.tools as tools
from core.engine.product.roadmap_models import Roadmap, RoadmapItem, RoadmapStaleness


@pytest.mark.asyncio
async def test_ace_roadmap_renders_lanes():
    item = RoadmapItem(
        title="experience.accessibility",
        pillar="experience",
        discipline="accessibility",
        gap=0.4,
        rank=0.9,
        rationale="below floor",
        blocking_patterns=[],
        spec_status="building",
        staleness=RoadmapStaleness.FRESH,
        lane="now",
        cbt=0,
    )
    fake = Roadmap(
        product_id="product:platform",
        lanes={"now": [item], "next": [], "blocked": [], "parked": [], "done": []},
        ambition_summary="",
    )
    with patch.object(tools, "compute_roadmap", new=AsyncMock(return_value=fake)):
        result = await tools.ace_roadmap(product_id="product:platform")
    assert result["lanes"]["now"][0]["title"] == "experience.accessibility"
    assert result["lanes"]["now"][0]["spec_status"] == "building"
