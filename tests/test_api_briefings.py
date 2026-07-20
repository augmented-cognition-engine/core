# tests/test_api_briefings.py
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
async def test_briefings_requires_auth(client):
    resp = await client.get("/briefings?product=product:test")
    assert resp.status_code == 401


@pytest.mark.asyncio
async def test_briefings_latest_requires_auth(client):
    resp = await client.get("/briefings/latest?product=product:test")
    assert resp.status_code == 401


@pytest.mark.asyncio
async def test_briefings_by_id_requires_auth(client):
    resp = await client.get("/briefings/briefing:test?product=product:test")
    assert resp.status_code == 401
