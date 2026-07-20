# tests/test_schema.py
import pytest

pytestmark = pytest.mark.e2e


@pytest.mark.asyncio
async def test_schema_tables_exist(db_pool):
    """After applying v001, all structural tables must be queryable."""
    import subprocess
    import sys

    result = subprocess.run([sys.executable, "scripts/schema_apply.py"], capture_output=True, text=True)
    assert result.returncode == 0, result.stderr

    expected_tables = [
        "tenant",
        "org",
        "workspace",
        "user",
        "membership",
        "domain",
        "subdomain",
        "specialty",
        "domain_flow_config",
    ]
    async with db_pool.connection() as db:
        for table in expected_tables:
            rows = await db.query(f"SELECT * FROM {table} LIMIT 1")
            # SurrealDB returns [] for empty table — not an error
            assert rows is not None, f"Table {table} not accessible"


# test_seed_creates_12_domains removed — seed_domains.py was deleted
# during the domain_path -> discipline migration.
