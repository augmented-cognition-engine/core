from __future__ import annotations

from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest


def _pool(query):
    db = AsyncMock()
    db.query = AsyncMock(side_effect=query)
    pool = MagicMock()
    pool.connection.return_value.__aenter__ = AsyncMock(return_value=db)
    pool.connection.return_value.__aexit__ = AsyncMock(return_value=False)
    return pool


@pytest.fixture
def one_engine():
    from core.engine.sentinel.registry import engine_registry, register_engine

    original = dict(engine_registry)
    engine_registry.clear()

    @register_engine(name="configured_start", cron="0 1 * * *", description="test")
    async def run(product_id: str) -> dict:
        return {"product_id": product_id}

    yield
    engine_registry.clear()
    engine_registry.update(original)


@pytest.mark.asyncio
async def test_fresh_storage_is_explicitly_disabled_with_zero_jobs(one_engine):
    from core.engine.sentinel.scheduler import SentinelScheduler

    async def query(sql, params=None):
        return [[]]

    scheduler = SentinelScheduler(_pool(query), default_org_id="product:configured")
    with patch("core.engine.sentinel.scheduler.AsyncIOScheduler") as aps:
        state = await scheduler.start_for_configured_product()

    assert state == {
        "status": "disabled",
        "product_id": "product:configured",
        "reason": "fresh_storage_no_product",
        "job_count": 0,
    }
    assert scheduler.running is False
    aps.assert_not_called()


@pytest.mark.asyncio
async def test_missing_configured_product_is_degraded_with_zero_jobs(one_engine):
    from core.engine.sentinel.scheduler import SentinelScheduler

    async def query(sql, params=None):
        if "WHERE id" in sql:
            return [[]]
        return [[{"id": "product:someone_else"}]]

    scheduler = SentinelScheduler(_pool(query), default_org_id="product:configured")
    with patch("core.engine.sentinel.scheduler.AsyncIOScheduler") as aps:
        state = await scheduler.start_for_configured_product()

    assert state["status"] == "degraded"
    assert state["reason"] == "configured_product_missing"
    assert state["job_count"] == 0
    assert scheduler.running is False
    aps.assert_not_called()


@pytest.mark.asyncio
async def test_valid_configured_product_owns_overrides_and_every_job(one_engine):
    from core.engine.sentinel.scheduler import SentinelScheduler

    async def query(sql, params=None):
        if "FROM product" in sql:
            assert "<record>" not in sql
            assert params["product"].table_name == "product"
            assert params["product"].id == "configured"
            return [[{"id": "product:configured"}]]
        if "engine_schedule_override" in sql:
            assert "<record>" not in sql
            assert params["product"].table_name == "product"
            assert params["product"].id == "configured"
            return [[]]
        raise AssertionError(sql)

    scheduler = SentinelScheduler(_pool(query), default_org_id="product:configured")
    aps = MagicMock()
    with patch("core.engine.sentinel.scheduler.AsyncIOScheduler", return_value=aps):
        state = await scheduler.start_for_configured_product()

    assert state["status"] == "running"
    assert state["product_id"] == "product:configured"
    assert state["reason"] is None
    assert state["job_count"] == aps.add_job.call_count
    job_args = [call.kwargs["args"] for call in aps.add_job.call_args_list]
    assert ["configured_start", "product:configured"] in job_args
    assert all(args[1] == "product:configured" for args in job_args)
    aps.start.assert_called_once()


@pytest.mark.asyncio
async def test_startup_dependency_failure_is_degraded_and_schedules_nothing(one_engine):
    from core.engine.sentinel.scheduler import SentinelScheduler

    async def query(sql, params=None):
        raise RuntimeError("database unavailable")

    scheduler = SentinelScheduler(_pool(query), default_org_id="product:configured")
    with patch("core.engine.sentinel.scheduler.AsyncIOScheduler") as aps:
        state = await scheduler.start_for_configured_product()

    assert state["status"] == "degraded"
    assert state["reason"] == "startup_dependency_unavailable:RuntimeError"
    assert state["job_count"] == 0
    aps.assert_not_called()


def test_api_startup_wires_the_single_configured_product():
    source = Path("core/engine/api/main.py").read_text()
    assert "SentinelScheduler(db_pool=pool, default_org_id=settings.default_org)" in source
    assert "await scheduler.start_for_configured_product()" in source
    assert 'scheduler.load_overrides("product:default")' not in source
