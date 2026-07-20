# tests/test_edge_writer.py
"""Tests for the centralized edge writer."""

from unittest.mock import AsyncMock, MagicMock

import pytest


@pytest.fixture
def mock_pool():
    """Mock DB pool with connection context manager."""
    mock_db = AsyncMock()
    mock_db.query = AsyncMock(return_value=[])
    mock_conn = MagicMock()
    mock_conn.__aenter__ = AsyncMock(return_value=mock_db)
    mock_conn.__aexit__ = AsyncMock(return_value=False)
    mock_p = MagicMock()
    mock_p.connection.return_value = mock_conn
    return mock_p, mock_db


@pytest.mark.asyncio
async def test_create_edge_basic(mock_pool):
    """create_edge issues a RELATE query with created_at."""
    mock_p, mock_db = mock_pool
    from core.engine.graph.edge_writer import create_edge

    await create_edge("became", "initiative:abc", "idea:xyz", pool=mock_p)

    mock_db.query.assert_called()
    # Second call should be the RELATE (first is SELECT check)
    relate_call = mock_db.query.call_args_list[1]
    assert "RELATE" in relate_call[0][0]
    assert "became" in relate_call[0][0]
    assert "created_at" in relate_call[0][0]


@pytest.mark.asyncio
async def test_create_edge_with_metadata(mock_pool):
    """create_edge passes metadata fields into SET clause."""
    mock_p, mock_db = mock_pool
    from core.engine.graph.edge_writer import create_edge

    await create_edge(
        "quality_delta",
        "task:t1",
        "capability_quality:cq1",
        metadata={"before_score": 0.3, "after_score": 0.8, "delta": 0.5},
        pool=mock_p,
    )

    relate_call = mock_db.query.call_args_list[1]
    query = relate_call[0][0]
    assert "before_score" in query
    assert "after_score" in query


@pytest.mark.asyncio
async def test_create_edge_deduplicates(mock_pool):
    """create_edge checks for existing edge before creating."""
    mock_p, mock_db = mock_pool
    # SELECT check returns an existing edge
    mock_db.query = AsyncMock(return_value=[{"id": "became:existing"}])
    from core.engine.graph.edge_writer import create_edge

    await create_edge("became", "initiative:abc", "idea:xyz", pool=mock_p)

    # Should have queried for existence but NOT issued RELATE
    assert mock_db.query.call_count == 1  # only the SELECT, no RELATE


@pytest.mark.asyncio
async def test_create_edge_swallows_errors(mock_pool):
    """create_edge never raises — logs and returns None on failure."""
    mock_p, mock_db = mock_pool
    mock_db.query = AsyncMock(side_effect=Exception("DB down"))
    from core.engine.graph.edge_writer import create_edge

    result = await create_edge("became", "initiative:abc", "idea:xyz", pool=mock_p)

    assert result is None  # no exception raised


@pytest.mark.asyncio
async def test_create_edges_batch(mock_pool):
    """create_edges creates multiple edges, skipping failures."""
    mock_p, mock_db = mock_pool
    mock_db.query = AsyncMock(return_value=[])
    from core.engine.graph.edge_writer import create_edges

    edges = [
        ("loaded", "task:t1", "insight:i1"),
        ("loaded", "task:t1", "insight:i2"),
        ("loaded", "task:t1", "insight:i3"),
    ]
    await create_edges(edges, pool=mock_p)

    # 3 edges × 2 queries each (check + create) = 6
    assert mock_db.query.call_count == 6
