# tests/test_dual_loader_graph_expansion.py
# Tests the shared snapshot-expansion helper (lives in insight_neighbors, used by
# dual_loader + load_intelligence + ace_load). File kept under this name so it stays
# exempt from the conftest graph-expansion autouse disable.
from unittest.mock import AsyncMock, patch

import pytest

import core.engine.graph.insight_neighbors as inb


def _snapshot(insights):
    return {"insights": list(insights)}


@pytest.mark.asyncio
async def test_expand_folds_neighbors(monkeypatch):
    monkeypatch.setattr(inb.settings, "graph_expansion_enabled", True)
    snap = _snapshot([{"id": "insight:a", "content": "A", "confidence": 0.9}])
    neighbors = [
        {
            "insight_id": "insight:b",
            "content": "B",
            "confidence": 0.8,
            "insight_type": "fact",
            "relationship": "depends_on",
            "direction": "outgoing",
            "via_insight": "insight:a",
            "edge_confidence": 0.9,
        },
    ]
    with patch.object(inb, "load_insight_neighbors", new=AsyncMock(return_value=neighbors)):
        await inb.expand_snapshot_relationships(snap, "product:test")
    assert len(snap["relationship_neighbors"]) == 1
    folded = [i for i in snap["insights"] if i.get("source_graph") == "graph_neighbor"]
    assert len(folded) == 1
    assert folded[0]["id"] == "insight:b"
    assert folded[0]["relationship"] == "depends_on"
    assert folded[0]["via_insight"] == "insight:a"


@pytest.mark.asyncio
async def test_expand_dedupes_vs_loaded(monkeypatch):
    monkeypatch.setattr(inb.settings, "graph_expansion_enabled", True)
    snap = _snapshot(
        [{"id": "insight:a", "content": "A", "confidence": 0.9}, {"id": "insight:b", "content": "B", "confidence": 0.5}]
    )
    neighbors = [
        {
            "insight_id": "insight:b",
            "content": "B",
            "confidence": 0.5,
            "insight_type": "fact",
            "relationship": "solves",
            "direction": "outgoing",
            "via_insight": "insight:a",
            "edge_confidence": 0.8,
        }
    ]
    with patch.object(inb, "load_insight_neighbors", new=AsyncMock(return_value=neighbors)):
        await inb.expand_snapshot_relationships(snap, "product:test")
    assert snap["relationship_neighbors"] == []  # insight:b already loaded
    assert len(snap["insights"]) == 2  # unchanged


@pytest.mark.asyncio
async def test_expand_gated_off_sets_empty(monkeypatch):
    monkeypatch.setattr(inb.settings, "graph_expansion_enabled", False)
    snap = _snapshot([{"id": "insight:a", "content": "A", "confidence": 0.9}])
    called = AsyncMock(return_value=[{"insight_id": "insight:b"}])
    with patch.object(inb, "load_insight_neighbors", new=called):
        await inb.expand_snapshot_relationships(snap, "product:test")
    assert snap["relationship_neighbors"] == []
    assert len(snap["insights"]) == 1
    called.assert_not_called()


@pytest.mark.asyncio
async def test_expand_non_fatal(monkeypatch):
    monkeypatch.setattr(inb.settings, "graph_expansion_enabled", True)
    snap = _snapshot([{"id": "insight:a", "content": "A", "confidence": 0.9}])
    with patch.object(inb, "load_insight_neighbors", new=AsyncMock(side_effect=RuntimeError("boom"))):
        await inb.expand_snapshot_relationships(snap, "product:test")
    assert snap["relationship_neighbors"] == []
    assert len(snap["insights"]) == 1


@pytest.mark.asyncio
async def test_expand_no_seeds(monkeypatch):
    monkeypatch.setattr(inb.settings, "graph_expansion_enabled", True)
    snap = _snapshot([])
    called = AsyncMock(return_value=[])
    with patch.object(inb, "load_insight_neighbors", new=called):
        await inb.expand_snapshot_relationships(snap, "product:test")
    assert snap["relationship_neighbors"] == []
    called.assert_not_called()


@pytest.mark.asyncio
async def test_dual_loader_wires_shared_expander():
    """dual_loader uses the shared helper (not a private copy)."""
    import core.engine.orchestrator.dual_loader as dl

    assert dl.expand_snapshot_relationships is inb.expand_snapshot_relationships
