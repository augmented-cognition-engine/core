# tests/test_graph_traverse.py
"""Tests for the unified graph traversal API."""

from contextlib import asynccontextmanager
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi import HTTPException

from core.engine.api.graph_traverse import (
    TraverseRequest,
    TraverseResponse,
    _build_hop_query,
    _serialize_node,
    traverse_graph,
)
from core.engine.code_intelligence.impact import IMPACT_MAX_PATH_CHARS, IMPACT_MAX_REF_CHARS

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


# The graph↔product mapping row `/graph/impact-by-path` resolves before it reads
# anything out of the named graph: one `graph` record carrying the requested
# `graph_id`, returned only because it is bound to the principal's product.
_GRAPH_OWNED = [{"graph_id": "default"}]


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
        # First call = graph↔product mapping, second = start node lookup,
        # third = traversal hop.
        mock_db.query = AsyncMock(side_effect=[_GRAPH_OWNED, [start_node], connected])

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

        mock_db.query = AsyncMock(side_effect=[_GRAPH_OWNED, [start_node], hop1_nodes, hop2_nodes])

        body = TraverseRequest(start="graph_file:a", depth=2, direction="out")

        with patch("core.engine.api.graph_traverse.pool", mock_pool):
            result = await traverse_graph(body, mock_user)

        # Should have called query at least 3 times (mapping + start + hop)
        assert mock_db.query.call_count >= 3

    @pytest.mark.asyncio
    async def test_traverse_filters_by_edge_type(self, mock_pool, mock_db, mock_user):
        """Only requested edge types should appear in query."""
        start_node = {"id": "graph_file:x", "path": "x.py", "graph_id": "default"}
        mock_db.query = AsyncMock(side_effect=[_GRAPH_OWNED, [start_node], []])

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
        mock_db.query = AsyncMock(side_effect=[_GRAPH_OWNED, [start_node], []])

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
        mock_db.query = AsyncMock(side_effect=[_GRAPH_OWNED, [start_node], []])

        body = TraverseRequest(start="graph_file:x", direction="in")

        with patch("core.engine.api.graph_traverse.pool", mock_pool):
            await traverse_graph(body, mock_user)

        calls = [str(c) for c in mock_db.query.call_args_list]
        arrow_calls = [c for c in calls if "<-" in c]
        assert len(arrow_calls) >= 1

    @pytest.mark.asyncio
    async def test_traverse_missing_start_node(self, mock_pool, mock_db, mock_user):
        """Return empty result when start node doesn't exist."""
        # Mapping succeeds, but the start-node read (scoped to the authorized
        # graph) finds nothing.
        mock_db.query = AsyncMock(side_effect=[_GRAPH_OWNED, []])

        body = TraverseRequest(start="graph_file:nonexistent")

        with patch("core.engine.api.graph_traverse.pool", mock_pool):
            result = await traverse_graph(body, mock_user)

        assert result.start_node is None
        assert result.nodes == []
        assert result.edges == []

    @pytest.mark.asyncio
    async def test_missing_product_rejects_before_any_db_call(self, mock_pool, mock_db):
        """A principal with no product binding is refused before a connection is even opened."""
        mock_db.query = AsyncMock(side_effect=AssertionError("no query may run for an unbound principal"))

        body = TraverseRequest(start="graph_file:x", graph_id="default")

        with patch("core.engine.api.graph_traverse.pool", mock_pool):
            with pytest.raises(HTTPException) as excinfo:
                await traverse_graph(body, user={"sub": "user:test"})

        assert excinfo.value.status_code == 403
        assert mock_db.query.await_args_list == []

    @pytest.mark.asyncio
    async def test_direct_traverse_cross_product_graph_rejects_on_mapping_first(self, mock_pool, mock_db, mock_user):
        """A direct POST /graph/traverse for another product's graph is refused before any node read.

        This is the same mapping-first boundary `get_impact` already relied on,
        now enforced by `traverse_graph` itself so a caller cannot bypass it by
        hitting the traversal endpoint directly instead of a shortcut.
        """
        # The competitor's graph exists, but no `graph` record binds it to this
        # principal's product, so the product-scoped mapping read returns nothing.
        mock_db.query = AsyncMock(side_effect=[[]])

        body = TraverseRequest(start="graph_file:secret", graph_id="competitor-graph")

        with patch("core.engine.api.graph_traverse.pool", mock_pool):
            with pytest.raises(HTTPException) as excinfo:
                await traverse_graph(body, mock_user)

        assert excinfo.value.status_code == 404
        assert excinfo.value.detail == "Not found"
        assert "competitor-graph" not in str(excinfo.value.detail)
        queries = [call.args[0] for call in mock_db.query.await_args_list]
        assert len(queries) == 1
        assert "FROM graph WHERE" in queries[0]
        assert "graph_file" not in queries[0]

    @pytest.mark.asyncio
    async def test_mapping_query_is_first_and_bound_to_the_principal_product(self, mock_pool, mock_db, mock_user):
        """The mapping lookup — not a node or edge read — is always the first query traverse_graph issues."""
        start_node = {"id": "graph_file:x", "path": "x.py", "graph_id": "default"}
        mock_db.query = AsyncMock(side_effect=[_GRAPH_OWNED, [start_node], []])

        body = TraverseRequest(start="graph_file:x", graph_id="default")

        with patch("core.engine.api.graph_traverse.pool", mock_pool):
            await traverse_graph(body, mock_user)

        first = mock_db.query.await_args_list[0]
        assert "FROM graph WHERE graph_id = $gid AND product = <record>$product" in first.args[0]
        assert first.args[1] == {"gid": "default", "product": "product:platform"}

    @pytest.mark.asyncio
    async def test_a_mapped_same_graph_start_succeeds(self, mock_pool, mock_db, mock_user):
        """A graph correctly bound to the principal's product, with a matching start row, traverses normally."""
        start_node = {"id": "graph_file:main_py", "path": "main.py", "graph_id": "default"}
        mock_db.query = AsyncMock(side_effect=[_GRAPH_OWNED, [start_node], []])

        body = TraverseRequest(start="graph_file:main_py", graph_id="default")

        with patch("core.engine.api.graph_traverse.pool", mock_pool):
            result = await traverse_graph(body, mock_user)

        assert result.start_node is not None
        assert result.start_node["id"] == "graph_file:main_py"

    @pytest.mark.asyncio
    async def test_a_foreign_graph_start_row_is_not_returned_and_no_hop_query_runs(self, mock_pool, mock_db, mock_user):
        """The reproduced exploit: a node ID that resolves in the authorized graph query, but whose
        actual row belongs to a different (e.g. competitor) graph, must never be returned.

        `get_impact` authorizes `graph_id=default` for `product:platform`, but the previous
        `SELECT * FROM {start}` had no `graph_id` filter — so a `graph_file:secret` row actually
        owned by `graph_id=competitor_secret` was still returned. The start-node read must be
        scoped with `WHERE graph_id = $graph_id`, so a foreign-graph row comes back empty and no
        hop query ever runs.
        """
        # Mapping succeeds: 'default' is bound to product:platform.
        mock_db.query = AsyncMock(side_effect=[_GRAPH_OWNED, []])

        body = TraverseRequest(start="graph_file:secret", graph_id="default")

        with patch("core.engine.api.graph_traverse.pool", mock_pool):
            result = await traverse_graph(body, mock_user)

        assert result.start_node is None
        assert result.nodes == []
        assert result.edges == []
        # Exactly two queries ran: the mapping read, then the scoped start-node
        # read that came back empty — no hop query was ever issued.
        assert len(mock_db.query.await_args_list) == 2
        start_call = mock_db.query.await_args_list[1]
        assert "FROM graph_file:secret WHERE graph_id = $graph_id" in start_call.args[0]
        assert start_call.args[1] == {"graph_id": "default"}


