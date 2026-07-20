# tests/test_api_conflicts.py
from contextlib import asynccontextmanager

import pytest
from httpx import ASGITransport, AsyncClient


@pytest.fixture
async def client():
    from core.engine.api.main import app

    @asynccontextmanager
    async def mock_lifespan(app):
        yield

    app.router.lifespan_context = mock_lifespan
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
        yield c


@pytest.mark.asyncio
async def test_conflicts_requires_auth(client):
    resp = await client.get("/conflicts?product=product:test")
    assert resp.status_code == 401


@pytest.mark.asyncio
async def test_resolve_conflict_requires_auth(client):
    resp = await client.post(
        "/conflicts/conflict:test/resolve",
        json={"resolution_type": "keep_b", "resolution": "test"},
    )
    assert resp.status_code == 401


def test_valid_resolution_types():
    from core.engine.api.conflicts import VALID_RESOLUTION_TYPES

    assert "keep_a" in VALID_RESOLUTION_TYPES
    assert "keep_b" in VALID_RESOLUTION_TYPES
    assert "keep_both" in VALID_RESOLUTION_TYPES
    assert "merge" in VALID_RESOLUTION_TYPES
    assert len(VALID_RESOLUTION_TYPES) == 4
