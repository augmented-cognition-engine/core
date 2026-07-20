import os
import tempfile

from core.engine.intelligence.graph_builder import GraphBuilder
from core.engine.intelligence.queries import symbol_blast_radius, symbol_callers


def _make_repo() -> str:
    d = tempfile.mkdtemp()
    with open(os.path.join(d, "models.py"), "w") as f:
        f.write("class User:\n    pass\n\ndef get_user(uid):\n    return User()\n")
    with open(os.path.join(d, "services.py"), "w") as f:
        f.write("from models import User, get_user\n\ndef fetch_user(uid):\n    return get_user(uid)\n")
    return d


def test_phase1_adds_symbol_nodes():
    d = _make_repo()
    builder = GraphBuilder(d)
    builder.phase1_treesitter()
    symbol_nodes = [n for n in builder.graph.nodes if "::" in n]
    assert len(symbol_nodes) >= 3  # User, get_user, fetch_user


def test_phase1_symbol_nodes_have_metadata():
    d = _make_repo()
    builder = GraphBuilder(d)
    builder.phase1_treesitter()
    symbol_nodes = [n for n in builder.graph.nodes if "::" in n]
    assert len(symbol_nodes) > 0
    node_data = builder.graph.nodes[symbol_nodes[0]]
    assert "kind" in node_data
    assert "name" in node_data
    assert "file" in node_data
    assert "line_start" in node_data


def test_phase1_file_contains_symbol_edges():
    d = _make_repo()
    builder = GraphBuilder(d)
    builder.phase1_treesitter()
    contains_edges = [(u, v) for u, v, data in builder.graph.edges(data=True) if data.get("edge_type") == "contains"]
    assert len(contains_edges) >= 3


def test_symbol_blast_radius_returns_dict():
    d = _make_repo()
    builder = GraphBuilder(d)
    builder.phase1_treesitter()
    result = symbol_blast_radius("models.py::get_user", builder.graph)
    assert "symbol" in result
    assert "direct_callers" in result
    assert "total_affected" in result


def test_symbol_blast_radius_unknown_returns_zero():
    d = _make_repo()
    builder = GraphBuilder(d)
    builder.phase1_treesitter()
    result = symbol_blast_radius("ghost.py::phantom", builder.graph)
    assert result["total_affected"] == 0


def test_symbol_callers_unknown_returns_empty():
    d = _make_repo()
    builder = GraphBuilder(d)
    builder.phase1_treesitter()
    assert symbol_callers("ghost.py::phantom", builder.graph) == []
