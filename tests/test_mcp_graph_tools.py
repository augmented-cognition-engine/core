# tests/test_mcp_graph_tools.py
"""Tests for MCP graph tools — ace_impact, ace_history, ace_related."""

from unittest.mock import AsyncMock, patch

import pytest

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_pool_mock(side_effects):
    """Return a pool mock where db.query returns successive side_effects."""
    mock_pool = AsyncMock()
    mock_conn = AsyncMock()
    mock_conn.query = AsyncMock(side_effect=side_effects)
    mock_pool.connection.return_value.__aenter__ = AsyncMock(return_value=mock_conn)
    mock_pool.connection.return_value.__aexit__ = AsyncMock(return_value=False)
    return mock_pool, mock_conn


# ---------------------------------------------------------------------------
# ace_impact
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_ace_impact_returns_dependents():
    """ace_impact() returns dependent files and functions as a dict."""
    from core.engine.mcp.tools import ace_impact

    file_row = {
        "id": "graph_file:engine_core_db_py",
        "path": "core/engine/core/db.py",
        "change_frequency": 7,
    }
    importer_rows = [
        {"path": "core/engine/mcp/tools.py", "name": "tools", "language": "python"},
        {"path": "core/engine/api/graph_traverse.py", "name": "graph_traverse", "language": "python"},
    ]
    function_rows = [
        {"name": "pool", "kind": "variable", "line_start": 10, "line_end": 10},
        {"name": "parse_rows", "kind": "function", "line_start": 20, "line_end": 30},
    ]
    capability_rows = [
        {"slug": "graph-tools", "name": "Graph Tools"},
    ]

    with patch("core.engine.mcp.tools.pool") as mock_pool:
        mock_conn = AsyncMock()
        mock_conn.query = AsyncMock(
            side_effect=[
                [file_row],  # path lookup → parse_one returns file_row
                importer_rows,  # importers traversal
                function_rows,  # functions traversal
                capability_rows,  # capabilities query
            ]
        )
        mock_pool.connection.return_value.__aenter__ = AsyncMock(return_value=mock_conn)
        mock_pool.connection.return_value.__aexit__ = AsyncMock(return_value=False)

        result = await ace_impact("core/engine/core/db.py")

    assert isinstance(result, dict)
    assert result["file"] == "core/engine/core/db.py"
    assert result["importer_count"] == 2
    assert result["function_count"] == 2
    assert result["safe_to_delete"] is False
    assert any("core/engine/mcp/tools.py" in str(r) for r in result["importers"])
    assert any("core/engine/api/graph_traverse.py" in str(r) for r in result["importers"])
    assert any("parse_rows" in str(f) for f in result["functions"])
    assert "summary" in result


@pytest.mark.asyncio
async def test_ace_impact_file_not_found():
    """ace_impact() returns an error dict when the file isn't in the graph."""
    from core.engine.mcp.tools import ace_impact

    with patch("core.engine.mcp.tools.pool") as mock_pool:
        mock_conn = AsyncMock()
        mock_conn.query = AsyncMock(
            side_effect=[
                # path lookup — not found
                [],
            ]
        )
        mock_pool.connection.return_value.__aenter__ = AsyncMock(return_value=mock_conn)
        mock_pool.connection.return_value.__aexit__ = AsyncMock(return_value=False)

        result = await ace_impact("engine/nonexistent/file.py")

    assert isinstance(result, dict)
    assert "error" in result
    assert "not found" in result["error"].lower()
    assert "engine/nonexistent/file.py" in result["error"]


@pytest.mark.asyncio
async def test_ace_impact_no_dependents():
    """ace_impact() handles a leaf file with no importers — safe_to_delete=True."""
    from core.engine.mcp.tools import ace_impact

    file_row = {
        "id": "graph_file:engine_utils_leaf_py",
        "path": "engine/utils/leaf.py",
        "change_frequency": 1,
    }

    with patch("core.engine.mcp.tools.pool") as mock_pool:
        mock_conn = AsyncMock()
        mock_conn.query = AsyncMock(
            side_effect=[
                [file_row],  # path lookup
                [],  # no importers
                [],  # no functions
                [],  # no capabilities
            ]
        )
        mock_pool.connection.return_value.__aenter__ = AsyncMock(return_value=mock_conn)
        mock_pool.connection.return_value.__aexit__ = AsyncMock(return_value=False)

        result = await ace_impact("engine/utils/leaf.py")

    assert isinstance(result, dict)
    assert result["file"] == "engine/utils/leaf.py"
    assert result["importer_count"] == 0
    assert result["safe_to_delete"] is True
    assert result["importers"] == []


