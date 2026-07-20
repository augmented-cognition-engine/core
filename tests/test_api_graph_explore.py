# tests/test_api_graph_explore.py
"""Tests for graph explorer API: /graph/overview, /graph/explore/{id}, /graph/diagram/..."""

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
# Helpers to build fake DB responses
# ---------------------------------------------------------------------------


def _make_pool_ctx(query_side_effect=None, query_return=None):
    """Return a patched pool.connection() context manager with a mock db."""
    mock_db = AsyncMock()
    if query_side_effect is not None:
        mock_db.query.side_effect = query_side_effect
    else:
        mock_db.query.return_value = query_return or []

    mock_ctx = MagicMock()
    mock_ctx.__aenter__ = AsyncMock(return_value=mock_db)
    mock_ctx.__aexit__ = AsyncMock(return_value=False)
    return mock_ctx, mock_db


# ---------------------------------------------------------------------------
# GET /graph/overview
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
@patch("core.engine.api.graph_explore.pool")
@patch("core.engine.api.graph_explore.parse_rows")
@patch("core.engine.api.graph_explore.parse_one")
@patch("core.engine.api.graph_explore.serialize_record")
async def test_graph_overview_returns_nodes_and_edges(
    mock_serialize_record,
    mock_parse_one,
    mock_parse_rows,
    mock_pool,
):
    """GET /graph/overview returns nodes and edges with counts."""
    from core.engine.api.main import app
    from core.engine.core.auth import get_current_user

    app.router.lifespan_context = mock_lifespan
    app.dependency_overrides[get_current_user] = _mock_user

    mock_db = AsyncMock()
    mock_db.query.return_value = []
    mock_ctx = MagicMock()
    mock_ctx.__aenter__ = AsyncMock(return_value=mock_db)
    mock_ctx.__aexit__ = AsyncMock(return_value=False)
    mock_pool.connection.return_value = mock_ctx

    # capability rows returned for first query, empty for the rest
    cap_row = {"id": "capability:auth", "name": "Auth", "status": "active", "priority": 1}
    realizes_row = {
        "id": "realizes:1",
        "in": "capability:auth",
        "out": "graph_file:engine_core_auth_py",
    }
    # serialize_record: return dicts unchanged; stringify everything else
    mock_serialize_record.side_effect = lambda v: v if isinstance(v, dict) else str(v)

    def _parse_rows_side_effect(result):
        return result if isinstance(result, list) else []

    mock_parse_rows.side_effect = _parse_rows_side_effect
    mock_parse_one.return_value = None

    # Simulate: capabilities → [cap_row], realizes → [realizes_row], initiatives → [], sessions → []
    query_results = [
        [cap_row],  # capabilities
        [realizes_row],  # realizes edges
        [],  # initiatives
        [],  # sessions
    ]
    mock_db.query.side_effect = query_results + [[]] * 20  # extra empty for file fetches

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        resp = await ac.get("/graph/overview")

    assert resp.status_code == 200
    data = resp.json()
    assert "nodes" in data
    assert "edges" in data
    assert "node_count" in data
    assert "edge_count" in data
    assert isinstance(data["nodes"], list)
    assert isinstance(data["edges"], list)

    app.dependency_overrides.clear()


@pytest.mark.asyncio
async def test_graph_overview_requires_auth():
    """GET /graph/overview returns 401 without auth."""
    from core.engine.api.main import app

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        resp = await ac.get("/graph/overview")

    assert resp.status_code == 401


