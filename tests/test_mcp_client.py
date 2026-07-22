# tests/test_mcp_client.py
"""Tests for the ``ace_mcp_client`` standalone MCP thin client.

The thin client lives at the top-level ``ace_mcp_client/`` package (extracted
from ``core/mcp/``, retiring the ``mcp``-SDK shadow footgun). This file merges
the former ``tests/test_ace_mcp_client_spec.py`` spec tests — written against
the standalone package name and skipped until the extraction — with the live
coverage that previously imported ``core.mcp.*``.
"""

from __future__ import annotations

import inspect
import json
from pathlib import Path
from unittest.mock import AsyncMock

import httpx
import pytest

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _mock_response(data: dict, status_code: int = 200) -> httpx.Response:
    """Build a fake httpx.Response."""
    return httpx.Response(
        status_code=status_code,
        json=data,
        request=httpx.Request("GET", "http://test"),
    )


# ---------------------------------------------------------------------------
# 1. token resolution chain
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_client_resolves_token_from_env(monkeypatch):
    """ACE_TOKEN env var is picked up."""
    monkeypatch.setenv("ACE_TOKEN", "tok-from-env")
    from ace_mcp_client.client import AceClient

    c = AceClient()
    token = await c._resolve_token()
    assert token == "tok-from-env"
    await c.close()


@pytest.mark.asyncio
async def test_client_explicit_token_wins(monkeypatch):
    """Explicit token parameter takes priority over env."""
    monkeypatch.setenv("ACE_TOKEN", "env-token")
    from ace_mcp_client.client import AceClient

    c = AceClient(token="explicit-token")
    token = await c._resolve_token()
    assert token == "explicit-token"
    await c.close()


@pytest.mark.asyncio
async def test_client_base_url_from_env(monkeypatch):
    """ACE_URL env var sets base URL."""
    monkeypatch.setenv("ACE_URL", "http://custom:9999")
    from ace_mcp_client.client import AceClient

    c = AceClient()
    assert c.base_url == "http://custom:9999"
    await c.close()


@pytest.mark.asyncio
async def test_client_resolves_token_from_file(monkeypatch, tmp_path):
    """Token from ~/.ace/token.json."""
    monkeypatch.delenv("ACE_TOKEN", raising=False)
    monkeypatch.delenv("ACE_API_KEY", raising=False)

    token_file = tmp_path / "token.json"
    token_file.write_text(json.dumps({"token": "tok-from-file"}))

    import ace_mcp_client.client as client_mod

    monkeypatch.setattr(client_mod, "_TOKEN_FILE", token_file)

    c = client_mod.AceClient()
    token = await c._resolve_token()
    assert token == "tok-from-file"
    await c.close()


@pytest.mark.asyncio
async def test_client_resolves_token_via_api_key(monkeypatch):
    """ACE_API_KEY triggers POST /auth/token exchange."""
    monkeypatch.delenv("ACE_TOKEN", raising=False)
    monkeypatch.setenv("ACE_API_KEY", "my-api-key")

    import ace_mcp_client.client as client_mod

    # Point token file to nonexistent path so it's skipped
    monkeypatch.setattr(client_mod, "_TOKEN_FILE", Path("/nonexistent/token.json"))

    c = client_mod.AceClient()

    mock_client = AsyncMock(spec=httpx.AsyncClient)
    mock_client.post = AsyncMock(return_value=_mock_response({"token": "tok-from-exchange"}))
    c._client = mock_client

    token = await c._resolve_token()
    assert token == "tok-from-exchange"
    mock_client.post.assert_called_once_with(
        "/auth/token",
        json={"api_key": "my-api-key"},
    )


# ---------------------------------------------------------------------------
# 2. test_all_tools_callable — all 11 are async functions
# ---------------------------------------------------------------------------


def test_all_tools_are_async_functions():
    """All 11 tool functions exist and are async."""
    from ace_mcp_client.tools import (
        ace_briefing,
        ace_capture,
        ace_capture_idea,
        ace_history,
        ace_impact,
        ace_load,
        ace_related,
        ace_search,
        ace_start,
        ace_status,
        ace_task,
    )

    tools = [
        ace_start,
        ace_load,
        ace_capture,
        ace_task,
        ace_status,
        ace_capture_idea,
        ace_search,
        ace_briefing,
        ace_impact,
        ace_history,
        ace_related,
    ]
    assert len(tools) == 11
    for tool in tools:
        assert callable(tool), f"{tool.__name__} is not callable"
        assert inspect.iscoroutinefunction(tool), f"{tool.__name__} is not async"


