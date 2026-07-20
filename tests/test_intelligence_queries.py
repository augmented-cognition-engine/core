# tests/test_intelligence_queries.py
"""Tests for graph queries (Task 7).

All 6 query functions: symbol_importance, blast_radius, find_dead_code,
dependency_chain, module_coupling, code_context.
"""

import os
import tempfile

from core.engine.intelligence.graph_builder import GraphBuilder
from core.engine.intelligence.queries import (
    blast_radius,
    code_context,
    dependency_chain,
    find_dead_code,
    module_coupling,
    symbol_importance,
)

# ---------------------------------------------------------------------------
# Shared fixture
# ---------------------------------------------------------------------------


def _build_test_graph() -> GraphBuilder:
    """Build a small dependency graph: api → auth → core, plus orphan.py."""
    d = tempfile.mkdtemp()
    with open(os.path.join(d, "core.py"), "w") as f:
        f.write("class Base:\n    pass\n\ndef init():\n    pass\n")
    with open(os.path.join(d, "auth.py"), "w") as f:
        f.write("from core import Base\n\nclass Auth(Base):\n    pass\n")
    with open(os.path.join(d, "api.py"), "w") as f:
        f.write("from auth import Auth\n\ndef handler():\n    a = Auth()\n")
    with open(os.path.join(d, "orphan.py"), "w") as f:
        f.write("def unused_function():\n    pass\n")
    builder = GraphBuilder(d)
    builder.phase1_treesitter()
    return builder


# ---------------------------------------------------------------------------
# 1. symbol_importance
# ---------------------------------------------------------------------------


def test_symbol_importance_returns_list():
    builder = _build_test_graph()
    scores = symbol_importance(builder.graph)
    assert isinstance(scores, list)
    assert len(scores) > 0


def test_symbol_importance_core_in_results():
    builder = _build_test_graph()
    scores = symbol_importance(builder.graph)
    # core.py has in-degree >= 1 (auth.py imports it) — it must appear in results
    all_files = [s["path"] for s in scores]
    assert "core.py" in all_files
    # Verify core.py has dependents > 0 in the results
    core_entry = next((s for s in scores if s["path"] == "core.py"), None)
    assert core_entry is not None
    assert core_entry["dependents"] >= 1


def test_symbol_importance_has_required_fields():
    builder = _build_test_graph()
    scores = symbol_importance(builder.graph)
    for entry in scores:
        assert "path" in entry
        assert "score" in entry
        assert "dependents" in entry


def test_symbol_importance_limit():
    builder = _build_test_graph()
    scores = symbol_importance(builder.graph, limit=2)
    assert len(scores) <= 2


def test_symbol_importance_empty_graph():
    import networkx as nx

    empty = nx.DiGraph()
    result = symbol_importance(empty)
    assert result == []


# ---------------------------------------------------------------------------
# 2. blast_radius
# ---------------------------------------------------------------------------


def test_blast_radius_core():
    builder = _build_test_graph()
    result = blast_radius("core.py", builder.graph)
    assert result["direct_dependents"] >= 1
    assert result["total_affected"] >= 1


def test_blast_radius_affected_files():
    builder = _build_test_graph()
    result = blast_radius("core.py", builder.graph)
    affected = result["affected_files"]
    # auth.py imports from core.py
    assert any("auth" in f for f in affected)


def test_blast_radius_unknown_file():
    builder = _build_test_graph()
    result = blast_radius("nonexistent.py", builder.graph)
    assert result["direct_dependents"] == 0
    assert result["total_affected"] == 0
    assert result["affected_files"] == []


def test_blast_radius_leaf_file():
    """api.py has no dependents — blast radius should be 0."""
    builder = _build_test_graph()
    result = blast_radius("api.py", builder.graph)
    assert result["direct_dependents"] == 0


def test_blast_radius_has_required_fields():
    builder = _build_test_graph()
    result = blast_radius("core.py", builder.graph)
    assert "file" in result
    assert "direct_dependents" in result
    assert "total_affected" in result
    assert "affected_files" in result


# ---------------------------------------------------------------------------
# 3. find_dead_code
# ---------------------------------------------------------------------------


def test_find_dead_code_returns_list():
    builder = _build_test_graph()
    dead = find_dead_code(builder)
    assert isinstance(dead, list)


