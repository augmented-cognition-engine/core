# tests/test_portal_views.py
"""Tests for cross-product signals portal endpoint."""

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
async def test_cross_product_signals_returns_shape(app_with_mocks):
    app, mock_db = app_with_mocks
    mock_db.query = AsyncMock(return_value=[[]])

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        resp = await client.get("/portal/cross-product-signals")
        assert resp.status_code == 200
        data = resp.json()
        assert "now" in data
        assert "next" in data
        assert "pulse" in data
        assert isinstance(data["now"], list)
        assert isinstance(data["next"], list)
        pulse = data["pulse"]
        assert "gates_waiting" in pulse
        assert "initiatives_active" in pulse
        assert "engagements_at_risk" in pulse


@pytest.mark.asyncio
async def test_cross_product_signals_pulse_values_are_ints(app_with_mocks):
    app, mock_db = app_with_mocks
    mock_db.query = AsyncMock(return_value=[[]])

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        resp = await client.get("/portal/cross-product-signals")
        assert resp.status_code == 200
        pulse = resp.json()["pulse"]
        assert isinstance(pulse["gates_waiting"], int), "gates_waiting must be int"
        assert isinstance(pulse["initiatives_active"], int), "initiatives_active must be int"
        assert isinstance(pulse["engagements_at_risk"], int), "engagements_at_risk must be int"


@pytest.mark.asyncio
async def test_cross_product_signals_item_shape(app_with_mocks):
    """When now/next items are present they must carry the required keys."""
    app, mock_db = app_with_mocks

    # Simulate a single gate row returned for tenant resolution + products +
    # gate_evaluation queries.  First three calls return structural data; the
    # rest stay empty so pulse counters work cleanly.
    tenant_row = [{"tenant": "tenant:default"}]
    product_row = [{"id": "product:alpha", "name": "Alpha"}]
    gate_row = [
        {
            "id": "gate_evaluation:1",
            "entity_type": "spec",
            "entity_id": "spec:1",
            "product": "product:alpha",
            "created_at": "2026-01-01T00:00:00Z",
        }
    ]

    call_results = [
        [tenant_row],  # SELECT tenant FROM product
        [product_row],  # SELECT id, name FROM product
        [gate_row],  # gate_evaluation pending
        [[]],  # paused initiatives
        [[]],  # ready ideas
        [[]],  # active initiative count
    ]
    mock_db.query = AsyncMock(side_effect=call_results)

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        resp = await client.get("/portal/cross-product-signals")
        assert resp.status_code == 200
        data = resp.json()

    now = data["now"]
    assert len(now) >= 1, "Expected at least one now item from the gate row"
    item = now[0]
    for key in ("id", "type", "title", "product_id", "product_name", "created_at"):
        assert key in item, f"now item missing required key: {key}"
