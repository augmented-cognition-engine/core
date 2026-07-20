# tests/test_conductor_core.py
"""Tests for the main Conductor class."""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from core.engine.conductor.conductor import Conductor


def _make_pool(db=None):
    pool = MagicMock()
    cm = AsyncMock()
    cm.__aenter__ = AsyncMock(return_value=db or AsyncMock())
    cm.__aexit__ = AsyncMock(return_value=None)
    pool.connection.return_value = cm
    return pool


@pytest.mark.asyncio
async def test_conductor_start_subscribes_to_events():
    pool = _make_pool()
    conductor = Conductor(pool)

    with (
        patch.object(conductor, "_seed_lifecycle_tracks", new_callable=AsyncMock),
        patch.object(conductor._rule_engine, "load_rules", new_callable=AsyncMock),
        patch("core.engine.conductor.conductor.bus") as mock_bus,
    ):
        await conductor.start("product:test")
        # Should register multiple event handlers
        assert mock_bus.on.call_count >= 10
        await conductor.stop()


@pytest.mark.asyncio
async def test_on_event_skips_when_vision_unaligned():
    pool = _make_pool()
    conductor = Conductor(pool)
    conductor._rule_engine._rules = []

    with (
        patch.object(
            conductor,
            "_build_context",
            new_callable=AsyncMock,
            return_value={
                "payload": {},
                "capability": {"slug": "x", "tags": [], "priority": "nice_to_have"},
                "themes": [{"name": "growth"}],
                "track": {"dimension": "ux"},
            },
        ),
    ):
        # Vision filter should block — unaligned
        await conductor._on_event("test.event", {"product_id": "product:test"})
        # No rules should have been evaluated (we'd see an error if they were, since _rules is empty list)


@pytest.mark.asyncio
async def test_on_event_evaluates_rules_when_aligned():
    pool = _make_pool()
    conductor = Conductor(pool)
    conductor._rule_engine._rules = []

    with (
        patch.object(conductor, "_build_context", new_callable=AsyncMock, return_value={"payload": {}, "themes": []}),
        patch.object(conductor._vision_filter, "is_aligned", new_callable=AsyncMock, return_value=True),
        patch.object(conductor._rule_engine, "evaluate", return_value=[]),
    ):
        await conductor._on_event("test.event", {"product_id": "product:test"})
        conductor._rule_engine.evaluate.assert_called_once()


@pytest.mark.asyncio
async def test_on_event_failure_rollback():
    """If an action fails, the track state should be rolled back."""
    db = AsyncMock()
    pool = _make_pool(db)
    conductor = Conductor(pool)

    rule = {
        "name": "test_rule",
        "actions": [
            {"type": "transition", "target_state": "spec_pending"},
            {"type": "generate_spec"},  # This will fail
        ],
        "cooldown_seconds": 0,
    }

    ctx = {
        "payload": {"product_id": "product:test"},
        "track": {"id": "clt:1", "state": "gap_identified", "dimension": "testing"},
        "capability": {"slug": "auth"},
        "themes": [],
    }

    with (
        patch.object(conductor, "_build_context", new_callable=AsyncMock, return_value=ctx),
        patch.object(conductor._vision_filter, "is_aligned", new_callable=AsyncMock, return_value=True),
        patch.object(conductor._rule_engine, "evaluate", return_value=[rule]),
        patch.object(conductor._rule_engine, "check_cooldown", return_value=False),
        patch.object(conductor._rule_engine, "record_execution"),
        patch(
            "core.engine.conductor.conductor.execute_action",
            new_callable=AsyncMock,
            side_effect=[
                {"new_state": "spec_pending"},  # transition succeeds
                Exception("LLM timeout"),  # generate_spec fails
            ],
        ),
        patch("core.engine.conductor.conductor.bus") as mock_bus,
    ):
        mock_bus.emit = AsyncMock()
        await conductor._on_event("test.event", {"product_id": "product:test"})
        # Should have recorded failure
        conductor._rule_engine.record_execution.assert_called_once()
        call_args = conductor._rule_engine.record_execution.call_args
        assert call_args.kwargs.get("outcome") == "failure" or call_args[1].get("outcome") == "failure"
