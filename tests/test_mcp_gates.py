"""Tests for MCP gate tools."""

from unittest.mock import AsyncMock, patch

import pytest

from core.engine.mcp.tools import ace_approve_gate, ace_pending_gates, ace_reject_gate


@pytest.mark.asyncio
async def test_ace_pending_gates():
    with patch("core.engine.mcp.tools.GateEngine") as MockGE:
        mock_ge = AsyncMock()
        MockGE.return_value = mock_ge
        mock_ge.list_pending = AsyncMock(
            return_value=[
                {"entity_type": "idea", "entity_id": "idea:1", "gate_state": "spec_review"},
            ]
        )

        result = await ace_pending_gates()
        assert result["count"] == 1
        assert result["gates"][0]["entity_type"] == "idea"


@pytest.mark.asyncio
async def test_ace_approve_gate():
    with patch("core.engine.mcp.tools.GateEngine") as MockGE:
        mock_ge = AsyncMock()
        MockGE.return_value = mock_ge
        mock_ge.approve_gate = AsyncMock(
            return_value={
                "decision": {"id": "decision:1"},
                "entity": {"id": "idea:1", "status": "planned"},
            }
        )

        result = await ace_approve_gate("idea", "idea:1", "Looks good")
        assert result["decision"]["id"] == "decision:1"


@pytest.mark.asyncio
async def test_ace_reject_gate():
    with patch("core.engine.mcp.tools.GateEngine") as MockGE:
        mock_ge = AsyncMock()
        MockGE.return_value = mock_ge
        mock_ge.reject_gate = AsyncMock(
            return_value={
                "decision": {"id": "decision:2"},
                "entity": {"id": "idea:1", "status": "ready"},
            }
        )

        result = await ace_reject_gate("idea", "idea:1", "Needs more detail")
        assert result["decision"]["id"] == "decision:2"
