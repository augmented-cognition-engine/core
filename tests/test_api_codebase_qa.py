"""Tests for codebase Q&A API endpoint."""

from contextlib import asynccontextmanager
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from httpx import ASGITransport, AsyncClient


@asynccontextmanager
async def mock_lifespan(app):
    yield


def _mock_user():
    return {"product": "product:test", "sub": "user:1"}


def _make_pool_mock():
    """Return a context-manager-compatible pool mock."""
    mock_db = AsyncMock()
    mock_db.query = AsyncMock(return_value=[])

    mock_cm = MagicMock()
    mock_cm.__aenter__ = AsyncMock(return_value=mock_db)
    mock_cm.__aexit__ = AsyncMock(return_value=False)

    mock_pool = MagicMock()
    mock_pool.connection = MagicMock(return_value=mock_cm)
    return mock_pool, mock_db


def test_codebase_qa_endpoint_exists():
    """POST /codebase/ask should exist and require auth."""
    from fastapi.testclient import TestClient

    from core.engine.api.main import app

    client = TestClient(app, raise_server_exceptions=False)
    resp = client.post("/codebase/ask", json={"question": "how does auth work?"})
    assert resp.status_code in (401, 403, 422)


@pytest.mark.asyncio
@patch("core.engine.api.codebase_qa.ace_ask_product", new_callable=AsyncMock)
async def test_ask_codebase_returns_answer(mock_ask):
    """POST /codebase/ask returns structured answer when authenticated."""
    mock_ask.return_value = {
        "question_id": "product_question:abc123",
        "status": "open",
        "question": "how does auth work?",
        "answer": "Authentication uses JWT tokens issued at login.",
        "sources": [{"file": "core/engine/core/auth.py", "relevance": "high"}],
        "capabilities": ["auth", "session_management"],
    }

    from core.engine.api.main import app
    from core.engine.core.auth import get_current_user

    app.dependency_overrides[get_current_user] = _mock_user

    try:
        async with AsyncClient(
            transport=ASGITransport(app=app, raise_app_exceptions=False),
            base_url="http://test",
        ) as client:
            resp = await client.post(
                "/codebase/ask",
                json={"question": "how does auth work?"},
            )
        assert resp.status_code == 200
        data = resp.json()
        assert data["answer"] == "Authentication uses JWT tokens issued at login."
        assert data["sources"] == [{"file": "core/engine/core/auth.py", "relevance": "high"}]
        assert data["capabilities_referenced"] == ["auth", "session_management"]
    finally:
        app.dependency_overrides.pop(get_current_user, None)


@pytest.mark.asyncio
@patch("core.engine.api.codebase_qa.ace_ask_product", new_callable=AsyncMock)
async def test_ask_codebase_minimal_response(mock_ask):
    """POST /codebase/ask handles minimal MCP response (only question_id/status)."""
    mock_ask.return_value = {
        "question_id": "product_question:xyz",
        "status": "open",
        "question": "what databases are used?",
    }

    from core.engine.api.main import app
    from core.engine.core.auth import get_current_user

    app.dependency_overrides[get_current_user] = _mock_user

    try:
        async with AsyncClient(
            transport=ASGITransport(app=app, raise_app_exceptions=False),
            base_url="http://test",
        ) as client:
            resp = await client.post(
                "/codebase/ask",
                json={"question": "what databases are used?"},
            )
        assert resp.status_code == 200
        data = resp.json()
        assert data["answer"] == ""
        assert data["sources"] == []
        assert data["capabilities_referenced"] == []
    finally:
        app.dependency_overrides.pop(get_current_user, None)


@pytest.mark.asyncio
@patch("core.engine.api.codebase_qa.ace_ask_product", new_callable=AsyncMock)
async def test_ask_codebase_passes_org_id(mock_ask):
    """POST /codebase/ask passes product_id from authenticated user to ace_ask_product."""
    mock_ask.return_value = {"question_id": "q:1", "status": "open", "question": "?"}

    from core.engine.api.main import app
    from core.engine.core.auth import get_current_user

    app.dependency_overrides[get_current_user] = _mock_user

    try:
        async with AsyncClient(
            transport=ASGITransport(app=app, raise_app_exceptions=False),
            base_url="http://test",
        ) as client:
            await client.post("/codebase/ask", json={"question": "how does caching work?"})

        mock_ask.assert_called_once_with(question="how does caching work?", product_id="product:test")
    finally:
        app.dependency_overrides.pop(get_current_user, None)


@pytest.mark.asyncio
async def test_ask_codebase_requires_question():
    """POST /codebase/ask rejects requests without a question field."""
    from core.engine.api.main import app
    from core.engine.core.auth import get_current_user

    app.dependency_overrides[get_current_user] = _mock_user

    try:
        async with AsyncClient(
            transport=ASGITransport(app=app, raise_app_exceptions=False),
            base_url="http://test",
        ) as client:
            resp = await client.post("/codebase/ask", json={})
        assert resp.status_code == 422
    finally:
        app.dependency_overrides.pop(get_current_user, None)
