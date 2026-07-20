# tests/test_scheduler.py
from unittest.mock import AsyncMock, MagicMock, patch

import pytest


@pytest.mark.asyncio
async def test_scheduler_creates_engine_run_on_execution():
    """When an engine runs, scheduler creates an engine_run record with status tracking."""
    from core.engine.sentinel.registry import engine_registry, register_engine
    from core.engine.sentinel.scheduler import SentinelScheduler

    engine_registry.clear()

    @register_engine(name="mock_engine", cron="0 3 * * *", description="Mock")
    async def run(product_id: str) -> dict:
        return {"items_processed": 5}

    mock_db = AsyncMock()
    # query returns a list with one dict containing an id field
    mock_db.query = AsyncMock(return_value=[{"id": "engine_run:test123"}])

    scheduler = SentinelScheduler(db_pool=None)
    result = await scheduler.execute_engine("mock_engine", "product:test", db=mock_db)

    assert result["status"] == "completed"
    assert result["results"]["items_processed"] == 5
    # Should have created engine_run (first query call) and updated it (second)
    assert mock_db.query.call_count >= 2


@pytest.mark.asyncio
async def test_scheduler_logs_failure_on_engine_error():
    """When an engine raises, scheduler logs status='failed' with error message."""
    from core.engine.sentinel.registry import engine_registry, register_engine
    from core.engine.sentinel.scheduler import SentinelScheduler

    engine_registry.clear()

    @register_engine(name="failing_engine", cron="0 3 * * *", description="Fails")
    async def run(product_id: str) -> dict:
        raise RuntimeError("Something broke")

    mock_db = AsyncMock()
    mock_db.query = AsyncMock(return_value=[{"id": "engine_run:test456"}])

    scheduler = SentinelScheduler(db_pool=None)
    result = await scheduler.execute_engine("failing_engine", "product:test", db=mock_db)

    assert result["status"] == "failed"
    assert "Something broke" in result["error"]


@pytest.mark.asyncio
async def test_scheduler_rejects_unknown_engine():
    """Triggering an unregistered engine raises KeyError."""
    from core.engine.sentinel.registry import engine_registry
    from core.engine.sentinel.scheduler import SentinelScheduler

    engine_registry.clear()

    mock_db = AsyncMock()
    scheduler = SentinelScheduler(db_pool=None)

    with pytest.raises(KeyError, match="not registered"):
        await scheduler.execute_engine("nonexistent", "product:test", db=mock_db)


def test_scheduler_init_without_start():
    """SentinelScheduler can be instantiated without starting APScheduler."""
    from core.engine.sentinel.scheduler import SentinelScheduler

    scheduler = SentinelScheduler(db_pool=None)
    assert scheduler.running is False


@pytest.mark.asyncio
async def test_scheduler_start_registers_jobs():
    """Starting the scheduler registers APScheduler jobs for all engines in registry."""
    from core.engine.sentinel.registry import engine_registry, register_engine
    from core.engine.sentinel.scheduler import SentinelScheduler

    engine_registry.clear()

    @register_engine(name="start_test_a", cron="0 1 * * *", description="A")
    async def run_a(product_id: str) -> dict:
        return {}

    @register_engine(name="start_test_b", cron="0 2 * * *", description="B")
    async def run_b(product_id: str) -> dict:
        return {}

    scheduler = SentinelScheduler(db_pool=None, default_org_id="product:test")

    with patch("core.engine.sentinel.scheduler.AsyncIOScheduler") as mock_aps:
        mock_instance = MagicMock()
        mock_aps.return_value = mock_instance
        scheduler.start()
        # Should have added 2 jobs
        assert mock_instance.add_job.call_count == 2
        mock_instance.start.assert_called_once()

    scheduler.shutdown()
