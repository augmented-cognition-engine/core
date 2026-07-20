"""Tests for changelog generator: git log fallback and decision enrichment."""

import contextlib
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from core.engine.generation.changelog import _enrich_with_decisions, _fallback_changelog


def _pool_with(rows):
    mock_conn = AsyncMock()
    mock_conn.query = AsyncMock(return_value=[[]])

    @contextlib.asynccontextmanager
    async def _connection():
        yield mock_conn

    mock_pool = MagicMock()
    mock_pool.connection = _connection
    return mock_pool, rows


# ── _enrich_with_decisions ─────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_enrich_no_shas_returns_original():
    text = "No commits here."
    with (
        patch("core.engine.generation.changelog.pool") as mp,
        patch("core.engine.generation.changelog.parse_rows", return_value=[]),
    ):
        mp.connection = _pool_with([])[0].connection
        result, count = await _enrich_with_decisions(text, "product:test")
    assert result == text
    assert count == 0


@pytest.mark.asyncio
async def test_enrich_annotates_matching_sha():
    text = "- feat: add auth (abc1234)"
    decision_row = {
        "sha": "abc1234",
        "decision_title": "Always use JWT",
        "rationale": "Security policy.",
    }
    pool, _ = _pool_with([decision_row])
    with (
        patch("core.engine.generation.changelog.pool", pool),
        patch("core.engine.generation.changelog.parse_rows", return_value=[decision_row]),
    ):
        result, count = await _enrich_with_decisions(text, "product:test")

    assert '> Decision: "Always use JWT"' in result
    assert "> Why: Security policy." in result
    assert count == 1


@pytest.mark.asyncio
async def test_enrich_db_error_returns_original():
    text = "- fix: crash (deadbeef)"
    with patch("core.engine.generation.changelog.pool") as mp:
        mp.connection.side_effect = RuntimeError("DB down")
        result, count = await _enrich_with_decisions(text, "product:test")
    assert result == text
    assert count == 0


@pytest.mark.asyncio
async def test_enrich_no_decisions_returns_original():
    text = "- feat: new thing (abc1234)"
    pool, _ = _pool_with([])
    with (
        patch("core.engine.generation.changelog.pool", pool),
        patch("core.engine.generation.changelog.parse_rows", return_value=[]),
    ):
        result, count = await _enrich_with_decisions(text, "product:test")
    assert result == text
    assert count == 0


# ── _fallback_changelog ────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_fallback_returns_git_log_output():
    fake_log = "abc1234 feat: something\ndef5678 fix: bug"
    pool, _ = _pool_with([])

    with (
        patch("core.engine.generation.changelog.subprocess.check_output", return_value=fake_log.encode()),
        patch("core.engine.generation.changelog.pool", pool),
        patch("core.engine.generation.changelog.parse_rows", return_value=[]),
    ):
        result = await _fallback_changelog(None, "product:test")

    assert "abc1234" in result["content"]
    assert "git log" in result["generated_by"]


@pytest.mark.asyncio
async def test_fallback_handles_subprocess_error():
    import subprocess

    with patch(
        "core.engine.generation.changelog.subprocess.check_output", side_effect=subprocess.CalledProcessError(1, "git")
    ):
        result = await _fallback_changelog(None, "product:test")
    assert "error" in result or result.get("content") == ""
