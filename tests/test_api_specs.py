# tests/test_api_specs.py
"""API tests for agent spec and feedback endpoints."""

from contextlib import asynccontextmanager
from unittest.mock import AsyncMock, MagicMock, patch

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
async def test_create_spec_from_request(app_client):
    """POST /product/specs with source='human' returns 201 with spec."""
    created_spec = {
        "id": "agent_spec:1",
        "source": "human",
        "objective": "Add rate limiting to API endpoints",
        "acceptance_criteria": [
            {"criterion": "Rate limit header present", "verification": "Check response headers", "automated": True}
        ],
        "status": "draft",
    }

    with patch("core.engine.api.product.SpecGenerator") as MockGen:
        instance = MockGen.return_value
        instance.from_request = AsyncMock(return_value=created_spec)

        async with AsyncClient(transport=ASGITransport(app=app_client), base_url="http://test") as client:
            resp = await client.post(
                "/product/specs",
                json={"source": "human", "request": "add rate limiting"},
            )

    assert resp.status_code == 201
    body = resp.json()
    assert body["source"] == "human"
    assert body["objective"] == "Add rate limiting to API endpoints"
    assert body["status"] == "draft"


@pytest.mark.asyncio
async def test_list_specs(app_client):
    """GET /product/specs returns {specs, count}."""
    specs = [
        {"id": "agent_spec:1", "source": "human", "objective": "Add rate limiting", "status": "draft"},
        {"id": "agent_spec:2", "source": "gap", "objective": "Improve test coverage", "status": "approved"},
    ]

    mock_db = AsyncMock()
    mock_db.query = AsyncMock(return_value=[{"result": specs}])

    mock_pool = MagicMock()

    @asynccontextmanager
    async def mock_connection():
        yield mock_db

    mock_pool.connection = mock_connection

    with (
        patch("core.engine.api.product.pool", mock_pool),
        patch("core.engine.api.product.parse_rows", return_value=specs),
    ):
        async with AsyncClient(transport=ASGITransport(app=app_client), base_url="http://test") as client:
            resp = await client.get("/product/specs")

    assert resp.status_code == 200
    body = resp.json()
    assert "specs" in body
    assert "count" in body
    assert body["count"] == 2


@pytest.mark.asyncio
async def test_verify_spec(app_client):
    """POST /product/specs/{id}/verify returns verification result."""
    verification_result = {
        "spec_id": "agent_spec:1",
        "overall": "fully_met",
        "criteria_results": [
            {"criterion": "Rate limit header present", "status": "met", "evidence": "Header X-RateLimit found"}
        ],
        "follow_up_needed": False,
        "met": 1,
        "total": 1,
    }

    with patch("core.engine.api.product.AcceptanceVerifier") as MockVerifier:
        instance = MockVerifier.return_value
        instance.verify = AsyncMock(return_value=verification_result)

        async with AsyncClient(transport=ASGITransport(app=app_client), base_url="http://test") as client:
            resp = await client.post("/product/specs/agent_spec:1/verify")

    assert resp.status_code == 200
    body = resp.json()
    assert body["spec_id"] == "agent_spec:1"
    assert body["overall"] == "fully_met"
    assert body["follow_up_needed"] is False
    assert body["met"] == 1


@pytest.mark.asyncio
async def test_submit_feedback(app_client):
    """POST /product/feedback returns 201 with feedback handling result."""
    feedback_result = {
        "feedback_id": "agent_feedback:1",
        "feedback_type": "progress",
        "action": {"action": "progress_noted"},
    }

    with patch("core.engine.api.product.FeedbackHandler") as MockHandler:
        instance = MockHandler.return_value
        instance.handle = AsyncMock(return_value=feedback_result)

        async with AsyncClient(transport=ASGITransport(app=app_client), base_url="http://test") as client:
            resp = await client.post(
                "/product/feedback",
                json={
                    "spec_id": "agent_spec:1",
                    "feedback_type": "progress",
                    "content": "Completed 3 of 5 files",
                },
            )

    assert resp.status_code == 201
    body = resp.json()
    assert body["feedback_type"] == "progress"
    assert body["feedback_id"] == "agent_feedback:1"
