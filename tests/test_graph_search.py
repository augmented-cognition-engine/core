# tests/test_graph_search.py
"""Tests for the cross-table graph search API."""

from contextlib import asynccontextmanager
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from core.engine.api.graph_search import _relevance_score, graph_search

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
    return {"sub": "user:test", "email": "test@example.com"}


# ---------------------------------------------------------------------------
# Unit tests: relevance scoring
# ---------------------------------------------------------------------------


class TestRelevanceScore:
    def test_exact_match(self):
        assert _relevance_score("MCP Tools", "MCP Tools") == 0

    def test_exact_match_case_insensitive(self):
        assert _relevance_score("MCP Tools", "mcp tools") == 0

    def test_starts_with(self):
        assert _relevance_score("MCP Tools", "MCP") == 1

    def test_starts_with_case_insensitive(self):
        assert _relevance_score("MCP Tools", "mcp") == 1

    def test_contains(self):
        assert _relevance_score("MCP Tools", "Tools") == 2

    def test_contains_case_insensitive(self):
        assert _relevance_score("MCP Tools", "tools") == 2


# ---------------------------------------------------------------------------
# Endpoint tests
# ---------------------------------------------------------------------------


class TestGraphSearch:
    @pytest.mark.asyncio
    async def test_search_returns_matching_capabilities(self, mock_pool, mock_db, mock_user):
        """Search returns matching capabilities from the capability table."""
        cap_rows = [
            {"id": "capability:mcp_tools", "name": "MCP Tools", "slug": "mcp-tools"},
        ]

        # 5 tables queried in sequence: capability, initiative, decision, graph_file, idea
        mock_db.query = AsyncMock(
            side_effect=[
                cap_rows,  # capability
                [],  # initiative
                [],  # decision
                [],  # graph_file
                [],  # idea
            ]
        )

        with patch("core.engine.api.graph_search.pool", mock_pool):
            result = await graph_search(q="MCP", user=mock_user)

        assert len(result["results"]) == 1
        assert result["results"][0]["id"] == "capability:mcp_tools"
        assert result["results"][0]["label"] == "MCP Tools"
        assert result["results"][0]["layer"] == "product"
        assert result["results"][0]["type"] == "capability"

    @pytest.mark.asyncio
    async def test_search_returns_empty_for_no_match(self, mock_pool, mock_db, mock_user):
        """Search returns empty results when nothing matches."""
        mock_db.query = AsyncMock(
            side_effect=[
                [],  # capability
                [],  # initiative
                [],  # decision
                [],  # graph_file
                [],  # idea
            ]
        )

        with patch("core.engine.api.graph_search.pool", mock_pool):
            result = await graph_search(q="nonexistent_xyz", user=mock_user)

        assert result["results"] == []

    @pytest.mark.asyncio
    async def test_search_merges_across_tables(self, mock_pool, mock_db, mock_user):
        """Search merges results from multiple tables."""
        cap_rows = [
            {"id": "capability:auth", "name": "Auth System", "slug": "auth"},
        ]
        init_rows = [
            {"id": "initiative:auth_rework", "title": "Auth Rework", "slug": "auth-rework"},
        ]
        decision_rows = [
            {"id": "decision:auth_method", "title": "Auth Method Choice", "slug": "auth-method"},
        ]

        mock_db.query = AsyncMock(
            side_effect=[
                cap_rows,  # capability
                init_rows,  # initiative
                decision_rows,  # decision
                [],  # graph_file
                [],  # idea
            ]
        )

        with patch("core.engine.api.graph_search.pool", mock_pool):
            result = await graph_search(q="auth", user=mock_user)

        assert len(result["results"]) == 3
        types = {r["type"] for r in result["results"]}
        assert types == {"capability", "initiative", "decision"}

    @pytest.mark.asyncio
    async def test_search_sorts_by_relevance(self, mock_pool, mock_db, mock_user):
        """Exact match sorts before starts_with, which sorts before contains."""
        cap_rows = [
            {"id": "capability:mcp_tools", "name": "MCP Tools", "slug": "mcp-tools"},
            {"id": "capability:mcp", "name": "MCP", "slug": "mcp"},
            {"id": "capability:advanced_mcp", "name": "Advanced MCP", "slug": "advanced-mcp"},
        ]

        mock_db.query = AsyncMock(
            side_effect=[
                cap_rows,  # capability
                [],  # initiative
                [],  # decision
                [],  # graph_file
                [],  # idea
            ]
        )

        with patch("core.engine.api.graph_search.pool", mock_pool):
            result = await graph_search(q="MCP", user=mock_user)

        ids = [r["id"] for r in result["results"]]
        # Exact match first, then starts_with, then contains
        assert ids[0] == "capability:mcp"  # exact
        assert ids[1] == "capability:mcp_tools"  # starts_with
        assert ids[2] == "capability:advanced_mcp"  # contains

    @pytest.mark.asyncio
    async def test_search_caps_at_10_results(self, mock_pool, mock_db, mock_user):
        """Search returns at most 10 results even if more match."""
        # Each table returns 5 results (5 tables * 5 = 25 raw results)
        cap_rows = [{"id": f"capability:c{i}", "name": f"Cap {i}", "slug": f"c{i}"} for i in range(5)]
        init_rows = [{"id": f"initiative:i{i}", "title": f"Init {i}", "slug": f"i{i}"} for i in range(5)]
        decision_rows = [{"id": f"decision:d{i}", "title": f"Dec {i}", "slug": f"d{i}"} for i in range(5)]
        file_rows = [{"id": f"graph_file:f{i}", "name": f"File {i}", "path": f"f{i}.py"} for i in range(5)]
        idea_rows = [{"id": f"idea:id{i}", "title": f"Idea {i}"} for i in range(5)]

        mock_db.query = AsyncMock(
            side_effect=[
                cap_rows,
                init_rows,
                decision_rows,
                file_rows,
                idea_rows,
            ]
        )

        with patch("core.engine.api.graph_search.pool", mock_pool):
            result = await graph_search(q="a", user=mock_user)

        assert len(result["results"]) == 10

    @pytest.mark.asyncio
    async def test_search_strips_internal_score(self, mock_pool, mock_db, mock_user):
        """Internal _score field should not appear in results."""
        cap_rows = [
            {"id": "capability:test", "name": "Test", "slug": "test"},
        ]

        mock_db.query = AsyncMock(
            side_effect=[
                cap_rows,
                [],
                [],
                [],
                [],
            ]
        )

        with patch("core.engine.api.graph_search.pool", mock_pool):
            result = await graph_search(q="Test", user=mock_user)

        for r in result["results"]:
            assert "_score" not in r
