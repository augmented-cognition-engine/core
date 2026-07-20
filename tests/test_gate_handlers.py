"""Tests for gate event handlers."""

from unittest.mock import AsyncMock, patch

import pytest

from core.engine.events.gate_handlers import on_gate_approved, on_gate_pending


@pytest.mark.asyncio
async def test_on_gate_pending_dispatches_notification():
    payload = {
        "entity_type": "idea",
        "entity_id": "idea:1",
        "gate_state": "spec_review",
        "product_id": "product:test",
    }
    with patch("core.engine.events.gate_handlers.dispatch", new_callable=AsyncMock) as mock_dispatch:
        await on_gate_pending("gate.pending", payload)
        mock_dispatch.assert_called_once()
        call_kwargs = mock_dispatch.call_args
        assert call_kwargs.kwargs["tier"] == "actionable"
        assert "spec_review" in call_kwargs.kwargs["title"].lower() or "review" in call_kwargs.kwargs["title"].lower()


@pytest.mark.asyncio
async def test_on_gate_approved_dispatches_notification():
    payload = {
        "entity_type": "idea",
        "entity_id": "idea:1",
        "gate_state": "spec_review",
        "decision_id": "decision:1",
        "product_id": "product:test",
    }
    with patch("core.engine.events.gate_handlers.dispatch", new_callable=AsyncMock) as mock_dispatch:
        await on_gate_approved("gate.approved", payload)
        mock_dispatch.assert_called_once()
        call_kwargs = mock_dispatch.call_args
        assert call_kwargs.kwargs["tier"] == "informational"
