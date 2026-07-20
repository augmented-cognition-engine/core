# tests/test_mcp_server.py
"""Tests for MCP server setup — tool registration and metadata."""

import pytest


@pytest.mark.asyncio
async def test_mcp_server_has_thirty_tools():
    """Server registers exactly 30 tools (29 + ace_generate_tests)."""
    from core.engine.mcp.server import mcp

    tools = await mcp.list_tools()
    assert len(tools) >= 30


@pytest.mark.asyncio
async def test_loop_and_roadmap_tools_are_registered():
    """The build->ship loop + the canonical roadmap surface must be MCP-REGISTERED, not orphaned in
    tools.py. ace_discover was an unregistered orphan earlier this session, and ace_roadmap is
    correctly registered but was missing from the running (stale) server — this guards the whole
    entry surface so a defined-but-unexposed tool fails CI instead of going silently unreachable."""
    from core.engine.mcp.server import mcp

    names = {t.name for t in await mcp.list_tools()}
    for tool in ("ace_discover", "ace_build", "ace_promote", "ace_roadmap"):
        assert tool in names, f"{tool} is defined but NOT registered on the MCP server"


@pytest.mark.asyncio
async def test_mcp_server_tool_names():
    """All 30 tool names match the spec."""
    from core.engine.mcp.server import mcp

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
        "ace_impact_path",
        "ace_history",
        "ace_related",
        "ace_product_health",
        "ace_gaps",
        "ace_recommend",
        "ace_scan_repo",
        "ace_self_audit",
        "ace_ask_product",
        "ace_create_spec",
        "ace_submit_feedback",
        "ace_verify_spec",
        "ace_capture_decision",
        "ace_list_decisions",
        "ace_pending_gates",
        "ace_approve_gate",
        "ace_reject_gate",
        "ace_context",
        "ace_seam_check",
        "ace_pr_review",
        "ace_generate_tests",
    }
    assert expected.issubset(tool_names), f"Missing tools: {expected - tool_names}"


def test_mcp_server_metadata():
    """Server has correct name."""
    from core.engine.mcp.server import mcp

    assert mcp.name == "ACE Intelligence Engine"


@pytest.mark.asyncio
async def test_mcp_tool_descriptions_not_empty():
    """Every tool has a non-empty description."""
    from core.engine.mcp.server import mcp

    tools = await mcp.list_tools()
    for tool in tools:
        assert tool.description, f"Tool {tool.name} has empty description"
