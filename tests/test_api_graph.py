# tests/test_api_graph.py
import pytest
from httpx import ASGITransport, AsyncClient


@pytest.mark.asyncio
async def test_graph_requires_auth():
    from core.engine.api.main import app

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        resp = await ac.get("/graph?product=product:test")
    assert resp.status_code == 401


@pytest.mark.asyncio
async def test_proposals_requires_auth():
    from core.engine.api.main import app

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        resp = await ac.get("/proposals?product=product:test")
    assert resp.status_code == 401
