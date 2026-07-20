# tests/test_statistics.py
"""Tests for Welch's t-test — pure math, no scipy."""

import pytest

from core.engine.intelligence.statistics import _mean, _variance, is_significant, welch_t_test


def test_identical_groups():
    """Identical groups → t=0, p=1."""
    t, p = welch_t_test([0.5, 0.5, 0.5], [0.5, 0.5, 0.5])
    assert t == 0.0
    assert p == 1.0


def test_clearly_different_groups():
    """Very different groups → significant."""
    a = [0.1, 0.2, 0.15, 0.12, 0.18, 0.11, 0.14, 0.13, 0.16, 0.19]
    b = [0.8, 0.9, 0.85, 0.88, 0.82, 0.91, 0.87, 0.83, 0.86, 0.89]
    t, p = welch_t_test(a, b)
    assert t > 0  # b > a
    assert p < 0.01  # highly significant


def test_single_element_groups():
    """Single element → degenerate, p=1."""
    t, p = welch_t_test([0.5], [0.8])
    assert p == 1.0


def test_empty_groups():
    """Empty group → degenerate."""
    t, p = welch_t_test([], [0.5, 0.6])
    assert p == 1.0


def test_zero_variance_different_means():
    """Zero variance but different means → significant."""
    t, p = welch_t_test([0.5, 0.5, 0.5], [0.8, 0.8, 0.8])
    assert p < 0.05


def test_is_significant_requires_both_conditions():
    """Significance requires BOTH p < 0.05 AND improvement > 0.02."""
    a = [0.5, 0.5, 0.5, 0.5, 0.5, 0.5, 0.5, 0.5, 0.5, 0.5]
    b = [0.51, 0.51, 0.51, 0.51, 0.51, 0.51, 0.51, 0.51, 0.51, 0.51]
    # Tiny improvement (0.01) — below min_effect of 0.02
    assert is_significant(a, b, min_effect=0.02) is False


def test_is_significant_with_clear_improvement():
    a = [0.3, 0.35, 0.32, 0.28, 0.31, 0.33, 0.29, 0.34, 0.30, 0.32]
    b = [0.6, 0.65, 0.62, 0.58, 0.61, 0.63, 0.59, 0.64, 0.60, 0.62]
    assert is_significant(a, b) is True


def test_mean_and_variance():
    assert _mean([1, 2, 3, 4, 5]) == 3.0
    assert _variance([1, 2, 3, 4, 5]) == pytest.approx(2.5)
    assert _mean([]) == 0.0
    assert _variance([5]) == 0.0
