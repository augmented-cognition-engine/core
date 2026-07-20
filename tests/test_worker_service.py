# tests/test_worker_service.py
"""Regression tests migrated from service.py → intelligence.py.

service.py was deleted in the worker consolidation (2026-04-13).
The equivalent function is now engine.worker.intelligence.build_compact_index.

Key regression preserved: decisions SELECT must include created_at for
ORDER BY created_at DESC to work in SurrealDB v3.
"""

from unittest.mock import AsyncMock, MagicMock

import pytest


@pytest.mark.asyncio
async def test_build_compact_index_decisions_select_includes_created_at(monkeypatch):
    """Regression: ORDER BY created_at requires created_at in SELECT clause.

    SurrealDB v3 raises Validation error if you ORDER BY a field not in SELECT.
    Verify the decisions query includes created_at so ORDER BY works.
    """
    from core.engine.worker import intelligence as intel_mod

    captured_sqls: list[str] = []

    async def fake_query(sql, params=None):
        captured_sqls.append(sql)
        return []

    mock_db = AsyncMock()
    mock_db.query = fake_query

    mock_conn = MagicMock()
    mock_conn.__aenter__ = AsyncMock(return_value=mock_db)
    mock_conn.__aexit__ = AsyncMock(return_value=False)

    monkeypatch.setattr(intel_mod.pool, "connection", lambda: mock_conn)

    await intel_mod.build_compact_index(
        discipline="architecture",
        session_summary="",
        message_count=0,
        product_id="product:test",
    )

    # Find the decisions query
    decision_sql = next((s for s in captured_sqls if "FROM decision" in s), None)
    assert decision_sql is not None, "No decision query was issued"

    # Sentinel: created_at must be in SELECT for ORDER BY to work
    assert "created_at" in decision_sql, (
        "decisions SELECT missing 'created_at' — ORDER BY created_at DESC will raise Validation error in SurrealDB v3"
    )
    assert "ORDER BY created_at DESC" in decision_sql


@pytest.mark.asyncio
async def test_build_compact_index_empty_when_no_insights(monkeypatch):
    """If no insights or decisions match, compact_index is empty string."""
    from core.engine.worker import intelligence as intel_mod

    mock_db = AsyncMock()
    mock_db.query = AsyncMock(return_value=[])

    mock_conn = MagicMock()
    mock_conn.__aenter__ = AsyncMock(return_value=mock_db)
    mock_conn.__aexit__ = AsyncMock(return_value=False)

    monkeypatch.setattr(intel_mod.pool, "connection", lambda: mock_conn)

    result = await intel_mod.build_compact_index(
        discipline="newdiscipline",
        session_summary="",
        message_count=0,
        product_id="product:test",
    )

    assert result == ""
