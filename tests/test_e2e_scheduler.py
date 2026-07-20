# tests/test_e2e_scheduler.py
"""Integration and end-to-end tests for the sentinel scheduler system.

These tests require a running SurrealDB instance (make db-up).
They apply schema, create test data, and verify the full pipeline.
"""

import pytest

pytestmark = pytest.mark.e2e
from unittest.mock import AsyncMock, patch

from core.engine.core.db import parse_one, parse_rows


@pytest.mark.asyncio
async def test_e2e_schema_v007_applied(db_pool):
    """Schema v007 tables exist and are queryable."""
    import subprocess
    import sys

    result = subprocess.run([sys.executable, "scripts/schema_apply.py"], capture_output=True, text=True)
    assert result.returncode == 0, result.stderr

    async with db_pool.connection() as db:
        for table in ["engine_run", "output_version", "research_queue"]:
            rows = await db.query(f"SELECT * FROM {table} LIMIT 1")
            assert rows is not None, f"Table {table} not accessible"


@pytest.mark.asyncio
async def test_e2e_decay_manager_reduces_confidence(db_pool):
    """Create a stale insight, run decay_manager, verify confidence decreased."""
    import subprocess
    import sys

    subprocess.run([sys.executable, "scripts/schema_apply.py"], capture_output=True, text=True)

    async with db_pool.connection() as db:
        # Create test product
        await db.query("CREATE product:e2e_test SET name = 'E2E Test', tenant = tenant:test, settings = {}")
        await db.query("CREATE tenant:test SET name = 'Test Tenant'")

        # Create stale insight (last_confirmed 30 days ago, version tag = 14 day threshold)
        await db.query("""
            CREATE insight:e2e_stale SET
                product = product:e2e_test,
                content = 'React 18 is the latest version',
                insight_type = 'fact',
                tier = 'subdomain',
                source_domain = 'e2e_test',
                domain = 'technology',
                subdomain = 'frontend',
                tags = ['version'],
                confidence = 0.8,
                decay_rate = 0.05,
                last_confirmed = time::now() - 30d,
                created_at = time::now() - 60d,
                status = 'active'
        """)

        # Create fresh insight (last_confirmed 1 day ago)
        await db.query("""
            CREATE insight:e2e_fresh SET
                product = product:e2e_test,
                content = 'React uses JSX syntax',
                insight_type = 'fact',
                tier = 'subdomain',
                source_domain = 'e2e_test',
                domain = 'technology',
                subdomain = 'frontend',
                tags = ['fact'],
                confidence = 0.9,
                decay_rate = 0.01,
                last_confirmed = time::now() - 1d,
                created_at = time::now() - 30d,
                status = 'active'
        """)

    # Run decay manager
    from core.engine.sentinel.decay_manager import run as decay_run

    with patch("core.engine.sentinel.decay_manager._get_db", new_callable=AsyncMock) as mock_get_db:
        mock_get_db.return_value = db_pool
        result = await decay_run("product:e2e_test")

    assert result["insights_checked"] == 2
    assert result["insights_decayed"] == 1  # Only the stale one

    # Verify confidence decreased
    async with db_pool.connection() as db:
        rows = await db.query("SELECT confidence FROM insight:e2e_stale")
        stale = parse_one(rows)
        stale_conf = stale["confidence"] if stale else 0.8
        assert stale_conf < 0.8  # Was 0.8, should be 0.75 after one decay

        rows = await db.query("SELECT confidence FROM insight:e2e_fresh")
        fresh = parse_one(rows)
        fresh_conf = fresh["confidence"] if fresh else 0.0
        assert fresh_conf == 0.9  # Should be unchanged (confirmed 1 day ago, threshold 90 days)

    # Cleanup
    async with db_pool.connection() as db:
        await db.query("DELETE insight:e2e_stale")
        await db.query("DELETE insight:e2e_fresh")
        await db.query("DELETE product:e2e_test")
        await db.query("DELETE tenant:test")


