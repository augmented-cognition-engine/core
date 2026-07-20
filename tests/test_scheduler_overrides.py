# tests/test_scheduler_overrides.py
"""Tests for SentinelScheduler override loading, reschedule, disable, enable."""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_scheduler():
    """Return a SentinelScheduler with a mocked DB pool."""
    from core.engine.sentinel.scheduler import SentinelScheduler

    mock_pool = MagicMock()
    return SentinelScheduler(db_pool=mock_pool, default_org_id="product:default")


def _mock_db_with_rows(rows):
    """Return a mock db context manager that returns the given raw query result."""
    mock_db = AsyncMock()
    mock_db.query = AsyncMock(return_value=[rows])
    mock_pool = MagicMock()
    mock_pool.connection = MagicMock(
        return_value=AsyncMock(
            __aenter__=AsyncMock(return_value=mock_db),
            __aexit__=AsyncMock(return_value=False),
        )
    )
    return mock_pool


# ---------------------------------------------------------------------------
# load_overrides
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_load_overrides_returns_dict():
    """load_overrides parses DB rows into {engine: {cron, enabled}}."""
    sched = _make_scheduler()

    db_rows = [
        {"engine": "decay_manager", "cron": "0 4 * * *", "enabled": True},
        {"engine": "gap_analyzer", "cron": None, "enabled": False},
    ]
    sched._db_pool = _mock_db_with_rows(db_rows)

    result = await sched.load_overrides("product:default")

    assert result == {
        "decay_manager": {"cron": "0 4 * * *", "enabled": True},
        "gap_analyzer": {"cron": None, "enabled": False},
    }


@pytest.mark.asyncio
async def test_load_overrides_empty_returns_empty_dict():
    """load_overrides returns {} when no rows exist."""
    sched = _make_scheduler()
    sched._db_pool = _mock_db_with_rows([])

    result = await sched.load_overrides("product:default")

    assert result == {}


@pytest.mark.asyncio
async def test_load_overrides_db_error_returns_empty_dict():
    """load_overrides returns {} gracefully when DB query raises."""
    sched = _make_scheduler()

    mock_db = AsyncMock()
    mock_db.query = AsyncMock(side_effect=RuntimeError("DB unavailable"))
    mock_pool = MagicMock()
    mock_pool.connection = MagicMock(
        return_value=AsyncMock(
            __aenter__=AsyncMock(return_value=mock_db),
            __aexit__=AsyncMock(return_value=False),
        )
    )
    sched._db_pool = mock_pool

    result = await sched.load_overrides("product:default")

    assert result == {}


# ---------------------------------------------------------------------------
# start with overrides
# ---------------------------------------------------------------------------


def test_start_with_override_cron_uses_override():
    """start() uses override cron instead of registry default when provided."""
    from core.engine.sentinel.registry import engine_registry, register_engine

    engine_registry.clear()

    @register_engine(name="test_override_cron", cron="0 2 * * *", description="Test")
    async def run(product_id: str) -> dict:
        return {}

    sched = _make_scheduler()

    mock_apscheduler = MagicMock()
    with patch("core.engine.sentinel.scheduler.AsyncIOScheduler", return_value=mock_apscheduler):
        sched.start(overrides={"test_override_cron": {"cron": "0 4 * * *", "enabled": True}})

    # The job was added — extract the trigger arg
    add_job_calls = mock_apscheduler.add_job.call_args_list
    assert len(add_job_calls) == 1
    trigger_arg = add_job_calls[0][1]["trigger"]
    # CronTrigger built from "0 4 * * *" should have hour=4
    # APScheduler 3.x fields: year(0) month(1) day(2) week(3) day_of_week(4) hour(5) minute(6) second(7)
    hour_field = next(f for f in trigger_arg.fields if f.name == "hour")
    assert str(hour_field) == "4"


def test_start_with_disabled_override_skips_engine():
    """start() skips an engine when its override has enabled=False."""
    from core.engine.sentinel.registry import engine_registry, register_engine

    engine_registry.clear()

    @register_engine(name="test_disabled_eng", cron="0 2 * * *", description="Test")
    async def run(product_id: str) -> dict:
        return {}

    sched = _make_scheduler()

    mock_apscheduler = MagicMock()
    with patch("core.engine.sentinel.scheduler.AsyncIOScheduler", return_value=mock_apscheduler):
        sched.start(overrides={"test_disabled_eng": {"cron": None, "enabled": False}})

    # No job should have been added
    mock_apscheduler.add_job.assert_not_called()


# ---------------------------------------------------------------------------
# reschedule_engine
# ---------------------------------------------------------------------------


