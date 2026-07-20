"""Tests for the agents REST API — sessions, metrics, config overrides."""

from contextlib import asynccontextmanager
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from httpx import ASGITransport, AsyncClient

_AUTH = {"Authorization": "Bearer test"}  # bypasses APIKeyMiddleware; auth resolved via dependency_overrides


@asynccontextmanager
async def mock_lifespan(app):
    yield


def _mock_user():
    return {"product": "product:test", "sub": "user:1"}


def _make_pool_mock(rows=None, one=None):
    """Return a context-manager-compatible pool mock."""
    rows = rows or []
    mock_db = AsyncMock()
    mock_db.query = AsyncMock(return_value=[])

    mock_cm = MagicMock()
    mock_cm.__aenter__ = AsyncMock(return_value=mock_db)
    mock_cm.__aexit__ = AsyncMock(return_value=False)

    mock_pool = MagicMock()
    mock_pool.connection = MagicMock(return_value=mock_cm)
    return mock_pool, mock_db


@pytest.mark.asyncio
@patch("core.engine.api.agents.parse_rows")
@patch("core.engine.api.agents.pool")
async def test_list_agent_sessions(mock_pool, mock_parse_rows):
    """GET /agents/sessions returns sessions list with count."""
    from core.engine.api.main import app
    from core.engine.core.auth import get_current_user

    app.router.lifespan_context = mock_lifespan
    app.dependency_overrides[get_current_user] = _mock_user

    sessions = [
        {"id": "agent_session:1", "status": "active", "product": "product:test"},
        {"id": "agent_session:2", "status": "completed", "product": "product:test"},
    ]

    pool_inst, mock_db = _make_pool_mock()
    mock_pool.connection = pool_inst.connection
    mock_parse_rows.return_value = sessions

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        resp = await ac.get("/agents/sessions", headers=_AUTH)

    assert resp.status_code == 200
    data = resp.json()
    assert "sessions" in data
    assert "count" in data
    assert data["count"] == 2
    app.dependency_overrides.clear()


@pytest.mark.asyncio
@patch("core.engine.api.agents.parse_rows")
@patch("core.engine.api.agents.pool")
async def test_list_agent_sessions_status_filter(mock_pool, mock_parse_rows):
    """GET /agents/sessions?status=active filters by status."""
    from core.engine.api.main import app
    from core.engine.core.auth import get_current_user

    app.router.lifespan_context = mock_lifespan
    app.dependency_overrides[get_current_user] = _mock_user

    sessions = [{"id": "agent_session:1", "status": "active", "product": "product:test"}]

    pool_inst, mock_db = _make_pool_mock()
    mock_pool.connection = pool_inst.connection
    mock_parse_rows.return_value = sessions

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        resp = await ac.get("/agents/sessions?status=active", headers=_AUTH)

    assert resp.status_code == 200
    data = resp.json()
    assert data["count"] == 1
    app.dependency_overrides.clear()


@pytest.mark.asyncio
@patch("core.engine.api.agents.parse_rows")
@patch("core.engine.api.agents.pool")
async def test_get_agent_metrics(mock_pool, mock_parse_rows):
    """GET /agents/metrics returns by_archetype and by_mode."""
    from core.engine.api.main import app
    from core.engine.core.auth import get_current_user

    app.router.lifespan_context = mock_lifespan
    app.dependency_overrides[get_current_user] = _mock_user

    pool_inst, mock_db = _make_pool_mock()
    mock_pool.connection = pool_inst.connection

    by_archetype = [{"archetype": "researcher", "total": 10, "accepted": 8}]
    by_mode = [{"mode": "fast", "total": 15}]
    mock_parse_rows.side_effect = [by_archetype, by_mode]

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        resp = await ac.get("/agents/metrics", headers=_AUTH)

    assert resp.status_code == 200
    data = resp.json()
    assert "by_archetype" in data
    assert "by_mode" in data
    assert data["by_archetype"][0]["archetype"] == "researcher"
    assert data["by_mode"][0]["mode"] == "fast"
    app.dependency_overrides.clear()


@pytest.mark.asyncio
@patch("core.engine.api.agents.parse_rows")
@patch("core.engine.api.agents.pool")
async def test_list_agent_config(mock_pool, mock_parse_rows):
    """GET /agents/config returns overrides list with count."""
    from core.engine.api.main import app
    from core.engine.core.auth import get_current_user

    app.router.lifespan_context = mock_lifespan
    app.dependency_overrides[get_current_user] = _mock_user

    overrides = [
        {"id": "agent_config_override:1", "discipline": "security", "override": {"model": "claude-opus"}},
        {"id": "agent_config_override:2", "discipline": "testing", "override": {"model": "claude-haiku"}},
    ]

    pool_inst, mock_db = _make_pool_mock()
    mock_pool.connection = pool_inst.connection
    mock_parse_rows.return_value = overrides

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        resp = await ac.get("/agents/config", headers=_AUTH)

    assert resp.status_code == 200
    data = resp.json()
    assert "overrides" in data
    assert "count" in data
    assert data["count"] == 2
    assert data["overrides"][0]["discipline"] == "security"
    app.dependency_overrides.clear()


@pytest.mark.asyncio
@patch("core.engine.api.agents.parse_one")
@patch("core.engine.api.agents.pool")
async def test_upsert_agent_config(mock_pool, mock_parse_one):
    """PUT /agents/config upserts a discipline override."""
    from core.engine.api.main import app
    from core.engine.core.auth import get_current_user

    app.router.lifespan_context = mock_lifespan
    app.dependency_overrides[get_current_user] = _mock_user

    pool_inst, mock_db = _make_pool_mock()
    mock_pool.connection = pool_inst.connection
    mock_parse_one.return_value = {
        "id": "agent_config_override:1",
        "discipline": "security",
        "override": {"model": "claude-opus"},
    }

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        resp = await ac.put(
            "/agents/config",
            json={"discipline": "security", "override": {"model": "claude-opus"}},
            headers=_AUTH,
        )

    assert resp.status_code == 200
    data = resp.json()
    assert data["discipline"] == "security"
    app.dependency_overrides.clear()


@pytest.mark.asyncio
@patch("core.engine.api.agents.pool")
async def test_delete_agent_config(mock_pool):
    """DELETE /agents/config/{discipline} deletes the override."""
    from core.engine.api.main import app
    from core.engine.core.auth import get_current_user

    app.router.lifespan_context = mock_lifespan
    app.dependency_overrides[get_current_user] = _mock_user

    pool_inst, mock_db = _make_pool_mock()
    mock_pool.connection = pool_inst.connection

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        resp = await ac.delete("/agents/config/security", headers=_AUTH)

    assert resp.status_code == 200
    data = resp.json()
    assert data["discipline"] == "security"
    assert data["deleted"] is True
    app.dependency_overrides.clear()