@pytest.mark.asyncio
async def test_e2e_conflict_detector_finds_contradiction(db_pool):
    """Create contradicting insights, run conflict check, verify conflict record."""
    import subprocess
    import sys

    subprocess.run([sys.executable, "scripts/schema_apply.py"], capture_output=True, text=True)

    async with db_pool.connection() as db:
        # Cleanup leftover data from previous failed runs
        await db.query("DELETE conflict WHERE insight_a = insight:e2e_old")
        await db.query("DELETE insight:e2e_old")
        await db.query("DELETE insight:e2e_new")
        await db.query("DELETE product:e2e_cd")
        await db.query("DELETE tenant:cd")

        await db.query("CREATE product:e2e_cd SET name = 'CD Test', tenant = tenant:cd, settings = {}")
        await db.query("CREATE tenant:cd SET name = 'CD Tenant'")

        r1 = await db.query("""
            CREATE insight:e2e_old SET
                product = product:e2e_cd,
                content = 'React 18 is the latest stable version',
                insight_type = 'fact',
                tier = 'subdomain',
                source_domain = 'e2e_test',
                domain = 'technology',
                subdomain = 'frontend',
                tags = ['version'],
                confidence = 0.8,
                status = 'active'
        """)
        assert parse_rows(r1), f"insight:e2e_old CREATE failed: {r1}"
        r2 = await db.query("""
            CREATE insight:e2e_new SET
                product = product:e2e_cd,
                content = 'React 19 is the latest stable version',
                insight_type = 'fact',
                tier = 'subdomain',
                source_domain = 'e2e_test',
                domain = 'technology',
                subdomain = 'frontend',
                tags = ['version'],
                confidence = 0.9,
                status = 'active'
        """)
        assert parse_rows(r2), f"insight:e2e_new CREATE failed: {r2}"

    # Run conflict check with mocked LLM
    from core.engine.sentinel.conflict_detector import check_new_insights

    mock_llm = AsyncMock()
    mock_llm.complete_json = AsyncMock(
        return_value={
            "contradicts": True,
            "explanation": "React 18 vs React 19 version conflict",
        }
    )

    async with db_pool.connection() as db:
        result = await check_new_insights(
            new_insight_ids=["insight:e2e_new"],
            product_id="product:e2e_cd",
            db=db,
            llm=mock_llm,
        )

    assert result["conflicts_found"] == 1

    # Verify conflict record exists
    async with db_pool.connection() as db:
        rows = await db.query("""
            SELECT * FROM conflict
            WHERE insight_a = insight:e2e_old AND insight_b = insight:e2e_new
        """)
        conflicts = parse_rows(rows)
        assert len(conflicts) >= 1

    # Cleanup
    async with db_pool.connection() as db:
        await db.query("DELETE conflict WHERE insight_a = insight:e2e_old")
        await db.query("DELETE insight:e2e_old")
        await db.query("DELETE insight:e2e_new")
        await db.query("DELETE product:e2e_cd")
        await db.query("DELETE tenant:cd")


@pytest.mark.asyncio
async def test_e2e_engine_run_logging(db_pool):
    """Trigger an engine via scheduler, verify engine_run record in DB."""
    import subprocess
    import sys

    subprocess.run([sys.executable, "scripts/schema_apply.py"], capture_output=True, text=True)

    from core.engine.sentinel.registry import engine_registry, register_engine
    from core.engine.sentinel.scheduler import SentinelScheduler

    engine_registry.clear()

    @register_engine(name="e2e_test_engine", cron="0 5 * * *", description="E2E test")
    async def run(product_id: str) -> dict:
        return {"test_key": "test_value", "count": 42}

    async with db_pool.connection() as db:
        # Cleanup any leftover records from previous failed runs
        await db.query("DELETE engine_run WHERE engine = 'e2e_test_engine'")
        await db.query("DELETE product:e2e_engrun")
        await db.query("DELETE tenant:engrun")

        await db.query("CREATE product:e2e_engrun SET name = 'EngRun Test', tenant = tenant:engrun, settings = {}")
        await db.query("CREATE tenant:engrun SET name = 'EngRun Tenant'")

        scheduler = SentinelScheduler(db_pool=db_pool)
        result = await scheduler.execute_engine("e2e_test_engine", "product:e2e_engrun", db=db)

        assert result["status"] == "completed"
        assert result["results"]["count"] == 42

    # Verify engine_run record in a fresh connection
    async with db_pool.connection() as db:
        rows = await db.query("""
            SELECT * FROM engine_run
            WHERE engine = 'e2e_test_engine'
            ORDER BY started_at DESC
            LIMIT 1
        """)
        runs = parse_rows(rows)
        assert len(runs) == 1
        assert runs[0]["status"] == "completed"
        assert runs[0]["results"]["count"] == 42

    # Cleanup
    async with db_pool.connection() as db:
        await db.query("DELETE engine_run WHERE engine = 'e2e_test_engine'")
        await db.query("DELETE product:e2e_engrun")
        await db.query("DELETE tenant:engrun")
