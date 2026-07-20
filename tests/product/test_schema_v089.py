# tests/product/test_schema_v089.py
"""Schema v089 tests — ambition substrate + phase-aware ranking tables.

Requires running SurrealDB with schema applied (e2e marker).

Each test queries `INFO FOR TABLE <name>` and asserts that distinctive
fields from the v089 migration appear in the parsed table-info `fields`
section. SurrealDB v3's INFO query returns a struct even when a table is
undefined (with empty `fd`/`fields`), so a bare `is not None` check would
be a false positive — we must inspect the field list itself.
"""

import pytest

from core.engine.core.db import parse_one

pytestmark = pytest.mark.e2e


def _fields_blob(parsed: dict | None) -> str:
    """Stringify the `fields`/`fd` section of an INFO FOR TABLE result.

    SurrealDB v3 typically exposes per-field definitions under `fields`
    (some builds use `fd`). We coerce whichever is present to a string
    so that field-name substring assertions are scoped to actual field
    definitions, not arbitrary metadata.
    """
    assert parsed is not None, "INFO FOR TABLE returned no parsed result"
    fields_section = parsed.get("fields")
    if fields_section is None:
        fields_section = parsed.get("fd")
    if fields_section is None:
        # Fall back to the full parsed dict if the response shape is
        # unexpected — still narrower than `str(result)` from the raw
        # query result, but logs the issue if the assertion fails.
        fields_section = parsed
    return str(fields_section)


@pytest.mark.asyncio
async def test_ambition_table_exists(db_pool):
    async with db_pool.connection() as db:
        result = await db.query("INFO FOR TABLE ambition")
        fields = _fields_blob(parse_one(result))
        assert "target_json" in fields
        assert "phase_json" in fields


@pytest.mark.asyncio
async def test_phase_floors_table_exists(db_pool):
    async with db_pool.connection() as db:
        result = await db.query("INFO FOR TABLE phase_floors")
        fields = _fields_blob(parse_one(result))
        assert "floor_value" in fields
        assert "pillar" in fields


@pytest.mark.asyncio
async def test_required_pattern_relevance_table_exists(db_pool):
    async with db_pool.connection() as db:
        result = await db.query("INFO FOR TABLE required_pattern_relevance")
        fields = _fields_blob(parse_one(result))
        assert "contribution" in fields


@pytest.mark.asyncio
async def test_pillar_score_cache_table_exists(db_pool):
    async with db_pool.connection() as db:
        result = await db.query("INFO FOR TABLE pillar_score_cache")
        fields = _fields_blob(parse_one(result))
        assert "score" in fields
        assert "computed_at" in fields


@pytest.mark.asyncio
async def test_uncertainty_queries_table_exists(db_pool):
    async with db_pool.connection() as db:
        result = await db.query("INFO FOR TABLE uncertainty_queries")
        fields = _fields_blob(parse_one(result))
        assert "fallback_action" in fields


@pytest.mark.asyncio
async def test_recommendation_decay_state_table_exists(db_pool):
    async with db_pool.connection() as db:
        result = await db.query("INFO FOR TABLE recommendation_decay_state")
        fields = _fields_blob(parse_one(result))
        assert "consecutive_briefings_at_top" in fields


@pytest.mark.asyncio
async def test_product_table_has_product_type_field(db_pool):
    async with db_pool.connection() as db:
        result = await db.query("INFO FOR TABLE product")
        fields = _fields_blob(parse_one(result))
        assert "product_type" in fields
        assert "product_scale" in fields