# ---------------------------------------------------------------------------
# 3. server registration
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_server_registers_eleven_tools():
    """Thin client server registers exactly 11 tools."""
    from ace_mcp_client.server import mcp

    tools = await mcp.list_tools()
    assert len(tools) == 11


@pytest.mark.asyncio
async def test_server_tool_names():
    """The wire names match the documented thin public contract."""
    from ace_mcp_client.server import mcp

    tools = await mcp.list_tools()
    tool_names = {t.name for t in tools}
    expected = {
        "ace_start",
        "ace_load",
        "ace_capture",
        "ace_task",
        "ace_status",
        "ace_capture_idea",
        "ace_search",
        "ace_briefing",
        "ace_impact",
        "ace_history",
        "ace_related",
    }
    assert tool_names == expected


# ---------------------------------------------------------------------------
# 4. tool behavior — mocked client, verify API calls
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_ace_start_calls_health_and_attention():
    """ace_start makes GET /health, GET /portal/attention, and GET /briefings/latest."""
    import ace_mcp_client.tools as tools_mod

    mock_client = AsyncMock()
    mock_client.get = AsyncMock(
        side_effect=[
            {"status": "ok", "version": "0.2.0"},  # /health
            {"items": [{"type": "conflict", "title": "test"}]},  # /portal/attention
            {"content": "Morning briefing", "created_at": "2026-03-26"},  # /briefings/latest
        ]
    )

    old_client = tools_mod._client
    tools_mod._client = mock_client
    try:
        result = await tools_mod.ace_start()
        assert result["status"] == "ok"
        assert result["briefing_available"] is True
        assert mock_client.get.call_count == 3
    finally:
        tools_mod._client = old_client


@pytest.mark.asyncio
async def test_ace_impact_calls_graph_api():
    """ace_impact calls GET /graph/impact/{node_id}."""
    import ace_mcp_client.tools as tools_mod

    mock_client = AsyncMock()
    mock_client.get = AsyncMock(
        return_value={
            "nodes": [{"id": "graph_file:foo_py", "path": "foo.py", "_type": "graph_file"}],
            "edges": [{"from": "graph_file:bar_py", "to": "graph_file:foo_py", "type": "imports"}],
            "start_node": {"id": "graph_file:engine_core_db_py", "path": "engine/core/db.py"},
            "stats": {"node_count": 1, "edge_count": 1, "depth_reached": 2},
        }
    )

    old_client = tools_mod._client
    tools_mod._client = mock_client
    try:
        result = await tools_mod.ace_impact("engine/core/db.py")
        assert "Impact Analysis" in result
        assert "engine/core/db.py" in result
        mock_client.get.assert_called_once_with(
            "/graph/impact/graph_file:engine_core_db_py",
            params={"graph_id": "default"},
        )
    finally:
        tools_mod._client = old_client


@pytest.mark.asyncio
async def test_ace_capture_posts_observation():
    """ace_capture sends POST /observations with correct body."""
    import ace_mcp_client.tools as tools_mod

    mock_client = AsyncMock()
    mock_client.post = AsyncMock(return_value={"status": "captured", "id": "observation:abc"})

    old_client = tools_mod._client
    tools_mod._client = mock_client
    try:
        result = await tools_mod.ace_capture(
            observation_type="decision",
            content="Chose FastAPI over Flask",
            domain_path="architecture.web",
            confidence=0.9,
        )
        assert result["status"] == "captured"
        mock_client.post.assert_called_once_with(
            "/observations",
            json={
                "observation_type": "decision",
                "content": "Chose FastAPI over Flask",
                "domain_path": "architecture.web",
                "confidence": 0.9,
                "source_surface": "thin_mcp",
            },
        )
    finally:
        tools_mod._client = old_client


