# tests/test_middleware.py
"""Tests for correlation ID middleware and request logging middleware."""

from __future__ import annotations

import pytest
from httpx import ASGITransport, AsyncClient
from starlette.applications import Starlette
from starlette.requests import Request
from starlette.responses import JSONResponse
from starlette.routing import Route

from core.engine.api.middleware import CorrelationIDMiddleware, RequestLoggingMiddleware
from core.engine.core.log_context import get_correlation_id


async def _homepage(request: Request):
    return JSONResponse({"cid": get_correlation_id(), "path": request.url.path})


def _make_app(*middlewares):
    """Build a minimal Starlette app with the given middlewares."""
    app = Starlette(routes=[Route("/", _homepage), Route("/health", _homepage)])
    for mw in middlewares:
        app.add_middleware(mw)
    return app


@pytest.mark.asyncio
async def test_correlation_id_generated_when_missing():
    app = _make_app(CorrelationIDMiddleware)
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        resp = await client.get("/")
    assert resp.status_code == 200
    cid = resp.headers.get("X-Correlation-ID", "")
    assert len(cid) == 12
    assert resp.json()["cid"] == cid


@pytest.mark.asyncio
async def test_inbound_correlation_id_echoed():
    app = _make_app(CorrelationIDMiddleware)
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        resp = await client.get("/", headers={"X-Correlation-ID": "myid-abc"})
    assert resp.headers["X-Correlation-ID"] == "myid-abc"
    assert resp.json()["cid"] == "myid-abc"


@pytest.mark.asyncio
async def test_traceparent_header_used_as_correlation_id():
    """W3C traceparent trace-id fragment takes priority over X-Correlation-ID."""
    app = _make_app(CorrelationIDMiddleware)
    traceparent = "00-4bf92f3577b34da6a3ce929d0e0e4736-00f067aa0ba902b7-01"
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        resp = await client.get("/", headers={"traceparent": traceparent})
    # First 12 chars of trace-id: "4bf92f3577b3"
    assert resp.headers["X-Correlation-ID"] == "4bf92f3577b3"
    assert resp.json()["cid"] == "4bf92f3577b3"


@pytest.mark.asyncio
async def test_malformed_traceparent_falls_back_to_x_correlation_id():
    """Malformed traceparent is ignored and X-Correlation-ID is used instead."""
    app = _make_app(CorrelationIDMiddleware)
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        resp = await client.get(
            "/",
            headers={"traceparent": "bad-header", "X-Correlation-ID": "fallback-id"},
        )
    assert resp.headers["X-Correlation-ID"] == "fallback-id"


@pytest.mark.asyncio
async def test_request_logging_middleware_does_not_break_response():
    app = _make_app(RequestLoggingMiddleware, CorrelationIDMiddleware)
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        resp = await client.get("/")
    assert resp.status_code == 200
    assert "cid" in resp.json()


@pytest.mark.asyncio
async def test_health_endpoint_skipped_by_logging(caplog):
    """RequestLoggingMiddleware should not emit a log line for /health requests."""
    import logging

    app = _make_app(RequestLoggingMiddleware, CorrelationIDMiddleware)
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        with caplog.at_level(logging.INFO, logger="core.engine.api.middleware"):
            await client.get("/health")

    # No access log line for /health
    health_logs = [r for r in caplog.records if "/health" in r.getMessage()]
    assert len(health_logs) == 0


# ---------------------------------------------------------------------------
# APIKeyMiddleware
# ---------------------------------------------------------------------------

from unittest.mock import patch

from core.engine.api.middleware import APIKeyMiddleware


@pytest.mark.asyncio
async def test_api_key_middleware_noop_when_no_key_configured():
    """When API_KEY is empty, all requests pass through."""
    app = Starlette(routes=[Route("/", _homepage)])
    app.add_middleware(APIKeyMiddleware)
    with patch("core.engine.core.config.settings") as mock_settings:
        mock_settings.api_key = ""
        mock_settings.environment = "development"
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            resp = await client.get("/")
    assert resp.status_code == 200


