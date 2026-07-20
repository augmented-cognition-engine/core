# tests/test_portal_views_extended.py
"""Tests for portal attention, active-work, and pulse endpoints."""

from contextlib import asynccontextmanager
from unittest.mock import AsyncMock, MagicMock

import pytest
from httpx import ASGITransport, AsyncClient


@pytest.fixture
def mock_user():
    return {"sub": "user:test", "product": "product:test"}


@pytest.fixture
def mock_db():
    db = AsyncMock()
    db.query = AsyncMock(return_value=[[]])
    return db


@pytest.fixture
def mock_pool(mock_db):
    p = MagicMock()
    ctx = AsyncMock()
    ctx.__aenter__ = AsyncMock(return_value=mock_db)
    ctx.__aexit__ = AsyncMock(return_value=False)
    p.connection = MagicMock(return_value=ctx)
    p.init = AsyncMock()
    p.close = AsyncMock()
    return p


@pytest.fixture
def app_with_mocks(mock_user, mock_pool, mock_db):
    from core.engine.api.main import app
    from core.engine.core.auth import get_current_user

    @asynccontextmanager
    async def mock_lifespan(a):
        yield

    app.router.lifespan_context = mock_lifespan
    app.dependency_overrides[get_current_user] = lambda: mock_user

    import core.engine.api.portal_views as pv_mod

    orig_pool = pv_mod.pool
    pv_mod.pool = mock_pool

    yield app, mock_db

    app.dependency_overrides.clear()
    pv_mod.pool = orig_pool


@pytest.mark.asyncio
async def test_attention_items(app_with_mocks):
    """GET /portal/attention returns attention items."""
    app, mock_db = app_with_mocks
    mock_db.query = AsyncMock(return_value=[[]])

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        resp = await client.get("/portal/attention?product=product:test")
        assert resp.status_code == 200
        data = resp.json()
        assert "items" in data
        assert "count" in data


@pytest.mark.asyncio
async def test_active_work(app_with_mocks):
    """GET /portal/active-work returns running initiatives."""
    app, mock_db = app_with_mocks
    mock_db.query = AsyncMock(return_value=[[]])

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        resp = await client.get("/portal/active-work?product=product:test")
        assert resp.status_code == 200
        data = resp.json()
        assert "initiatives" in data
        assert "incubating_ideas" in data


@pytest.mark.asyncio
async def test_pulse_metrics(app_with_mocks):
    """GET /portal/pulse returns intelligence counts."""
    app, mock_db = app_with_mocks
    mock_db.query = AsyncMock(return_value=[[{"n": 42}]])

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        resp = await client.get("/portal/pulse?product=product:test")
        assert resp.status_code == 200
        data = resp.json()
        assert "insights" in data
        assert "specialties" in data
        assert "connections" in data
        assert "domains" in data
