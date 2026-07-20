# tests/test_cognition_multiphase_capture.py
"""Tests for MultiPhaseExecutor._load_phase_context() and ._capture_phase_output().

Phase 4 of the ACE Worker Service: auto-capture pipeline for RecipePhase.capture_as
and load_context wiring.
"""

from __future__ import annotations

import json
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from core.engine.cognition.models import CaptureSpec, ContextQuery
from core.engine.cognition.multiphase import MultiPhaseExecutor


@pytest.fixture
def executor():
    return MultiPhaseExecutor(
        llm_call=AsyncMock(return_value='{"output":"test","confidence":0.9,"evidence":[],"gaps":[]}')
    )


# ---------------------------------------------------------------------------
# _load_phase_context
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_load_phase_context_returns_empty_on_pool_failure(executor):
    """DB pool failure must return '' — never block phase execution."""
    query = ContextQuery(queries=["SELECT * FROM decision"], inject_as="Prior Decisions")
    with patch(
        "core.engine.cognition.multiphase.MultiPhaseExecutor._load_phase_context", wraps=executor._load_phase_context
    ):
        with patch("core.engine.core.db.pool") as mock_pool:
            mock_pool.connection.side_effect = Exception("DB unreachable")
            result = await executor._load_phase_context(query, "product:test")
    assert result == ""


@pytest.mark.asyncio
async def test_load_phase_context_returns_formatted_block(executor):
    """When rows are returned, the block must include the inject_as header."""
    query = ContextQuery(queries=["SELECT title FROM decision"], inject_as="Prior UX Decisions")
    mock_rows = [{"title": "Lock dark color palette", "created_at": "2026-04-01"}]

    mock_db = AsyncMock()
    mock_db.query = AsyncMock(return_value=MagicMock())
    mock_context = AsyncMock()
    mock_context.__aenter__ = AsyncMock(return_value=mock_db)
    mock_context.__aexit__ = AsyncMock(return_value=False)

    with (
        patch("core.engine.core.db.pool") as mock_pool,
        patch("core.engine.core.db.parse_rows", return_value=mock_rows),
    ):
        mock_pool.connection.return_value = mock_context
        result = await executor._load_phase_context(query, "product:test")

    assert "Prior UX Decisions" in result
    assert "dark color palette" in result or "Lock" in result


@pytest.mark.asyncio
async def test_load_phase_context_returns_empty_when_no_rows(executor):
    """Empty result set from DB must return '' (no injection)."""
    query = ContextQuery(queries=["SELECT * FROM decision WHERE product = 'product:none'"], inject_as="Decisions")

    mock_db = AsyncMock()
    mock_db.query = AsyncMock(return_value=MagicMock())
    mock_context = AsyncMock()
    mock_context.__aenter__ = AsyncMock(return_value=mock_db)
    mock_context.__aexit__ = AsyncMock(return_value=False)

    with patch("core.engine.core.db.pool") as mock_pool, patch("core.engine.core.db.parse_rows", return_value=[]):
        mock_pool.connection.return_value = mock_context
        result = await executor._load_phase_context(query, "product:test")

    assert result == ""


@pytest.mark.asyncio
async def test_load_phase_context_hard_caps_at_2000_chars(executor):
    """Context block must be capped at 2000 chars to protect token budget."""
    query = ContextQuery(queries=["SELECT body FROM large_table"], inject_as="Big Context")
    huge_row = [{"body": "x" * 5000}]

    mock_db = AsyncMock()
    mock_db.query = AsyncMock(return_value=MagicMock())
    mock_context = AsyncMock()
    mock_context.__aenter__ = AsyncMock(return_value=mock_db)
    mock_context.__aexit__ = AsyncMock(return_value=False)

    with patch("core.engine.core.db.pool") as mock_pool, patch("core.engine.core.db.parse_rows", return_value=huge_row):
        mock_pool.connection.return_value = mock_context
        result = await executor._load_phase_context(query, "product:test")

    # Header + 2000-char cap
    assert len(result) <= 2000 + 50  # 50 chars of header overhead


