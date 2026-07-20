# tests/test_ranker.py
"""Tests for engine.intelligence.ranker — relevance ranker."""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest


def _make_snapshot(n: int = 3) -> dict:
    insights = [
        {
            "id": f"insight:{i}",
            "content": f"content {i}",
            "confidence": round(i * 0.2, 1),
            "insight_type": "pattern",
            "source_graph": "specialty",
        }
        for i in range(1, n + 1)
    ]
    return {
        "insights": [dict(x) for x in insights],
        "specialty_insights": [dict(x) for x in insights],
        "org_insights": [],
    }


@pytest.mark.asyncio
async def test_rank_sorts_by_score():
    snapshot = _make_snapshot(3)
    mock_embedder = MagicMock()
    mock_embedder.dimensions = 768
    mock_embedder.embed = AsyncMock(return_value=[[0.1] * 768])
    with (
        patch("core.engine.intelligence.ranker.get_embedder", return_value=mock_embedder),
        patch("core.engine.intelligence.ranker.pool") as mock_pool,
        patch("core.engine.intelligence.ranker.parse_rows", return_value=[]),
    ):
        mock_db = AsyncMock()
        mock_db.query = AsyncMock(return_value=[])
        mock_pool.connection.return_value.__aenter__ = AsyncMock(return_value=mock_db)
        mock_pool.connection.return_value.__aexit__ = AsyncMock(return_value=False)
        from core.engine.intelligence.ranker import rank_insights

        result = await rank_insights(snapshot, "a task", "product:test")
    assert result["insights"][0]["id"] == "insight:3"


@pytest.mark.asyncio
async def test_rank_noop_on_no_embedder():
    snapshot = _make_snapshot(3)
    mock_embedder = MagicMock()
    mock_embedder.dimensions = 0
    with patch("core.engine.intelligence.ranker.get_embedder", return_value=mock_embedder):
        from core.engine.intelligence.ranker import rank_insights

        result = await rank_insights(snapshot, "task", "product:test")
    assert len(result["insights"]) == 3
    assert result["insights"][0]["confidence"] >= result["insights"][-1]["confidence"]


@pytest.mark.asyncio
async def test_rank_injects_vec_key():
    snapshot = _make_snapshot(2)
    mock_embedder = MagicMock()
    mock_embedder.dimensions = 768
    mock_embedder.embed = AsyncMock(return_value=[[0.1] * 768])
    with (
        patch("core.engine.intelligence.ranker.get_embedder", return_value=mock_embedder),
        patch("core.engine.intelligence.ranker.pool") as mock_pool,
        patch("core.engine.intelligence.ranker.parse_rows") as mock_parse,
    ):
        mock_parse.side_effect = [[{"id": "insight:1", "embedding": [0.5] * 768}], []]
        mock_db = AsyncMock()
        mock_db.query = AsyncMock(return_value=[])
        mock_pool.connection.return_value.__aenter__ = AsyncMock(return_value=mock_db)
        mock_pool.connection.return_value.__aexit__ = AsyncMock(return_value=False)
        from core.engine.intelligence.ranker import rank_insights

        result = await rank_insights(snapshot, "task", "product:test")
    ids_with_vec = [i["id"] for i in result["insights"] if "_vec" in i]
    assert "insight:1" in ids_with_vec


@pytest.mark.asyncio
async def test_rank_survives_db_failure():
    snapshot = _make_snapshot(2)
    mock_embedder = MagicMock()
    mock_embedder.dimensions = 768
    mock_embedder.embed = AsyncMock(return_value=[[0.1] * 768])
    with (
        patch("core.engine.intelligence.ranker.get_embedder", return_value=mock_embedder),
        patch("core.engine.intelligence.ranker.pool") as mock_pool,
    ):
        mock_db = AsyncMock()
        mock_db.query = AsyncMock(side_effect=Exception("DB down"))
        mock_pool.connection.return_value.__aenter__ = AsyncMock(return_value=mock_db)
        mock_pool.connection.return_value.__aexit__ = AsyncMock(return_value=False)
        from core.engine.intelligence.ranker import rank_insights

        result = await rank_insights(snapshot, "task", "product:test")
    assert len(result["insights"]) == 2


@pytest.mark.asyncio
async def test_rank_uses_utilization_score():
    snapshot = {
        "insights": [
            {"id": "insight:1", "content": "x", "confidence": 0.3, "source_graph": "specialty"},
            {"id": "insight:2", "content": "y", "confidence": 0.9, "source_graph": "specialty"},
        ],
        "specialty_insights": [],
        "org_insights": [],
    }
    mock_embedder = MagicMock()
    mock_embedder.dimensions = 768
    mock_embedder.embed = AsyncMock(return_value=[[0.1] * 768])
    utilization_rows = [
        {"insight": "insight:1", "utilization_score": 0.95},
        {"insight": "insight:2", "utilization_score": 0.05},
    ]
    with (
        patch("core.engine.intelligence.ranker.get_embedder", return_value=mock_embedder),
        patch("core.engine.intelligence.ranker.pool") as mock_pool,
        patch("core.engine.intelligence.ranker.parse_rows") as mock_parse,
    ):
        mock_parse.side_effect = [[], utilization_rows]
        mock_db = AsyncMock()
        mock_db.query = AsyncMock(return_value=[])
        mock_pool.connection.return_value.__aenter__ = AsyncMock(return_value=mock_db)
        mock_pool.connection.return_value.__aexit__ = AsyncMock(return_value=False)
        from core.engine.intelligence.ranker import rank_insights

        result = await rank_insights(snapshot, "task", "product:test")
    assert result["insights"][0]["id"] == "insight:1"