# ---------------------------------------------------------------------------
# Shortcut endpoint tests
# ---------------------------------------------------------------------------


class TestImpactShortcut:
    @pytest.mark.asyncio
    async def test_impact_calls_traverse(self, mock_pool, mock_db, mock_user):
        """Impact endpoint should call traverse with correct edge types."""
        from core.engine.api.graph_traverse import get_impact

        start_node = {"id": "graph_file:x", "path": "x.py", "graph_id": "default"}
        # queries[0] is the graph↔product mapping read the route now resolves
        # before it ever calls traverse_graph; queries[1] is the start-node read.
        mock_db.query = AsyncMock(side_effect=[_GRAPH_OWNED, [start_node], [], []])

        with patch("core.engine.api.graph_traverse.pool", mock_pool):
            result = await get_impact("graph_file:x", graph_id="default", user=mock_user)

        assert isinstance(result, TraverseResponse)
        first = mock_db.query.await_args_list[0]
        assert "FROM graph WHERE graph_id = $gid AND product = <record>$product" in first.args[0]


class TestImpactShortcutGraphAuthorization:
    """`/graph/impact/{node_id}` authorizes `graph_id` exactly like
    `/graph/impact-by-path`: the requested graph must be bound to the
    authenticated principal's product — through the same `graph` record the
    capability mapper's product→graph lookup already uses — before
    `traverse_graph`, and its own `SELECT * FROM {start}`, is ever reached.
    """

    @pytest.mark.asyncio
    async def test_a_graph_mapped_to_another_product_is_refused_without_reading_a_node(
        self, mock_pool, mock_db, mock_user
    ):
        from fastapi import HTTPException

        from core.engine.api.graph_traverse import get_impact

        # The competitor's graph exists, but no `graph` record binds it to this
        # principal's product, so the product-scoped mapping read returns nothing.
        mock_db.query = AsyncMock(side_effect=[[]])

        with patch("core.engine.api.graph_traverse.pool", mock_pool):
            with pytest.raises(HTTPException) as excinfo:
                await get_impact("graph_file:x", graph_id="competitor-graph", user=mock_user)

        # 404, not 403 — matching `impact-by-path`, so the refusal never
        # confirms that some other product's graph exists.
        assert excinfo.value.status_code == 404
        assert excinfo.value.detail == "Not found"
        assert "competitor-graph" not in str(excinfo.value.detail)
        queries = [call.args[0] for call in mock_db.query.await_args_list]
        assert len(queries) == 1
        assert "FROM graph WHERE" in queries[0]
        assert not any(table in queries[0] for table in ("graph_file", "depends_on", "imports", "breaks", "tests"))

    @pytest.mark.asyncio
    async def test_an_unknown_graph_is_refused_without_reading_a_node(self, mock_pool, mock_db, mock_user):
        from fastapi import HTTPException

        from core.engine.api.graph_traverse import get_impact

        mock_db.query = AsyncMock(side_effect=[[]])

        with patch("core.engine.api.graph_traverse.pool", mock_pool):
            with pytest.raises(HTTPException) as excinfo:
                await get_impact("graph_file:x", graph_id="no-such-graph", user=mock_user)

        assert excinfo.value.status_code == 404
        assert len(mock_db.query.await_args_list) == 1

    @pytest.mark.asyncio
    async def test_the_default_graph_is_not_exempt_from_the_mapping(self, mock_pool, mock_db, mock_user):
        """The compatibility default is preserved when valid — and only when valid."""
        from fastapi import HTTPException

        from core.engine.api.graph_traverse import get_impact

        mock_db.query = AsyncMock(side_effect=[[]])

        with patch("core.engine.api.graph_traverse.pool", mock_pool):
            with pytest.raises(HTTPException) as excinfo:
                await get_impact("graph_file:x", graph_id="default", user=mock_user)

        assert excinfo.value.status_code == 404
        assert len(mock_db.query.await_args_list) == 1

    @pytest.mark.asyncio
    async def test_a_mapped_graph_reaches_traverse_graph(self, mock_pool, mock_db, mock_user):
        """A graph correctly bound to the principal's product continues to `traverse_graph`."""
        from core.engine.api.graph_traverse import get_impact

        start_node = {"id": "graph_file:x", "path": "x.py", "graph_id": "platform-main"}
        mock_db.query = AsyncMock(side_effect=[[{"graph_id": "platform-main"}], [start_node], [], []])

        with patch("core.engine.api.graph_traverse.pool", mock_pool):
            result = await get_impact("graph_file:x", graph_id="platform-main", user=mock_user)

        assert isinstance(result, TraverseResponse)
        assert result.start_node is not None
        first = mock_db.query.await_args_list[0]
        assert first.args[1] == {"gid": "platform-main", "product": "product:platform"}
        # The start-node read is the second query, never the first.
        second = mock_db.query.await_args_list[1]
        assert "FROM graph_file:x" in second.args[0]

    @pytest.mark.asyncio
    async def test_a_principal_without_a_product_binding_is_refused_before_any_db_call(self, mock_pool, mock_db):
        from fastapi import HTTPException

        from core.engine.api.graph_traverse import get_impact

        mock_db.query = AsyncMock(side_effect=AssertionError("no query may run for an unbound principal"))

        with patch("core.engine.api.graph_traverse.pool", mock_pool):
            with pytest.raises(HTTPException) as excinfo:
                await get_impact("graph_file:x", graph_id="default", user={"sub": "user:test"})

        assert excinfo.value.status_code == 403
        assert mock_db.query.await_args_list == []

    @pytest.mark.asyncio
    async def test_oversized_graph_id_is_refused_before_any_db_call(self, mock_pool, mock_db, mock_user):
        from fastapi import HTTPException

        from core.engine.api.graph_traverse import get_impact

        mock_db.query = AsyncMock(side_effect=AssertionError("no query may run for a rejected selector"))
        overlong = "g" * (IMPACT_MAX_REF_CHARS + 1)

        with patch("core.engine.api.graph_traverse.pool", mock_pool):
            with pytest.raises(HTTPException) as excinfo:
                await get_impact("graph_file:x", graph_id=overlong, user=mock_user)

        assert excinfo.value.status_code == 422
        assert mock_db.query.await_args_list == []
        assert overlong not in str(excinfo.value.detail)

    @pytest.mark.asyncio
    async def test_oversized_node_id_is_refused_before_any_db_call(self, mock_pool, mock_db, mock_user):
        from fastapi import HTTPException

        from core.engine.api.graph_traverse import get_impact

        mock_db.query = AsyncMock(side_effect=AssertionError("no query may run for a rejected selector"))
        overlong = "graph_file:" + "x" * IMPACT_MAX_PATH_CHARS

        with patch("core.engine.api.graph_traverse.pool", mock_pool):
            with pytest.raises(HTTPException) as excinfo:
                await get_impact(overlong, graph_id="default", user=mock_user)

        assert excinfo.value.status_code == 422
        assert mock_db.query.await_args_list == []

    @pytest.mark.asyncio
    async def test_non_string_graph_id_is_refused_before_any_db_call(self, mock_pool, mock_db, mock_user):
        from fastapi import HTTPException

        from core.engine.api.graph_traverse import get_impact

        mock_db.query = AsyncMock(side_effect=AssertionError("no query may run for a rejected selector"))

        with patch("core.engine.api.graph_traverse.pool", mock_pool):
            with pytest.raises(HTTPException) as excinfo:
                await get_impact("graph_file:x", graph_id=7, user=mock_user)

        assert excinfo.value.status_code == 422
        assert "must be a string" in str(excinfo.value.detail)
        assert mock_db.query.await_args_list == []