@pytest.mark.asyncio
async def test_api_key_middleware_fails_closed_in_production_without_key():
    """A missing production API_KEY is a configuration failure, never open access."""
    app = Starlette(routes=[Route("/private", _homepage)])
    app.add_middleware(APIKeyMiddleware)
    with patch("core.engine.core.config.settings") as mock_settings:
        mock_settings.api_key = ""
        mock_settings.environment = "production"
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            resp = await client.get("/private")
    assert resp.status_code == 503
    assert resp.json()["detail"] == "API authentication is not configured"


@pytest.mark.asyncio
async def test_api_key_middleware_rejects_missing_key():
    """When API_KEY is set, requests without X-API-Key or Bearer token get 401."""
    app = Starlette(routes=[Route("/", _homepage)])
    app.add_middleware(APIKeyMiddleware)
    with patch("core.engine.core.config.settings") as mock_settings:
        mock_settings.api_key = "secret"
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            resp = await client.get("/")
    assert resp.status_code == 401


@pytest.mark.asyncio
async def test_api_key_middleware_accepts_valid_key():
    """Correct X-API-Key header passes through."""
    app = Starlette(routes=[Route("/", _homepage)])
    app.add_middleware(APIKeyMiddleware)
    with patch("core.engine.core.config.settings") as mock_settings:
        mock_settings.api_key = "secret"
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            resp = await client.get("/", headers={"X-API-Key": "secret"})
    assert resp.status_code == 200


@pytest.mark.asyncio
async def test_api_key_middleware_accepts_bearer_token():
    """A verified Authorization bearer token passes through."""
    app = Starlette(routes=[Route("/", _homepage)])
    app.add_middleware(APIKeyMiddleware)
    with patch("core.engine.core.config.settings") as mock_settings:
        mock_settings.api_key = "secret"
        with patch("core.engine.core.auth.verify_token", return_value={"sub": "user:default"}):
            async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
                resp = await client.get("/", headers={"Authorization": "Bearer valid-token"})
    assert resp.status_code == 200


@pytest.mark.asyncio
async def test_api_key_middleware_rejects_invalid_bearer_token():
    """Bearer-shaped text is not authentication unless JWT verification succeeds."""
    from fastapi import HTTPException

    app = Starlette(routes=[Route("/", _homepage)])
    app.add_middleware(APIKeyMiddleware)
    with patch("core.engine.core.config.settings") as mock_settings:
        mock_settings.api_key = "secret"
        with patch("core.engine.core.auth.verify_token", side_effect=HTTPException(status_code=401)):
            async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
                resp = await client.get("/", headers={"Authorization": "Bearer arbitrary-text"})
    assert resp.status_code == 401


@pytest.mark.asyncio
async def test_api_key_middleware_skips_health():
    """Health endpoint bypasses API key check even when key is configured."""
    app = Starlette(routes=[Route("/health", _homepage)])
    app.add_middleware(APIKeyMiddleware)
    with patch("core.engine.core.config.settings") as mock_settings:
        mock_settings.api_key = "secret"
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            resp = await client.get("/health")
    assert resp.status_code == 200


@pytest.mark.asyncio
async def test_api_key_middleware_skips_auth_token():
    """/auth/token bypasses API key check so clients can exchange for JWT."""
    app = Starlette(routes=[Route("/auth/token", _homepage, methods=["POST"])])
    app.add_middleware(APIKeyMiddleware)
    with patch("core.engine.core.config.settings") as mock_settings:
        mock_settings.api_key = "secret"
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            resp = await client.post("/auth/token")
    assert resp.status_code == 200


@pytest.mark.asyncio
async def test_api_key_middleware_does_not_exempt_memory():
    """Home-directory memory must remain behind the configured API gate."""
    app = Starlette(routes=[Route("/memory/projects", _homepage)])
    app.add_middleware(APIKeyMiddleware)
    with patch("core.engine.core.config.settings") as mock_settings:
        mock_settings.api_key = "secret"
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            resp = await client.get("/memory/projects")
    assert resp.status_code == 401
