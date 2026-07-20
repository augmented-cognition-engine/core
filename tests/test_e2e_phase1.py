# tests/test_e2e_phase1.py
"""Phase 1 complete verification — all three sub-phases."""

import pytest

pytestmark = pytest.mark.e2e


@pytest.mark.asyncio
async def test_document_table_exists(db_pool):
    async with db_pool.connection() as db:
        result = await db.query("SELECT * FROM document LIMIT 1")
        assert result is not None


@pytest.mark.asyncio
async def test_all_phase1_tables_exist(db_pool):
    """All tables from v001-v004 should be queryable."""
    tables = [
        # v001
        "tenant",
        "org",
        "user",
        "workspace",
        "membership",
        "domain",
        "subdomain",
        "specialty",
        "domain_flow_config",
        "config_entry",
        # v002
        "memory",
        "observation",
        "insight",
        "task",
        "conflict",
        # v003
        "maturation",
        "maturation_history",
        # v004
        "document",
    ]
    async with db_pool.connection() as db:
        for table in tables:
            result = await db.query(f"SELECT * FROM {table} LIMIT 1")
            assert result is not None, f"Table {table} not accessible"