class TestImpactByPath:
    @pytest.mark.asyncio
    @pytest.mark.parametrize("importers", [[], [{"id": "graph_file:caller", "path": "caller.py"}]])
    async def test_static_reachability_never_claims_safe_or_breaking(self, mock_pool, mock_db, mock_user, importers):
        from core.engine.api.graph_traverse import impact_by_path

        file_node = {"id": "graph_file:target", "path": "target.py", "name": "target"}
        mock_db.query = AsyncMock(
            side_effect=[
                _GRAPH_OWNED,
                [file_node],
                importers,
                [{"id": "graph_function:f", "name": "f"}],
                [],
                [],
                [{"slug": "graph-tools", "name": "Graph Tools"}],
            ]
        )

        with patch("core.engine.api.graph_traverse.pool", mock_pool):
            result = await impact_by_path("target.py", graph_id="default", product="product:platform", user=mock_user)

        assert result["safe_to_delete"] is False
        assert result["deletion_safety"] == "not_assessed"
        assert result["fragility_assessed"] is False
        assert result["breakage_assessed"] is False
        assert result["impact_evidence_basis"] == "direct_static_importers_and_cochange"
        assert "deletion safety not assessed" in result["impact_summary"]
        assert result["summary"] == result["impact_summary"]
        assert "SAFE:" not in result["impact_summary"]
        assert "BREAKING" not in result["impact_summary"]
        assert len(result["uncertainties"]) == 3

    @pytest.mark.asyncio
    async def test_zero_and_nonzero_importers_and_cochange_are_summarized_deterministically(
        self, mock_pool, mock_db, mock_user
    ):
        from core.engine.api.graph_traverse import impact_by_path

        file_node = {"id": "graph_file:target", "path": "target.py", "name": "target"}

        async def _run(importers, cochange_out, cochange_in):
            mock_db.query = AsyncMock(
                side_effect=[_GRAPH_OWNED, [file_node], importers, [], cochange_out, cochange_in, []]
            )
            with patch("core.engine.api.graph_traverse.pool", mock_pool):
                return await impact_by_path("target.py", graph_id="default", product="", user=mock_user)

        empty = await _run([], [], [])
        assert empty["impact_summary"] == (
            "NO DIRECT STATIC IMPORTERS OBSERVED: 0 file(s) import this, 0 function(s) defined, "
            "0 co-change partner(s); deletion safety not assessed"
        )

        loaded = await _run(
            [{"id": "graph_file:caller", "path": "caller.py"}],
            [{"id": "graph_file:peer", "path": "peer.py"}],
            [{"id": "graph_file:other", "path": "other.py"}],
        )
        assert loaded["impact_summary"] == (
            "IMPACT OBSERVED: 1 file(s) import this, 0 function(s) defined, "
            "2 co-change partner(s); deletion safety not assessed"
        )
        assert loaded["cochange_partner_count"] == 2
        # The same summary text is published under both established keys.
        assert loaded["summary"] == loaded["impact_summary"]

    @pytest.mark.asyncio
    async def test_requested_product_must_match_the_authenticated_principal(self, mock_pool, mock_db, mock_user):
        from fastapi import HTTPException

        from core.engine.api.graph_traverse import impact_by_path

        mock_db.query = AsyncMock(side_effect=AssertionError("no query may run for a rejected product"))
        with patch("core.engine.api.graph_traverse.pool", mock_pool):
            with pytest.raises(HTTPException) as excinfo:
                await impact_by_path("target.py", graph_id="default", product="product:other", user=mock_user)

        assert excinfo.value.status_code == 404

    @pytest.mark.asyncio
    async def test_principal_without_a_product_binding_is_refused(self, mock_pool, mock_db):
        from fastapi import HTTPException

        from core.engine.api.graph_traverse import impact_by_path

        mock_db.query = AsyncMock(side_effect=AssertionError("no query may run for an unbound principal"))
        with patch("core.engine.api.graph_traverse.pool", mock_pool):
            with pytest.raises(HTTPException) as excinfo:
                await impact_by_path("target.py", graph_id="default", product="", user={"sub": "user:test"})

        assert excinfo.value.status_code == 403

    @pytest.mark.asyncio
    async def test_capability_query_is_bound_to_the_principal_product(self, mock_pool, mock_db, mock_user):
        from core.engine.api.graph_traverse import impact_by_path

        file_node = {"id": "graph_file:target", "path": "target.py"}
        mock_db.query = AsyncMock(side_effect=[_GRAPH_OWNED, [file_node], [], [], [], [], []])

        with patch("core.engine.api.graph_traverse.pool", mock_pool):
            result = await impact_by_path("target.py", graph_id="default", product="", user=mock_user)

        capability_call = mock_db.query.await_args_list[-1]
        assert capability_call.args[1]["product"] == "product:platform"
        assert result["product_ref"] == "product:platform"

    @pytest.mark.asyncio
    async def test_every_collection_query_is_bounded_at_limit_bound_plus_one(self, mock_pool, mock_db, mock_user):
        from core.engine.api.graph_traverse import impact_by_path
        from core.engine.code_intelligence.impact import (
            IMPACT_MAX_CAPABILITIES,
            IMPACT_MAX_COCHANGE_PARTNERS,
            IMPACT_MAX_FUNCTIONS,
            IMPACT_MAX_IMPORTERS,
        )

        file_node = {"id": "graph_file:target", "path": "target.py"}
        mock_db.query = AsyncMock(side_effect=[_GRAPH_OWNED, [file_node], [], [], [], [], []])

        with patch("core.engine.api.graph_traverse.pool", mock_pool):
            await impact_by_path("target.py", graph_id="default", product="", user=mock_user)

        # queries[0] is the graph↔product mapping read; queries[1] resolves the
        # path to a node, and every collection query follows it.
        queries = [call.args[0] for call in mock_db.query.await_args_list]
        assert f"LIMIT {IMPACT_MAX_IMPORTERS + 1}" in queries[2]
        assert f"LIMIT {IMPACT_MAX_FUNCTIONS + 1}" in queries[3]
        assert f"LIMIT {IMPACT_MAX_COCHANGE_PARTNERS + 1}" in queries[4]
        assert f"LIMIT {IMPACT_MAX_COCHANGE_PARTNERS + 1}" in queries[5]
        assert f"LIMIT {IMPACT_MAX_CAPABILITIES + 1}" in queries[6]

    @pytest.mark.asyncio
    async def test_overflowing_importers_are_trimmed_deduped_and_disclosed(self, mock_pool, mock_db, mock_user):
        from core.engine.api.graph_traverse import impact_by_path
        from core.engine.code_intelligence.impact import IMPACT_MAX_IMPORTERS

        file_node = {"id": "graph_file:target", "path": "target.py"}
        # One row past the bound, plus a duplicate of the first row: the bound
        # is what caps the response, and the duplicate must not consume a slot.
        overflowing = [
            {"id": f"graph_file:i{index:04d}", "path": f"pkg/i{index:04d}.py"}
            for index in range(IMPACT_MAX_IMPORTERS + 1)
        ]
        overflowing.append(dict(overflowing[0]))
        mock_db.query = AsyncMock(side_effect=[_GRAPH_OWNED, [file_node], overflowing, [], [], [], []])

        with patch("core.engine.api.graph_traverse.pool", mock_pool):
            result = await impact_by_path("target.py", graph_id="default", product="", user=mock_user)

        assert result["importer_count"] == IMPACT_MAX_IMPORTERS
        assert len(result["importers"]) == IMPACT_MAX_IMPORTERS
        assert len({row["node_id"] for row in result["importers"]}) == IMPACT_MAX_IMPORTERS
        # Deterministic order, independent of the order the database returned.
        assert [row["path"] for row in result["importers"]] == sorted(row["path"] for row in result["importers"])
        window = result["observation_windows"]["importers"]
        assert window["truncated"] is True
        assert window["undisclosed_remainder"] == "unknown"
        assert window["bound"] == IMPACT_MAX_IMPORTERS
        assert result["truncated_collections"] == ["importers"]
        assert any("remainder is unknown" in item for item in result["uncertainties"])
        assert "bounded traversal truncated in: importers" in result["impact_summary"]

    @pytest.mark.asyncio
    async def test_a_duplicate_heavy_cochange_direction_still_discloses_its_hit_window(
        self, mock_pool, mock_db, mock_user
    ):
        """Deduping the two directions must not erase an overflow either one already hit."""
        from core.engine.api.graph_traverse import impact_by_path
        from core.engine.code_intelligence.impact import IMPACT_MAX_COCHANGE_PARTNERS

        file_node = {"id": "graph_file:target", "path": "target.py"}
        # One partner, returned bound+1 times by the outgoing direction, and
        # returned again by the incoming one: one visible partner, and a
        # direction whose true edge set continues past what was fetched.
        duplicate_heavy = [{"id": "graph_file:peer", "path": "peer.py"}] * (IMPACT_MAX_COCHANGE_PARTNERS + 1)
        mock_db.query = AsyncMock(
            side_effect=[
                _GRAPH_OWNED,
                [file_node],
                [],
                [],
                duplicate_heavy,
                [{"id": "graph_file:peer", "path": "peer.py"}],
                [],
            ]
        )

        with patch("core.engine.api.graph_traverse.pool", mock_pool):
            result = await impact_by_path("target.py", graph_id="default", product="", user=mock_user)

        assert result["cochange_partner_count"] == 1
        window = result["observation_windows"]["cochange_partners"]
        assert window["truncated"] is True
        assert window["undisclosed_remainder"] == "unknown"
        assert result["truncated_collections"] == ["cochange_partners"]
        assert "bounded traversal truncated in: cochange_partners" in result["impact_summary"]
        assert any("remainder is unknown and uncounted" in item for item in result["uncertainties"])

    @pytest.mark.asyncio
    async def test_response_names_its_graph_target_and_evidence_and_refuses_authority(
        self, mock_pool, mock_db, mock_user
    ):
        from core.engine.api.graph_traverse import impact_by_path

        file_node = {"id": "graph_file:target", "path": "target.py"}
        mock_db.query = AsyncMock(side_effect=[_GRAPH_OWNED, [file_node], [], [], [], [], []])

        with patch("core.engine.api.graph_traverse.pool", mock_pool):
            result = await impact_by_path("target.py", graph_id="default", product="", user=mock_user)

        assert result["contract"] == "ace.code-intelligence.impact-observation/v1alpha1"
        assert result["graph_id"] == "default"
        assert result["product_ref"] == "product:platform"
        assert result["target_path"] == "target.py"
        assert result["target_node_id"] == "graph_file:target"
        assert result["observation_id"].startswith("code_impact_observation:")
        assert result["evidence_id"].startswith("code_impact_evidence:")
        # Freshness is absent, and it is reported as absent rather than as current.
        assert result["graph_revision"] == "unestablished"
        assert result["graph_revision_established"] is False
        assert result["graph_freshness"] == "unestablished"
        assert result["graph_freshness_established"] is False
        for authority in (
            "source_authority",
            "reasoning_authority",
            "change_authority",
            "approval_authority",
            "delivery_authority",
            "execution_authority",
            "effect_authority",
        ):
            assert result[authority] is False, authority

    @pytest.mark.asyncio
    async def test_missing_file_stays_an_error_not_a_zero_importer_observation(self, mock_pool, mock_db, mock_user):
        from core.engine.api.graph_traverse import impact_by_path

        mock_db.query = AsyncMock(side_effect=[_GRAPH_OWNED, []])

        with patch("core.engine.api.graph_traverse.pool", mock_pool):
            result = await impact_by_path("missing.py", graph_id="default", product="", user=mock_user)

        assert "not found in graph" in result["error"]
        assert "importer_count" not in result
        assert "safe_to_delete" not in result


