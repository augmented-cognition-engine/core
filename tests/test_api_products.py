# tests/test_api_products.py
"""Tests for GET/POST /products and POST /products/{slug}/link."""

from unittest.mock import AsyncMock, patch

from fastapi.testclient import TestClient

from core.engine.api.main import app
from core.engine.core.auth import get_current_user

MOCK_USER = {"sub": "user:test", "product": "product:test"}


def test_list_products_requires_auth():
    """GET /products returns 401 without JWT."""
    client = TestClient(app)
    resp = client.get("/products")
    assert resp.status_code == 401


def test_list_products_returns_list():
    """GET /products returns a products list."""
    app.dependency_overrides[get_current_user] = lambda: MOCK_USER
    with patch("core.engine.api.products.pool") as mock_pool:
        mock_conn = AsyncMock()
        mock_pool.connection.return_value.__aenter__ = AsyncMock(return_value=mock_conn)
        mock_pool.connection.return_value.__aexit__ = AsyncMock(return_value=False)
        # First query: get tenant. Second query: get products list.
        mock_conn.query = AsyncMock(
            side_effect=[
                [{"tenant": "tenant:test"}],  # tenant lookup
                [{"id": "product:test", "name": "Test"}],  # products list
            ]
        )

        client = TestClient(app)
        resp = client.get("/products")

    app.dependency_overrides.clear()
    assert resp.status_code == 200
    assert "products" in resp.json()


def test_create_product_requires_auth():
    """POST /products returns 401 without JWT."""
    client = TestClient(app)
    resp = client.post("/products", json={"name": "test_product"})
    assert resp.status_code == 401


def test_create_product_success():
    """POST /products creates a product and returns it."""
    app.dependency_overrides[get_current_user] = lambda: MOCK_USER
    with patch("core.engine.api.products.pool") as mock_pool:
        mock_conn = AsyncMock()
        mock_pool.connection.return_value.__aenter__ = AsyncMock(return_value=mock_conn)
        mock_pool.connection.return_value.__aexit__ = AsyncMock(return_value=False)
        mock_conn.query = AsyncMock(
            side_effect=[
                [],  # existing check (not found)
                [{"tenant": "tenant:test"}],  # tenant lookup
                [],  # upsert (no return needed)
                [{"id": "product:test_product", "name": "test_product"}],  # final select
            ]
        )

        client = TestClient(app)
        resp = client.post("/products", json={"name": "test_product"})

    app.dependency_overrides.clear()
    assert resp.status_code == 201


def test_link_repo_requires_auth():
    """POST /products/{slug}/link returns 401 without JWT."""
    client = TestClient(app)
    resp = client.post("/products/test_product/link", json={"repo_path": "/projects/test"})
    assert resp.status_code == 401


def test_create_product_conflict():
    """POST /products returns 409 if product already exists."""
    app.dependency_overrides[get_current_user] = lambda: MOCK_USER
    with patch("core.engine.api.products.pool") as mock_pool:
        mock_conn = AsyncMock()
        mock_pool.connection.return_value.__aenter__ = AsyncMock(return_value=mock_conn)
        mock_pool.connection.return_value.__aexit__ = AsyncMock(return_value=False)
        mock_conn.query = AsyncMock(
            side_effect=[
                [{"id": "product:existing"}],  # existing check — found
            ]
        )
        client = TestClient(app)
        resp = client.post("/products", json={"name": "existing"})
    app.dependency_overrides.clear()
    assert resp.status_code == 409


def test_link_repo_success():
    """POST /products/{slug}/link creates a project record."""
    app.dependency_overrides[get_current_user] = lambda: MOCK_USER
    with patch("core.engine.api.products.pool") as mock_pool:
        mock_conn = AsyncMock()
        mock_pool.connection.return_value.__aenter__ = AsyncMock(return_value=mock_conn)
        mock_pool.connection.return_value.__aexit__ = AsyncMock(return_value=False)
        mock_conn.query = AsyncMock(
            side_effect=[
                [{"id": "product:test_product"}],  # existing check — found
                [],  # upsert project
            ]
        )
        client = TestClient(app)
        resp = client.post("/products/test_product/link", json={"repo_path": "/projects/myrepo"})
    app.dependency_overrides.clear()
    assert resp.status_code == 201
    data = resp.json()
    assert data["product"] == "product:test_product"


def test_link_repo_not_found():
    """POST /products/{slug}/link returns 404 for unknown product."""
    app.dependency_overrides[get_current_user] = lambda: MOCK_USER
    with patch("core.engine.api.products.pool") as mock_pool:
        mock_conn = AsyncMock()
        mock_pool.connection.return_value.__aenter__ = AsyncMock(return_value=mock_conn)
        mock_pool.connection.return_value.__aexit__ = AsyncMock(return_value=False)
        mock_conn.query = AsyncMock(return_value=[])  # product not found
        client = TestClient(app)
        resp = client.post("/products/unknown/link", json={"repo_path": "/projects/myrepo"})
    app.dependency_overrides.clear()
    assert resp.status_code == 404