@pytest.mark.asyncio
async def test_ace_load_calls_intel_context():
    """ace_load calls GET /intel/context with topic and org."""
    import ace_mcp_client.tools as tools_mod

    mock_client = AsyncMock()
    mock_client.get = AsyncMock(
        return_value={
            "domain_path": "python.testing",
            "insights": [{"content": "Use pytest"}],
            "corrections": [],
            "preferences": [{"content": "Prefer fixtures"}],
            "framework_recommendation": None,
            "total_count": 2,
        }
    )

    old_client = tools_mod._client
    tools_mod._client = mock_client
    try:
        result = await tools_mod.ace_load("python testing")
        assert result["domain_path"] == "python.testing"
        assert len(result["insights"]) == 1
        mock_client.get.assert_called_once_with(
            "/intel/context",
            params={"q": "python testing", "product": "product:default"},
        )
    finally:
        tools_mod._client = old_client


@pytest.mark.asyncio
async def test_ace_search_calls_intel_search():
    """ace_search calls GET /intel/search."""
    import ace_mcp_client.tools as tools_mod

    mock_client = AsyncMock()
    mock_client.get = AsyncMock(
        return_value={
            "query": "fastapi",
            "results": [
                {"content": "Use FastAPI", "insight_type": "preference"},
                {"content": "Fast routing", "insight_type": "insight"},
            ],
            "count": 2,
        }
    )

    old_client = tools_mod._client
    tools_mod._client = mock_client
    try:
        # Without filter
        result = await tools_mod.ace_search("fastapi")
        assert result["count"] == 2

        # With filter
        mock_client.get.reset_mock()
        mock_client.get = AsyncMock(
            return_value={
                "query": "fastapi",
                "results": [
                    {"content": "Use FastAPI", "insight_type": "preference"},
                    {"content": "Fast routing", "insight_type": "insight"},
                ],
                "count": 2,
            }
        )
        result = await tools_mod.ace_search("fastapi", knowledge_type="preference")
        assert result["count"] == 1
        assert result["results"][0]["insight_type"] == "preference"
    finally:
        tools_mod._client = old_client


@pytest.mark.asyncio
async def test_ace_task_posts_to_tasks():
    """ace_task sends POST /tasks."""
    import ace_mcp_client.tools as tools_mod

    mock_client = AsyncMock()
    mock_client.submit_task = AsyncMock(
        return_value={
            "id": "task:123",
            "domain_path": "code.review",
            "output": "Here is your review...",
            "status": "completed",
        }
    )

    old_client = tools_mod._client
    tools_mod._client = mock_client
    try:
        result = await tools_mod.ace_task("Review this PR")
        assert result["id"] == "task:123"
        mock_client.submit_task.assert_called_once_with(
            {"description": "Review this PR", "workspace_id": "workspace:default"},
        )
    finally:
        tools_mod._client = old_client


@pytest.mark.asyncio
async def test_ace_task_passes_structured_decision_without_parsing_prose():
    import ace_mcp_client.tools as tools_mod

    mock_client = AsyncMock()
    mock_client.submit_task = AsyncMock(return_value={"id": "task:123", "status": "pending"})
    decision = {
        "selected_option": "Keep eleven tools",
        "scope": "public MCP contract",
        "assumptions": ["compatibility is required"],
        "alternatives": ["add a tool"],
        "reconsideration_conditions": ["a compatible extension is impossible"],
    }
    old_client = tools_mod._client
    tools_mod._client = mock_client
    try:
        await tools_mod.ace_task("Make a decision", decision=decision)
        mock_client.submit_task.assert_awaited_once_with(
            {
                "description": "Make a decision",
                "workspace_id": "workspace:default",
                "decision": decision,
            }
        )
    finally:
        tools_mod._client = old_client


@pytest.mark.asyncio
async def test_ace_capture_passes_linked_correction_fields():
    import ace_mcp_client.tools as tools_mod

    mock_client = AsyncMock()
    mock_client.post = AsyncMock(return_value={"status": "captured", "id": "observation:c1"})
    old_client = tools_mod._client
    tools_mod._client = mock_client
    try:
        await tools_mod.ace_capture(
            observation_type="correction",
            content="Use option B",
            domain_path="product.decisions",
            affected_decision_id="decision:one",
            affected_task_id="task:one",
            expires_at="2026-08-01T00:00:00Z",
        )
        body = mock_client.post.await_args.kwargs["json"]
        assert body["source_surface"] == "thin_mcp"
        assert body["affected_decision_id"] == "decision:one"
        assert body["affected_task_id"] == "task:one"
        assert body["lifecycle_state"] == "active"
        assert body["expires_at"] == "2026-08-01T00:00:00Z"
    finally:
        tools_mod._client = old_client


