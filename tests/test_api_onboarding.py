# tests/test_api_onboarding.py
"""API tests for POST /onboarding."""

from contextlib import asynccontextmanager
from unittest.mock import AsyncMock, patch

import pytest
from httpx import ASGITransport, AsyncClient

_MOCK_USER = {"sub": "user:test", "product": "product:test"}


@pytest.fixture
def app_client():
    from core.engine.api.main import app
    from core.engine.core.auth import get_current_user

    @asynccontextmanager
    async def mock_lifespan(a):
        yield

    app.router.lifespan_context = mock_lifespan
    app.dependency_overrides[get_current_user] = lambda: _MOCK_USER

    yield app

    app.dependency_overrides.clear()


@pytest.mark.asyncio
async def test_onboard_returns_specialties(app_client):
    """POST /onboarding with needs_onboarding=True scaffolds specialties and returns 201."""
    specialty = {
        "id": "specialty:abc",
        "slug": "quantitative-finance",
        "name": "Quantitative Finance",
        "description": "Statistical and mathematical models for trading.",
        "perspective": "practitioner",
        "priority": "core",
    }

    with (
        patch(
            "core.engine.api.onboarding.needs_onboarding",
            new_callable=AsyncMock,
            return_value=True,
        ),
        patch(
            "core.engine.api.onboarding.scaffold_specialties",
            new_callable=AsyncMock,
            return_value=[specialty],
        ),
    ):
        async with AsyncClient(transport=ASGITransport(app=app_client), base_url="http://test") as client:
            resp = await client.post(
                "/onboarding",
                json={"role_description": "I'm a quantitative trader"},
            )

    assert resp.status_code == 201
    body = resp.json()
    assert body["specialties_created"] == 1
    assert body["specialties"][0]["slug"] == "quantitative-finance"


@pytest.mark.asyncio
async def test_onboard_409_when_already_onboarded(app_client):
    """POST /onboarding returns 409 when org already has specialties."""
    with patch(
        "core.engine.api.onboarding.needs_onboarding",
        new_callable=AsyncMock,
        return_value=False,
    ):
        async with AsyncClient(transport=ASGITransport(app=app_client), base_url="http://test") as client:
            resp = await client.post(
                "/onboarding",
                json={"role_description": "I'm a quantitative trader"},
            )

    assert resp.status_code == 409
    assert "already" in resp.json()["detail"].lower()
