# tests/test_graph_health.py
"""Tests for the graph health-map API."""

from contextlib import asynccontextmanager
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from core.engine.api.graph_health import health_map

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def mock_db():
    """Mock database connection that records all queries."""
    db = AsyncMock()
    db.query = AsyncMock(return_value=[])
    return db


@pytest.fixture
def mock_pool(mock_db):
    """Mock pool that yields the mock db."""
    mock_p = MagicMock()

    @asynccontextmanager
    async def _conn():
        yield mock_db

    mock_p.connection = _conn
    return mock_p


@pytest.fixture
def mock_user():
    return {"sub": "user:test", "email": "test@example.com", "product": "product:platform"}


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


class TestHealthMapCapabilities:
    @pytest.mark.asyncio
    async def test_capabilities_with_quality_scores(self, mock_pool, mock_db, mock_user):
        """Capabilities with quality scores return correct average health_score."""
        cap_rows = [
            {
                "id": "capability:auth",
                "name": "Authentication",
                "slug": "auth",
                "status": "built",
                "product": "product:platform",
            },
        ]
        quality_rows = [
            {"capability": "capability:auth", "discipline": "testing", "score": 0.8, "product": "product:platform"},
            {"capability": "capability:auth", "discipline": "security", "score": 0.6, "product": "product:platform"},
            {
                "capability": "capability:auth",
                "discipline": "documentation",
                "score": 0.2,
                "product": "product:platform",
            },
        ]

        def _query_side_effect(query, params=None):
            if "FROM capability WHERE" in query:
                return cap_rows
            if "FROM capability_quality WHERE" in query:
                return quality_rows
            if "FROM graph_file WHERE" in query:
                return []
            # Edge count queries — return empty
            return []

        mock_db.query = AsyncMock(side_effect=_query_side_effect)

        with patch("core.engine.api.graph_health.pool", mock_pool):
            result = await health_map(filter="all", user=mock_user)

        nodes = result["nodes"]
        cap_nodes = [n for n in nodes if n["type"] == "capability"]
        assert len(cap_nodes) == 1

        node = cap_nodes[0]
        assert node["id"] == "capability:auth"
        assert node["label"] == "Authentication"
        assert node["layer"] == "product"
        # Average of 0.8 + 0.6 + 0.2 = 1.6 / 3 = 0.533...
        assert node["health_score"] == pytest.approx(0.53, abs=0.01)
        # documentation has score 0.2 < 0.5 → gap
        assert "documentation" in node["gaps"]
        assert "testing" not in node["gaps"]
        assert node["details"]["status"] == "built"


class TestHealthMapEmpty:
    @pytest.mark.asyncio
    async def test_empty_graph_returns_empty_nodes(self, mock_pool, mock_db, mock_user):
        """Empty graph returns empty nodes list."""
        mock_db.query = AsyncMock(return_value=[])

        with patch("core.engine.api.graph_health.pool", mock_pool):
            result = await health_map(filter="all", user=mock_user)

        assert result["nodes"] == []


class TestHealthMapHighRisk:
    @pytest.mark.asyncio
    async def test_high_risk_filter_only_low_scores(self, mock_pool, mock_db, mock_user):
        """high_risk filter only returns nodes with health_score < 0.4."""
        cap_rows = [
            {
                "id": "capability:healthy",
                "name": "Healthy Cap",
                "slug": "healthy",
                "status": "built",
                "product": "product:platform",
            },
            {
                "id": "capability:risky",
                "name": "Risky Cap",
                "slug": "risky",
                "status": "built",
                "product": "product:platform",
            },
        ]
        quality_rows = [
            # healthy: avg = 0.9
            {"capability": "capability:healthy", "discipline": "testing", "score": 0.9, "product": "product:platform"},
            # risky: avg = 0.2
            {"capability": "capability:risky", "discipline": "testing", "score": 0.2, "product": "product:platform"},
        ]

        def _query_side_effect(query, params=None):
            if "FROM capability WHERE" in query:
                return cap_rows
            if "FROM capability_quality WHERE" in query:
                return quality_rows
            if "FROM graph_file WHERE" in query:
                return []
            return []

        mock_db.query = AsyncMock(side_effect=_query_side_effect)

        with patch("core.engine.api.graph_health.pool", mock_pool):
            result = await health_map(filter="high_risk", user=mock_user)

        nodes = result["nodes"]
        # Only the risky capability (score 0.2) should appear
        assert len(nodes) == 1
        assert nodes[0]["id"] == "capability:risky"
        assert nodes[0]["health_score"] < 0.4