@pytest.mark.asyncio
async def test_ace_impact_fragility_score_high_with_many_dependents():
    """ace_impact() reports high importer count when file has many dependents."""
    from core.engine.mcp.tools import ace_impact

    file_node = {
        "id": "graph_file:engine_core_db_py",
        "path": "core/engine/core/db.py",
        "change_frequency": 15,
    }
    # 12 importers
    importer_rows = [{"path": f"engine/module_{i}.py", "name": f"module_{i}", "language": "python"} for i in range(12)]

    with patch("core.engine.mcp.tools.pool") as mock_pool:
        mock_conn = AsyncMock()
        mock_conn.query = AsyncMock(
            side_effect=[
                [file_node],  # path lookup
                importer_rows,  # importers traversal (12 rows)
                [],  # no functions
                [],  # no capabilities
            ]
        )
        mock_pool.connection.return_value.__aenter__ = AsyncMock(return_value=mock_conn)
        mock_pool.connection.return_value.__aexit__ = AsyncMock(return_value=False)

        result = await ace_impact("core/engine/core/db.py")

    assert isinstance(result, dict)
    assert result["importer_count"] == 12
    assert result["safe_to_delete"] is False
    # Summary should mention 12 file(s)
    assert "12 file(s)" in result["summary"]


# ---------------------------------------------------------------------------
# ace_history
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_ace_history_returns_decisions():
    """ace_history() returns the decision trail for a file."""
    from core.engine.mcp.tools import ace_history

    file_row = {
        "id": "graph_file:engine_core_db_py",
        "path": "core/engine/core/db.py",
    }
    decision_rows = [
        {
            "id": "graph_decision:d1",
            "title": "Add connection pooling",
            "description": "Single connection caused blocking; replaced with pool.",
            "outcome": "Throughput improved 10x",
            "created_at": "2026-02-10T12:00:00Z",
            "tags": ["performance", "db"],
        },
        {
            "id": "graph_decision:d2",
            "title": "Add watchdog task",
            "description": "Pool connections leaked under load.",
            "outcome": "Zero leaked connections after watchdog",
            "created_at": "2026-02-15T09:00:00Z",
            "tags": ["reliability"],
        },
    ]

    with patch("core.engine.mcp.tools.pool") as mock_pool:
        mock_conn = AsyncMock()
        mock_conn.query = AsyncMock(
            side_effect=[
                [file_row],  # slug lookup
                decision_rows,  # improves decisions
                [],  # informed_by decisions
            ]
        )
        mock_pool.connection.return_value.__aenter__ = AsyncMock(return_value=mock_conn)
        mock_pool.connection.return_value.__aexit__ = AsyncMock(return_value=False)

        result = await ace_history("core/engine/core/db.py")

    assert "core/engine/core/db.py" in result
    assert "Add connection pooling" in result
    assert "Throughput improved 10x" in result
    assert "Add watchdog task" in result
    assert "performance" in result
    assert "Decision History" in result


@pytest.mark.asyncio
async def test_ace_history_file_not_found():
    """ace_history() returns a helpful message when file isn't in the graph."""
    from core.engine.mcp.tools import ace_history

    with patch("core.engine.mcp.tools.pool") as mock_pool:
        mock_conn = AsyncMock()
        mock_conn.query = AsyncMock(side_effect=[[], []])
        mock_pool.connection.return_value.__aenter__ = AsyncMock(return_value=mock_conn)
        mock_pool.connection.return_value.__aexit__ = AsyncMock(return_value=False)

        result = await ace_history("engine/ghost/file.py")

    assert "not found" in result.lower()
    assert "engine/ghost/file.py" in result


@pytest.mark.asyncio
async def test_ace_history_no_decisions():
    """ace_history() returns appropriate message when no decisions exist."""
    from core.engine.mcp.tools import ace_history

    file_row = {
        "id": "graph_file:engine_utils_new_py",
        "path": "engine/utils/new.py",
    }

    with patch("core.engine.mcp.tools.pool") as mock_pool:
        mock_conn = AsyncMock()
        mock_conn.query = AsyncMock(side_effect=[[file_row], [], []])
        mock_pool.connection.return_value.__aenter__ = AsyncMock(return_value=mock_conn)
        mock_pool.connection.return_value.__aexit__ = AsyncMock(return_value=False)

        result = await ace_history("engine/utils/new.py")

    assert "engine/utils/new.py" in result
    assert "No decisions" in result or "no decisions" in result.lower()