def test_reschedule_engine_changes_job():
    """reschedule_engine removes old job and adds new one with updated cron."""
    from core.engine.sentinel.registry import engine_registry, register_engine

    engine_registry.clear()

    @register_engine(name="test_reschedule", cron="0 2 * * *", description="Test")
    async def run(product_id: str) -> dict:
        return {}

    sched = _make_scheduler()
    mock_apscheduler = MagicMock()
    mock_apscheduler.get_job = MagicMock(return_value=MagicMock())  # job exists

    with patch("core.engine.sentinel.scheduler.AsyncIOScheduler", return_value=mock_apscheduler):
        sched.start(overrides={})

    sched.reschedule_engine("test_reschedule", "30 4 * * *")

    mock_apscheduler.remove_job.assert_called_once_with("sentinel_test_reschedule")
    assert mock_apscheduler.add_job.call_count == 2  # once in start, once in reschedule


def test_reschedule_engine_adds_fresh_when_job_absent():
    """reschedule_engine adds a fresh job when the engine was previously disabled."""
    from core.engine.sentinel.registry import engine_registry, register_engine

    engine_registry.clear()

    @register_engine(name="test_reschedule_fresh", cron="0 2 * * *", description="Test")
    async def run(product_id: str) -> dict:
        return {}

    sched = _make_scheduler()
    mock_apscheduler = MagicMock()
    mock_apscheduler.get_job = MagicMock(return_value=None)  # job not present

    with patch("core.engine.sentinel.scheduler.AsyncIOScheduler", return_value=mock_apscheduler):
        sched.start(overrides={"test_reschedule_fresh": {"cron": None, "enabled": False}})

    sched.reschedule_engine("test_reschedule_fresh", "30 4 * * *")

    # remove_job should NOT be called (job was absent)
    mock_apscheduler.remove_job.assert_not_called()
    # add_job called once (reschedule only — start skipped disabled engine)
    assert mock_apscheduler.add_job.call_count == 1


# ---------------------------------------------------------------------------
# disable_engine
# ---------------------------------------------------------------------------


def test_disable_engine_removes_job():
    """disable_engine removes the APScheduler job."""
    from core.engine.sentinel.registry import engine_registry, register_engine

    engine_registry.clear()

    @register_engine(name="test_disable", cron="0 2 * * *", description="Test")
    async def run(product_id: str) -> dict:
        return {}

    sched = _make_scheduler()
    mock_apscheduler = MagicMock()
    mock_apscheduler.get_job = MagicMock(return_value=MagicMock())  # job exists

    with patch("core.engine.sentinel.scheduler.AsyncIOScheduler", return_value=mock_apscheduler):
        sched.start(overrides={})

    sched.disable_engine("test_disable")

    mock_apscheduler.remove_job.assert_called_once_with("sentinel_test_disable")


def test_disable_engine_noop_when_already_absent():
    """disable_engine does not raise when engine is not in scheduler."""
    from core.engine.sentinel.registry import engine_registry, register_engine

    engine_registry.clear()

    @register_engine(name="test_disable_noop", cron="0 2 * * *", description="Test")
    async def run(product_id: str) -> dict:
        return {}

    sched = _make_scheduler()
    mock_apscheduler = MagicMock()
    mock_apscheduler.get_job = MagicMock(return_value=None)  # job absent

    with patch("core.engine.sentinel.scheduler.AsyncIOScheduler", return_value=mock_apscheduler):
        sched.start(overrides={})

    sched.disable_engine("test_disable_noop")  # should not raise

    mock_apscheduler.remove_job.assert_not_called()


# ---------------------------------------------------------------------------
# enable_engine
# ---------------------------------------------------------------------------


def test_enable_engine_adds_job():
    """enable_engine adds the APScheduler job back."""
    from core.engine.sentinel.registry import engine_registry, register_engine

    engine_registry.clear()

    @register_engine(name="test_enable", cron="0 2 * * *", description="Test")
    async def run(product_id: str) -> dict:
        return {}

    sched = _make_scheduler()
    mock_apscheduler = MagicMock()

    with patch("core.engine.sentinel.scheduler.AsyncIOScheduler", return_value=mock_apscheduler):
        # Start with engine disabled
        sched.start(overrides={"test_enable": {"cron": None, "enabled": False}})

    call_count_before = mock_apscheduler.add_job.call_count  # 0

    sched.enable_engine("test_enable", "0 5 * * *")

    assert mock_apscheduler.add_job.call_count == call_count_before + 1
    add_call_kwargs = mock_apscheduler.add_job.call_args[1]
    assert add_call_kwargs["id"] == "sentinel_test_enable"
