# tests/test_api_reasoning.py
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
async def test_frameworks_requires_auth(client):
    resp = await client.get("/frameworks?product=product:test")
    assert resp.status_code == 401


@pytest.mark.asyncio
async def test_framework_get_requires_auth(client):
    resp = await client.get("/frameworks/first-principles")
    assert resp.status_code == 401


@pytest.mark.asyncio
async def test_framework_perf_requires_auth(client):
    resp = await client.get("/framework-perf?product=product:test")
    assert resp.status_code == 401
