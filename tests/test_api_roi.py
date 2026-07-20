# tests/test_api_roi.py
"""Tests for ROI API endpoints."""

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

    import core.engine.api.roi as roi_mod

    orig_pool = roi_mod.pool
    roi_mod.pool = mock_pool

    yield app, mock_db

    app.dependency_overrides.clear()
    roi_mod.pool = orig_pool


@pytest.mark.asyncio
async def test_get_roi(app_with_mocks):
    """GET /roi returns weekly/monthly/all-time structure."""
    app, mock_db = app_with_mocks
    mock_db.query = AsyncMock(
        return_value=[
            [
                {"event_type": "mistake_prevented", "count": 3, "minutes_saved": 90},
            ]
        ]
    )

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        resp = await client.get("/roi?product=product:test")
        assert resp.status_code == 200
        data = resp.json()
        assert "this_week" in data
        assert "this_month" in data
        assert "all_time" in data
        assert "hours_saved" in data["all_time"]


@pytest.mark.asyncio
async def test_get_roi_summary(app_with_mocks):
    """GET /roi/summary returns aggregate counts."""
    app, mock_db = app_with_mocks
    mock_db.query = AsyncMock(
        return_value=[
            [
                {"event_type": "mistake_prevented", "count": 5, "minutes_saved": 150},
                {"event_type": "gap_filled", "count": 3, "minutes_saved": 135},
            ]
        ]
    )

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        resp = await client.get("/roi/summary?product=product:test")
        assert resp.status_code == 200
        data = resp.json()
        assert data["mistakes_prevented"] == 5
        assert data["gaps_filled"] == 3
        assert data["total_hours_saved"] == pytest.approx(4.75, abs=0.1)
