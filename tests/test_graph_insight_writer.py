# tests/test_graph_insight_writer.py
"""Unit tests for engine.graph.insight_writer.write_insight_to_graph.

Phase 3: shadow graph_insight table retired.
Only real-table edges (insight -> informed_by -> specialty) are written.
"""

from contextlib import asynccontextmanager
from unittest.mock import AsyncMock, MagicMock

import pytest

from core.engine.graph.insight_writer import _slugify_id, write_insight_to_graph

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_pool(db_mock):
    """Build a mock pool whose .connection() yields db_mock."""
    mock_pool = MagicMock()

    @asynccontextmanager
    async def _conn():
        yield db_mock

    mock_pool.connection = _conn
    return mock_pool


def _make_db(query_side_effect=None):
    """Build a mock DB whose .query() returns controllable values."""
    db = AsyncMock()
    if query_side_effect is not None:
        db.query = AsyncMock(side_effect=query_side_effect)
    else:
        db.query = AsyncMock(return_value=[])
    return db


# ---------------------------------------------------------------------------
# _slugify_id
# ---------------------------------------------------------------------------


class TestSlugifyId:
    def test_basic_record_id(self):
        assert _slugify_id("insight:abc123") == "abc123"

    def test_no_colon(self):
        assert _slugify_id("abc123") == "abc123"

    def test_angle_bracket_escaping(self):
        # SurrealDB may return ⟨...⟩ for complex IDs
        assert _slugify_id("insight:⟨abc-123⟩") == "abc_123"

    def test_special_chars_replaced(self):
        slug = _slugify_id("insight:foo.bar/baz")
        assert slug == "foo_bar_baz"

    def test_empty_record_part(self):
        # Degenerate: "insight:" with nothing after
        result = _slugify_id("insight:")
        assert result == "unknown"


# ---------------------------------------------------------------------------
# test_write_insight — no shadow writes
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_write_insight_no_shadow_writes():
    """Without specialty or task, no queries are issued (graph_insight retired)."""
    db = _make_db()
    pool = _make_pool(db)

    result = await write_insight_to_graph(
        insight_id="insight:abc123",
        content="Test insight",
        insight_type="fact",
        confidence=0.8,
        source="capture",
        tags=["python", "testing"],
        db_pool=pool,
    )

    # No queries — graph_insight UPSERT is retired
    assert db.query.call_count == 0
    assert result is not None
    assert result["insight_id"] == "insight:abc123"
    assert result["edges"] == []


# ---------------------------------------------------------------------------
# test_write_insight_with_specialty
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_write_insight_with_specialty():
    """When specialty_slug is given and specialty exists, informed_by RELATE is issued on real tables."""
    specialty_real_record = {"id": "specialty:backend"}

    responses = [
        specialty_real_record,  # SELECT specialty (real table)
        [],  # RELATE insight -> informed_by -> specialty
    ]
    db = _make_db(query_side_effect=responses)
    pool = _make_pool(db)

    result = await write_insight_to_graph(
        insight_id="insight:abc123",
        content="Backend pattern",
        insight_type="pattern",
        confidence=0.9,
        source="capture",
        tags=[],
        specialty_slug="backend",
        db_pool=pool,
    )

    assert db.query.call_count == 2

    # First call: SELECT specialty (real table)
    spec_query, spec_params = db.query.call_args_list[0][0]
    assert "specialty" in spec_query
    assert "graph_specialty" not in spec_query
    assert spec_params["slug"] == "backend"

    # Second call: RELATE on real tables
    relate_query, _ = db.query.call_args_list[1][0]
    assert "informed_by" in relate_query

    assert result is not None
    assert "informed_by" in result["edges"]


@pytest.mark.asyncio
async def test_write_insight_with_specialty_not_found():
    """When specialty is not found, RELATE is skipped."""
    responses = [
        [],  # SELECT specialty (real table) -- empty
    ]
    db = _make_db(query_side_effect=responses)
    pool = _make_pool(db)

    result = await write_insight_to_graph(
        insight_id="insight:abc123",
        content="Orphan insight",
        insight_type="fact",
        confidence=0.7,
        source="capture",
        tags=[],
        specialty_slug="nonexistent-specialty",
        db_pool=pool,
    )

    assert db.query.call_count == 1
    assert result is not None
    assert result["edges"] == []


# ---------------------------------------------------------------------------
# test_write_insight_with_task (retired — no edge written)
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_write_insight_with_task_no_edge():
    """task_id param is accepted for compatibility but no produced edge is written."""
    db = _make_db()
    pool = _make_pool(db)

    result = await write_insight_to_graph(
        insight_id="insight:abc123",
        content="Task-produced insight",
        insight_type="fix",
        confidence=0.85,
        source="overnight",
        tags=["fix"],
        task_id="build_api",
        db_pool=pool,
    )

    # No queries — graph_task produced edge is retired
    assert db.query.call_count == 0
    assert result is not None
    assert result["edges"] == []


@pytest.mark.asyncio
async def test_write_insight_with_both_specialty_and_task():
    """Specialty edge is written; task_id is accepted but no produced edge."""
    specialty_real_record = {"id": "specialty:frontend"}

    responses = [
        specialty_real_record,  # SELECT specialty (real table)
        [],  # RELATE informed_by (real tables)
    ]
    db = _make_db(query_side_effect=responses)
    pool = _make_pool(db)

    result = await write_insight_to_graph(
        insight_id="insight:xyz",
        content="UI pattern",
        insight_type="code_pattern",
        confidence=0.75,
        source="agent",
        tags=["ui"],
        specialty_slug="frontend",
        task_id="build_ui",
        db_pool=pool,
    )

    # 2 queries: SELECT specialty + RELATE informed_by (no graph_task/produced)
    assert db.query.call_count == 2
    assert result is not None
    assert "informed_by" in result["edges"]


# ---------------------------------------------------------------------------
# test_write_insight_best_effort
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_write_insight_best_effort_on_db_error():
    """A DB error causes the function to return None without raising."""
    db = _make_db()
    db.query = AsyncMock(side_effect=RuntimeError("DB is down"))
    pool = _make_pool(db)

    # Must not raise
    result = await write_insight_to_graph(
        insight_id="insight:fail",
        content="This will fail",
        insight_type="fact",
        confidence=0.5,
        source="capture",
        tags=[],
        specialty_slug="backend",  # triggers a query that will fail
        db_pool=pool,
    )

    assert result is None


@pytest.mark.asyncio
async def test_write_insight_pool_error():
    """Connection pool failure causes function to return None without raising."""
    bad_pool = MagicMock()

    @asynccontextmanager
    async def _bad_conn():
        raise ConnectionError("Pool unavailable")
        yield  # unreachable, but makes it a generator

    bad_pool.connection = _bad_conn

    result = await write_insight_to_graph(
        insight_id="insight:pool_fail",
        content="Pool failure",
        insight_type="fact",
        confidence=0.5,
        source="capture",
        tags=[],
        db_pool=bad_pool,
    )

    assert result is None


# NOTE: the former `test_synthesizer_write_insight_calls_graph_writer` integration
# test was removed in Phase 1 (A+). `_write_insight` no longer calls
# write_insight_to_graph — it routes through atomic_capture_write, which writes the
# informed_by/derived_from edges inside one transaction. That path is covered by
# tests/test_synthesizer_atomic.py and tests/test_atomic_capture_write.py.
# write_insight_to_graph itself (still used by sentinel engines) is covered above.
