# tests/test_auth_separation.py
"""Tests for JWT secret / API key separation."""

from unittest.mock import patch

from fastapi.testclient import TestClient

from core.engine.api.main import app
from core.engine.core.auth import verify_token


def test_login_rejects_jwt_secret():
    """Login does NOT accept JWT_SECRET as credential."""
    with patch("core.engine.api.auth_routes.settings") as mock_settings:
        mock_settings.jwt_secret = "super-secret-jwt-signing-key"
        mock_settings.jwt_algorithm = "HS256"
        mock_settings.jwt_expire_minutes = 60
        mock_settings.api_key = "my-login-key"
        mock_settings.demo_pass = ""

        client = TestClient(app)
        resp = client.post("/auth/token", json={"api_key": "super-secret-jwt-signing-key"})
        assert resp.status_code == 401


def test_login_accepts_api_key():
    """Login accepts API_KEY."""
    with patch("core.engine.api.auth_routes.settings") as mock_settings:
        mock_settings.jwt_secret = "jwt-secret"
        mock_settings.jwt_algorithm = "HS256"
        mock_settings.jwt_expire_minutes = 60
        mock_settings.api_key = "my-login-key"
        mock_settings.demo_pass = ""

        client = TestClient(app)
        resp = client.post("/auth/token", json={"api_key": "my-login-key"})
        assert resp.status_code == 200
        claims = verify_token(resp.json()["token"])
        assert claims["authorities"] == [
            "administer_lifecycle",
            "cognition-review",
            "deliver_export",
            "intelligence_build",
            "observe_read",
        ]
        assert claims["local_owner"] is True


def test_login_accepts_demo_pass():
    """Login also accepts demo_pass as alternative credential."""
    with patch("core.engine.api.auth_routes.settings") as mock_settings:
        mock_settings.jwt_secret = "jwt-secret"
        mock_settings.jwt_algorithm = "HS256"
        mock_settings.jwt_expire_minutes = 60
        mock_settings.api_key = "api-key"
        mock_settings.demo_pass = "demo123"

        client = TestClient(app)
        resp = client.post("/auth/token", json={"api_key": "demo123"})
        assert resp.status_code == 200
        claims = verify_token(resp.json()["token"])
        assert claims["authorities"] == []
        assert claims["local_owner"] is False


def test_login_refuses_ambiguous_owner_and_demo_credentials():
    with patch("core.engine.api.auth_routes.settings") as mock_settings:
        mock_settings.api_key = "shared-key"
        mock_settings.demo_pass = "shared-key"

        client = TestClient(app)
        resp = client.post("/auth/token", json={"api_key": "shared-key"})
        assert resp.status_code == 503


def test_refresh_preserves_signed_authorities():
    client = TestClient(app)
    app.dependency_overrides.clear()
    from core.engine.core.auth import get_current_user

    app.dependency_overrides[get_current_user] = lambda: {
        "sub": "user:reviewer",
        "product": "product:platform",
        "authorities": ["cognition-review"],
    }
    try:
        resp = client.post("/auth/token/refresh", headers={"Authorization": "Bearer test"})
    finally:
        app.dependency_overrides.clear()
    assert resp.status_code == 200
    claims = verify_token(resp.json()["token"])
    assert claims["authorities"] == ["cognition-review"]
