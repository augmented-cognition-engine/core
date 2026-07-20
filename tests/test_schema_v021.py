# tests/test_schema_v021.py
"""Test v021 evolution schema tables exist and accept records."""

import subprocess
import sys

import pytest

pytestmark = pytest.mark.e2e


@pytest.mark.asyncio
async def test_v021_tables_exist(db_pool):
    """After applying v021, evolution_run, source_reputation, autonomy_level must be queryable."""
    result = subprocess.run(
        [sys.executable, "scripts/schema_apply.py"],
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0, result.stderr

    expected_tables = ["evolution_run", "source_reputation", "autonomy_level"]
    async with db_pool.connection() as db:
        for table in expected_tables:
            rows = await db.query(f"SELECT * FROM {table} LIMIT 1")
            assert rows is not None, f"Table {table} not accessible"


@pytest.mark.asyncio
async def test_evolution_run_create(db_pool):
    """evolution_run table accepts a record with all required fields."""
    async with db_pool.connection() as db:
        result = await db.query("""
            CREATE evolution_run SET
                product = product:default,
                phase = 'completed',
                hypotheses = ['hyp1', 'hyp2'],
                findings = ['finding1'],
                experiments_run = 2,
                committed = 1,
                proposed = 0,
                failed = 1,
                total_cost = 2.50
        """)
        row = result[0][0] if isinstance(result[0], list) else result[0]
        assert row["experiments_run"] == 2
        assert row["committed"] == 1
        await db.query(f"DELETE {row['id']}")


@pytest.mark.asyncio
async def test_autonomy_level_create(db_pool):
    """autonomy_level table accepts a record."""
    async with db_pool.connection() as db:
        result = await db.query("""
            CREATE autonomy_level SET
                product = product:default,
                domain_path = 'ux',
                level = 'supervised',
                commits_total = 0,
                commits_accurate = 0,
                accuracy_rate = 0.0
        """)
        row = result[0][0] if isinstance(result[0], list) else result[0]
        assert row["level"] == "supervised"
        await db.query(f"DELETE {row['id']}")
