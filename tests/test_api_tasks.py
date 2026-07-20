# tests/test_api_tasks.py
import pytest
from httpx import ASGITransport, AsyncClient


@pytest.mark.asyncio
async def test_tasks_endpoint_requires_auth():
    from contextlib import asynccontextmanager

    from core.engine.api.main import app

    @asynccontextmanager
    async def mock_lifespan(app):
        yield

    app.router.lifespan_context = mock_lifespan

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        resp = await ac.post("/tasks", json={"description": "test", "workspace_id": "ws:1"})
    assert resp.status_code == 401
