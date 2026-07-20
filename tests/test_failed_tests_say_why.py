"""'tests_ok=False' is not a reason. It is a shrug.

Build #6 — the first build to get all the way through reasoning, codegen and the no-slop critic
(uncovered=[], the gate was SATISFIED) — died like this:

    reason: unresolved after 3 repair(s): tests_ok=False, uncovered=[]

The arm ran a test command, it failed, and the output was thrown away. So the human is told the
build failed and given nothing to act on: not the command, not the error, not a line number.

The repair loop DOES see the output (it feeds `tests={out!r}` back into regeneration). Only the
person is kept in the dark, which is precisely backwards: the loop gets three attempts to read the
error and a human gets none.

An unactionable failure is a lying instrument in the same family as everything else this codebase
keeps finding — it reports that something is wrong while withholding the one fact that would let
you fix it.
"""

from __future__ import annotations

import pytest

from core.engine.arms.base import Action, ActionPlan, ArmResult, RiskTier
from core.engine.arms.strategy.profile import WorkProfile


def _plan() -> ActionPlan:
    return ActionPlan(
        summary="code: add a docstring",
        actions=[Action(verb="write_file", args={"path": "a.py"}, risk=RiskTier.REVERSIBLE)],
        test_cmd=["pytest", "-q", "tests/test_thing.py"],
        surfaced_concerns=[],
        profile=WorkProfile(scope="module", novelty="extend", risk="isolated", verify_depth="smoke"),
    )


@pytest.mark.asyncio
async def test_a_failing_test_command_reports_the_command_AND_the_output(monkeypatch):
    from core.engine.arms.brain_hand_arm import BrainHandArm

    class _Arm(BrainHandArm):
        domain = "code"

        def can_handle(self, s):
            return True

    arm = _Arm()
    arm._intent = "add a docstring"

    async def _critic(concerns, ws):
        return True, []  # the no-slop gate is HAPPY — tests are the only thing failing

    async def _regen(solution, profile, ctx):
        return {"files": [{"path": "a.py", "content": "x = 1"}], "test_cmd": ["pytest", "-q"]}

    arm._critic = _critic
    arm.phase["generate"] = _regen

    async def _always_fails(self, cmd, ws):
        return False, "ImportError: No module named 'surrealdb'\n1 error in 0.03s"

    async def _run(self, plan, ws):
        return None

    monkeypatch.setattr("core.engine.arms.execution.runtime.ExecutionRuntime.run_tests", _always_fails)
    monkeypatch.setattr("core.engine.arms.execution.runtime.ExecutionRuntime.run", _run)

    class _WS:
        path = "/tmp/x"

    verdict = await arm.verify(ArmResult(plan=_plan(), workspace=_WS()), _plan())

    assert verdict.passed is False
    assert "surrealdb" in verdict.reason or "ImportError" in verdict.reason, (
        "the TEST OUTPUT must reach the human. 'tests_ok=False' tells them a build failed and "
        "withholds the only fact that would let them fix it — while the repair loop, which already "
        "gets the output, has been reading it the whole time."
    )
    assert "pytest" in verdict.reason, "and say WHAT was run, so it can be reproduced by hand"