@pytest.mark.asyncio
async def test_ace_history_includes_informed_by():
    """ace_history() includes decisions connected via informed_by edges."""
    from core.engine.mcp.tools import ace_history

    file_row = {"id": "graph_file:engine_core_config_py", "path": "core/engine/core/config.py"}
    informed_rows = [
        {
            "id": "graph_decision:d5",
            "title": "Use pydantic-settings for config",
            "description": "Typed env loading",
            "outcome": "No more KeyError on missing env vars",
            "created_at": "2026-01-05T10:00:00Z",
        }
    ]

    with patch("core.engine.mcp.tools.pool") as mock_pool:
        mock_conn = AsyncMock()
        mock_conn.query = AsyncMock(
            side_effect=[
                [file_row],
                [],  # no improves decisions
                informed_rows,  # informed_by decisions
            ]
        )
        mock_pool.connection.return_value.__aenter__ = AsyncMock(return_value=mock_conn)
        mock_pool.connection.return_value.__aexit__ = AsyncMock(return_value=False)

        result = await ace_history("core/engine/core/config.py")

    assert "Use pydantic-settings for config" in result
    assert "Also informed by" in result


# ---------------------------------------------------------------------------
# ace_related
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_ace_related_returns_connections():
    """ace_related() returns imports, importers, co-changed files, and decisions."""
    from core.engine.mcp.tools import ace_related

    file_row = {
        "id": "graph_file:engine_core_db_py",
        "path": "core/engine/core/db.py",
    }
    import_rows = [
        {"id": "graph_file:engine_core_config_py", "path": "core/engine/core/config.py"},
    ]
    importer_rows = [
        {"id": "graph_file:engine_mcp_tools_py", "path": "core/engine/mcp/tools.py"},
        {"id": "graph_file:engine_api_graph_traverse_py", "path": "core/engine/api/graph_traverse.py"},
    ]
    related_rows = [
        {"id": "graph_file:engine_core_auth_py", "path": "core/engine/core/auth.py"},
    ]
    function_rows = [
        {"id": "graph_function:parse_rows", "name": "parse_rows"},
        {"id": "graph_function:pool", "name": "pool"},
    ]
    decision_rows = [
        {"id": "graph_decision:d1", "title": "Connection pooling", "created_at": "2026-02-10T12:00:00Z"},
    ]

    with patch("core.engine.mcp.tools.pool") as mock_pool:
        mock_conn = AsyncMock()
        mock_conn.query = AsyncMock(
            side_effect=[
                [file_row],  # slug lookup
                import_rows,  # outgoing imports
                importer_rows,  # incoming imports
                related_rows,  # related_to
                function_rows,  # functions
                decision_rows,  # decisions
            ]
        )
        mock_pool.connection.return_value.__aenter__ = AsyncMock(return_value=mock_conn)
        mock_pool.connection.return_value.__aexit__ = AsyncMock(return_value=False)

        result = await ace_related("core/engine/core/db.py")

    assert "core/engine/core/db.py" in result
    assert "core/engine/core/config.py" in result
    assert "core/engine/mcp/tools.py" in result
    assert "core/engine/core/auth.py" in result
    assert "parse_rows" in result
    assert "Connection pooling" in result
    assert "Imports" in result
    assert "Imported by" in result
    assert "Co-changed" in result


@pytest.mark.asyncio
async def test_ace_related_file_not_found():
    """ace_related() returns a helpful message when the file isn't in the graph."""
    from core.engine.mcp.tools import ace_related

    with patch("core.engine.mcp.tools.pool") as mock_pool:
        mock_conn = AsyncMock()
        mock_conn.query = AsyncMock(side_effect=[[], []])
        mock_pool.connection.return_value.__aenter__ = AsyncMock(return_value=mock_conn)
        mock_pool.connection.return_value.__aexit__ = AsyncMock(return_value=False)

        result = await ace_related("engine/does/not/exist.py")

    assert "not found" in result.lower()
    assert "engine/does/not/exist.py" in result


@pytest.mark.asyncio
async def test_ace_related_isolated_file():
    """ace_related() handles a file with no connections."""
    from core.engine.mcp.tools import ace_related

    file_row = {"id": "graph_file:engine_scratch_py", "path": "engine/scratch.py"}

    with patch("core.engine.mcp.tools.pool") as mock_pool:
        mock_conn = AsyncMock()
        mock_conn.query = AsyncMock(side_effect=[[file_row], [], [], [], [], []])
        mock_pool.connection.return_value.__aenter__ = AsyncMock(return_value=mock_conn)
        mock_pool.connection.return_value.__aexit__ = AsyncMock(return_value=False)

        result = await ace_related("engine/scratch.py")

    assert "engine/scratch.py" in result
    assert "0 connections" in result or "isolated" in result.lower()


# ---------------------------------------------------------------------------
# Server registration
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_mcp_server_has_twenty_two_tools():
    """Server registers expected number of tools."""
    from core.engine.mcp.server import mcp

    tools = await mcp.list_tools()
    assert len(tools) >= 30


@pytest.mark.asyncio
async def test_mcp_server_graph_tool_names():
    """The 3 new graph tool names are registered."""
    from core.engine.mcp.server import mcp

    tools = await mcp.list_tools()
    tool_names = {t.name for t in tools}
    assert "ace_impact" in tool_names
    assert "ace_history" in tool_names
    assert "ace_related" in tool_names
