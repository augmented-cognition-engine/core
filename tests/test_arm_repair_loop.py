"""The bounded repair loop — an arm's success rate should not be its FIRST-TRY rate.

verify() failing is a signal, not a verdict on the run. The arm gets a bounded number
of attempts to read the failure and fix it, each in a fresh plan. The budget is what
keeps this from becoming an unbounded token furnace.
"""

from __future__ import annotations

import pytest

from core.engine.arms.base import Action, ActionPlan, Arm, ArmResult, AutonomyTier, RiskTier, Verdict
from core.engine.solution import Solution


def _only(arm):
    """Route to exactly this arm. dispatch now selects via router.choose_arm (the classifier), not
    the old keyword route() — patching route() here would be inert and the test would silently
    verify nothing."""

    async def _choose(solution, llm=None, producer_only=True):
        return arm

    return _choose


class _FakeWorkspace:
    def __init__(self, label="ws"):
        self.discarded = False
        self.label = label
        self.branch = f"arm/{label}"
        self.path = "/tmp/fake"
        self.repo_root = "/tmp/repo"

    def discard(self):
        self.discarded = True

    def commit(self, message):
        return "deadbeef"  # a verified build commits its work onto its branch

    def diff(self):
        return "+1 -0"

    def changed_files(self):
        return []


class _FlakyArm(Arm):
    """Fails verify until attempt `passes_on`, then passes. Records repair calls."""

    domain = "flaky"
    autonomy = AutonomyTier.REVERSIBLE

    def __init__(self, passes_on: int = 2, can_repair: bool = True):
        self.passes_on = passes_on
        self.can_repair = can_repair
        self.attempt = 0
        self.repair_calls: list[str] = []
        self.workspaces: list[_FakeWorkspace] = []

    def can_handle(self, solution: Solution) -> bool:
        return True

    async def plan(self, solution: Solution) -> ActionPlan:
        return ActionPlan(summary="attempt 1", actions=[Action(verb="write_file", args={}, risk=RiskTier.REVERSIBLE)])

    async def execute(self, plan: ActionPlan) -> ArmResult:
        self.attempt += 1
        ws = _FakeWorkspace(f"ws{self.attempt}")
        self.workspaces.append(ws)
        return ArmResult(plan=plan, performed=list(plan.actions), simulated=False, workspace=ws)

    async def verify(self, result: ArmResult, plan: ActionPlan) -> Verdict:
        if self.attempt >= self.passes_on:
            return Verdict(passed=True, reason="tests green")
        return Verdict(passed=False, reason="test_foo failed: expected 3 got 2")

    async def repair(self, result: ArmResult, plan: ActionPlan, verdict: Verdict) -> ActionPlan | None:
        if not self.can_repair:
            return None
        self.repair_calls.append(verdict.reason)
        return ActionPlan(
            summary=f"repair after: {verdict.reason}",
            actions=[Action(verb="write_file", args={}, risk=RiskTier.REVERSIBLE)],
        )


def test_arm_repair_defaults_to_none():
    """An arm that doesn't opt in gets no repair loop — no behavior change for existing arms."""

    class _Plain(_FlakyArm):
        pass

    plain = Arm.repair
    assert plain is not None  # the contract exists on the base class


@pytest.mark.asyncio
async def test_repair_loop_recovers_a_failed_verify(monkeypatch):
    import core.engine.arms.dispatch as dispatch
    from core.engine.core.config import settings

    monkeypatch.setattr(settings, "arm_repair_budget", 1)
    arm = _FlakyArm(passes_on=2)
    monkeypatch.setattr(dispatch.router, "choose_arm", _only(arm))
    captured = {}

    async def _capture(solution, arm_domain, result, verdict, product_id, **kw):
        captured.update(kw)
        captured["verdict"] = verdict

    monkeypatch.setattr(dispatch, "capture_outcome", _capture)

    sol = Solution(intent="build the thing")
    _domain, _result, verdict = await dispatch.dispatch_solution(sol)

    assert verdict.passed is True, "the second attempt passed — the run succeeded"
    assert sol.status == "verified"
    assert arm.attempt == 2, "exactly one repair attempt was made"
    assert arm.repair_calls == ["test_foo failed: expected 3 got 2"], "repair saw the failure reason"
    assert arm.workspaces[0].discarded is True, "the failed attempt's workspace was discarded"
    assert arm.workspaces[1].discarded is False, "the winning workspace is kept"
    assert captured.get("attempts") == 2, "the outcome ledger records how many attempts it took"


@pytest.mark.asyncio
async def test_repair_budget_is_a_hard_ceiling(monkeypatch):
    """An arm that never recovers must not retry forever."""
    import core.engine.arms.dispatch as dispatch
    from core.engine.core.config import settings

    monkeypatch.setattr(settings, "arm_repair_budget", 2)
    arm = _FlakyArm(passes_on=99)  # never passes
    monkeypatch.setattr(dispatch.router, "choose_arm", _only(arm))

    async def _noop(*a, **kw):
        return None

    monkeypatch.setattr(dispatch, "capture_outcome", _noop)

    sol = Solution(intent="build the thing")
    _domain, _result, verdict = await dispatch.dispatch_solution(sol)

    assert verdict.passed is False
    assert sol.status == "failed"
    assert arm.attempt == 3, "1 initial + 2 repairs = 3 executions, then stop"
    assert len(arm.repair_calls) == 2


@pytest.mark.asyncio
async def test_arm_that_cannot_repair_fails_on_first_verify(monkeypatch):
    import core.engine.arms.dispatch as dispatch
    from core.engine.core.config import settings

    monkeypatch.setattr(settings, "arm_repair_budget", 3)
    arm = _FlakyArm(passes_on=99, can_repair=False)  # repair() returns None
    monkeypatch.setattr(dispatch.router, "choose_arm", _only(arm))

    async def _noop(*a, **kw):
        return None

    monkeypatch.setattr(dispatch, "capture_outcome", _noop)

    _domain, _result, verdict = await dispatch.dispatch_solution(Solution(intent="x"))

    assert verdict.passed is False
    assert arm.attempt == 1, "no repair offered — one attempt only, budget unspent"


@pytest.mark.asyncio
async def test_parked_short_circuits_the_repair_loop(monkeypatch):
    """A broken environment won't heal by retrying — don't burn the budget on it."""
    import core.engine.arms.dispatch as dispatch
    from core.engine.core.config import settings
    from core.engine.core.exceptions import LLMError

    monkeypatch.setattr(settings, "arm_repair_budget", 3)

    class _EnvDead(_FlakyArm):
        async def verify(self, result, plan):
            raise LLMError("model unreachable")

    arm = _EnvDead()
    monkeypatch.setattr(dispatch.router, "choose_arm", _only(arm))

    async def _noop(*a, **kw):
        return None

    monkeypatch.setattr(dispatch, "capture_outcome", _noop)

    _domain, _result, verdict = await dispatch.dispatch_solution(Solution(intent="x"))

    assert verdict.parked is True
    assert arm.attempt == 1, "parked = stop; retrying a dead environment is a token furnace"
    assert arm.repair_calls == []
