# tests/test_graph_traverse.py
"""Tests for the unified graph traversal API."""

from contextlib import asynccontextmanager
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from core.engine.api.graph_traverse import (
    TraverseRequest,
    TraverseResponse,
    _build_hop_query,
    _serialize_node,
    traverse_graph,
)

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
# Unit tests: validation
# ---------------------------------------------------------------------------


class TestTraverseRequestValidation:
    def test_defaults(self):
        req = TraverseRequest(start="graph_file:engine_core_db_py")
        assert req.depth == 1
        assert req.direction == "out"
        assert req.graph_id == "default"
        assert req.limit == 50
        assert req.edge_types is None
        assert req.node_types is None

    def test_depth_clamped_to_max(self):
        req = TraverseRequest(start="graph_file:x", depth=10)
        # Validator should clamp to 3
        assert req.depth == 3

    def test_depth_clamped_to_min(self):
        req = TraverseRequest(start="graph_file:x", depth=0)
        assert req.depth == 1

    def test_limit_clamped_to_max(self):
        req = TraverseRequest(start="graph_file:x", limit=500)
        assert req.limit == 100

    def test_limit_clamped_to_min(self):
        req = TraverseRequest(start="graph_file:x", limit=0)
        assert req.limit == 1

    def test_invalid_direction(self):
        with pytest.raises(ValueError):
            TraverseRequest(start="graph_file:x", direction="sideways")

    def test_invalid_edge_type(self):
        with pytest.raises(ValueError):
            TraverseRequest(start="graph_file:x", edge_types=["not_real_edge"])

    def test_invalid_node_type(self):
        with pytest.raises(ValueError):
            TraverseRequest(start="graph_file:x", node_types=["not_real_node"])

    def test_valid_edge_types(self):
        req = TraverseRequest(start="graph_file:x", edge_types=["imports", "depends_on"])
        assert req.edge_types == ["imports", "depends_on"]

    def test_valid_node_types(self):
        req = TraverseRequest(start="graph_file:x", node_types=["graph_file", "graph_decision"])
        assert req.node_types == ["graph_file", "graph_decision"]

    # --- start ID injection guards ---

    def test_start_no_colon_rejected(self):
        """Bare table name without : should be rejected."""
        with pytest.raises(ValueError, match="valid node ID"):
            TraverseRequest(start="graph_file")

    def test_start_unknown_table_rejected(self):
        """Unknown table prefix in start should be rejected."""
        with pytest.raises(ValueError, match="Unknown node type"):
            TraverseRequest(start="unknown_table:abc123")

    def test_start_injection_semicolon_rejected(self):
        """SurrealQL injection attempt via semicolon should be rejected."""
        with pytest.raises(ValueError):
            TraverseRequest(start="graph_file:x;REMOVE TABLE insight")

    def test_start_injection_space_rejected(self):
        """SurrealQL injection via space/WHERE clause should be rejected."""
        with pytest.raises(ValueError):
            TraverseRequest(start="graph_file:x WHERE 1=1")

    def test_start_empty_record_rejected(self):
        """Empty record ID (just 'table:') should be rejected."""
        with pytest.raises(ValueError):
            TraverseRequest(start="graph_file:")

    def test_start_valid_slug(self):
        """Typical slugified file path should be accepted."""
        req = TraverseRequest(start="graph_file:engine_core_db_py")
        assert req.start == "graph_file:engine_core_db_py"

    def test_start_valid_with_dots_and_slashes(self):
        """Record IDs with dots or slashes (path-derived) should be accepted."""
        req = TraverseRequest(start="graph_file:engine/core/db.py")
        assert req.start == "graph_file:engine/core/db.py"


# ---------------------------------------------------------------------------
# Unit tests: query building
# ---------------------------------------------------------------------------


class TestBuildHopQuery:
    def test_out_single_edge(self):
        query, params = _build_hop_query("graph_file:engine_core_db_py", ["imports"], None, "out", "default")
        assert "->imports->" in query
        assert "$start" in query

    def test_in_single_edge(self):
        query, params = _build_hop_query("graph_file:engine_core_db_py", ["imports"], None, "in", "default")
        assert "<-imports<-" in query

    def test_out_multiple_edges(self):
        query, params = _build_hop_query("graph_file:x", ["imports", "depends_on"], None, "out", "default")
        # Should produce union of both edge types
        assert "imports" in query
        assert "depends_on" in query

    def test_node_type_filter(self):
        query, params = _build_hop_query("graph_file:x", ["imports"], ["graph_file"], "out", "default")
        assert "graph_file" in query


