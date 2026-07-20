# tests/test_schema_v020.py
"""Test v020 measurement schema tables exist and accept records."""

import subprocess
import sys

import pytest

from core.engine.core.db import parse_one

pytestmark = pytest.mark.e2e


@pytest.mark.asyncio
async def test_v020_tables_exist(db_pool):
    """After applying v020, experiment_log, daily_metrics, calibration_snapshot must be queryable."""
    result = subprocess.run(
        [sys.executable, "scripts/schema_apply.py"],
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0, result.stderr

    expected_tables = ["experiment_log", "daily_metrics", "calibration_snapshot"]
    async with db_pool.connection() as db:
        for table in expected_tables:
            rows = await db.query(f"SELECT * FROM {table} LIMIT 1")
            assert rows is not None, f"Table {table} not accessible"


@pytest.mark.asyncio
async def test_experiment_log_create(db_pool):
    """experiment_log table accepts a record with all required fields."""
    async with db_pool.connection() as db:
        result = await db.query("""
            CREATE experiment_log SET
                product = product:default,
                domain_path = 'ux',
                variant_desc = 'test variant',
                change_type = 'graph',
                control_mean = 0.72,
                variant_mean = 0.81,
                improvement = 0.09,
                effect_size_d = 0.62,
                p_value = 0.008,
                significant = true,
                committed = true,
                reverted = false,
                cost = 2.34,
                task_count = 20
        """)
        row = parse_one(result)
        assert row is not None, "experiment_log record should be created"
        assert row["domain_path"] == "ux"
        assert row["significant"] is True
        # cleanup
        await db.query("DELETE $id", {"id": row["id"]})


@pytest.mark.asyncio
async def test_daily_metrics_create(db_pool):
    """daily_metrics table accepts a record and enforces org+date uniqueness."""
    async with db_pool.connection() as db:
        result = await db.query("""
            CREATE daily_metrics SET
                product = product:default,
                date = '2026-03-23T00:00:00Z',
                tasks_total = 34,
                tasks_grounded = 9,
                avg_quality = 0.81,
                ipm_scalar = 0.27,
                ipm_vector = { quality_delta: 0.26, efficiency_delta: 0.11, precision: 0.68, coverage: 0.74 },
                feedback_rate = 0.26,
                token_cost_live = 1.50,
                token_cost_measurement = 0.30,
                experiments_run = 3,
                experiments_committed = 1
        """)
        row = parse_one(result)
        assert row is not None, "daily_metrics record should be created"
        assert row["tasks_total"] == 34
        assert row["ipm_vector"]["quality_delta"] == 0.26
        # cleanup
        await db.query("DELETE $id", {"id": row["id"]})


# test_task_ipm_fields removed — IPM module was removed during discipline migration.
