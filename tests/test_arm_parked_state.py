"""The parked terminal state — 'the environment broke' is not 'the work was wrong'.

A failed build means the arm produced something that doesn't hold up: discard it.
A PARKED build means we never got to find out — the LLM timed out, the DB was down,
the disk was full. Retrying is pointless and discarding the workspace destroys
evidence. Parked is the state an unattended run leaves behind for a human.
"""

from __future__ import annotations

import pytest

from core.engine.arms.base import Action, ActionPlan, Arm, ArmResult, AutonomyTier, RiskTier, Verdict
from core.engine.core.exceptions import DatabaseError, LLMError
from core.engine.solution import Solution


def _only(arm):
    """Route to exactly this arm. dispatch now selects via router.choose_arm (the classifier), not
    the old keyword route() — patching route() here would be inert and the test would silently
    verify nothing."""

    async def _choose(solution, llm=None, producer_only=True):
        return arm

    return _choose


def test_verdict_carries_parked_and_diagnosis():
    v = Verdict(passed=False, reason="boom")
    assert v.parked is False  # backward-compatible default
    assert v.diagnosis == ""

    p = Verdict(passed=False, reason="llm timeout", parked=True, diagnosis="LLM unreachable — check ANTHROPIC creds")
    assert p.parked is True
    assert "unreachable" in p.diagnosis


@pytest.mark.parametrize(
    "exc",
    [
        LLMError("llm timed out"),
        DatabaseError("surreal refused the connection"),
        TimeoutError("hung"),
        ConnectionError("socket closed"),
        OSError("no space left on device"),
    ],
)
def test_environmental_exceptions_park(exc):
    from core.engine.arms.dispatch import _is_environmental

    assert _is_environmental(exc) is True


@pytest.mark.parametrize(
    "exc",
    [ValueError("the plan referenced a file that does not exist"), KeyError("path"), AssertionError("bad output")],
)
def test_work_exceptions_do_not_park(exc):
    from core.engine.arms.dispatch import _is_environmental

    assert _is_environmental(exc) is False


class _FakeWorkspace:
    def __init__(self):
        self.discarded = False
        self.branch = "arm/fake-1"
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


class _EnvBrokenArm(Arm):
    """Executes fine, but the environment dies during verify."""

    domain = "envbroken"
    autonomy = AutonomyTier.REVERSIBLE

    def __init__(self):
        self.workspace = _FakeWorkspace()

    def can_handle(self, solution: Solution) -> bool:
        return True

    async def plan(self, solution: Solution) -> ActionPlan:
        return ActionPlan(summary="s", actions=[Action(verb="write_file", args={}, risk=RiskTier.REVERSIBLE)])

    async def execute(self, plan: ActionPlan) -> ArmResult:
        return ArmResult(plan=plan, performed=list(plan.actions), simulated=False, workspace=self.workspace)

    async def verify(self, result: ArmResult, plan: ActionPlan) -> Verdict:
        raise LLMError("the model never answered")


@pytest.mark.asyncio
async def test_dispatch_parks_on_environmental_failure_and_keeps_the_workspace(monkeypatch):
    """The load-bearing case: an unattended run hits a broken environment. It must NOT
    report 'failed' (which reads as 'the code was wrong') and must NOT discard the
    workspace (which destroys the evidence a human needs)."""
    import core.engine.arms.dispatch as dispatch

    arm = _EnvBrokenArm()
    monkeypatch.setattr(dispatch.router, "choose_arm", _only(arm))
    captured = {}

    async def _fake_capture(solution, arm_domain, result, verdict, product_id, **kw):
        captured["verdict"] = verdict

    monkeypatch.setattr(dispatch, "capture_outcome", _fake_capture)

    sol = Solution(intent="build the thing")
    domain, result, verdict = await dispatch.dispatch_solution(sol)

    assert domain == "envbroken"
    assert verdict.passed is False
    assert verdict.parked is True, "an environmental failure must park, not fail"
    assert "never answered" in verdict.diagnosis
    assert sol.status == "parked"
    assert arm.workspace.discarded is False, "parked work is preserved for the human"
    assert captured["verdict"].parked is True, "the outcome ledger records the parked state"


class _BadWorkArm(_EnvBrokenArm):
    """The work itself is wrong — a normal failure, not a park."""

    domain = "badwork"

    async def verify(self, result: ArmResult, plan: ActionPlan) -> Verdict:
        raise ValueError("the arm wrote a file outside the workspace")


@pytest.mark.asyncio
async def test_dispatch_fails_and_discards_on_work_failure(monkeypatch):
    import core.engine.arms.dispatch as dispatch

    arm = _BadWorkArm()
    monkeypatch.setattr(dispatch.router, "choose_arm", _only(arm))

    async def _noop(*a, **kw):
        return None

    monkeypatch.setattr(dispatch, "capture_outcome", _noop)

    sol = Solution(intent="build the thing")
    _domain, _result, verdict = await dispatch.dispatch_solution(sol)

    assert verdict.passed is False
    assert verdict.parked is False
    assert sol.status == "failed"
    assert arm.workspace.discarded is True, "a failed attempt is reversible — throw it away"
