# tests/test_schema_idempotency.py
"""Schema migration idempotency — running apply twice should not fail."""

import pytest

pytestmark = pytest.mark.e2e


@pytest.mark.asyncio
async def test_schema_apply_is_idempotent(db_pool):
    """Running schema_apply twice should succeed without errors."""
    from scripts.schema_apply import apply_schema

    await apply_schema()  # First run
    await apply_schema()  # Second run — should not raise
