# tests/test_conductor_rule_actions.py
"""Tests for rule action executors."""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from core.engine.conductor.rule_actions import execute_action


def _make_pool(db=None):
    pool = MagicMock()
    cm = AsyncMock()
    cm.__aenter__ = AsyncMock(return_value=db or AsyncMock())
    cm.__aexit__ = AsyncMock(return_value=None)
    pool.connection.return_value = cm
    return pool


@pytest.mark.asyncio
async def test_transition_action_updates_db():
    db = AsyncMock()
    pool = _make_pool(db)
    ctx = {
        "track": {"id": "capability_lifecycle_track:abc", "state": "gap_identified"},
        "payload": {"product_id": "product:test"},
    }
    action = {"type": "transition", "target_state": "spec_pending"}

    with patch("core.engine.conductor.rule_actions.bus") as mock_bus:
        mock_bus.emit = AsyncMock()
        result = await execute_action(action, ctx, pool)

    assert result["new_state"] == "spec_pending"
    db.query.assert_called_once()


@pytest.mark.asyncio
async def test_notify_action_dispatches():
    pool = _make_pool()
    ctx = {
        "payload": {"product_id": "product:test"},
        "capability": {"slug": "auth"},
        "track": {"dimension": "security"},
    }
    action = {
        "type": "notify",
        "tier": "actionable",
        "category": "test_cat",
        "title_template": "Gap in ${capability.slug}",
    }

    with patch("core.engine.conductor.rule_actions.dispatch", new_callable=AsyncMock) as mock_dispatch:
        await execute_action(action, ctx, pool)
        mock_dispatch.assert_called_once()
        call_kwargs = mock_dispatch.call_args
        assert call_kwargs.kwargs["tier"] == "actionable"


@pytest.mark.asyncio
async def test_emit_event_action():
    pool = _make_pool()
    ctx = {"payload": {"product_id": "product:test"}}
    action = {"type": "emit_event", "event": "conductor.test_event", "payload_merge": {"key": "val"}}

    with patch("core.engine.conductor.rule_actions.bus") as mock_bus:
        mock_bus.emit = AsyncMock()
        await execute_action(action, ctx, pool)
        mock_bus.emit.assert_called_once()
        args = mock_bus.emit.call_args[0]
        assert args[0] == "conductor.test_event"
        assert args[1]["key"] == "val"


@pytest.mark.asyncio
async def test_unknown_action_type_raises():
    pool = _make_pool()
    with pytest.raises(ValueError, match="Unknown action type"):
        await execute_action({"type": "bogus"}, {}, pool)


@pytest.mark.asyncio
async def test_assess_risk_low_emits_gate_cleared():
    pool = _make_pool()
    ctx = {
        "track": {"id": "clt:1", "dimension": "testing", "active_spec_id": "agent_spec:1"},
        "spec": {"estimated_files": ["a.py"]},
        "capability": {"slug": "auth"},
        "payload": {"product_id": "product:test"},
    }
    action = {"type": "assess_risk"}

    with (
        patch(
            "core.engine.conductor.rule_actions.assess_risk",
            return_value={"risk_level": "low", "auto_approve": True, "reason": "ok", "risk_factors": []},
        ),
        patch("core.engine.conductor.rule_actions.bus") as mock_bus,
    ):
        mock_bus.emit = AsyncMock()
        result = await execute_action(action, ctx, pool)
        # Should emit gate_cleared for low risk
        mock_bus.emit.assert_called_once()
        event_name = mock_bus.emit.call_args[0][0]
        assert event_name == "conductor.gate_cleared"


@pytest.mark.asyncio
async def test_assess_risk_high_emits_gate_pending():
    pool = _make_pool()
    ctx = {
        "track": {"id": "clt:1", "dimension": "security", "active_spec_id": "agent_spec:1"},
        "spec": {"estimated_files": ["a.py"] * 15},
        "capability": {"slug": "auth"},
        "payload": {"product_id": "product:test"},
    }
    action = {"type": "assess_risk"}

    with (
        patch(
            "core.engine.conductor.rule_actions.assess_risk",
            return_value={"risk_level": "high", "auto_approve": False, "reason": "risky", "risk_factors": ["15 files"]},
        ),
        patch("core.engine.conductor.rule_actions.bus") as mock_bus,
        patch("core.engine.conductor.rule_actions.dispatch", new_callable=AsyncMock),
    ):
        mock_bus.emit = AsyncMock()
        result = await execute_action(action, ctx, pool)
        # Should emit gate_pending for high risk
        assert any(call[0][0] == "conductor.gate_pending" for call in mock_bus.emit.call_args_list)


@pytest.mark.asyncio
async def test_update_track_whitelists_fields():
    db = AsyncMock()
    pool = _make_pool(db)
    ctx = {"track": {"id": "clt:1"}, "payload": {"product_id": "product:test"}}
    action = {"type": "update_track", "fields": {"metadata": {"foo": "bar"}, "evil_field": "injected"}}

    result = await execute_action(action, ctx, pool)
    assert result["updated"] is True
    # Only whitelisted fields should be in the query
    assert "metadata" in result["fields"]
    assert "evil_field" not in result["fields"]
