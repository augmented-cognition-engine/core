# tests/test_intelligence_graph_builder.py
"""Tests for the code graph builder (Task 6).

All tests use in-memory mode (persist=False) — no DB required.
"""

import os
import tempfile

from core.engine.intelligence.graph_builder import GraphBuilder

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _create_test_repo() -> str:
    """Create a minimal Python + TypeScript repo in a temp directory."""
    d = tempfile.mkdtemp()
    with open(os.path.join(d, "models.py"), "w") as f:
        f.write("class User:\n    pass\n\nclass Post:\n    pass\n\ndef get_user(id):\n    return User()\n")
    with open(os.path.join(d, "services.py"), "w") as f:
        f.write("from models import User\n\nasync def fetch_user(id):\n    return User()\n")
    with open(os.path.join(d, "app.ts"), "w") as f:
        f.write("export function main(): void {\n  console.log('hello')\n}\n")
    return d


# ---------------------------------------------------------------------------
# Phase 1 — file scanning
# ---------------------------------------------------------------------------


def test_phase1_scans_files():
    d = _create_test_repo()
    builder = GraphBuilder(d)
    result = builder.phase1_treesitter()
    assert result["files"] >= 2


def test_phase1_scans_java_file():
    d = tempfile.mkdtemp()
    with open(os.path.join(d, "Main.java"), "w") as f:
        f.write(
            "public class Main {\n"
            "    public static void main(String[] args) {\n"
            '        System.out.println("hello");\n'
            "    }\n"
            "}\n"
        )
    builder = GraphBuilder(d)
    result = builder.phase1_treesitter()
    assert result["files"] >= 1
    assert result["classes"] >= 1
    assert result["functions"] >= 1  # main() method


def test_phase1_file_and_function_counts():
    d = _create_test_repo()
    builder = GraphBuilder(d)
    result = builder.phase1_treesitter()
    assert result["files"] >= 2
    assert result["functions"] >= 2


def test_phase1_extracts_symbols():
    d = _create_test_repo()
    builder = GraphBuilder(d)
    builder.phase1_treesitter()
    names = [s["name"] for s in builder.get_symbols()]
    assert "User" in names
    assert "Post" in names
    assert "get_user" in names


def test_phase1_extracts_imports():
    d = _create_test_repo()
    builder = GraphBuilder(d)
    builder.phase1_treesitter()
    imports = builder.get_imports()
    assert len(imports) >= 1
    modules = [i["module"] for i in imports]
    assert "models" in modules


def test_phase1_extracts_typescript_symbols():
    d = _create_test_repo()
    builder = GraphBuilder(d)
    builder.phase1_treesitter()
    names = [s["name"] for s in builder.get_symbols()]
    # TypeScript export function
    assert "main" in names


def test_empty_repo():
    d = tempfile.mkdtemp()
    builder = GraphBuilder(d)
    result = builder.phase1_treesitter()
    assert result["files"] == 0
    assert result["functions"] == 0
    assert result["classes"] == 0
    assert result["imports"] == 0


def test_returns_files():
    d = _create_test_repo()
    builder = GraphBuilder(d)
    builder.phase1_treesitter()
    files = builder.get_files()
    assert len(files) >= 2
    paths = [f["path"] for f in files]
    assert any("models.py" in p for p in paths)
    assert any("services.py" in p for p in paths)


# ---------------------------------------------------------------------------
# Graph structure
# ---------------------------------------------------------------------------


def test_graph_has_nodes_after_phase1():
    d = _create_test_repo()
    builder = GraphBuilder(d)
    builder.phase1_treesitter()
    g = builder.graph
    assert len(g.nodes) >= 2


def test_graph_has_edges_from_imports():
    d = _create_test_repo()
    builder = GraphBuilder(d)
    builder.phase1_treesitter()
    g = builder.graph
    # services.py imports User from models.py — should create an edge
    assert len(g.edges) >= 1


