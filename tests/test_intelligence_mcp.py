# tests/test_intelligence_mcp.py
"""Tests for intelligence MCP tools (Task 8).

Verifies:
- All query functions are importable and callable
- GraphBuilder is importable
- MCP tool functions are importable and callable
- Cached builder logic works in isolation
- init_project._fast_code_scan is accessible
"""

import pytest

# ---------------------------------------------------------------------------
# Import checks
# ---------------------------------------------------------------------------


def test_queries_importable():
    from core.engine.intelligence.queries import blast_radius, find_dead_code, symbol_importance

    assert callable(symbol_importance)
    assert callable(blast_radius)
    assert callable(find_dead_code)


def test_new_queries_importable():
    from core.engine.intelligence.queries import code_context, dependency_chain, module_coupling

    assert callable(code_context)
    assert callable(dependency_chain)
    assert callable(module_coupling)


def test_graph_builder_importable():
    from core.engine.intelligence.graph_builder import GraphBuilder

    assert GraphBuilder is not None
    assert callable(GraphBuilder)


def test_model_router_importable():
    from core.engine.intelligence.model_router import route_model

    assert callable(route_model)


def test_detector_importable():
    from core.engine.intelligence.detector import detect_languages

    assert callable(detect_languages)


# ---------------------------------------------------------------------------
# MCP tool function signatures
# ---------------------------------------------------------------------------


def test_ace_symbol_importance_importable():
    from core.engine.mcp.tools import ace_symbol_importance

    assert callable(ace_symbol_importance)


def test_ace_blast_radius_importable():
    from core.engine.mcp.tools import ace_blast_radius

    assert callable(ace_blast_radius)


def test_ace_find_dead_code_importable():
    from core.engine.mcp.tools import ace_find_dead_code

    assert callable(ace_find_dead_code)


def test_ace_code_context_importable():
    from core.engine.mcp.tools import ace_code_context

    assert callable(ace_code_context)


def test_ace_dependency_chain_importable():
    from core.engine.mcp.tools import ace_dependency_chain

    assert callable(ace_dependency_chain)


def test_ace_module_coupling_importable():
    from core.engine.mcp.tools import ace_module_coupling

    assert callable(ace_module_coupling)


# ---------------------------------------------------------------------------
# Cached builder logic
# ---------------------------------------------------------------------------


def test_cached_builder_builds_on_first_call(monkeypatch, tmp_path):
    """_get_builder() should create a GraphBuilder and scan the repo."""
    import core.engine.mcp.tools as tools_module
    from core.engine.intelligence.graph_builder import GraphBuilder

    # Reset cache
    monkeypatch.setattr(tools_module, "_cached_builder", None)
    monkeypatch.setattr(tools_module, "_cached_mtime", 0.0)

    # Point _get_builder at our temp repo
    (tmp_path / "app.py").write_text("def main(): pass\n")
    monkeypatch.chdir(tmp_path)

    builder = tools_module._get_builder()
    assert isinstance(builder, GraphBuilder)
    # After scanning, should have files
    assert len(builder.get_files()) >= 1


def test_cached_builder_reuses_on_same_mtime(monkeypatch, tmp_path):
    """_get_builder() should NOT rebuild when mtime hasn't changed."""
    import core.engine.mcp.tools as tools_module

    (tmp_path / "app.py").write_text("def run(): pass\n")
    monkeypatch.chdir(tmp_path)

    # Reset cache, prime it
    monkeypatch.setattr(tools_module, "_cached_builder", None)
    monkeypatch.setattr(tools_module, "_cached_mtime", 0.0)
    first = tools_module._get_builder()

    # Second call with same mtime should return exact same object
    second = tools_module._get_builder()
    assert first is second


def test_cached_builder_rebuilds_on_mtime_change(monkeypatch, tmp_path):
    """_get_builder() rebuilds when directory mtime changes."""
    import core.engine.mcp.tools as tools_module

    (tmp_path / "app.py").write_text("def run(): pass\n")
    monkeypatch.chdir(tmp_path)

    monkeypatch.setattr(tools_module, "_cached_builder", None)
    monkeypatch.setattr(tools_module, "_cached_mtime", 0.0)
    first = tools_module._get_builder()

    # Force mtime mismatch
    monkeypatch.setattr(tools_module, "_cached_mtime", -1.0)
    second = tools_module._get_builder()
    assert first is not second


# ---------------------------------------------------------------------------
# init_project._fast_code_scan
# ---------------------------------------------------------------------------


def test_fast_code_scan_callable():
    from core.engine.runtime.init_project import _fast_code_scan

    assert callable(_fast_code_scan)


@pytest.mark.asyncio
async def test_fast_code_scan_returns_stats(tmp_path):
    """_fast_code_scan should return stats without a live DB (best-effort persist)."""
    from core.engine.runtime.init_project import _fast_code_scan

    (tmp_path / "main.py").write_text("def hello(): pass\n")
    (tmp_path / "utils.py").write_text("def helper(): pass\n")

    stats = await _fast_code_scan(str(tmp_path))
    # Must always have these keys
    assert "files_created" in stats
    assert "functions_created" in stats
    assert "imports_created" in stats
    # Sanity: picked up our 2 files
    assert stats["files_created"] >= 2


@pytest.mark.asyncio
async def test_fast_code_scan_empty_repo(tmp_path):
    from core.engine.runtime.init_project import _fast_code_scan

    stats = await _fast_code_scan(str(tmp_path))
    assert stats["files_created"] == 0
