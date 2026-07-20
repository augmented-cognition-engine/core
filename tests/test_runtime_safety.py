"""Tests for safety limits."""

from core.engine.runtime.safety import SafetyLimits


def test_default_limits():
    limits = SafetyLimits()
    assert limits.max_turns == 100
    assert limits.max_cost_usd is None  # no cap by default


def test_custom_limits():
    limits = SafetyLimits(max_turns=50, max_cost_usd=1.0)
    assert limits.max_turns == 50
    assert limits.max_cost_usd == 1.0


def test_check_turns_ok():
    limits = SafetyLimits(max_turns=10)
    ok, reason = limits.check_turn(5)
    assert ok
    assert reason == ""


def test_check_turns_exceeded():
    limits = SafetyLimits(max_turns=10)
    ok, reason = limits.check_turn(11)
    assert not ok
    assert "max_turns" in reason.lower() or "10" in reason


def test_check_cost_ok():
    limits = SafetyLimits(max_cost_usd=5.0)
    ok, reason = limits.check_cost(2.50)
    assert ok


def test_check_cost_exceeded():
    limits = SafetyLimits(max_cost_usd=1.0)
    ok, reason = limits.check_cost(1.50)
    assert not ok
    assert "cost" in reason.lower() or "budget" in reason.lower()


def test_no_cost_limit():
    limits = SafetyLimits()
    ok, _ = limits.check_cost(999.0)
    assert ok  # no limit set
