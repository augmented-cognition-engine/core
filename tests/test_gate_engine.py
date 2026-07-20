"""Tests for the GateEngine — gate evaluation, approval, rejection."""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from core.engine.pm.gate_engine import GateEngine


@pytest.fixture
def gate_engine():
    mock_pool = AsyncMock()
    return GateEngine(mock_pool)


# --- Evaluate ---


@pytest.mark.asyncio
async def test_evaluate_low_risk_auto_approves(gate_engine):
    """Low-risk idea gate should auto-approve."""
    with patch.object(gate_engine, "_load_entity_context", new_callable=AsyncMock) as mock_ctx:
        mock_ctx.return_value = {
            "entity": {"id": "idea:1", "status": "ready", "classification": {"complexity": "simple"}},
            "complexity": "simple",
            "disciplines": ["testing"],
            "file_count": 1,
        }
        result = await gate_engine.evaluate_gate("idea", "idea:1", "ready", "speccing", "product:test")

    assert result["auto_approve"] is True
    assert result["risk_level"] == "low"


@pytest.mark.asyncio
async def test_evaluate_high_risk_needs_human(gate_engine):
    """High-risk gate should not auto-approve."""
    with patch.object(gate_engine, "_load_entity_context", new_callable=AsyncMock) as mock_ctx:
        mock_ctx.return_value = {
            "entity": {"id": "idea:1", "status": "spec_review"},
            "complexity": "complex",
            "disciplines": ["security", "architecture"],
            "file_count": 20,
        }
        result = await gate_engine.evaluate_gate("idea", "idea:1", "spec_review", "planned", "product:test")

    assert result["auto_approve"] is False
    assert result["risk_level"] == "high"


# --- Approve ---


@pytest.mark.asyncio
async def test_approve_creates_decision(gate_engine):
    """Approving a gate creates a decision record and transitions the entity."""
    with (
        patch.object(gate_engine, "_transition_entity", new_callable=AsyncMock) as mock_trans,
        patch("core.engine.pm.gate_engine.create_decision", new_callable=AsyncMock) as mock_decision,
        patch("core.engine.pm.gate_engine.bus") as mock_bus,
    ):
        mock_bus.emit = AsyncMock()
        mock_decision.return_value = {"id": "decision:1", "title": "Spec approved"}
        mock_trans.return_value = {"id": "idea:1", "status": "planned"}

        result = await gate_engine.approve_gate(
            "idea",
            "idea:1",
            "spec_review",
            "Looks good",
            "product:test",
            "user:1",
        )

    assert result["decision"]["id"] == "decision:1"
    assert result["entity"]["status"] == "planned"
    mock_decision.assert_called_once()
    mock_bus.emit.assert_called()


# --- Reject ---


@pytest.mark.asyncio
async def test_reject_creates_rejection_decision(gate_engine):
    """Rejecting a gate creates a rejection decision and transitions entity back."""
    with (
        patch.object(gate_engine, "_transition_entity", new_callable=AsyncMock) as mock_trans,
        patch("core.engine.pm.gate_engine.create_decision", new_callable=AsyncMock) as mock_decision,
        patch("core.engine.pm.gate_engine.bus") as mock_bus,
    ):
        mock_bus.emit = AsyncMock()
        mock_decision.return_value = {"id": "decision:2", "decision_type": "rejection"}
        mock_trans.return_value = {"id": "idea:1", "status": "ready"}

        result = await gate_engine.reject_gate(
            "idea",
            "idea:1",
            "spec_review",
            "Needs more detail",
            "product:test",
            "user:1",
        )

    assert result["decision"]["id"] == "decision:2"
    assert result["entity"]["status"] == "ready"
    # Rejection decision should have rejection type
    call_kwargs = mock_decision.call_args
    assert call_kwargs[1]["decision_type"] == "rejection" or call_kwargs.kwargs.get("decision_type") == "rejection"


# --- Pending ---


@pytest.mark.asyncio
async def test_list_pending_gates(gate_engine):
    """List pending gates queries ideas and initiatives in review states."""
    with patch.object(gate_engine, "_load_entity_context", new_callable=AsyncMock) as mock_ctx:
        mock_ctx.return_value = {"complexity": "simple", "disciplines": [], "file_count": 0}

        mock_db = AsyncMock()
        mock_db.query = AsyncMock(
            side_effect=[
                [{"id": "idea:1", "status": "spec_review", "title": "Webhooks"}],
                [],  # idea plan_review
                [{"id": "initiative:2", "status": "review", "title": "Auth rewrite"}],
                [],  # milestone review
                [],  # work_item review
            ]
        )
        mock_pool = MagicMock()
        mock_pool.connection.return_value.__aenter__ = AsyncMock(return_value=mock_db)
        mock_pool.connection.return_value.__aexit__ = AsyncMock(return_value=False)
        gate_engine._pool = mock_pool

        result = await gate_engine.list_pending("product:test")

    assert len(result) == 2
    assert result[0]["entity_type"] == "idea"
    assert result[0]["risk_level"] in ("low", "medium", "high")
    assert result[1]["entity_type"] == "initiative"
