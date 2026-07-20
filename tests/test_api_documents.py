# tests/test_api_documents.py
import pytest
from httpx import ASGITransport, AsyncClient


@pytest.mark.asyncio
async def test_documents_requires_auth():
    from core.engine.api.main import app

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        resp = await ac.get("/documents?product=product:test")
    assert resp.status_code == 401


@pytest.mark.asyncio
async def test_activity_requires_auth():
    from core.engine.api.main import app

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        resp = await ac.get("/portal/activity?product=product:test")
    assert resp.status_code == 401
