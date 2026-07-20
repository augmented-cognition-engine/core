# tests/test_api_capture_auth.py
"""Tests for POST /sessions authentication."""

from fastapi.testclient import TestClient

from core.engine.api.main import app


def test_sessions_requires_auth():
    """POST /sessions returns 401 without JWT."""
    client = TestClient(app)
    resp = client.post(
        "/sessions",
        json={
            "transcript": "test transcript",
            "product_id": "product:test",
        },
    )
    assert resp.status_code == 401


def test_sessions_uses_jwt_org():
    """POST /sessions extracts product_id from JWT, not request body."""
    from unittest.mock import AsyncMock, patch

    from core.engine.core.auth import get_current_user

    mock_user = {"sub": "user:test", "product": "org:from_jwt"}
    app.dependency_overrides[get_current_user] = lambda: mock_user

    with patch("core.engine.api.capture.CapturePipeline") as mock_pipeline:
        mock_instance = AsyncMock()
        mock_pipeline.return_value = mock_instance
        mock_instance.run = AsyncMock()

        client = TestClient(app)
        resp = client.post(
            "/sessions",
            json={
                "transcript": "test transcript",
            },
        )

    app.dependency_overrides.clear()

    assert resp.status_code == 202
    # Verify pipeline was created with org from JWT
    call_kwargs = mock_pipeline.call_args[1]
    assert call_kwargs["product_id"] == "org:from_jwt"
