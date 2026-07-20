"""Tests for POST /auth/switch-product."""

from unittest.mock import AsyncMock, patch

from fastapi.testclient import TestClient

from core.engine.api.main import app
from core.engine.core.auth import get_current_user

MOCK_USER = {"sub": "user:test", "product": "product:test"}
_AUTH = {"Authorization": "Bearer test"}  # bypasses APIKeyMiddleware; auth resolved via dependency_overrides


def test_switch_product_requires_auth():
    """POST /auth/switch-product returns 401 without JWT."""
    client = TestClient(app)
    resp = client.post("/auth/switch-product", json={"product_id": "product:other"})
    assert resp.status_code == 401


def test_switch_product_404_unknown():
    """POST /auth/switch-product returns 404 for a product outside the caller's tenant."""
    app.dependency_overrides[get_current_user] = lambda: MOCK_USER
    with patch("core.engine.api.auth_routes.pool") as mock_pool:
        mock_conn = AsyncMock()
        mock_pool.connection.return_value.__aenter__ = AsyncMock(return_value=mock_conn)
        mock_pool.connection.return_value.__aexit__ = AsyncMock(return_value=False)
        # First query: caller's tenant lookup. Second query: target product check (not found).
        mock_conn.query = AsyncMock(
            side_effect=[
                [{"tenant": "tenant:test"}],  # caller's tenant
                [],  # target product not in this tenant
            ]
        )

        client = TestClient(app)
        resp = client.post("/auth/switch-product", json={"product_id": "product:unknown"}, headers=_AUTH)

    app.dependency_overrides.clear()
    assert resp.status_code == 404


def test_switch_product_returns_new_token():
    """POST /auth/switch-product returns a new JWT with the new product claim."""
    app.dependency_overrides[get_current_user] = lambda: MOCK_USER
    with patch("core.engine.api.auth_routes.pool") as mock_pool:
        mock_conn = AsyncMock()
        mock_pool.connection.return_value.__aenter__ = AsyncMock(return_value=mock_conn)
        mock_pool.connection.return_value.__aexit__ = AsyncMock(return_value=False)
        # First query: caller's tenant lookup. Second query: target product found in same tenant.
        mock_conn.query = AsyncMock(
            side_effect=[
                [{"tenant": "tenant:test"}],  # caller's tenant
                [{"id": "product:trading_system"}],  # target product found
            ]
        )

        client = TestClient(app)
        resp = client.post("/auth/switch-product", json={"product_id": "product:trading_system"}, headers=_AUTH)

    app.dependency_overrides.clear()
    assert resp.status_code == 200
    data = resp.json()
    assert "token" in data
