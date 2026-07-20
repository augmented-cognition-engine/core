from core.engine.intelligence.depth_budget import _DEFAULT_BUDGET, budget_for_depth


def test_depth_1_has_smallest_budget():
    b = budget_for_depth(1)
    assert b.context_tokens == 400
    assert b.recall_multiplier == 0.5
    assert b.load_pm_context is False


def test_depth_3_auto_loads_pm_context():
    b = budget_for_depth(3)
    assert b.context_tokens == 800
    assert b.recall_multiplier == 1.0
    assert b.load_pm_context is True


def test_depth_4_full_budget():
    b = budget_for_depth(4)
    assert b.context_tokens == 1200
    assert b.recall_multiplier == 1.0
    assert b.load_pm_context is True


def test_out_of_range_depth_returns_default():
    b = budget_for_depth(99)
    assert b == _DEFAULT_BUDGET
    assert b.depth == 2


def test_depth_budget_is_frozen():
    import pytest

    b = budget_for_depth(2)
    with pytest.raises(AttributeError):
        b.context_tokens = 999


def test_all_depths_covered():
    budgets = [budget_for_depth(d) for d in range(1, 5)]
    token_budgets = [b.context_tokens for b in budgets]
    assert token_budgets == sorted(token_budgets)
    assert len(set(token_budgets)) == 4
