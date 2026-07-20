# tests/test_auth_separation.py
"""Tests for JWT secret / API key separation."""

from unittest.mock import patch

from fastapi.testclient import TestClient

from core.engine.api.main import app


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
        assert "token" in resp.json()


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