class TestImpactByPathGraphAuthorization:
    """`graph_id` is a caller assertion, and it is authorized like one.

    Every node table in this schema is partitioned by `graph_id` alone, so a
    principal that passes the product fence and then names another product's
    graph would read that graph's files, importers, functions, and co-change
    edges in full. The requested graph must be bound to the principal's own
    product — through the same `graph` record → `product` link the capability
    mapper's product→graph lookup already uses — before anything in it is read.
    """

    @staticmethod
    def _mapping_calls(mock_db):
        return [call.args[0] for call in mock_db.query.await_args_list]

    @pytest.mark.asyncio
    async def test_the_mapping_is_resolved_before_any_graph_read(self, mock_pool, mock_db, mock_user):
        from core.engine.api.graph_traverse import impact_by_path

        file_node = {"id": "graph_file:target", "path": "target.py"}
        mock_db.query = AsyncMock(side_effect=[_GRAPH_OWNED, [file_node], [], [], [], [], []])

        with patch("core.engine.api.graph_traverse.pool", mock_pool):
            result = await impact_by_path("target.py", graph_id="default", product="", user=mock_user)

        first = mock_db.query.await_args_list[0]
        assert "FROM graph WHERE graph_id = $gid AND product = <record>$product" in first.args[0]
        assert first.args[1] == {"gid": "default", "product": "product:platform"}
        # The product bound into the mapping read is the principal's own, and
        # the graph read that follows is the path lookup, not the other way round.
        assert "FROM graph_file" in self._mapping_calls(mock_db)[1]
        assert result["graph_id"] == "default"

    @pytest.mark.asyncio
    async def test_a_graph_mapped_to_another_product_is_refused_without_reading_it(self, mock_pool, mock_db, mock_user):
        from fastapi import HTTPException

        from core.engine.api.graph_traverse import impact_by_path

        # The competitor's graph exists, but no `graph` record binds it to this
        # principal's product, so the product-scoped mapping read returns nothing.
        mock_db.query = AsyncMock(side_effect=[[]])

        with patch("core.engine.api.graph_traverse.pool", mock_pool):
            with pytest.raises(HTTPException) as excinfo:
                await impact_by_path("target.py", graph_id="competitor-graph", product="", user=mock_user)

        # 404 like `verify_ownership`: the refusal never distinguishes a graph
        # that belongs to someone else from one that does not exist.
        assert excinfo.value.status_code == 404
        assert excinfo.value.detail == "Not found"
        assert "competitor-graph" not in str(excinfo.value.detail)
        # Exactly one query ran, and it was the mapping read — no graph_file,
        # import, function, or co-change row of that graph was touched.
        queries = self._mapping_calls(mock_db)
        assert len(queries) == 1
        assert "FROM graph WHERE" in queries[0]
        assert not any(table in queries[0] for table in ("graph_file", "imports", "graph_function", "related_to"))

    @pytest.mark.asyncio
    async def test_an_unknown_graph_is_refused_without_reading_it(self, mock_pool, mock_db, mock_user):
        from fastapi import HTTPException

        from core.engine.api.graph_traverse import impact_by_path

        mock_db.query = AsyncMock(side_effect=[[]])

        with patch("core.engine.api.graph_traverse.pool", mock_pool):
            with pytest.raises(HTTPException) as excinfo:
                await impact_by_path("target.py", graph_id="no-such-graph", product="", user=mock_user)

        assert excinfo.value.status_code == 404
        assert len(mock_db.query.await_args_list) == 1

    @pytest.mark.asyncio
    async def test_a_mapping_row_naming_a_different_graph_is_refused(self, mock_pool, mock_db, mock_user):
        """A mapping read that answers about some other graph does not authorize this one."""
        from fastapi import HTTPException

        from core.engine.api.graph_traverse import impact_by_path

        mock_db.query = AsyncMock(side_effect=[[{"graph_id": "default"}]])

        with patch("core.engine.api.graph_traverse.pool", mock_pool):
            with pytest.raises(HTTPException) as excinfo:
                await impact_by_path("target.py", graph_id="competitor-graph", product="", user=mock_user)

        assert excinfo.value.status_code == 404
        assert len(mock_db.query.await_args_list) == 1

    @pytest.mark.asyncio
    async def test_the_default_graph_is_not_exempt_from_the_mapping(self, mock_pool, mock_db, mock_user):
        """The compatibility default is preserved when valid — and only when valid."""
        from fastapi import HTTPException

        from core.engine.api.graph_traverse import impact_by_path

        mock_db.query = AsyncMock(side_effect=[[]])

        with patch("core.engine.api.graph_traverse.pool", mock_pool):
            with pytest.raises(HTTPException) as excinfo:
                await impact_by_path("target.py", graph_id="default", product="", user=mock_user)

        assert excinfo.value.status_code == 404
        assert len(mock_db.query.await_args_list) == 1

    @pytest.mark.asyncio
    async def test_a_platform_principal_reads_its_own_mapped_graph(self, mock_pool, mock_db, mock_user):
        from core.engine.api.graph_traverse import impact_by_path

        file_node = {"id": "graph_file:target", "path": "target.py"}
        mock_db.query = AsyncMock(
            side_effect=[
                [{"graph_id": "platform-main"}],
                [file_node],
                [{"id": "graph_file:caller", "path": "caller.py"}],
                [],
                [],
                [],
                [{"slug": "graph-tools", "name": "Graph Tools"}],
            ]
        )

        with patch("core.engine.api.graph_traverse.pool", mock_pool):
            result = await impact_by_path("target.py", graph_id="platform-main", product="", user=mock_user)

        assert result["graph_id"] == "platform-main"
        assert result["product_ref"] == "product:platform"
        assert result["importer_count"] == 1
        assert result["capability_count"] == 1
        # Every collection query stayed inside the authorized graph.
        for call in mock_db.query.await_args_list[1:]:
            assert call.args[1].get("gid", "platform-main") == "platform-main"

    @pytest.mark.asyncio
    async def test_a_rejected_product_is_refused_before_the_mapping_read(self, mock_pool, mock_db, mock_user):
        """The product fence still runs first, so a cross-product request never reaches the mapping."""
        from fastapi import HTTPException

        from core.engine.api.graph_traverse import impact_by_path

        mock_db.query = AsyncMock(side_effect=AssertionError("no query may run for a rejected product"))

        with patch("core.engine.api.graph_traverse.pool", mock_pool):
            with pytest.raises(HTTPException) as excinfo:
                await impact_by_path("target.py", graph_id="competitor-graph", product="product:other", user=mock_user)

        assert excinfo.value.status_code == 404
        assert mock_db.query.await_args_list == []