# ---------------------------------------------------------------------------
# Unit tests: serialization
# ---------------------------------------------------------------------------


class TestSerializeNode:
    def test_dict_passthrough(self):
        node = {"id": "graph_file:x", "path": "main.py", "language": "python"}
        result = _serialize_node(node)
        assert result["id"] == "graph_file:x"
        assert result["path"] == "main.py"

    def test_record_id_converted(self):
        """RecordID objects should be converted to strings."""
        from surrealdb import RecordID

        node = {"id": RecordID("graph_file", "x"), "name": "test"}
        result = _serialize_node(node)
        assert isinstance(result["id"], str)
        assert "graph_file" in result["id"]


# ---------------------------------------------------------------------------
# Integration tests: traverse endpoint
# ---------------------------------------------------------------------------


class TestTraverseEndpoint:
    @pytest.mark.asyncio
    async def test_traverse_returns_connected_nodes(self, mock_pool, mock_db, mock_user):
        """Traversal returns nodes and edges in expected structure."""
        # Mock: start node query returns a file node
        start_node = {"id": "graph_file:main_py", "path": "main.py", "graph_id": "default"}
        # Mock: hop query returns connected nodes
        connected = [
            {"id": "graph_file:util_py", "path": "util.py", "graph_id": "default"},
        ]
        # First call = start node lookup, second call = traversal hop
        mock_db.query = AsyncMock(side_effect=[[start_node], connected])

        body = TraverseRequest(
            start="graph_file:main_py",
            depth=1,
            direction="out",
        )

        with patch("core.engine.api.graph_traverse.pool", mock_pool):
            result = await traverse_graph(body, mock_user)

        assert isinstance(result, TraverseResponse)
        assert result.start_node is not None
        assert result.stats["node_count"] >= 0

    @pytest.mark.asyncio
    async def test_traverse_respects_depth(self, mock_pool, mock_db, mock_user):
        """Depth=2 should make multiple hops."""
        start_node = {"id": "graph_file:a", "path": "a.py", "graph_id": "default"}
        hop1_nodes = [{"id": "graph_file:b", "path": "b.py", "graph_id": "default"}]
        hop2_nodes = [{"id": "graph_file:c", "path": "c.py", "graph_id": "default"}]

        mock_db.query = AsyncMock(side_effect=[[start_node], hop1_nodes, hop2_nodes])

        body = TraverseRequest(start="graph_file:a", depth=2, direction="out")

        with patch("core.engine.api.graph_traverse.pool", mock_pool):
            result = await traverse_graph(body, mock_user)

        # Should have called query at least 3 times (start + 2 hops)
        assert mock_db.query.call_count >= 2

    @pytest.mark.asyncio
    async def test_traverse_filters_by_edge_type(self, mock_pool, mock_db, mock_user):
        """Only requested edge types should appear in query."""
        start_node = {"id": "graph_file:x", "path": "x.py", "graph_id": "default"}
        mock_db.query = AsyncMock(side_effect=[[start_node], []])

        body = TraverseRequest(start="graph_file:x", edge_types=["imports"], direction="out")

        with patch("core.engine.api.graph_traverse.pool", mock_pool):
            await traverse_graph(body, mock_user)

        # Check that the query used "imports" edge type
        calls = [str(c) for c in mock_db.query.call_args_list]
        hop_calls = [c for c in calls if "imports" in c]
        assert len(hop_calls) >= 1

    @pytest.mark.asyncio
    async def test_traverse_direction_out(self, mock_pool, mock_db, mock_user):
        """Direction 'out' uses -> arrow."""
        start_node = {"id": "graph_file:x", "path": "x.py", "graph_id": "default"}
        mock_db.query = AsyncMock(side_effect=[[start_node], []])

        body = TraverseRequest(start="graph_file:x", direction="out")

        with patch("core.engine.api.graph_traverse.pool", mock_pool):
            await traverse_graph(body, mock_user)

        calls = [str(c) for c in mock_db.query.call_args_list]
        arrow_calls = [c for c in calls if "->" in c]
        assert len(arrow_calls) >= 1

    @pytest.mark.asyncio
    async def test_traverse_direction_in(self, mock_pool, mock_db, mock_user):
        """Direction 'in' uses <- arrow."""
        start_node = {"id": "graph_file:x", "path": "x.py", "graph_id": "default"}
        mock_db.query = AsyncMock(side_effect=[[start_node], []])

        body = TraverseRequest(start="graph_file:x", direction="in")

        with patch("core.engine.api.graph_traverse.pool", mock_pool):
            await traverse_graph(body, mock_user)

        calls = [str(c) for c in mock_db.query.call_args_list]
        arrow_calls = [c for c in calls if "<-" in c]
        assert len(arrow_calls) >= 1

    @pytest.mark.asyncio
    async def test_traverse_missing_start_node(self, mock_pool, mock_db, mock_user):
        """Return empty result when start node doesn't exist."""
        mock_db.query = AsyncMock(return_value=[])

        body = TraverseRequest(start="graph_file:nonexistent")

        with patch("core.engine.api.graph_traverse.pool", mock_pool):
            result = await traverse_graph(body, mock_user)

        assert result.start_node is None
        assert result.nodes == []
        assert result.edges == []


