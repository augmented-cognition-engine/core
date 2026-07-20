# tests/test_api.py
import pytest
from httpx import ASGITransport, AsyncClient


@pytest.fixture
async def client():
    # Override lifespan so pool.init() is not called during tests
    from contextlib import asynccontextmanager

    from core.engine.api.main import app

    @asynccontextmanager
    async def mock_lifespan(app):
        yield

    app.router.lifespan_context = mock_lifespan
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
        yield c


@pytest.mark.asyncio
async def test_health_returns_200(client):
    """Health endpoint must return 200 with a known status and version.

    'ok' and 'degraded' are both valid — the endpoint legitimately reports
    'degraded' when the DB or LLM dependency is unreachable from the test
    subprocess. Asserting 'ok' exclusively couples the test to infrastructure
    that isn't guaranteed to be running.
    """
    response = await client.get("/health")
    assert response.status_code == 200
    body = response.json()
    assert body["status"] in {"ok", "degraded"}
    assert "version" in body


@pytest.mark.asyncio
async def test_tasks_requires_auth(client):
    response = await client.post("/tasks", json={"description": "test", "workspace_id": "ws:1"})
    assert response.status_code == 401


@pytest.mark.asyncio
async def test_intel_requires_auth(client):
    response = await client.get("/intel/experience.design-systems?product=product:test")
    assert response.status_code == 401
