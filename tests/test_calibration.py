# tests/test_calibration.py
"""Tests for calibration pure functions — bucketing, miscalibration, apply."""

import pytest

from core.engine.intelligence.calibration import (
    apply_calibration,
    bucket_tasks,
    compute_calibration,
)


def _make_task(domain="architecture", self_assessment=0.8, feedback="accepted"):
    return {
        "domain_path": domain,
        "self_assessment": self_assessment,
        "feedback_human": feedback,
    }


def test_bucket_tasks_groups_by_domain_and_confidence():
    tasks = [
        _make_task(self_assessment=0.8),
        _make_task(self_assessment=0.82),  # rounds to 0.8
        _make_task(self_assessment=0.9),
    ]
    buckets = bucket_tasks(tasks)
    assert "architecture" in buckets
    assert "0.8" in buckets["architecture"]
    assert len(buckets["architecture"]["0.8"]) == 2


def test_bucket_tasks_skips_missing_data():
    tasks = [
        {"domain_path": "tech", "self_assessment": None, "feedback_human": "accepted"},
        {"domain_path": "tech", "self_assessment": 0.8, "feedback_human": None},
        {"domain_path": "tech"},  # missing both
    ]
    buckets = bucket_tasks(tasks)
    assert buckets == {}


def test_compute_calibration_overconfident():
    """Domain with high predicted but low actual success = overconfident."""
    buckets = {
        "legal": {
            "0.9": [
                {"predicted": 0.9, "actual": 0.0},  # rejected
                {"predicted": 0.9, "actual": 0.5},  # edited
                {"predicted": 0.9, "actual": 0.0},
                {"predicted": 0.9, "actual": 0.5},
                {"predicted": 0.9, "actual": 0.0},
            ],
        },
    }
    cal = compute_calibration(buckets)
    assert "legal" in cal
    assert "0.9" in cal["legal"]
    # predicted=0.9, actual success rate=0/5 (none >= 0.7) → miscalibration=0.9
    assert cal["legal"]["0.9"]["miscalibration"] > 0.5  # overconfident


def test_compute_calibration_well_calibrated():
    """Domain with predicted matching actual = well calibrated."""
    buckets = {
        "architecture": {
            "0.8": [
                {"predicted": 0.8, "actual": 1.0},
                {"predicted": 0.8, "actual": 1.0},
                {"predicted": 0.8, "actual": 1.0},
                {"predicted": 0.8, "actual": 1.0},
                {"predicted": 0.8, "actual": 0.0},
            ],
        },
    }
    cal = compute_calibration(buckets)
    # 4/5 success = 0.8, predicted=0.8, miscalibration=0.0
    assert abs(cal["architecture"]["0.8"]["miscalibration"]) < 0.05


def test_compute_calibration_skips_small_buckets():
    """Buckets with < 5 samples are excluded."""
    buckets = {"tech": {"0.8": [{"predicted": 0.8, "actual": 1.0}] * 3}}
    cal = compute_calibration(buckets)
    assert cal == {"tech": {}}


def test_apply_calibration_adjusts_overconfident():
    """Overconfident domain gets reduced confidence."""
    cal_data = {
        "legal": {
            "0.9": {"predicted": 0.9, "actual": 0.5, "count": 10, "miscalibration": 0.4},
        },
    }
    adjusted = apply_calibration(0.9, "legal", cal_data)
    assert adjusted == pytest.approx(0.5, abs=0.01)


def test_apply_calibration_clamps_to_range():
    """Result clamped to [0.0, 1.0]."""
    cal_data = {
        "domain": {"0.3": {"miscalibration": -0.8}},  # underconfident by 0.8
    }
    # 0.3 - (-0.8) = 1.1 → clamped to 1.0
    adjusted = apply_calibration(0.3, "domain", cal_data)
    assert adjusted == 1.0

    # Overconfident by 0.5 on a 0.3 → 0.3-0.5 = -0.2 → clamped to 0.0
    cal_data2 = {"domain": {"0.3": {"miscalibration": 0.5}}}
    adjusted2 = apply_calibration(0.3, "domain", cal_data2)
    assert adjusted2 == 0.0


def test_apply_calibration_no_data_returns_raw():
    """No calibration data → return raw confidence unchanged."""
    assert apply_calibration(0.75, "tech", {}) == 0.75
    assert apply_calibration(0.75, "tech", None) == 0.75


def test_apply_calibration_falls_back_to_first_level_domain():
    """architecture.backend falls back to architecture if no exact match."""
    cal_data = {
        "architecture": {
            "0.8": {"miscalibration": 0.1},
        },
    }
    adjusted = apply_calibration(0.8, "architecture.backend", cal_data)
    assert adjusted == pytest.approx(0.7, abs=0.01)
