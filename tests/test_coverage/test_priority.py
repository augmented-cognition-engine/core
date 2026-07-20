"""Tests for coverage_priority: rank_capabilities scoring math."""

from unittest.mock import patch

import pytest

from core.engine.intelligence.coverage_priority import rank_capabilities


def _make_cap(slug, pct, priority=0.5, untested=0):
    return {
        "slug": slug,
        "name": slug,
        "function_pct": pct,
        "priority": priority,
        "untested": untested,
    }


@pytest.mark.asyncio
async def test_rank_empty_when_db_fails():
    with patch("core.engine.intelligence.coverage_priority.pool") as mp:
        mp.connection.side_effect = RuntimeError("DB down")
        result = await rank_capabilities("product:test")
    assert result == []


@pytest.mark.asyncio
async def test_rank_unmeasured_gets_priority_times_07():
    rows = [_make_cap("unmeasured", pct=0.0, priority=0.8, untested=0)]
    with (
        patch("core.engine.intelligence.coverage_priority.pool"),
        patch("core.engine.intelligence.coverage_priority.parse_rows", return_value=rows),
    ):
        result = await rank_capabilities("product:test")

    assert len(result) == 1
    # Score = 0.8 × 0.7 = 0.56
    assert result[0]["score"] == pytest.approx(0.56, abs=1e-3)


@pytest.mark.asyncio
async def test_rank_low_coverage_scores_high():
    rows = [
        _make_cap("low_cov", pct=0.1, priority=1.0, untested=5),
        _make_cap("high_cov", pct=0.9, priority=1.0, untested=0),
    ]
    with (
        patch("core.engine.intelligence.coverage_priority.pool"),
        patch("core.engine.intelligence.coverage_priority.parse_rows", return_value=rows),
    ):
        result = await rank_capabilities("product:test")

    slugs = [r["slug"] for r in result]
    assert slugs[0] == "low_cov"
    assert slugs[1] == "high_cov"


@pytest.mark.asyncio
async def test_rank_respects_limit():
    rows = [_make_cap(f"cap_{i}", pct=i * 0.1, priority=0.5) for i in range(20)]
    with (
        patch("core.engine.intelligence.coverage_priority.pool"),
        patch("core.engine.intelligence.coverage_priority.parse_rows", return_value=rows),
    ):
        result = await rank_capabilities("product:test", limit=5)

    assert len(result) == 5


@pytest.mark.asyncio
async def test_rank_untested_bonus_capped_at_20():
    rows = [
        _make_cap("big_untested", pct=0.5, priority=0.5, untested=100),
        _make_cap("small_untested", pct=0.5, priority=0.5, untested=0),
    ]
    with (
        patch("core.engine.intelligence.coverage_priority.pool"),
        patch("core.engine.intelligence.coverage_priority.parse_rows", return_value=rows),
    ):
        result = await rank_capabilities("product:test")

    # big_untested should rank higher due to untested bonus (capped at 20 × 0.02 = 0.4)
    assert result[0]["slug"] == "big_untested"
