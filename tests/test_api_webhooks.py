"""Authority and tenant-scope tests for generic webhook ingestion."""

from unittest.mock import AsyncMock, patch

from fastapi.testclient import TestClient

from core.engine.api.main import app
from core.engine.core.auth import get_current_user


def test_webhook_ingest_requires_authentication() -> None:
    response = TestClient(app).post("/webhooks/ingest", json={"source": "test", "content": "payload"})

    assert response.status_code == 401


def test_webhook_ingest_scopes_write_to_authenticated_product() -> None:
    app.dependency_overrides[get_current_user] = lambda: {
        "sub": "user:test",
        "product": "product:tenant-a",
    }
    try:
        with patch("core.engine.api.webhooks.pool") as mock_pool:
            connection = AsyncMock()
            connection.query = AsyncMock(return_value=[[{"id": "memory:webhook"}]])
            mock_pool.connection.return_value.__aenter__ = AsyncMock(return_value=connection)
            mock_pool.connection.return_value.__aexit__ = AsyncMock(return_value=False)

            response = TestClient(app).post(
                "/webhooks/ingest",
                json={"source": "test", "content": "synthetic payload"},
            )
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 202
    query, params = connection.query.await_args.args
    assert "product = <record>$product" in query
    assert params["product"] == "product:tenant-a"
