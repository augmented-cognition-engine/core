# tests/test_api_observations.py
"""Tests for POST /observations — lightweight observation capture."""

from unittest.mock import AsyncMock, patch

import pytest
from fastapi.testclient import TestClient

from core.engine.api.main import app
from core.engine.core.auth import get_current_user


@pytest.fixture
def client():
    mock_user = {"sub": "user:test", "product": "product:test"}
    app.dependency_overrides[get_current_user] = lambda: mock_user
    yield TestClient(app)
    app.dependency_overrides.clear()


def test_create_observation_returns_201(client):
    """POST /observations creates an observation and returns 201."""
    with patch("core.engine.api.capture.pool") as mock_pool:
        mock_conn = AsyncMock()
        mock_conn.query = AsyncMock(return_value=[[{"id": "observation:abc"}]])
        mock_pool.connection.return_value.__aenter__ = AsyncMock(return_value=mock_conn)
        mock_pool.connection.return_value.__aexit__ = AsyncMock(return_value=False)

        resp = client.post(
            "/observations",
            json={
                "observation_type": "correction",
                "content": "Use rem not px",
                "domain_path": "design_systems.tokens",
                "confidence": 0.85,
            },
        )

    assert resp.status_code == 201
    data = resp.json()
    assert data["status"] == "captured"
    assert "id" in data


def test_create_observation_default_confidence(client):
    """POST /observations uses default confidence of 0.7."""
    with patch("core.engine.api.capture.pool") as mock_pool:
        mock_conn = AsyncMock()
        mock_conn.query = AsyncMock(return_value=[[{"id": "observation:def"}]])
        mock_pool.connection.return_value.__aenter__ = AsyncMock(return_value=mock_conn)
        mock_pool.connection.return_value.__aexit__ = AsyncMock(return_value=False)

        resp = client.post(
            "/observations",
            json={
                "observation_type": "pattern",
                "content": "Teams prefer async standup",
                "domain_path": "operations.process",
            },
        )

    assert resp.status_code == 201
    call_args = mock_conn.query.call_args
    # Params dict is the second positional arg to db.query(sql, params)
    params = call_args[0][1] if len(call_args[0]) > 1 else call_args[1]
    assert params["confidence"] == 0.7


def test_create_observation_validates_required_fields(client):
    """POST /observations returns 422 when required fields are missing."""
    resp = client.post(
        "/observations",
        json={
            "observation_type": "correction",
            # missing content and domain_path
        },
    )
    assert resp.status_code == 422