@pytest.mark.asyncio
async def test_ace_capture_idea_posts_to_ideas():
    """ace_capture_idea sends POST /ideas."""
    import ace_mcp_client.tools as tools_mod

    mock_client = AsyncMock()
    mock_client.post = AsyncMock(return_value={"id": "idea:abc", "status": "captured"})

    old_client = tools_mod._client
    tools_mod._client = mock_client
    try:
        result = await tools_mod.ace_capture_idea("What if we add dark mode?", context="User requested it")
        mock_client.post.assert_called_once_with(
            "/ideas",
            json={"raw_input": "What if we add dark mode?\n\nContext: User requested it"},
        )
        assert result["status"] == "captured"
    finally:
        tools_mod._client = old_client


@pytest.mark.asyncio
async def test_ace_history_calls_graph_api():
    """ace_history calls GET /graph/history/{node_id}."""
    import ace_mcp_client.tools as tools_mod

    mock_client = AsyncMock()
    mock_client.get = AsyncMock(
        return_value={
            "nodes": [],
            "edges": [],
            "start_node": {"id": "graph_file:main_py", "path": "main.py"},
            "stats": {"node_count": 0, "edge_count": 0, "depth_reached": 0},
        }
    )

    old_client = tools_mod._client
    tools_mod._client = mock_client
    try:
        result = await tools_mod.ace_history("main.py")
        assert "Decision History" in result
        mock_client.get.assert_called_once_with(
            "/graph/history/graph_file:main_py",
            params={"graph_id": "default"},
        )
    finally:
        tools_mod._client = old_client


@pytest.mark.asyncio
async def test_ace_related_calls_graph_api():
    """ace_related calls GET /graph/related/{node_id}."""
    import ace_mcp_client.tools as tools_mod

    mock_client = AsyncMock()
    mock_client.get = AsyncMock(
        return_value={
            "nodes": [{"id": "graph_file:utils_py", "path": "utils.py", "_type": "graph_file"}],
            "edges": [{"from": "graph_file:main_py", "to": "graph_file:utils_py", "type": "imports"}],
            "start_node": {"id": "graph_file:main_py", "path": "main.py"},
            "stats": {"node_count": 1, "edge_count": 1, "depth_reached": 1},
        }
    )

    old_client = tools_mod._client
    tools_mod._client = mock_client
    try:
        result = await tools_mod.ace_related("main.py")
        assert "Connected Graph" in result
        mock_client.get.assert_called_once_with(
            "/graph/related/graph_file:main_py",
            params={"graph_id": "default"},
        )
    finally:
        tools_mod._client = old_client


# ---------------------------------------------------------------------------
# 5. formatting helpers
# ---------------------------------------------------------------------------


def test_slugify_path():
    """_slugify_path converts file paths to SurrealDB slugs."""
    from ace_mcp_client.tools import _slugify_path

    assert _slugify_path("engine/core/db.py") == "engine_core_db_py"
    assert _slugify_path("main.py") == "main_py"
    assert _slugify_path("src/utils/helpers.ts") == "src_utils_helpers_ts"
    assert _slugify_path("README.md") == "readme_md"


def test_format_traverse_no_start_node():
    """When start_node is None, returns 'not found' message."""
    from ace_mcp_client.tools import _format_traverse_result

    result = _format_traverse_result(
        {"nodes": [], "edges": [], "start_node": None, "stats": {}},
        "nonexistent.py",
        "Impact Analysis",
    )
    assert "not found in graph" in result
    assert "nonexistent.py" in result


# ---------------------------------------------------------------------------
# 6. test_zero_engine_imports — the critical check
# ---------------------------------------------------------------------------


def test_zero_engine_imports():
    """The thin client package must have ZERO imports from engine/."""
    import ast

    package_dir = Path(__file__).parent.parent / "ace_mcp_client"
    assert package_dir.exists(), f"Package dir not found: {package_dir}"

    for py_file in package_dir.glob("*.py"):
        source = py_file.read_text()
        tree = ast.parse(source)
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                for alias in node.names:
                    assert not alias.name.startswith("engine"), f"{py_file.name} imports '{alias.name}' from engine"
            elif isinstance(node, ast.ImportFrom):
                if node.module and node.module.startswith("engine"):
                    raise AssertionError(f"{py_file.name} imports from '{node.module}'")
