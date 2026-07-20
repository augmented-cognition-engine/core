"""Tests for the ace_explain_run MCP tool — 'why did ACE conclude this?' (trace reachability)."""

from unittest.mock import AsyncMock, patch

import pytest


def _events():
    return [
        {
            "seq": 0,
            "event_type": "run_started",
            "payload": {"thought": "Should we ship?", "depth": 3, "discipline": "strategy"},
        },
        {
            "seq": 1,
            "event_type": "phase",
            "payload": {"cognitive_function": "frame", "output": "framed it", "confidence": 0.8},
        },
        {
            "seq": 2,
            "event_type": "phase",
            "payload": {"cognitive_function": "conclude", "output": "ship it", "confidence": 0.7},
        },
        {
            "seq": 3,
            "event_type": "run_complete",
            "payload": {"conclusion": "Ship the curated marketplace.", "status": "complete"},
        },
    ]


@pytest.mark.asyncio
async def test_ace_explain_run_replays_a_run():
    from core.engine.mcp.tools import ace_explain_run

    with patch("core.engine.cognition.run_ledger.get_run_events", AsyncMock(return_value=_events())):
        out = await ace_explain_run("reasoning_run:abc")
    assert out["available"] is True
    assert out["thought"] == "Should we ship?"
    assert len(out["phases"]) == 2  # frame, conclude
    assert out["phases"][0]["function"] == "frame"
    assert out["phases"][0]["confidence"] == 0.8
    assert out["conclusion"] == "Ship the curated marketplace."


@pytest.mark.asyncio
async def test_ace_explain_run_defaults_to_most_recent():
    from core.engine.mcp.tools import ace_explain_run

    with (
        patch(
            "core.engine.cognition.run_ledger.get_recent_runs", AsyncMock(return_value=[{"id": "reasoning_run:latest"}])
        ),
        patch("core.engine.cognition.run_ledger.get_run_events", AsyncMock(return_value=_events())) as ge,
    ):
        out = await ace_explain_run()  # no run_id → explain the most recent run
    assert out["available"] is True
    assert out["run_id"] == "reasoning_run:latest"
    ge.assert_awaited_once_with("reasoning_run:latest")


@pytest.mark.asyncio
async def test_ace_explain_run_unavailable_when_no_runs():
    from core.engine.mcp.tools import ace_explain_run

    with patch("core.engine.cognition.run_ledger.get_recent_runs", AsyncMock(return_value=[])):
        out = await ace_explain_run()
    assert out["available"] is False


@pytest.mark.asyncio
async def test_ace_explain_run_is_registered_on_server():
    """Reachability guard — the tool must be discoverable via the MCP server."""
    from core.engine.mcp import server

    tools = await server.mcp.list_tools()
    names = {getattr(t, "name", None) for t in tools}
    assert "ace_explain_run" in names
