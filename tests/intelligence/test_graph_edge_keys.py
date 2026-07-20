"""Every edge in the NetworkX graph must carry `edge_type` — never a bare `type`.

Regression guard: graph_builder previously wrote `contains` edges under
`edge_type` and `imports` edges under `type`, so any renderer or query
filtering by edge type silently dropped half the graph.
"""

from pathlib import Path

import pytest

from core.engine.intelligence.graph_builder import GraphBuilder


@pytest.fixture()
def built_graph(tmp_path: Path) -> GraphBuilder:
    """Build a two-file graph with a real import edge between them."""
    (tmp_path / "alpha.py").write_text(
        "def alpha_fn():\n    return 1\n",
        encoding="utf-8",
    )
    (tmp_path / "beta.py").write_text(
        "from alpha import alpha_fn\n\n\ndef beta_fn():\n    return alpha_fn()\n",
        encoding="utf-8",
    )
    builder = GraphBuilder(str(tmp_path))
    builder.phase1_treesitter()
    return builder


def test_every_edge_carries_edge_type(built_graph: GraphBuilder) -> None:
    edges = list(built_graph._nx_graph.edges(data=True))
    assert edges, "fixture produced no edges — the graph builder did not run"
    missing = [(u, v, d) for u, v, d in edges if "edge_type" not in d]
    assert missing == [], f"edges without edge_type: {missing}"


def test_no_edge_carries_a_bare_type_key(built_graph: GraphBuilder) -> None:
    stragglers = [(u, v, d) for u, v, d in built_graph._nx_graph.edges(data=True) if "type" in d]
    assert stragglers == [], f"edges still using the legacy `type` key: {stragglers}"


def test_both_contains_and_imports_are_present(built_graph: GraphBuilder) -> None:
    kinds = {d["edge_type"] for _, _, d in built_graph._nx_graph.edges(data=True)}
    assert "contains" in kinds
    assert "imports" in kinds
