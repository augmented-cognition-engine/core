"""A build must not be able to run away silently.

MEASURED, on a real build, by counting every model call:

    call  1:  10.8s
    call  5:  48.5s
    call 10:  58.9s
    call 16:  91.6s     <- 8.5x slower than the first
    20 calls, 1126s of model time

That is the whole "24-minute hang" I chased all afternoon. It was never a deadlock and never a
wedge: a build makes ~20 model calls with large prompts (code context, graph, decisions), and on
the subprocess provider each costs 45-90s. The build was WORKING, exactly on schedule, and I called
it broken because nothing bounded it and nothing reported progress.

So the fix is not a provider ban — it is a BUDGET. A build that outruns its budget parks with a
diagnosis, which is exactly what parked is for: nobody judged that work, the workspace is preserved,
a human decides. TimeoutError is already classified environmental, so the existing machinery does
the rest.

The budget has to be generous enough that a legitimate slow build finishes (a CLI build genuinely
needs ~20 minutes) and tight enough that a runaway is caught the same day. Too tight is worse than
none: it would park real work and teach you to ignore parks.
"""

from __future__ import annotations

import asyncio

import pytest

from core.engine.arms.base import Action, ActionPlan, Arm, ArmResult, AutonomyTier, RiskTier, Verdict
from core.engine.solution import Solution


def _only(arm):
    async def _choose(solution, llm=None, producer_only=False):
        return arm

    return _choose


class _SlowArm(Arm):
    """Takes longer than its budget — the runaway build."""

    domain = "code"
    autonomy = AutonomyTier.REVERSIBLE

    def can_handle(self, s):
        return True

    async def plan(self, s):
        await asyncio.sleep(5)  # outruns the budget the test sets
        return ActionPlan(summary="x", actions=[Action(verb="w", args={}, risk=RiskTier.REVERSIBLE)])

    async def execute(self, plan):
        return ArmResult(plan=plan, performed=list(plan.actions), simulated=False)

    async def verify(self, result, plan):
        return Verdict(passed=True, reason="green")


@pytest.mark.asyncio
async def test_a_build_that_outruns_its_budget_is_PARKED_not_failed(monkeypatch):
    """Parked, not failed: nobody judged that work. Reporting it as a failure would blame the arm
    for a clock."""
    import core.engine.arms.dispatch as dispatch
    from core.engine.core.config import settings

    monkeypatch.setattr(settings, "arm_build_timeout_s", 1)  # 1s budget vs a 5s plan
    monkeypatch.setattr(dispatch.router, "choose_arm", _only(_SlowArm()))

    async def _noop(*a, **kw):
        return None

    monkeypatch.setattr(dispatch, "capture_outcome", _noop)

    sol = Solution(intent="build the thing")
    _domain, _result, verdict = await dispatch.dispatch_solution(sol)

    assert verdict.parked is True, "an over-budget build was never JUDGED — it is parked, not failed"
    assert verdict.passed is False
    assert sol.status == "parked"
    assert "budget" in verdict.diagnosis.lower() or "timed out" in verdict.diagnosis.lower()


class _FastArm(_SlowArm):
    async def plan(self, s):
        return ActionPlan(summary="x", actions=[Action(verb="w", args={}, risk=RiskTier.REVERSIBLE)])


@pytest.mark.asyncio
async def test_a_build_inside_its_budget_is_untouched(monkeypatch):
    """The budget must not cry wolf. A real CLI build legitimately needs ~20 minutes; parking honest
    work would teach a human to ignore parks, which is worse than having no budget at all."""
    import core.engine.arms.dispatch as dispatch
    from core.engine.core.config import settings

    monkeypatch.setattr(settings, "arm_build_timeout_s", 60)
    monkeypatch.setattr(settings, "arm_adversarial_review", False)
    monkeypatch.setattr(dispatch.router, "choose_arm", _only(_FastArm()))

    async def _noop(*a, **kw):
        return None

    monkeypatch.setattr(dispatch, "capture_outcome", _noop)

    _domain, _result, verdict = await dispatch.dispatch_solution(Solution(intent="build"))

    assert verdict.passed is True
    assert verdict.parked is False


def test_the_default_budget_fits_a_real_cli_build():
    """Measured: ~20 calls at 45-90s each. The default must not park an honest slow build."""
    from core.engine.core.config import settings

    assert settings.arm_build_timeout_s >= 1800, (
        "a real CLI build takes 15-25 minutes (20 calls x 45-90s, measured). A budget under 30 "
        "minutes would park legitimate work and train the human to ignore the parked signal."
    )