class TestImpactByPathBoundedSelectors:
    """Path, graph, and product are bounded against the central Code constants.

    They are refused — not trimmed — before a connection is opened, and the
    refusal names the field and its limit without echoing what was sent.
    """

    @pytest.mark.asyncio
    @pytest.mark.parametrize(
        ("field", "kwargs"),
        [
            ("graph_id", {"graph_id": "g" * (IMPACT_MAX_REF_CHARS + 1), "product": ""}),
            ("product", {"graph_id": "default", "product": "p" * (IMPACT_MAX_REF_CHARS + 1)}),
            ("graph_id", {"graph_id": "", "product": ""}),
        ],
    )
    async def test_an_oversized_or_empty_selector_is_refused_before_any_db_call(
        self, mock_pool, mock_db, mock_user, field, kwargs
    ):
        from fastapi import HTTPException

        from core.engine.api.graph_traverse import impact_by_path

        mock_db.query = AsyncMock(side_effect=AssertionError("no query may run for a rejected selector"))

        with patch("core.engine.api.graph_traverse.pool", mock_pool):
            with pytest.raises(HTTPException) as excinfo:
                await impact_by_path("target.py", user=mock_user, **kwargs)

        assert excinfo.value.status_code == 422
        assert mock_db.query.await_args_list == []
        detail = str(excinfo.value.detail)
        assert detail.startswith(field)
        assert len(detail) < 120
        # Bounded and non-echoing: the rejected value is never reflected back.
        for value in kwargs.values():
            if len(value) > IMPACT_MAX_REF_CHARS:
                assert value not in detail

    @pytest.mark.asyncio
    async def test_an_oversized_path_is_refused_rather_than_truncated(self, mock_pool, mock_db, mock_user):
        from fastapi import HTTPException

        from core.engine.api.graph_traverse import impact_by_path

        overlong = "a" * (IMPACT_MAX_PATH_CHARS + 1)
        mock_db.query = AsyncMock(side_effect=AssertionError("no query may run for a rejected path"))

        with patch("core.engine.api.graph_traverse.pool", mock_pool):
            with pytest.raises(HTTPException) as excinfo:
                await impact_by_path(overlong, graph_id="default", product="", user=mock_user)

        assert excinfo.value.status_code == 422
        assert mock_db.query.await_args_list == []
        # Refused outright — no shortened variant of the caller's path is queried.
        assert overlong[:64] not in str(excinfo.value.detail)

    @pytest.mark.asyncio
    async def test_non_string_selectors_are_refused_before_any_db_call(self, mock_pool, mock_db, mock_user):
        from fastapi import HTTPException

        from core.engine.api.graph_traverse import impact_by_path

        mock_db.query = AsyncMock(side_effect=AssertionError("no query may run for a rejected selector"))

        for kwargs in (
            {"graph_id": ["default"], "product": ""},
            {"graph_id": 7, "product": ""},
            {"graph_id": "default", "product": {"product": "product:platform"}},
        ):
            with patch("core.engine.api.graph_traverse.pool", mock_pool):
                with pytest.raises(HTTPException) as excinfo:
                    await impact_by_path("target.py", user=mock_user, **kwargs)
            assert excinfo.value.status_code == 422
            assert "must be a string" in str(excinfo.value.detail)

        assert mock_db.query.await_args_list == []

    def test_the_route_declares_the_central_bounds(self):
        import inspect

        from annotated_types import MaxLen, MinLen

        from core.engine.api.graph_traverse import impact_by_path

        sig = inspect.signature(impact_by_path)

        def _bounds(name):
            return list(sig.parameters[name].default.metadata)

        assert _bounds("path") == [MinLen(1), MaxLen(IMPACT_MAX_PATH_CHARS)]
        assert _bounds("graph_id") == [MinLen(1), MaxLen(IMPACT_MAX_REF_CHARS)]
        # `product` stays optionally empty — an unstated product still resolves
        # to the principal's own — but it is length-bounded like the rest.
        assert _bounds("product") == [MaxLen(IMPACT_MAX_REF_CHARS)]

    def test_an_oversized_query_string_is_refused_over_http_without_a_db_call(self):
        from fastapi.testclient import TestClient

        from core.engine.api.main import app
        from core.engine.core.auth import get_current_user

        app.dependency_overrides[get_current_user] = lambda: {
            "sub": "user:test",
            "product": "product:platform",
        }
        try:
            with patch("core.engine.api.graph_traverse.pool") as mock_pool:
                mock_conn = AsyncMock()
                mock_pool.connection.return_value.__aenter__ = AsyncMock(return_value=mock_conn)
                mock_pool.connection.return_value.__aexit__ = AsyncMock(return_value=False)
                mock_conn.query = AsyncMock(side_effect=AssertionError("no query may run for a rejected selector"))

                client = TestClient(app)
                resp = client.get(
                    "/graph/impact-by-path",
                    params={"path": "target.py", "graph_id": "g" * (IMPACT_MAX_REF_CHARS + 1)},
                )
                assert mock_conn.query.await_args_list == []
        finally:
            app.dependency_overrides.clear()

        assert resp.status_code == 422


