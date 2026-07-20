"""Tests for coverage_binder: aggregation and severity mapping."""

import pytest

from core.engine.intelligence.coverage_binder import _aggregate, _severity_for_untested
from core.engine.scanner.coverage_extractor import CoverageRow

# ── _aggregate ─────────────────────────────────────────────────────────────


def _row(lc, lt, bc=0, bt=0, fc=0, ft=0, untested=None):
    return CoverageRow(
        file="f.py",
        lines_covered=lc,
        lines_total=lt,
        branches_covered=bc,
        branches_total=bt,
        functions_covered=fc,
        functions_total=ft,
        untested_functions=untested or [],
    )


def test_aggregate_single_row_line_pct():
    agg = _aggregate([_row(80, 100)])
    assert agg["line_pct"] == pytest.approx(0.8)


def test_aggregate_multiple_rows_sums_counts():
    rows = [_row(50, 100), _row(30, 50)]
    agg = _aggregate(rows)
    assert agg["line_pct"] == pytest.approx(80 / 150)


def test_aggregate_zero_totals_returns_zero_pct():
    agg = _aggregate([_row(0, 0)])
    assert agg["line_pct"] == 0.0
    assert agg["branch_pct"] == 0.0
    assert agg["function_pct"] == 0.0


def test_aggregate_files_count():
    rows = [_row(1, 1), _row(1, 1), _row(1, 1)]
    agg = _aggregate(rows)
    assert agg["files"] == 3


def test_aggregate_untested_sum():
    rows = [
        _row(0, 10, untested=["a", "b"]),
        _row(0, 10, untested=["c"]),
    ]
    agg = _aggregate(rows)
    assert agg["untested"] == 3


def test_aggregate_branch_pct():
    agg = _aggregate([_row(0, 10, bc=3, bt=4)])
    assert agg["branch_pct"] == pytest.approx(0.75)


def test_aggregate_function_pct():
    agg = _aggregate([_row(0, 10, fc=2, ft=5)])
    assert agg["function_pct"] == pytest.approx(0.4)


# ── _severity_for_untested ─────────────────────────────────────────────────


def test_severity_below_30_pct_is_high():
    assert _severity_for_untested(0.0) == "high"
    assert _severity_for_untested(0.29) == "high"


def test_severity_30_to_60_pct_is_medium():
    assert _severity_for_untested(0.3) == "medium"
    assert _severity_for_untested(0.59) == "medium"


def test_severity_60_pct_and_above_is_low():
    assert _severity_for_untested(0.6) == "low"
    assert _severity_for_untested(1.0) == "low"
