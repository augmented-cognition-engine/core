# tests/test_graph_clusters.py
"""Tests for community detection (engine/graph/cluster.py) and GET /graph/clusters endpoint."""

from contextlib import asynccontextmanager
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from core.engine.graph.cluster import build_graph, compute_inter_cluster_edges, detect_clusters

# ---------------------------------------------------------------------------
# Pure logic tests — build_graph
# ---------------------------------------------------------------------------


def test_build_graph_creates_correct_nodes_and_edges():
    """build_graph creates correct nodes and edges from edge dicts."""
    edges = [
        {"from": "capability:auth", "to": "graph_file:auth_py", "type": "realizes"},
        {"from": "capability:auth", "to": "graph_file:login_py", "type": "realizes"},
        {"from": "idea:fast_login", "to": "initiative:perf", "type": "became"},
    ]
    g = build_graph(edges)
    assert g.number_of_nodes() == 5
    assert g.number_of_edges() == 3
    assert g.has_edge("capability:auth", "graph_file:auth_py")
    assert g.has_edge("capability:auth", "graph_file:login_py")
    assert g.has_edge("idea:fast_login", "initiative:perf")


def test_build_graph_empty_edges():
    """build_graph with empty list returns empty graph."""
    g = build_graph([])
    assert g.number_of_nodes() == 0
    assert g.number_of_edges() == 0


def test_build_graph_skips_missing_fields():
    """build_graph skips edges with missing from/to fields."""
    edges = [
        {"from": "a:1", "to": "b:2", "type": "x"},
        {"from": "", "to": "b:3", "type": "y"},
        {"to": "b:4", "type": "z"},
        {"from": "a:5", "type": "w"},
    ]
    g = build_graph(edges)
    assert g.number_of_nodes() == 2
    assert g.number_of_edges() == 1


# ---------------------------------------------------------------------------
# Pure logic tests — detect_clusters
# ---------------------------------------------------------------------------


def test_detect_clusters_two_disconnected_cliques():
    """Two disconnected cliques of 5 nodes each → 2 clusters."""
    edges = []
    # Clique A: capability nodes
    clique_a = [f"capability:c{i}" for i in range(5)]
    for i in range(5):
        for j in range(i + 1, 5):
            edges.append({"from": clique_a[i], "to": clique_a[j], "type": "depends_on"})

    # Clique B: graph_file nodes
    clique_b = [f"graph_file:f{i}" for i in range(5)]
    for i in range(5):
        for j in range(i + 1, 5):
            edges.append({"from": clique_b[i], "to": clique_b[j], "type": "imports"})

    g = build_graph(edges)
    assert g.number_of_nodes() == 10

    clusters = detect_clusters(g, min_nodes=5)
    assert len(clusters) == 2

    # Check cluster properties
    for cluster in clusters:
        assert cluster["node_count"] == 5
        assert "id" in cluster
        assert "dominant_layer" in cluster
        assert "label" in cluster
        assert "nodes" in cluster
        assert len(cluster["nodes"]) == 5

    # Check dominant layers
    layers = {c["dominant_layer"] for c in clusters}
    assert "product" in layers  # capability nodes
    assert "code" in layers  # graph_file nodes


def test_detect_clusters_too_few_nodes():
    """Graph with fewer than min_nodes returns empty clusters."""
    edges = [
        {"from": "a:1", "to": "b:2", "type": "x"},
        {"from": "b:2", "to": "c:3", "type": "y"},
    ]
    g = build_graph(edges)
    assert g.number_of_nodes() == 3

    clusters = detect_clusters(g, min_nodes=5)
    assert clusters == []


def test_detect_clusters_label_prefers_capability():
    """Cluster label should prefer capability node id when present."""
    edges = []
    nodes = ["capability:auth", "graph_file:f1", "graph_file:f2", "graph_file:f3", "graph_file:f4"]
    # Make a fully connected clique so Louvain keeps it as one community
    for i in range(len(nodes)):
        for j in range(i + 1, len(nodes)):
            edges.append({"from": nodes[i], "to": nodes[j], "type": "realizes"})

    g = build_graph(edges)
    clusters = detect_clusters(g, min_nodes=5)
    assert len(clusters) == 1
    assert clusters[0]["label"] == "capability:auth"


