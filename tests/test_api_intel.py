# tests/test_api_intel.py
import pytest
from httpx import ASGITransport, AsyncClient


@pytest.mark.asyncio
async def test_intel_endpoint_requires_auth():
    from contextlib import asynccontextmanager

    from core.engine.api.main import app

    @asynccontextmanager
    async def mock_lifespan(app):
        yield

    app.router.lifespan_context = mock_lifespan

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        resp = await ac.get("/intel/technology.engineering?product=product:test")
    assert resp.status_code == 401
