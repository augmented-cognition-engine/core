# tests/test_insight_neighbors.py
from unittest.mock import AsyncMock, patch

import pytest

from core.engine.graph.insight_neighbors import load_insight_neighbors


def _fake_pool(query_fn):
    """Patch the module pool with a fake connection whose .query runs query_fn."""
    mock_pool = patch("core.engine.graph.insight_neighbors.pool").start()
    mock_conn = AsyncMock()
    mock_conn.query = AsyncMock(side_effect=query_fn)
    mock_pool.connection.return_value.__aenter__ = AsyncMock(return_value=mock_conn)
    mock_pool.connection.return_value.__aexit__ = AsyncMock(return_value=False)
    return mock_pool, mock_conn


@pytest.mark.asyncio
async def test_outgoing_depends_on_edge_tagged(monkeypatch):
    async def q(sql, params=None):
        if "FROM insight" in sql:
            return [[{"id": "insight:nbr", "content": "Y", "confidence": 0.8, "insight_type": "fact"}]]
        if "FROM operational_relationship" in sql:
            return [[{"in": "insight:seed", "out": "insight:nbr", "predicate": "depends_on", "confidence": 0.9}]]
        return [[]]

    _fake_pool(q)
    try:
        out = await load_insight_neighbors(["insight:seed"], "product:test")
    finally:
        patch.stopall()
    assert len(out) == 1
    n = out[0]
    assert n["insight_id"] == "insight:nbr"
    assert n["relationship"] == "depends_on"
    assert n["direction"] == "outgoing"
    assert n["via_insight"] == "insight:seed"
    assert n["edge_confidence"] == 0.9
    assert n["content"] == "Y"


@pytest.mark.asyncio
async def test_incoming_direction_when_seed_is_out(monkeypatch):
    async def q(sql, params=None):
        if "FROM insight" in sql:
            return [[{"id": "insight:src", "content": "cause", "confidence": 0.7, "insight_type": "fact"}]]
        if "FROM operational_relationship" in sql:
            return [[{"in": "insight:src", "out": "insight:seed", "predicate": "causes", "confidence": 0.85}]]
        return [[]]

    _fake_pool(q)
    try:
        out = await load_insight_neighbors(["insight:seed"], "product:test")
    finally:
        patch.stopall()
    assert out[0]["insight_id"] == "insight:src"
    assert out[0]["direction"] == "incoming"


@pytest.mark.asyncio
async def test_relationship_query_uses_operational_projection_only():
    seen = []

    async def q(sql, params=None):
        seen.append(sql)
        return [[]]

    _fake_pool(q)
    try:
        await load_insight_neighbors(["insight:seed"], "product:test")
    finally:
        patch.stopall()
    edge_queries = [s for s in seen if "FROM insight" not in s]
    assert len(edge_queries) == 1
    assert "FROM operational_relationship" in edge_queries[0]


@pytest.mark.asyncio
async def test_dedupe_and_skip_self():
    """A neighbor equal to a seed is skipped; the same neighbor via two edges appears once."""

    async def q(sql, params=None):
        if "FROM insight" in sql:
            return [[{"id": "insight:nbr", "content": "Y", "confidence": 0.8, "insight_type": "fact"}]]
        if "FROM operational_relationship" in sql:
            return [
                [
                    {"in": "insight:seed", "out": "insight:nbr", "predicate": "depends_on", "confidence": 0.9},
                    {"in": "insight:seed", "out": "insight:nbr", "predicate": "solves", "confidence": 0.7},
                    {"in": "insight:seed", "out": "insight:seed", "predicate": "solves", "confidence": 0.95},
                ]
            ]  # self edge
        return [[]]

    _fake_pool(q)
    try:
        out = await load_insight_neighbors(["insight:seed"], "product:test")
    finally:
        patch.stopall()
    ids = [n["insight_id"] for n in out]
    assert ids == ["insight:nbr"]  # deduped; self-edge skipped


@pytest.mark.asyncio
async def test_total_cap_enforced():
    async def q(sql, params=None):
        if "FROM insight" in sql:
            return [
                [{"id": f"insight:n{i}", "content": "x", "confidence": 0.5, "insight_type": "fact"} for i in range(5)]
            ]
        if "FROM operational_relationship" in sql:
            return [
                [
                    {
                        "in": "insight:seed",
                        "out": f"insight:n{i}",
                        "predicate": "depends_on",
                        "confidence": 0.9 - i * 0.05,
                    }
                    for i in range(5)
                ]
            ]
        return [[]]

    _fake_pool(q)
    try:
        out = await load_insight_neighbors(["insight:seed"], "product:test", neighbors_per_seed=10, total_cap=2)
    finally:
        patch.stopall()
    assert len(out) == 2  # total_cap


@pytest.mark.asyncio
async def test_min_edge_confidence_floor():
    async def q(sql, params=None):
        if "FROM insight" in sql:
            return [[{"id": "insight:hi", "content": "x", "confidence": 0.5, "insight_type": "fact"}]]
        if "FROM operational_relationship" in sql:
            return [
                [
                    {"in": "insight:seed", "out": "insight:hi", "predicate": "depends_on", "confidence": 0.9},
                    {"in": "insight:seed", "out": "insight:lo", "predicate": "depends_on", "confidence": 0.2},
                ]
            ]
        return [[]]

    _fake_pool(q)
    try:
        out = await load_insight_neighbors(["insight:seed"], "product:test", min_edge_confidence=0.5)
    finally:
        patch.stopall()
    assert [n["insight_id"] for n in out] == ["insight:hi"]


@pytest.mark.asyncio
async def test_empty_seeds_no_query():
    called = []

    async def q(sql, params=None):
        called.append(sql)
        return [[]]

    _fake_pool(q)
    try:
        out = await load_insight_neighbors([], "product:test")
    finally:
        patch.stopall()
    assert out == []
    assert called == []  # no DB work


@pytest.mark.asyncio
async def test_non_fatal_on_db_error():
    async def q(sql, params=None):
        raise RuntimeError("db down")

    _fake_pool(q)
    try:
        out = await load_insight_neighbors(["insight:seed"], "product:test")
    finally:
        patch.stopall()
    assert out == []


@pytest.mark.asyncio
async def test_seed_and_id_bindings_are_record_ids():
    """Guard: $seeds and content-load $ids must bind as RecordIDs (SurrealDB v3
    does not coerce strings in `IN $list`), else the reader matches nothing."""
    from surrealdb import RecordID

    captured = []

    async def q(sql, params=None):
        captured.append((sql, params))
        if "FROM insight" in sql:
            return [[{"id": "insight:nbr", "content": "Y", "confidence": 0.8, "insight_type": "fact"}]]
        if "FROM operational_relationship" in sql:
            return [[{"in": "insight:seed", "out": "insight:nbr", "predicate": "depends_on", "confidence": 0.9}]]
        return [[]]

    _fake_pool(q)
    try:
        await load_insight_neighbors(["insight:seed"], "product:test")
    finally:
        patch.stopall()
    edge_calls = [(s, p) for s, p in captured if "FROM operational_relationship" in s]
    assert edge_calls and all(isinstance(x, RecordID) for x in edge_calls[0][1]["seeds"])
    id_calls = [(s, p) for s, p in captured if "FROM insight" in s]
    assert id_calls and all(isinstance(x, RecordID) for x in id_calls[0][1]["ids"])
