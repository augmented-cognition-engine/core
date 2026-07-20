"""Integration test: scheduler honors `trigger` on registered engines."""

from unittest.mock import AsyncMock

import pytest


@pytest.mark.integration
async def test_scheduler_skips_engine_when_trigger_returns_false():
    """When an engine has trigger=False_returning_fn, _execute_engine_inner
    returns 'skipped' status and does NOT call the engine function."""
    from core.engine.sentinel import scheduler as sched

    engine_fn = AsyncMock(return_value={"work": "done"})

    async def _trigger_false(_product_id):
        return False

    entry = {"fn": engine_fn, "cron": "0 6 * * 1", "description": "test", "trigger": _trigger_false}
    fake_db = AsyncMock()
    fake_db.query = AsyncMock(return_value=[])

    s = sched.SentinelScheduler(db_pool=None)
    result = await s._execute_engine_inner("test_engine", entry, "product:platform", fake_db)

    assert result["status"] == "skipped"
    assert result["reason"] == "trigger_returned_false"
    engine_fn.assert_not_called()


@pytest.mark.integration
async def test_scheduler_runs_engine_when_trigger_returns_true():
    """When trigger returns True, the engine fn IS called."""
    from core.engine.sentinel import scheduler as sched

    engine_fn = AsyncMock(return_value={"work": "done"})

    async def _trigger_true(_product_id):
        return True

    entry = {"fn": engine_fn, "cron": "0 6 * * 1", "description": "test", "trigger": _trigger_true}
    fake_db = AsyncMock()
    fake_db.query = AsyncMock(return_value=[{"id": "engine_run:fake"}])

    s = sched.SentinelScheduler(db_pool=None)
    result = await s._execute_engine_inner("test_engine", entry, "product:platform", fake_db)

    engine_fn.assert_called_once_with("product:platform")


@pytest.mark.unit
def test_register_engine_accepts_optional_trigger():
    """register_engine() accepts a trigger= kwarg and stores it in the registry."""
    from core.engine.sentinel.registry import engine_registry, register_engine

    async def _my_trigger(_p):
        return True

    @register_engine(name="test_engine_with_trigger", cron="0 0 * * *", description="test", trigger=_my_trigger)
    async def _run(_p):
        return {}

    try:
        assert engine_registry["test_engine_with_trigger"]["trigger"] is _my_trigger
    finally:
        engine_registry.pop("test_engine_with_trigger", None)


@pytest.mark.unit
def test_register_engine_default_trigger_is_none():
    """Engines registered without trigger= have trigger=None (backward compat)."""
    from core.engine.sentinel.registry import engine_registry, register_engine

    @register_engine(name="test_engine_no_trigger", cron="0 0 * * *", description="test")
    async def _run(_p):
        return {}

    try:
        assert engine_registry["test_engine_no_trigger"]["trigger"] is None
    finally:
        engine_registry.pop("test_engine_no_trigger", None)
