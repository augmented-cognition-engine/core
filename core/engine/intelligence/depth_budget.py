from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class DepthBudget:
    depth: int
    context_tokens: int
    recall_multiplier: float
    load_pm_context: bool


_BUDGETS: dict[int, DepthBudget] = {
    1: DepthBudget(depth=1, context_tokens=400, recall_multiplier=0.5, load_pm_context=False),
    2: DepthBudget(depth=2, context_tokens=600, recall_multiplier=0.75, load_pm_context=False),
    3: DepthBudget(depth=3, context_tokens=800, recall_multiplier=1.0, load_pm_context=True),
    4: DepthBudget(depth=4, context_tokens=1200, recall_multiplier=1.0, load_pm_context=True),
}
_DEFAULT_BUDGET = _BUDGETS[2]


def budget_for_depth(depth: int) -> DepthBudget:
    return _BUDGETS.get(depth, _DEFAULT_BUDGET)
