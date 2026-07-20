"""The repair loop convened an 11-agent committee. Three times. To fix a docstring.

Build #5, with every model call fingerprinted:

    CALL  5-15  "Original task: You are a systems-thinking senior engineer..."   <- 11 committee calls
    CALL 16     "You are a systems-thinking senior engineer..."                  <- the shallow path
    CALL 17     "Produce the code change as strict JSON"                         <- codegen
    CALL 19-29  "Original task: ..."                                             <- 11 MORE

    BUILD5 DONE in 60.0 min with 31 llm calls — parked at its budget.

The generate phase takes (solution, profile, ctx). Both repair sites call it as:

    regen(None, plan, {...})          # <- the PLAN, in the PROFILE slot

So the reasoner was handed an ActionPlan and asked "is this shallow?". ActionPlan has no `risk`,
so the answer was no, so the committee convened — eleven agents, every repair pass, on work the
classifier had already called isolated and smoke-verifiable.

The bug is older than today and was HARMLESS until this morning: _phase_generate never read the
profile, so passing garbage in that slot cost nothing. Making the profile load-bearing turned a
latent type confusion into 22 wasted model calls and a parked build — which is the honest price of
a positional argument nobody was checking.

Repair must carry the depth of the work it is repairing. A docstring does not become an
architecture problem because the first attempt failed.
"""

from __future__ import annotations

import pytest

from core.engine.arms.base import Action, ActionPlan, ArmResult, RiskTier, Verdict
from core.engine.arms.strategy.profile import WorkProfile


def _shallow_plan() -> ActionPlan:
    return ActionPlan(
        summary="code: add a docstring",
        actions=[Action(verb="write_file", args={"path": "a.py"}, risk=RiskTier.REVERSIBLE)],
        test_cmd=["pytest"],
        surfaced_concerns=[],
        profile=WorkProfile(scope="module", novelty="extend", risk="isolated", verify_depth="smoke"),
    )


def _arm():
    from core.engine.arms.brain_hand_arm import BrainHandArm

    class _Concrete(BrainHandArm):
        domain = "code"

        def can_handle(self, s):
            return True

    arm = _Concrete()
    arm._intent = "add a docstring"
    arm.regen_profiles: list = []

    async def _generate(solution, profile, ctx):
        arm.regen_profiles.append(profile)
        return {"files": [{"path": "a.py", "content": "x = 1"}], "test_cmd": ["pytest"]}

    arm.phase["generate"] = _generate
    return arm


@pytest.mark.asyncio
async def test_the_OUTER_repair_hands_the_reasoner_a_real_profile():
    """The critic-refutation repair. It must pass the WorkProfile, not the ActionPlan."""
    arm = _arm()
    plan = _shallow_plan()
    refuted = Verdict(passed=False, reason="adversarial review: unreachable", source="critic")

    await arm.repair(ArmResult(plan=plan), plan, refuted)

    got = arm.regen_profiles[0]
    assert isinstance(got, WorkProfile), (
        f"the repair handed the reasoner a {type(got).__name__}. It must be the WorkProfile — an "
        "ActionPlan has no `risk`, so the depth check says 'not shallow' and an 11-agent committee "
        "convenes to repair a docstring."
    )
    assert got.risk == "isolated" and got.verify_depth == "smoke", "and it must be the ORIGINAL depth"


@pytest.mark.asyncio
async def test_the_INNER_repair_loop_also_keeps_the_depth(monkeypatch):
    """verify()'s own repair loop — the one that actually ran 11 committee calls, three times."""
    arm = _arm()
    plan = _shallow_plan()

    class _WS:
        path = "/tmp/x"

    async def _critic(concerns, ws):
        return True, []  # pass on the second look, so the loop runs exactly one repair

    calls = {"n": 0}

    async def _failing_then_passing(self, cmd, ws):  # a METHOD — self, cmd, ws
        calls["n"] += 1
        return (calls["n"] > 1), "boom"

    async def _run(self, plan, ws):
        return None

    arm._critic = _critic
    monkeypatch.setattr(
        "core.engine.arms.execution.runtime.ExecutionRuntime.run_tests", _failing_then_passing, raising=False
    )
    monkeypatch.setattr("core.engine.arms.execution.runtime.ExecutionRuntime.run", _run, raising=False)

    await arm.verify(ArmResult(plan=plan, workspace=_WS()), plan)

    assert arm.regen_profiles, "the inner loop must have repaired at least once"
    got = arm.regen_profiles[0]
    assert isinstance(got, WorkProfile), (
        f"the inner repair handed the reasoner a {type(got).__name__} — this is the bug that cost "
        "22 model calls and parked a 60-minute build"
    )
    assert got.risk == "isolated", "a docstring does not become an architecture problem on retry"


async def _noop_run():
    return None
