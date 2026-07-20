# tests/test_worker_intelligence.py
"""Tests for engine/worker/intelligence.py — compact index builder.

Key sentinel: index must be ≤ ~300 tokens (~1200 chars), not the 1000-token
flat dump from the legacy hook.
"""

import pytest


@pytest.mark.asyncio
async def test_compact_index_empty_when_no_data(monkeypatch):
    """Returns empty string when DB has no data for discipline."""
    from unittest.mock import AsyncMock, MagicMock

    from core.engine.worker import intelligence as intel_mod

    # Mock pool.connection() context manager to return empty results
    mock_db = AsyncMock()
    mock_db.query = AsyncMock(return_value=[])

    mock_conn = MagicMock()
    mock_conn.__aenter__ = AsyncMock(return_value=mock_db)
    mock_conn.__aexit__ = AsyncMock(return_value=False)

    monkeypatch.setattr(intel_mod.pool, "connection", lambda: mock_conn)

    result = await intel_mod.build_compact_index(
        discipline="ux",
        session_summary="",
        message_count=0,
        product_id="product:test",
    )

    # Empty DB → empty index (no header-only output)
    assert result == ""


@pytest.mark.asyncio
async def test_compact_index_token_budget_sentinel(monkeypatch):
    """Sentinel: index must be ≤ 1200 chars (~300 tokens), never a flat 1000-token dump."""
    from unittest.mock import AsyncMock, MagicMock

    from core.engine.worker import intelligence as intel_mod

    # Mock DB returning lots of data
    def fake_parse_rows(result):
        if result == "insight_count":
            return [{"n": 42}]
        if result == "decisions":
            return [
                {
                    "title": "Use dark dense restrained aesthetic direction for portal",
                    "decision_type": "ux",
                    "id": "decision:abc123",
                },
                {
                    "title": "Space Grotesk as primary display font for portal interface",
                    "decision_type": "ux",
                    "id": "decision:def456",
                },
                {
                    "title": "JetBrains Mono for all metadata and operational data display",
                    "decision_type": "ux",
                    "id": "decision:ghi789",
                },
            ]
        if result == "capabilities":
            return [{"n": 15}]
        if result == "global":
            return [{"n": 88}]
        return []

    call_count = [0]

    async def fake_query(sql, params=None):
        call_count[0] += 1
        # Return mock results based on call order
        if call_count[0] == 1:
            return "insight_count"
        elif call_count[0] == 2:
            return "decisions"
        elif call_count[0] == 3:
            return "capabilities"
        elif call_count[0] == 4:
            return "global"
        return []

    mock_db = AsyncMock()
    mock_db.query = fake_query

    mock_conn = MagicMock()
    mock_conn.__aenter__ = AsyncMock(return_value=mock_db)
    mock_conn.__aexit__ = AsyncMock(return_value=False)

    monkeypatch.setattr(intel_mod.pool, "connection", lambda: mock_conn)
    monkeypatch.setattr(intel_mod, "parse_rows", fake_parse_rows)

    result = await intel_mod.build_compact_index(
        discipline="ux",
        session_summary="exploring cognitive composition and worker architecture for last 30 minutes",
        message_count=12,
        product_id="product:test",
    )

    # Sentinel: index must be under budget — NOT a 1000-token flat dump
    assert len(result) <= intel_mod._MAX_INDEX_CHARS, (
        f"Compact index exceeds token budget: {len(result)} chars > {intel_mod._MAX_INDEX_CHARS}. "
        f"This would be a ~{len(result) // 4} token flat dump instead of a compact index."
    )

    # Must contain discipline section
    assert "[ux]" in result

    # Must start with the header
    assert result.startswith("## Context")


@pytest.mark.asyncio
async def test_compact_index_includes_session_context(monkeypatch):
    """Session summary appears in index when session has 3+ messages."""
    from unittest.mock import AsyncMock, MagicMock

    from core.engine.worker import intelligence as intel_mod

    call_count = [0]
    fake_decisions = [
        {"title": "Use SurrealDB for session state", "decision_type": "architecture", "id": "decision:xyz"}
    ]

    async def fake_query(sql, params=None):
        call_count[0] += 1
        if call_count[0] == 2:
            return "decisions"
        return []

    def fake_parse_rows(result):
        if result == "decisions":
            return fake_decisions
        return []

    mock_db = AsyncMock()
    mock_db.query = fake_query

    mock_conn = MagicMock()
    mock_conn.__aenter__ = AsyncMock(return_value=mock_db)
    mock_conn.__aexit__ = AsyncMock(return_value=False)

    monkeypatch.setattr(intel_mod.pool, "connection", lambda: mock_conn)
    monkeypatch.setattr(intel_mod, "parse_rows", fake_parse_rows)

    result = await intel_mod.build_compact_index(
        discipline="architecture",
        session_summary="exploring worker service architecture and session intelligence",
        message_count=8,
        product_id="product:test",
    )

    assert "[session]" in result
    assert "8 msgs" in result
    assert "worker service" in result


@pytest.mark.asyncio
async def test_compact_index_omits_session_for_short_sessions(monkeypatch):
    """Session context not included for short sessions (< 3 messages)."""
    from unittest.mock import AsyncMock, MagicMock

    from core.engine.worker import intelligence as intel_mod

    mock_db = AsyncMock()
    mock_db.query = AsyncMock(return_value=[])

    mock_conn = MagicMock()
    mock_conn.__aenter__ = AsyncMock(return_value=mock_db)
    mock_conn.__aexit__ = AsyncMock(return_value=False)

    monkeypatch.setattr(intel_mod.pool, "connection", lambda: mock_conn)

    result = await intel_mod.build_compact_index(
        discipline="architecture",
        session_summary="some summary",
        message_count=1,  # too short
        product_id="product:test",
    )

    assert "[session]" not in result


@pytest.mark.asyncio
async def test_compact_index_handles_db_failure_gracefully(monkeypatch):
    """DB failure returns empty string without raising."""
    from unittest.mock import AsyncMock, MagicMock

    from core.engine.worker import intelligence as intel_mod

    mock_db = AsyncMock()
    mock_db.query = AsyncMock(side_effect=RuntimeError("DB connection failed"))

    mock_conn = MagicMock()
    mock_conn.__aenter__ = AsyncMock(return_value=mock_db)
    mock_conn.__aexit__ = AsyncMock(return_value=False)

    monkeypatch.setattr(intel_mod.pool, "connection", lambda: mock_conn)

    result = await intel_mod.build_compact_index(
        discipline="ux",
        session_summary="some session",
        message_count=5,
        product_id="product:test",
    )

    # Must not raise — graceful empty
    assert result == ""
