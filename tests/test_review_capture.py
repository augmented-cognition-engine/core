# tests/test_review_capture.py
"""Tests for automatic review decision capture."""

from __future__ import annotations

from unittest.mock import AsyncMock, patch

import pytest

from core.engine.review.capture import capture_review_decisions


@pytest.mark.asyncio
async def test_capture_review_decisions():
    """Should create observations for discipline selection, judge, and gate."""
    with patch("core.engine.review.capture.pool") as mock_pool:
        mock_conn = AsyncMock()
        mock_conn.query = AsyncMock(return_value=[[]])
        mock_pool.connection.return_value.__aenter__ = AsyncMock(return_value=mock_conn)
        mock_pool.connection.return_value.__aexit__ = AsyncMock(return_value=False)

        await capture_review_decisions(
            pr_title="Fix auth",
            disciplines=["security", "architecture"],
            synthesis_summary="2 findings",
            findings_count=2,
            findings_before_judge=4,
            findings_after_judge=2,
            pass_quality_gate=False,
            gate_failures=["Critical findings: 1"],
            discipline_scores={"security": 0.6, "architecture": 0.9},
            autofix_result={"type": "local", "files_fixed": 1},
        )

    # Should have made 4 DB calls: discipline, judge, gate, autofix
    assert mock_conn.query.call_count == 4


@pytest.mark.asyncio
async def test_capture_no_findings_skips_judge():
    """No judge observation when no findings before judge."""
    with patch("core.engine.review.capture.pool") as mock_pool:
        mock_conn = AsyncMock()
        mock_conn.query = AsyncMock(return_value=[[]])
        mock_pool.connection.return_value.__aenter__ = AsyncMock(return_value=mock_conn)
        mock_pool.connection.return_value.__aexit__ = AsyncMock(return_value=False)

        await capture_review_decisions(
            pr_title="Clean PR",
            disciplines=["testing"],
            synthesis_summary="No issues",
            findings_count=0,
            findings_before_judge=0,
            findings_after_judge=0,
            pass_quality_gate=True,
            gate_failures=[],
            discipline_scores={"testing": 1.0},
        )

    # Should have made 2 DB calls: discipline + gate (no judge, no autofix)
    assert mock_conn.query.call_count == 2


@pytest.mark.asyncio
async def test_capture_failure_is_silent():
    """Capture failures should never propagate."""
    with patch("core.engine.review.capture.pool") as mock_pool:
        mock_pool.connection.side_effect = Exception("DB down")

        # Should not raise
        await capture_review_decisions(
            pr_title="test",
            disciplines=[],
            synthesis_summary="",
            findings_count=0,
            findings_before_judge=0,
            findings_after_judge=0,
            pass_quality_gate=True,
            gate_failures=[],
            discipline_scores={},
        )