# ---------------------------------------------------------------------------
# GET /graph/explore/{node_id}
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
@patch("core.engine.api.graph_explore.pool")
@patch("core.engine.api.graph_explore.parse_rows")
@patch("core.engine.api.graph_explore.parse_one")
@patch("core.engine.api.graph_explore.serialize_record")
async def test_explore_node_returns_node_edges_connected(
    mock_serialize_record,
    mock_parse_one,
    mock_parse_rows,
    mock_pool,
):
    """GET /graph/explore/{id} returns node, edges, and connected nodes."""
    from core.engine.api.main import app
    from core.engine.core.auth import get_current_user

    app.router.lifespan_context = mock_lifespan
    app.dependency_overrides[get_current_user] = _mock_user

    mock_db = AsyncMock()
    mock_ctx = MagicMock()
    mock_ctx.__aenter__ = AsyncMock(return_value=mock_db)
    mock_ctx.__aexit__ = AsyncMock(return_value=False)
    mock_pool.connection.return_value = mock_ctx

    mock_serialize_record.side_effect = lambda v: v if isinstance(v, dict) else str(v)

    node_row = {"id": "capability:auth", "name": "Auth", "status": "active"}
    edge_row = {
        "id": "realizes:1",
        "in": "capability:auth",
        "out": "graph_file:engine_core_auth_py",
    }
    connected_row = {"id": "graph_file:engine_core_auth_py", "path": "core/engine/core/auth.py"}

    call_count = 0

    def _parse_one_side(result):
        nonlocal call_count
        call_count += 1
        if call_count == 1:
            return node_row
        # connected node fetches
        return connected_row

    def _parse_rows_side(result):
        if isinstance(result, list) and result:
            return result
        return []

    mock_parse_one.side_effect = _parse_one_side
    mock_parse_rows.side_effect = _parse_rows_side

    # node fetch → realizes edges (1 table) → rest empty → connected node fetch
    per_table_returns = [[edge_row]] + [[]] * (len([]) + 14)  # 1 hit + 14 empty tables
    mock_db.query.side_effect = [[node_row]] + per_table_returns + [[connected_row]] * 5

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        resp = await ac.get("/graph/explore/capability:auth")

    assert resp.status_code == 200
    data = resp.json()
    assert "node" in data
    assert "edges" in data
    assert "connected" in data
    assert isinstance(data["edges"], list)
    assert isinstance(data["connected"], list)

    app.dependency_overrides.clear()


@pytest.mark.asyncio
@patch("core.engine.api.graph_explore.pool")
@patch("core.engine.api.graph_explore.parse_rows")
@patch("core.engine.api.graph_explore.parse_one")
@patch("core.engine.api.graph_explore.serialize_record")
async def test_explore_node_not_found(
    mock_serialize_record,
    mock_parse_one,
    mock_parse_rows,
    mock_pool,
):
    """GET /graph/explore/{id} returns 404 when node does not exist."""
    from core.engine.api.main import app
    from core.engine.core.auth import get_current_user

    app.router.lifespan_context = mock_lifespan
    app.dependency_overrides[get_current_user] = _mock_user

    mock_db = AsyncMock()
    mock_db.query.return_value = []
    mock_ctx = MagicMock()
    mock_ctx.__aenter__ = AsyncMock(return_value=mock_db)
    mock_ctx.__aexit__ = AsyncMock(return_value=False)
    mock_pool.connection.return_value = mock_ctx

    mock_parse_one.return_value = None
    mock_parse_rows.return_value = []
    mock_serialize_record.side_effect = lambda v: v if isinstance(v, dict) else str(v)

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        resp = await ac.get("/graph/explore/capability:nonexistent")

    assert resp.status_code == 404

    app.dependency_overrides.clear()


@pytest.mark.asyncio
async def test_explore_node_requires_auth():
    """GET /graph/explore/{id} returns 401 without auth."""
    from core.engine.api.main import app

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        resp = await ac.get("/graph/explore/capability:auth")

    assert resp.status_code == 401


# ---------------------------------------------------------------------------
# GET /graph/diagram/{query_type}/{node_id}
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
@patch("core.engine.api.graph_explore.pool")
@patch("core.engine.api.graph_explore.parse_rows")
@patch("core.engine.api.graph_explore.parse_one")
@patch("core.engine.api.graph_explore.serialize_record")
async def test_diagram_capability_architecture_returns_mermaid(
    mock_serialize_record,
    mock_parse_one,
    mock_parse_rows,
    mock_pool,
):
    """GET /graph/diagram/capability_architecture/{id} returns a mermaid string and title."""
    from core.engine.api.main import app
    from core.engine.core.auth import get_current_user

    app.router.lifespan_context = mock_lifespan
    app.dependency_overrides[get_current_user] = _mock_user

    mock_db = AsyncMock()
    mock_db.query.return_value = []
    mock_ctx = MagicMock()
    mock_ctx.__aenter__ = AsyncMock(return_value=mock_db)
    mock_ctx.__aexit__ = AsyncMock(return_value=False)
    mock_pool.connection.return_value = mock_ctx

    mock_serialize_record.side_effect = lambda v: v if isinstance(v, dict) else str(v)

    root_row = {"id": "capability:auth", "name": "Auth Service", "status": "active"}

    call_count = 0

    def _parse_one_side(result):
        nonlocal call_count
        call_count += 1
        if call_count == 1:
            return root_row
        return None

    mock_parse_one.side_effect = _parse_one_side
    mock_parse_rows.return_value = []

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        resp = await ac.get("/graph/diagram/capability_architecture/capability:auth")

    assert resp.status_code == 200
    data = resp.json()
    assert "mermaid" in data
    assert "title" in data
    assert "flowchart" in data["mermaid"]
    assert isinstance(data["title"], str)

    app.dependency_overrides.clear()