# ---------------------------------------------------------------------------
# Pure logic tests — compute_inter_cluster_edges
# ---------------------------------------------------------------------------


def test_compute_inter_cluster_edges():
    """Cross-cluster edges are counted correctly."""
    edges = []
    # Clique A
    clique_a = [f"capability:c{i}" for i in range(5)]
    for i in range(5):
        for j in range(i + 1, 5):
            edges.append({"from": clique_a[i], "to": clique_a[j], "type": "depends_on"})

    # Clique B
    clique_b = [f"graph_file:f{i}" for i in range(5)]
    for i in range(5):
        for j in range(i + 1, 5):
            edges.append({"from": clique_b[i], "to": clique_b[j], "type": "imports"})

    # One bridge edge between clusters
    edges.append({"from": "capability:c0", "to": "graph_file:f0", "type": "realizes"})

    g = build_graph(edges)
    clusters = detect_clusters(g, min_nodes=5)
    assert len(clusters) == 2

    inter_edges = compute_inter_cluster_edges(g, clusters)
    assert len(inter_edges) == 1
    assert inter_edges[0]["weight"] == 1
    assert "from_cluster" in inter_edges[0]
    assert "to_cluster" in inter_edges[0]


def test_compute_inter_cluster_edges_no_cross():
    """No cross-cluster edges when clusters are fully disconnected."""
    edges = []
    clique_a = [f"capability:c{i}" for i in range(5)]
    for i in range(5):
        for j in range(i + 1, 5):
            edges.append({"from": clique_a[i], "to": clique_a[j], "type": "depends_on"})

    clique_b = [f"graph_file:f{i}" for i in range(5)]
    for i in range(5):
        for j in range(i + 1, 5):
            edges.append({"from": clique_b[i], "to": clique_b[j], "type": "imports"})

    g = build_graph(edges)
    clusters = detect_clusters(g, min_nodes=5)
    inter_edges = compute_inter_cluster_edges(g, clusters)
    assert inter_edges == []


# ---------------------------------------------------------------------------
# API endpoint tests — GET /graph/clusters
# ---------------------------------------------------------------------------


@asynccontextmanager
async def mock_lifespan(app):
    yield


def _mock_user():
    return {"product": "product:test", "sub": "user:1"}


@pytest.mark.asyncio
@patch("core.engine.api.graph_clusters.pool")
@patch("core.engine.api.graph_clusters.serialize_record")
async def test_graph_clusters_endpoint_returns_structure(mock_serialize_record, mock_pool):
    """GET /graph/clusters returns clusters, inter_cluster_edges, computed_at."""
    from httpx import ASGITransport, AsyncClient

    from core.engine.api.main import app
    from core.engine.core.auth import get_current_user

    app.router.lifespan_context = mock_lifespan
    app.dependency_overrides[get_current_user] = _mock_user

    mock_db = AsyncMock()
    mock_db.query.return_value = []
    mock_ctx = MagicMock()
    mock_ctx.__aenter__ = AsyncMock(return_value=mock_db)
    mock_ctx.__aexit__ = AsyncMock(return_value=False)
    mock_pool.connection.return_value = mock_ctx

    mock_serialize_record.side_effect = lambda v: v if isinstance(v, dict) else str(v)

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        resp = await ac.get("/graph/clusters")

    assert resp.status_code == 200
    data = resp.json()
    assert "clusters" in data
    assert "inter_cluster_edges" in data
    assert "computed_at" in data
    assert isinstance(data["clusters"], list)
    assert isinstance(data["inter_cluster_edges"], list)

    app.dependency_overrides.clear()


@pytest.mark.asyncio
async def test_graph_clusters_requires_auth():
    """GET /graph/clusters returns 401 without auth."""
    from httpx import ASGITransport, AsyncClient

    from core.engine.api.main import app

    app.router.lifespan_context = mock_lifespan

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        resp = await ac.get("/graph/clusters")

    assert resp.status_code == 401