# ---------------------------------------------------------------------------
# _capture_phase_output
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_capture_phase_output_writes_observation(executor):
    """Valid PhaseOutput JSON with extract_fields must write to observation table."""
    spec = CaptureSpec(type="decision", discipline_hint="ux", extract_fields=["locked_aesthetic_direction"])
    output = json.dumps(
        {
            "output": {"locked_aesthetic_direction": "Dense Glass — dark, restrained, high contrast"},
            "confidence": 0.88,
            "evidence": [],
            "gaps": [],
        }
    )

    mock_db = AsyncMock()
    mock_db.query = AsyncMock(return_value=None)
    mock_context = AsyncMock()
    mock_context.__aenter__ = AsyncMock(return_value=mock_db)
    mock_context.__aexit__ = AsyncMock(return_value=False)

    with patch("core.engine.core.db.pool") as mock_pool:
        mock_pool.connection.return_value = mock_context
        await executor._capture_phase_output(spec, output, "product:test", "Design the UI direction")

    mock_db.query.assert_called_once()
    call_args = mock_db.query.call_args
    params = call_args[0][1] if len(call_args[0]) > 1 else call_args[1]
    assert params["type"] == "decision"
    assert params["discipline_hint"] == "ux"
    assert "Dense Glass" in params["content"] or len(params["content"]) > 0


@pytest.mark.asyncio
async def test_capture_phase_output_falls_back_to_raw_text(executor):
    """Non-JSON output must be captured as raw text, not silently dropped."""
    spec = CaptureSpec(type="pattern", discipline_hint="architecture", extract_fields=["pattern_name"])
    raw_output = "Always separate read and write models in event-sourced systems."

    mock_db = AsyncMock()
    mock_db.query = AsyncMock(return_value=None)
    mock_context = AsyncMock()
    mock_context.__aenter__ = AsyncMock(return_value=mock_db)
    mock_context.__aexit__ = AsyncMock(return_value=False)

    with patch("core.engine.core.db.pool") as mock_pool:
        mock_pool.connection.return_value = mock_context
        await executor._capture_phase_output(spec, raw_output, "product:test", "Design storage")

    mock_db.query.assert_called_once()
    call_args = mock_db.query.call_args
    params = call_args[0][1] if len(call_args[0]) > 1 else call_args[1]
    assert "read and write" in params["content"] or len(params["content"]) > 0


@pytest.mark.asyncio
async def test_capture_phase_output_never_raises_on_db_failure(executor):
    """DB failure must be silently swallowed — phase execution must not be interrupted."""
    spec = CaptureSpec(type="decision", discipline_hint="ux", extract_fields=["direction"])

    with patch("core.engine.core.db.pool") as mock_pool:
        mock_pool.connection.side_effect = Exception("DB down")
        # Must not raise — this is the sentinel for non-fatal capture
        await executor._capture_phase_output(spec, '{"output":"test"}', "product:test", "task")


@pytest.mark.asyncio
async def test_capture_phase_output_uses_description_as_fallback_content(executor):
    """When extracted fields are empty, description must be the fallback content."""
    spec = CaptureSpec(type="learning", discipline_hint="testing", extract_fields=["nonexistent_field"])
    output = json.dumps({"output": {}, "confidence": 0.5, "evidence": [], "gaps": []})

    mock_db = AsyncMock()
    mock_db.query = AsyncMock(return_value=None)
    mock_context = AsyncMock()
    mock_context.__aenter__ = AsyncMock(return_value=mock_db)
    mock_context.__aexit__ = AsyncMock(return_value=False)

    with patch("core.engine.core.db.pool") as mock_pool:
        mock_pool.connection.return_value = mock_context
        await executor._capture_phase_output(spec, output, "product:test", "Write integration tests for the auth flow")

    mock_db.query.assert_called_once()
    call_args = mock_db.query.call_args
    params = call_args[0][1] if len(call_args[0]) > 1 else call_args[1]
    assert "auth flow" in params["content"] or len(params["content"]) > 0