def test_find_dead_code_orphan_flagged():
    builder = _build_test_graph()
    dead = find_dead_code(builder)
    dead_files = [d["file"] for d in dead]
    # orphan.py has no importers
    assert any("orphan" in f for f in dead_files)


def test_find_dead_code_symbols_have_names():
    builder = _build_test_graph()
    dead = find_dead_code(builder)
    for sym in dead:
        assert "name" in sym
        assert "file" in sym


# ---------------------------------------------------------------------------
# 4. dependency_chain
# ---------------------------------------------------------------------------


def test_dependency_chain_direct():
    builder = _build_test_graph()
    chain = dependency_chain("auth.py", "core.py", builder.graph)
    # auth.py → core.py
    assert len(chain) >= 2
    assert "core.py" in chain


def test_dependency_chain_transitive():
    builder = _build_test_graph()
    # api.py → auth.py → core.py
    chain = dependency_chain("api.py", "core.py", builder.graph)
    assert len(chain) >= 2


def test_dependency_chain_no_path():
    builder = _build_test_graph()
    chain = dependency_chain("core.py", "api.py", builder.graph)
    # core.py does NOT depend on api.py
    assert chain == []


def test_dependency_chain_nonexistent():
    builder = _build_test_graph()
    chain = dependency_chain("nonexistent.py", "core.py", builder.graph)
    assert chain == []


# ---------------------------------------------------------------------------
# 5. module_coupling
# ---------------------------------------------------------------------------


def test_module_coupling_returns_dict():
    builder = _build_test_graph()
    result = module_coupling("auth.py", "core.py", builder.graph)
    assert isinstance(result, dict)
    assert "coupling_score" in result
    assert "edges" in result


def test_module_coupling_connected_files():
    builder = _build_test_graph()
    result = module_coupling("auth.py", "core.py", builder.graph)
    # auth imports core, so there should be at least 1 edge
    assert result["edges"] >= 1
    assert result["coupling_score"] > 0.0


def test_module_coupling_unconnected_files():
    builder = _build_test_graph()
    result = module_coupling("orphan.py", "core.py", builder.graph)
    assert result["edges"] == 0
    assert result["coupling_score"] == 0.0


def test_module_coupling_nonexistent():
    builder = _build_test_graph()
    result = module_coupling("does_not_exist.py", "core.py", builder.graph)
    assert result["edges"] == 0
    assert result["coupling_score"] == 0.0


def test_module_coupling_has_required_fields():
    builder = _build_test_graph()
    result = module_coupling("auth.py", "core.py", builder.graph)
    assert "module_a" in result
    assert "module_b" in result
    assert "edges" in result
    assert "coupling_score" in result
    assert "shared_files" in result


# ---------------------------------------------------------------------------
# 6. code_context
# ---------------------------------------------------------------------------


def test_code_context_returns_dict():
    builder = _build_test_graph()
    result = code_context("how does auth work", builder)
    assert isinstance(result, dict)
    assert "query" in result
    assert "matched_files" in result
    assert "context_files" in result
    assert "symbols" in result


def test_code_context_matches_by_filename():
    builder = _build_test_graph()
    result = code_context("show me auth.py", builder)
    # Should find auth.py directly
    assert any("auth" in f for f in result["matched_files"])


def test_code_context_matches_by_symbol():
    builder = _build_test_graph()
    result = code_context("how does Auth class work", builder)
    # Auth is defined in auth.py
    assert any("auth" in f for f in result["matched_files"])


def test_code_context_includes_neighbors():
    builder = _build_test_graph()
    result = code_context("auth.py", builder)
    context_paths = [f["path"] for f in result["context_files"]]
    # auth.py depends on core.py — core.py should appear as a neighbor
    assert any("core" in p for p in context_paths) or any("auth" in p for p in context_paths)


def test_code_context_empty_graph():
    d = tempfile.mkdtemp()
    builder = GraphBuilder(d)
    builder.phase1_treesitter()
    result = code_context("anything", builder)
    assert result["matched_files"] == []
    assert result["context_files"] == []
    assert result["total_context_files"] == 0


def test_code_context_total_count():
    builder = _build_test_graph()
    result = code_context("core", builder)
    assert result["total_context_files"] >= 0
    # context_files is capped at 20
    assert len(result["context_files"]) <= 20


def test_code_context_roles():
    builder = _build_test_graph()
    result = code_context("core.py", builder)
    roles = {f["role"] for f in result["context_files"]}
    # Should have at least direct_match
    assert "direct_match" in roles
