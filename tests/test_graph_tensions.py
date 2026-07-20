# tests/test_graph_tensions.py
from core.engine.graph.insight_neighbors import classify_tensions


def _n(rel):
    return {
        "insight_id": f"insight:{rel}",
        "relationship": rel,
        "content": rel,
        "direction": "outgoing",
        "via_insight": "insight:seed",
        "edge_confidence": 0.9,
    }


def test_classify_partitions_by_relationship_semantics():
    neighbors = [_n("breaks"), _n("reverts"), _n("causes"), _n("depends_on"), _n("solves")]
    out = classify_tensions(neighbors)
    assert [n["relationship"] for n in out["tensions"]] == ["breaks", "reverts"]
    assert [n["relationship"] for n in out["consequences"]] == ["causes"]
    assert {n["relationship"] for n in out["support"]} == {"depends_on", "solves"}


def test_classify_unknown_relationship_is_support():
    out = classify_tensions([_n("informed_by"), _n("mystery")])
    assert out["tensions"] == [] and out["consequences"] == []
    assert {n["relationship"] for n in out["support"]} == {"informed_by", "mystery"}


def test_classify_empty():
    out = classify_tensions([])
    assert out == {"tensions": [], "consequences": [], "support": []}


from unittest.mock import AsyncMock, patch

import pytest

import core.engine.graph.insight_neighbors as inb


@pytest.mark.asyncio
async def test_expand_sets_graph_tensions(monkeypatch):
    monkeypatch.setattr(inb.settings, "graph_expansion_enabled", True)
    snap = {"insights": [{"id": "insight:a", "content": "A", "confidence": 0.9}]}
    neighbors = [
        {
            "insight_id": "insight:b",
            "content": "B",
            "confidence": 0.8,
            "insight_type": "fact",
            "relationship": "breaks",
            "direction": "outgoing",
            "via_insight": "insight:a",
            "edge_confidence": 0.95,
        },
        {
            "insight_id": "insight:c",
            "content": "C",
            "confidence": 0.7,
            "insight_type": "fact",
            "relationship": "depends_on",
            "direction": "outgoing",
            "via_insight": "insight:a",
            "edge_confidence": 0.8,
        },
    ]
    with patch.object(inb, "load_insight_neighbors", new=AsyncMock(return_value=neighbors)):
        await inb.expand_snapshot_relationships(snap, "product:test")
    assert [n["insight_id"] for n in snap["graph_tensions"]["tensions"]] == ["insight:b"]
    assert snap["graph_tensions"]["consequences"] == []
    # additive: relationship_neighbors still carries all fresh neighbors (M3.1 contract intact)
    assert len(snap["relationship_neighbors"]) == 2


@pytest.mark.asyncio
async def test_expand_graph_tensions_empty_when_gated_off(monkeypatch):
    monkeypatch.setattr(inb.settings, "graph_expansion_enabled", False)
    snap = {"insights": [{"id": "insight:a", "content": "A"}]}
    await inb.expand_snapshot_relationships(snap, "product:test")
    assert snap["graph_tensions"] == {"tensions": [], "consequences": []}