def test_graph_property_returns_digraph():
    import networkx as nx

    d = _create_test_repo()
    builder = GraphBuilder(d)
    assert isinstance(builder.graph, nx.DiGraph)


# ---------------------------------------------------------------------------
# Centrality
# ---------------------------------------------------------------------------


def test_centrality():
    d = _create_test_repo()
    builder = GraphBuilder(d)
    builder.phase1_treesitter()
    scores = builder.compute_centrality()
    assert len(scores) > 0
    # All scores should be positive floats
    for score in scores.values():
        assert score > 0.0


def test_centrality_empty_graph():
    d = tempfile.mkdtemp()
    builder = GraphBuilder(d)
    builder.phase1_treesitter()
    scores = builder.compute_centrality()
    assert scores == {}


# ---------------------------------------------------------------------------
# persist=False (default) — no DB, no errors
# ---------------------------------------------------------------------------


def test_persist_false_is_default():
    d = _create_test_repo()
    builder = GraphBuilder(d)
    # Should not raise even though no DB is available
    result = builder.phase1_treesitter()
    assert result["files"] >= 2


def test_persist_false_explicit():
    d = _create_test_repo()
    builder = GraphBuilder(d, persist=False)
    result = builder.phase1_treesitter()
    assert result["files"] >= 2


# ---------------------------------------------------------------------------
# Skip directories
# ---------------------------------------------------------------------------


def test_skips_hidden_dirs():
    d = tempfile.mkdtemp()
    hidden = os.path.join(d, ".git")
    os.makedirs(hidden)
    with open(os.path.join(hidden, "config.py"), "w") as f:
        f.write("x = 1\n")
    with open(os.path.join(d, "main.py"), "w") as f:
        f.write("def run(): pass\n")

    builder = GraphBuilder(d)
    result = builder.phase1_treesitter()
    assert result["files"] == 1  # only main.py


def test_skips_pycache():
    d = tempfile.mkdtemp()
    cache = os.path.join(d, "__pycache__")
    os.makedirs(cache)
    with open(os.path.join(cache, "module.py"), "w") as f:
        f.write("x = 1\n")
    with open(os.path.join(d, "app.py"), "w") as f:
        f.write("def main(): pass\n")

    builder = GraphBuilder(d)
    result = builder.phase1_treesitter()
    assert result["files"] == 1


# ---------------------------------------------------------------------------
# Incremental updates
# ---------------------------------------------------------------------------


def test_incremental_update():
    d = _create_test_repo()
    builder = GraphBuilder(d)
    builder.phase1_treesitter()

    initial_symbols = len(builder.get_symbols())

    # Modify a file — add extra classes so symbol count grows
    with open(os.path.join(d, "models.py"), "w") as f:
        f.write(
            "class User:\n    pass\n\nclass Post:\n    pass\n\n"
            "class Comment:\n    pass\n\nclass Tag:\n    pass\n\n"
            "class Like:\n    pass\n"
        )

    stats = builder.incremental_update(["models.py"])
    assert stats["updated"] == 1

    # Should have more symbols now
    new_symbols = len(builder.get_symbols())
    assert new_symbols > initial_symbols


def test_incremental_delete():
    d = _create_test_repo()
    builder = GraphBuilder(d)
    builder.phase1_treesitter()

    initial_nodes = builder.graph.number_of_nodes()

    # Delete a file
    os.unlink(os.path.join(d, "services.py"))
    stats = builder.incremental_update(["services.py"])

    # Graph should have fewer nodes
    assert builder.graph.number_of_nodes() < initial_nodes


def test_incremental_update_returns_stats():
    d = _create_test_repo()
    builder = GraphBuilder(d)
    builder.phase1_treesitter()

    with open(os.path.join(d, "models.py"), "w") as f:
        f.write("def helper(): pass\n")

    stats = builder.incremental_update(["models.py"])
    assert "updated" in stats
    assert "symbols_added" in stats
    assert stats["updated"] == 1