class TestImpactByPathPublicProductDefault:
    """The `product` query parameter's default is a frozen public contract:

    it must stay 'product:platform', not empty, and — being a caller
    assertion rather than an authorization — is still checked against the
    authenticated principal like any explicitly requested value.
    """

    def test_fastapi_parameter_default_is_platform(self):
        import inspect

        from core.engine.api.graph_traverse import impact_by_path

        sig = inspect.signature(impact_by_path)
        assert sig.parameters["product"].default.default == "product:platform"

    def test_omitted_product_matches_a_platform_principal(self):
        from fastapi.testclient import TestClient

        from core.engine.api.main import app
        from core.engine.core.auth import get_current_user

        app.dependency_overrides[get_current_user] = lambda: {
            "sub": "user:test",
            "product": "product:platform",
        }
        file_node = {"id": "graph_file:target", "path": "target.py"}
        try:
            with patch("core.engine.api.graph_traverse.pool") as mock_pool:
                mock_conn = AsyncMock()
                mock_pool.connection.return_value.__aenter__ = AsyncMock(return_value=mock_conn)
                mock_pool.connection.return_value.__aexit__ = AsyncMock(return_value=False)
                mock_conn.query = AsyncMock(side_effect=[_GRAPH_OWNED, [file_node], [], [], [], [], []])

                client = TestClient(app)
                resp = client.get("/graph/impact-by-path", params={"path": "target.py"})
        finally:
            app.dependency_overrides.clear()

        assert resp.status_code == 200
        assert resp.json()["product_ref"] == "product:platform"

    def test_default_product_mismatches_a_non_platform_principal(self):
        from fastapi.testclient import TestClient

        from core.engine.api.main import app
        from core.engine.core.auth import get_current_user

        app.dependency_overrides[get_current_user] = lambda: {
            "sub": "user:other",
            "product": "product:other",
        }
        try:
            with patch("core.engine.api.graph_traverse.pool") as mock_pool:
                mock_conn = AsyncMock()
                mock_pool.connection.return_value.__aenter__ = AsyncMock(return_value=mock_conn)
                mock_pool.connection.return_value.__aexit__ = AsyncMock(return_value=False)
                mock_conn.query = AsyncMock(side_effect=AssertionError("no query may run for a rejected product"))

                client = TestClient(app)
                # Omitting `product` still resolves to the public default of
                # 'product:platform', which must be rejected before any graph read.
                resp = client.get("/graph/impact-by-path", params={"path": "target.py"})
        finally:
            app.dependency_overrides.clear()

        assert resp.status_code == 404