def test_products_list_includes_health_fields():
    """GET /products returns health fields on each product."""
    app.dependency_overrides[get_current_user] = lambda: MOCK_USER
    with patch("core.engine.api.products.pool") as mock_pool:
        mock_conn = AsyncMock()
        mock_pool.connection.return_value.__aenter__ = AsyncMock(return_value=mock_conn)
        mock_pool.connection.return_value.__aexit__ = AsyncMock(return_value=False)
        # Query sequence:
        #   1. tenant lookup
        #   2. products list
        #   3. open gates count (gate_evaluation pending)
        #   4. active initiatives count
        #   5. at-risk initiatives count (paused/blocked)
        #   6. last task activity
        mock_conn.query = AsyncMock(
            side_effect=[
                [{"tenant": "tenant:test"}],  # 1 tenant
                [
                    {
                        "id": "product:test",
                        "name": "Test",  # 2 products
                        "created_at": "2026-01-01T00:00:00Z",
                    }
                ],
                [{"n": 2}],  # 3 open_gates
                [{"n": 1}],  # 4 active_initiatives
                [{"n": 0}],  # 5 at_risk
                [{"created_at": "2026-04-10T12:00:00Z"}],  # 6 last_activity
            ]
        )

        client = TestClient(app)
        resp = client.get("/products")

    app.dependency_overrides.clear()
    assert resp.status_code == 200
    data = resp.json()
    assert "products" in data
    assert len(data["products"]) == 1
    p = data["products"][0]
    assert "health" in p, "health field missing"
    assert "active_initiatives" in p, "active_initiatives field missing"
    assert "open_gates" in p, "open_gates field missing"
    assert "last_activity_at" in p, "last_activity_at field missing"
    assert p["health"] in ("green", "amber", "red"), f"unexpected health value: {p['health']}"
    # at_risk=0, open_gates=2 → amber
    assert p["health"] == "amber"
    assert p["active_initiatives"] == 1
    assert p["open_gates"] == 2


def test_products_list_health_red_when_at_risk():
    """GET /products returns health=red when initiatives are paused/blocked."""
    app.dependency_overrides[get_current_user] = lambda: MOCK_USER
    with patch("core.engine.api.products.pool") as mock_pool:
        mock_conn = AsyncMock()
        mock_pool.connection.return_value.__aenter__ = AsyncMock(return_value=mock_conn)
        mock_pool.connection.return_value.__aexit__ = AsyncMock(return_value=False)
        mock_conn.query = AsyncMock(
            side_effect=[
                [{"tenant": "tenant:test"}],
                [{"id": "product:test", "name": "Test", "created_at": "2026-01-01T00:00:00Z"}],
                [{"n": 0}],  # open_gates
                [{"n": 2}],  # active_initiatives
                [{"n": 1}],  # at_risk — paused/blocked
                [],  # last_activity (none)
            ]
        )

        client = TestClient(app)
        resp = client.get("/products")

    app.dependency_overrides.clear()
    assert resp.status_code == 200
    p = resp.json()["products"][0]
    assert p["health"] == "red"
    assert p["last_activity_at"] is None


def test_products_list_health_green_when_no_issues():
    """GET /products returns health=green when no open gates or at-risk initiatives."""
    app.dependency_overrides[get_current_user] = lambda: MOCK_USER
    with patch("core.engine.api.products.pool") as mock_pool:
        mock_conn = AsyncMock()
        mock_pool.connection.return_value.__aenter__ = AsyncMock(return_value=mock_conn)
        mock_pool.connection.return_value.__aexit__ = AsyncMock(return_value=False)
        mock_conn.query = AsyncMock(
            side_effect=[
                [{"tenant": "tenant:test"}],
                [{"id": "product:test", "name": "Test", "created_at": "2026-01-01T00:00:00Z"}],
                [{"n": 0}],  # open_gates
                [{"n": 3}],  # active_initiatives
                [{"n": 0}],  # at_risk
                [],  # last_activity (none)
            ]
        )

        client = TestClient(app)
        resp = client.get("/products")

    app.dependency_overrides.clear()
    assert resp.status_code == 200
    p = resp.json()["products"][0]
    assert p["health"] == "green"


def test_products_list_health_graceful_on_enrichment_failure():
    """GET /products returns health=green fallback when enrichment queries fail."""
    app.dependency_overrides[get_current_user] = lambda: MOCK_USER
    with patch("core.engine.api.products.pool") as mock_pool:
        mock_conn = AsyncMock()
        mock_pool.connection.return_value.__aenter__ = AsyncMock(return_value=mock_conn)
        mock_pool.connection.return_value.__aexit__ = AsyncMock(return_value=False)

        def raise_after_two(query, params=None):
            call_count = mock_conn.query.call_count
            if call_count <= 2:
                if call_count == 1:
                    return [{"tenant": "tenant:test"}]
                return [{"id": "product:test", "name": "Test", "created_at": "2026-01-01T00:00:00Z"}]
            raise RuntimeError("DB error")

        mock_conn.query = AsyncMock(side_effect=raise_after_two)

        client = TestClient(app)
        resp = client.get("/products")

    app.dependency_overrides.clear()
    assert resp.status_code == 200
    data = resp.json()
    assert len(data["products"]) == 1
    p = data["products"][0]
    assert p["health"] == "green"
    assert p["active_initiatives"] == 0
    assert p["open_gates"] == 0
    assert p["last_activity_at"] is None
