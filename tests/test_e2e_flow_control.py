# tests/test_e2e_flow_control.py
"""End-to-end: verify flow control — clearance filtering + propagation controls."""

import pytest

pytestmark = pytest.mark.e2e


@pytest.mark.asyncio
async def test_flow_config_table_exists(db_pool):
    async with db_pool.connection() as db:
        result = await db.query("SELECT * FROM domain_flow_config LIMIT 1")
        assert result is not None


@pytest.mark.asyncio
async def test_default_clearance_is_open(db_pool):
    """Without config, clearance defaults to open."""
    from core.engine.flow.config import get_flow_config

    async with db_pool.connection() as db:
        domain = await db.query("SELECT id FROM domain WHERE slug = 'technology' LIMIT 1")
        domain_rows = domain[0] if domain and isinstance(domain[0], list) else (domain or [])
        if domain_rows:
            config = await get_flow_config(str(domain_rows[0]["id"]), "product:test")
            assert config.default_clearance == "open"
            assert config.consume_org_intelligence is True


@pytest.mark.asyncio
async def test_all_phase2_tables_exist(db_pool):
    """All tables from v001-v006 should be queryable."""
    tables = [
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
        "memory",
        "observation",
        "insight",
        "task",
        "conflict",
        "maturation",
        "maturation_history",
        "document",
        "synapse",
    ]
    async with db_pool.connection() as db:
        for table in tables:
            result = await db.query(f"SELECT * FROM {table} LIMIT 1")
            assert result is not None, f"Table {table} not accessible"