class TestHistoryShortcut:
    @pytest.mark.asyncio
    async def test_history_calls_traverse(self, mock_pool, mock_db, mock_user):
        """History endpoint should call traverse with correct edge types."""
        from core.engine.api.graph_traverse import get_history

        start_node = {"id": "graph_file:x", "path": "x.py", "graph_id": "default"}
        # queries[0] is the graph↔product mapping the shared traversal boundary
        # now resolves before it reads any node; queries[1] is the start-node read.
        mock_db.query = AsyncMock(side_effect=[_GRAPH_OWNED, [start_node], [], []])

        with patch("core.engine.api.graph_traverse.pool", mock_pool):
            result = await get_history("graph_file:x", graph_id="default", user=mock_user)

        assert isinstance(result, TraverseResponse)


class TestRelatedShortcut:
    @pytest.mark.asyncio
    async def test_related_calls_traverse(self, mock_pool, mock_db, mock_user):
        """Related endpoint returns all edge types at depth 1."""
        from core.engine.api.graph_traverse import get_related

        start_node = {"id": "graph_file:x", "path": "x.py", "graph_id": "default"}
        # queries[0] is the graph↔product mapping the shared traversal boundary
        # now resolves before it reads any node; queries[1] is the start-node read.
        mock_db.query = AsyncMock(side_effect=[_GRAPH_OWNED, [start_node], []])

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
