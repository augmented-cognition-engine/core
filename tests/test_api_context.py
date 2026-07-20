# tests/test_api_context.py
"""Tests for GET /intel/context — intelligence context loading for a topic."""

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


def test_intel_context_returns_partitioned_intelligence(client):
    """GET /intel/context returns insights partitioned by type."""
    with (
        patch("core.engine.api.intel.load_intelligence", new_callable=AsyncMock) as mock_load,
        patch("core.engine.api.intel.calculate_maturation", new_callable=AsyncMock) as mock_mat,
    ):
        mock_load.return_value = {
            "insights": [
                {"content": "Use flat namespace", "confidence": 0.9, "insight_type": "pattern"},
                {"content": "Never use px", "confidence": 0.85, "insight_type": "correction"},
            ],
            "total_count": 2,
        }
        mock_mat.return_value = {"phase": 3, "phase_name": "reliable"}

        resp = client.get("/intel/context", params={"q": "design tokens", "product": "product:test"})

    assert resp.status_code == 200
    data = resp.json()
    assert data["domain_path"] == "design_tokens"
    assert len(data["insights"]) == 1
    assert len(data["corrections"]) == 1
    assert data["maturation_level"] == "reliable"
    assert data["total_count"] == 2
    mock_mat.assert_awaited_once_with("discipline", "design_tokens", "product:test")


def test_intel_context_requires_query_param(client):
    """GET /intel/context returns 422 when q param is missing."""
    resp = client.get("/intel/context", params={"product": "product:test"})
    assert resp.status_code == 422


def test_intel_context_normalizes_query(client):
    """GET /intel/context normalizes spaces to underscores in domain_path."""
    with (
        patch("core.engine.api.intel.load_intelligence", new_callable=AsyncMock) as mock_load,
        patch("core.engine.api.intel.calculate_maturation", new_callable=AsyncMock) as mock_mat,
    ):
        mock_load.return_value = {"insights": [], "total_count": 0}
        mock_mat.return_value = {"phase": 1, "phase_name": "nascent"}

        resp = client.get("/intel/context", params={"q": "Design Systems", "product": "product:test"})

    assert resp.status_code == 200
    data = resp.json()
    assert data["domain_path"] == "design_systems"
    mock_load.assert_called_once_with("design_systems", "product:test", mode="reactive")


def test_intel_context_uses_authenticated_product(client):
    """A caller cannot read intelligence from a different product scope."""
    with (
        patch("core.engine.api.intel.load_intelligence", new_callable=AsyncMock) as mock_load,
        patch("core.engine.api.intel.calculate_maturation", new_callable=AsyncMock) as mock_mat,
    ):
        mock_load.return_value = {"insights": [], "total_count": 0}
        mock_mat.return_value = {"phase": 1, "phase_name": "nascent"}

        resp = client.get("/intel/context", params={"q": "strategy", "product": "product:other"})

    assert resp.status_code == 200
    mock_load.assert_awaited_once_with("strategy", "product:test", mode="reactive")
    mock_mat.assert_awaited_once_with("discipline", "strategy", "product:test")
