# tests/test_ace_load_related.py
"""ace_load surfaces 1-hop graph neighbors as a `related` field, and load_intelligence
wires the same shared expander as dual_loader (Cognify M3 fast-follow)."""

from unittest.mock import AsyncMock, patch

import pytest


@pytest.mark.asyncio
async def test_ace_load_surfaces_related_and_excludes_neighbors_from_general():
    import core.engine.mcp.tools as tools

    snapshot = {
        "insights": [
            {"id": "insight:own", "content": "own", "insight_type": "fact"},
            {
                "id": "insight:nbr",
                "content": "nbr",
                "insight_type": "fact",
                "source_graph": "graph_neighbor",
                "relationship": "depends_on",
                "via_insight": "insight:own",
            },
        ],
        "relationship_neighbors": [
            {
                "insight_id": "insight:nbr",
                "content": "nbr",
                "relationship": "depends_on",
                "direction": "outgoing",
                "via_insight": "insight:own",
                "edge_confidence": 0.9,
            },
        ],
        "total_count": 1,
    }
    with patch.object(tools, "load_intelligence", new=AsyncMock(return_value=snapshot)):
        result = await tools.ace_load("testing", product_id="product:test")

    assert len(result["related"]) == 1
    assert result["related"][0]["relationship"] == "depends_on"
    assert result["related"][0]["via_insight"] == "insight:own"
    # the folded graph_neighbor must NOT leak into the own-insight buckets
    assert [i["id"] for i in result["insights"]] == ["insight:own"]


@pytest.mark.asyncio
async def test_ace_load_related_empty_when_no_neighbors():
    import core.engine.mcp.tools as tools

    snapshot = {"insights": [{"id": "insight:own", "content": "own", "insight_type": "fact"}], "total_count": 1}
    with patch.object(tools, "load_intelligence", new=AsyncMock(return_value=snapshot)):
        result = await tools.ace_load("testing", product_id="product:test")
    assert result["related"] == []
    assert [i["id"] for i in result["insights"]] == ["insight:own"]


def test_load_intelligence_wires_shared_expander():
    """load_intelligence uses the shared helper, not a private copy."""
    import core.engine.graph.insight_neighbors as inb
    import core.engine.orchestrator.loader as loader

    assert loader.expand_snapshot_relationships is inb.expand_snapshot_relationships


@pytest.mark.asyncio
async def test_ace_load_surfaces_tensions_partitioned_from_related():
    from unittest.mock import AsyncMock, patch

    import core.engine.mcp.tools as tools

    snapshot = {
        "insights": [{"id": "insight:own", "content": "own", "insight_type": "fact"}],
        "relationship_neighbors": [
            {"insight_id": "insight:brk", "relationship": "breaks", "content": "brk"},
            {"insight_id": "insight:dep", "relationship": "depends_on", "content": "dep"},
        ],
        "graph_tensions": {
            "tensions": [{"insight_id": "insight:brk", "relationship": "breaks", "content": "brk"}],
            "consequences": [],
        },
        "total_count": 1,
    }
    with patch.object(tools, "load_intelligence", new=AsyncMock(return_value=snapshot)):
        result = await tools.ace_load("testing", product_id="product:test")
    assert [t["insight_id"] for t in result["tensions"]["tensions"]] == ["insight:brk"]
    # related excludes the elevated tension id
    assert [r["insight_id"] for r in result["related"]] == ["insight:dep"]
