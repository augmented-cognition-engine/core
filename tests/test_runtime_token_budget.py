"""Tests for token budget auto-continue."""

from core.engine.runtime.token_budget import TokenBudget


def test_no_budget():
    budget = TokenBudget(total=None)
    assert budget.should_continue(5000) == "stop"


def test_continue_below_threshold():
    budget = TokenBudget(total=100000)
    assert budget.should_continue(50000) == "continue"


def test_stop_above_threshold():
    budget = TokenBudget(total=100000)
    assert budget.should_continue(95000) == "stop"  # > 90%


def test_diminishing_returns():
    budget = TokenBudget(total=100000)
    budget.record_continuation(50000)
    budget.record_continuation(50200)
    budget.record_continuation(50300)
    budget.record_continuation(50350)
    # 4 continuations, last two deltas < 500 -> diminishing
    result = budget.should_continue(50400)
    assert result == "stop"


def test_nudge_message():
    budget = TokenBudget(total=100000)
    msg = budget.get_nudge_message(50000)
    assert "continue" in msg.lower() or "resume" in msg.lower()
