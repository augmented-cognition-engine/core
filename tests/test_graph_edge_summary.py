# tests/test_graph_edge_summary.py
"""Tests for graph edge-summary API: GET /graph/edge-summary/{node_id}"""

from contextlib import asynccontextmanager
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from httpx import ASGITransport, AsyncClient


@asynccontextmanager
async def mock_lifespan(app):
    yield


def _mock_user():
    return {"product": "product:test", "sub": "user:1"}


# ---------------------------------------------------------------------------
# GET /graph/edge-summary/{node_id}
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
@patch("core.engine.api.graph_edge_summary.pool")
async def test_edge_summary_returns_grouped_counts(mock_pool):
    """GET /graph/edge-summary/{node_id} returns edge counts grouped by type."""
    from core.engine.api.main import app
    from core.engine.core.auth import get_current_user

    app.router.lifespan_context = mock_lifespan
    app.dependency_overrides[get_current_user] = _mock_user

    mock_db = AsyncMock()
    mock_ctx = MagicMock()
    mock_ctx.__aenter__ = AsyncMock(return_value=mock_db)
    mock_ctx.__aexit__ = AsyncMock(return_value=False)
    mock_pool.connection.return_value = mock_ctx

    # 15 tables; return counts for realizes (5) and depends_on (2), empty for rest
    def _side_effect(query, params=None):
        if "realizes" in query:
            return [{"c": 5}]
        if "depends_on" in query:
            return [{"c": 2}]
        return []

    mock_db.query = AsyncMock(side_effect=_side_effect)

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        resp = await ac.get("/graph/edge-summary/capability:mcp_tools")

    assert resp.status_code == 200
    data = resp.json()
    assert "edges" in data
    assert "total" in data
    assert data["edges"]["realizes"] == 5
    assert data["edges"]["depends_on"] == 2
    assert data["total"] == 7
    # Tables with zero count must not appear
    assert "became" not in data["edges"]

    app.dependency_overrides.clear()


@pytest.mark.asyncio
async def test_edge_summary_requires_auth():
    """GET /graph/edge-summary/{node_id} returns 401 without auth."""
    from core.engine.api.main import app

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        resp = await ac.get("/graph/edge-summary/capability:mcp_tools")

    assert resp.status_code == 401


@pytest.mark.asyncio
@patch("core.engine.api.graph_edge_summary.pool")
async def test_edge_summary_empty_node(mock_pool):
    """GET /graph/edge-summary/{node_id} returns total=0 and empty edges when no edges exist."""
    from core.engine.api.main import app
    from core.engine.core.auth import get_current_user

    app.router.lifespan_context = mock_lifespan
    app.dependency_overrides[get_current_user] = _mock_user

    mock_db = AsyncMock()
    mock_ctx = MagicMock()
    mock_ctx.__aenter__ = AsyncMock(return_value=mock_db)
    mock_ctx.__aexit__ = AsyncMock(return_value=False)
    mock_pool.connection.return_value = mock_ctx

    mock_db.query = AsyncMock(return_value=[])

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        resp = await ac.get("/graph/edge-summary/capability:nonexistent")

    assert resp.status_code == 200
    data = resp.json()
    assert data["edges"] == {}
    assert data["total"] == 0

    app.dependency_overrides.clear()
