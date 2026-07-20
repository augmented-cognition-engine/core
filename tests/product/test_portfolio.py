"""Tests for portfolio aggregation logic."""

from core.engine.product.portfolio import compute_badge_severity


def test_compute_badge_red_for_critical_notifications():
    notifications = [
        {"tier": "critical", "read": False},
        {"tier": "informational", "read": False},
    ]
    result = compute_badge_severity(notifications)
    assert result["severity"] == "red"
    assert result["count"] == 2


def test_compute_badge_yellow_for_actionable():
    notifications = [
        {"tier": "actionable", "read": False},
    ]
    result = compute_badge_severity(notifications)
    assert result["severity"] == "yellow"
    assert result["count"] == 1


def test_compute_badge_blue_for_informational_only():
    notifications = [
        {"tier": "informational", "read": False},
        {"tier": "informational", "read": False},
    ]
    result = compute_badge_severity(notifications)
    assert result["severity"] == "blue"
    assert result["count"] == 2


def test_compute_badge_none_when_all_read():
    notifications = [
        {"tier": "critical", "read": True},
    ]
    result = compute_badge_severity(notifications)
    assert result["severity"] is None
    assert result["count"] == 0


def test_compute_badge_none_for_empty():
    result = compute_badge_severity([])
    assert result["severity"] is None
    assert result["count"] == 0