@pytest.mark.asyncio
@patch("core.engine.api.graph_explore.pool")
@patch("core.engine.api.graph_explore.parse_rows")
@patch("core.engine.api.graph_explore.parse_one")
@patch("core.engine.api.graph_explore.serialize_record")
async def test_diagram_decision_tree_returns_mermaid(
    mock_serialize_record,
    mock_parse_one,
    mock_parse_rows,
    mock_pool,
):
    """GET /graph/diagram/decision_tree/{id} returns a mermaid string."""
    from core.engine.api.main import app
    from core.engine.core.auth import get_current_user

    app.router.lifespan_context = mock_lifespan
    app.dependency_overrides[get_current_user] = _mock_user

    mock_db = AsyncMock()
    mock_db.query.return_value = []
    mock_ctx = MagicMock()
    mock_ctx.__aenter__ = AsyncMock(return_value=mock_db)
    mock_ctx.__aexit__ = AsyncMock(return_value=False)
    mock_pool.connection.return_value = mock_ctx

    mock_serialize_record.side_effect = lambda v: v if isinstance(v, dict) else str(v)

    root_row = {"id": "decision:use_surrealdb", "title": "Use SurrealDB", "outcome": "accepted"}

    call_count = 0

    def _parse_one_side(result):
        nonlocal call_count
        call_count += 1
        if call_count == 1:
            return root_row
        return None

    mock_parse_one.side_effect = _parse_one_side
    mock_parse_rows.return_value = []

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        resp = await ac.get("/graph/diagram/decision_tree/decision:use_surrealdb")

    assert resp.status_code == 200
    data = resp.json()
    assert "mermaid" in data
    assert "title" in data
    assert "flowchart" in data["mermaid"]

    app.dependency_overrides.clear()


@pytest.mark.asyncio
@patch("core.engine.api.graph_explore.pool")
@patch("core.engine.api.graph_explore.parse_rows")
@patch("core.engine.api.graph_explore.parse_one")
@patch("core.engine.api.graph_explore.serialize_record")
async def test_diagram_initiative_flow_returns_mermaid(
    mock_serialize_record,
    mock_parse_one,
    mock_parse_rows,
    mock_pool,
):
    """GET /graph/diagram/initiative_flow/{id} returns a mermaid string."""
    from core.engine.api.main import app
    from core.engine.core.auth import get_current_user

    app.router.lifespan_context = mock_lifespan
    app.dependency_overrides[get_current_user] = _mock_user

    mock_db = AsyncMock()
    mock_db.query.return_value = []
    mock_ctx = MagicMock()
    mock_ctx.__aenter__ = AsyncMock(return_value=mock_db)
    mock_ctx.__aexit__ = AsyncMock(return_value=False)
    mock_pool.connection.return_value = mock_ctx

    mock_serialize_record.side_effect = lambda v: v if isinstance(v, dict) else str(v)

    root_row = {"id": "initiative:auth_hardening", "title": "Auth Hardening", "status": "active"}

    call_count = 0

    def _parse_one_side(result):
        nonlocal call_count
        call_count += 1
        if call_count == 1:
            return root_row
        return None

    mock_parse_one.side_effect = _parse_one_side
    mock_parse_rows.return_value = []

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        resp = await ac.get("/graph/diagram/initiative_flow/initiative:auth_hardening")

    assert resp.status_code == 200
    data = resp.json()
    assert "mermaid" in data
    assert "title" in data
    assert "flowchart" in data["mermaid"]

    app.dependency_overrides.clear()


@pytest.mark.asyncio
async def test_diagram_invalid_query_type():
    """GET /graph/diagram/invalid_type/{id} returns 400."""
    from core.engine.api.main import app
    from core.engine.core.auth import get_current_user

    app.router.lifespan_context = mock_lifespan
    app.dependency_overrides[get_current_user] = _mock_user

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        resp = await ac.get("/graph/diagram/invalid_type/capability:auth")

    assert resp.status_code == 400

    app.dependency_overrides.clear()


@pytest.mark.asyncio
async def test_diagram_requires_auth():
    """GET /graph/diagram/... returns 401 without auth."""
    from core.engine.api.main import app

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        resp = await ac.get("/graph/diagram/capability_architecture/capability:auth")

    assert resp.status_code == 401