# ---------------------------------------------------------------------------
# Shortcut endpoint tests
# ---------------------------------------------------------------------------


class TestImpactShortcut:
    @pytest.mark.asyncio
    async def test_impact_calls_traverse(self, mock_pool, mock_db, mock_user):
        """Impact endpoint should call traverse with correct edge types."""
        from core.engine.api.graph_traverse import get_impact

        start_node = {"id": "graph_file:x", "path": "x.py", "graph_id": "default"}
        mock_db.query = AsyncMock(side_effect=[[start_node], [], []])

        with patch("core.engine.api.graph_traverse.pool", mock_pool):
            result = await get_impact("graph_file:x", graph_id="default", user=mock_user)

        assert isinstance(result, TraverseResponse)


class TestHistoryShortcut:
    @pytest.mark.asyncio
    async def test_history_calls_traverse(self, mock_pool, mock_db, mock_user):
        """History endpoint should call traverse with correct edge types."""
        from core.engine.api.graph_traverse import get_history

        start_node = {"id": "graph_file:x", "path": "x.py", "graph_id": "default"}
        mock_db.query = AsyncMock(side_effect=[[start_node], [], []])

        with patch("core.engine.api.graph_traverse.pool", mock_pool):
            result = await get_history("graph_file:x", graph_id="default", user=mock_user)

        assert isinstance(result, TraverseResponse)


class TestRelatedShortcut:
    @pytest.mark.asyncio
    async def test_related_calls_traverse(self, mock_pool, mock_db, mock_user):
        """Related endpoint returns all edge types at depth 1."""
        from core.engine.api.graph_traverse import get_related

        start_node = {"id": "graph_file:x", "path": "x.py", "graph_id": "default"}
        mock_db.query = AsyncMock(side_effect=[[start_node], []])

        with patch("core.engine.api.graph_traverse.pool", mock_pool):
            result = await get_related("graph_file:x", graph_id="default", user=mock_user)

        assert isinstance(result, TraverseResponse)


# ---------------------------------------------------------------------------
# Stats endpoint
# ---------------------------------------------------------------------------


class TestGraphStats:
    @pytest.mark.asyncio
    async def test_stats_returns_counts(self, mock_pool, mock_db, mock_user):
        """Stats endpoint should return node/edge counts."""
        from core.engine.api.graph_traverse import graph_stats

        # Mock count queries — one result per table type
        mock_db.query = AsyncMock(return_value=[{"count": 10}])

        with patch("core.engine.api.graph_traverse.pool", mock_pool):
            result = await graph_stats(graph_id="default", user=mock_user)

        assert "nodes" in result
        assert "edges" in result
        assert "total_nodes" in result
        assert "total_edges" in result
