import pytest

import core.engine.arms.registry as reg
from core.engine.arms.base import ActionPlan, Arm, ArmResult, Verdict
from core.engine.arms.registry import register_arm, route
from core.engine.solution import Solution


@pytest.fixture(autouse=True)
def _restore_registry():
    """Snapshot and restore _registry around each test — prevents cross-file registry leak.

    ScaffoldArm self-registers on import via @register_arm; the module is cached and
    won't re-register if _registry.clear() leaks into dispatch tests. This fixture
    mirrors _restore_engine_registry in conftest.py.
    """
    snapshot = list(reg._registry)
    yield
    reg._registry[:] = snapshot


def _make_arm(name, handles):
    @register_arm
    class _A(Arm):
        domain = name

        def can_handle(self, solution):
            return handles

        async def plan(self, solution):
            return ActionPlan(summary="")

        async def execute(self, plan):
            return ArmResult(plan=plan)

        async def verify(self, result, plan):
            return Verdict(passed=True)

    return _A


def test_route_selects_handling_arms():
    reg._registry.clear()
    _make_arm("code", handles=True)
    _make_arm("design", handles=False)
    arms = route(Solution(intent="x"))
    assert [a.domain for a in arms] == ["code"]
