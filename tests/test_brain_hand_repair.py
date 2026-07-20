"""The critic's refutation must reach the arm — otherwise the outer repair loop is inert.

BrainHandArm.verify() already repairs against what IT can see: failing tests and uncovered
concerns (max_repair_passes, in-workspace regeneration). But the adversarial critic runs AFTER
verify() returns, so its refutation ("this is unreachable — nothing registers it") is a signal
the inner loop has never seen and cannot act on.

Without an outer repair, a critic refutation goes straight to `failed` and the build dies with a
fixable defect. With one, the arm regenerates against the critic's actual concerns.

The discipline: repair ONLY the signal the inner loop has not already spent its budget on. Re-
running the same generation against the same failing tests it just failed three times is a token
furnace, not a repair.
"""

from __future__ import annotations

import pytest

from core.engine.arms.base import ActionPlan, ArmResult, Verdict


class _Arm:
    """A BrainHandArm with a stubbed generate phase — we assert on what gets fed to it."""

    def __new__(cls):
        from core.engine.arms.brain_hand_arm import BrainHandArm

        class _Concrete(BrainHandArm):
            domain = "test"

            def can_handle(self, solution):
                return True

        arm = _Concrete()
        arm.regen_calls = []

        async def _generate(solution, plan, ctx):
            arm.regen_calls.append(ctx)
            return {"files": [{"path": "fixed.py", "content": "registered = True"}], "test_cmd": ["pytest"]}

        arm.phase["generate"] = _generate
        arm._intent = "add the widget"
        return arm


def _plan():
    return ActionPlan(summary="test: add the widget", actions=[], test_cmd=["pytest"], surfaced_concerns=["c1"])


@pytest.mark.asyncio
async def test_repair_regenerates_against_the_critics_concerns():
    arm = _Arm()
    plan = _plan()
    refuted = Verdict(
        passed=False,
        reason="adversarial review: the new tool is never registered — unreachable in prod",
        source="critic",
    )

    repaired = await arm.repair(ArmResult(plan=plan), plan, refuted)

    assert repaired is not None, "a critic refutation is a FIXABLE signal — the arm must get to try"
    assert repaired.actions, "the repaired plan must carry the regenerated files"
    assert repaired.actions[0].args["path"] == "fixed.py"

    ctx = arm.regen_calls[0]
    assert "never registered" in ctx["repair"], "the critic's ACTUAL concern must reach the generator"
    assert ctx["intent"] == "add the widget", "regeneration must stay on-target, not drift"


@pytest.mark.asyncio
async def test_repair_declines_a_failure_the_inner_loop_already_exhausted():
    """verify()'s own repair loop already spent 3 passes on these tests. Re-running the same
    generation against the same signal burns tokens and changes nothing."""
    arm = _Arm()
    plan = _plan()
    exhausted = Verdict(passed=False, reason="unresolved after 3 repair(s): tests_ok=False", source="arm")

    repaired = await arm.repair(ArmResult(plan=plan), plan, exhausted)

    assert repaired is None, "do not re-fight a battle the inner loop already lost three times"
    assert arm.regen_calls == [], "and do not spend a single LLM call finding that out"


@pytest.mark.asyncio
async def test_repair_declines_when_there_is_no_generate_phase():
    from core.engine.arms.brain_hand_arm import BrainHandArm

    class _NoGen(BrainHandArm):
        domain = "nogen"

        def can_handle(self, solution):
            return True

    arm = _NoGen()
    plan = _plan()
    refuted = Verdict(passed=False, reason="adversarial review: broken", source="critic")

    assert await arm.repair(ArmResult(plan=plan), plan, refuted) is None


@pytest.mark.asyncio
async def test_repair_is_non_fatal_when_regeneration_blows_up():
    arm = _Arm()

    async def _boom(solution, plan, ctx):
        raise RuntimeError("the model returned garbage")

    arm.phase["generate"] = _boom
    plan = _plan()
    refuted = Verdict(passed=False, reason="adversarial review: broken", source="critic")

    assert await arm.repair(ArmResult(plan=plan), plan, refuted) is None, (
        "a failed repair is a failed build, not a crash"
    )


def test_verdict_carries_its_source():
    """Without this the arm cannot tell WHO refuted it, and 'repair only new signals' is unwriteable."""
    assert Verdict(passed=True).source == "arm"  # the default: the arm judged itself


@pytest.mark.asyncio
async def test_the_critic_stamps_its_verdicts_as_critic_sourced():
    from core.engine.arms.critic import CriticVerdict, adversarial_verify
    from core.engine.solution import Solution

    class _LLM:
        async def complete_structured(self, prompt, schema, model=None, max_tokens=4096):
            return CriticVerdict(sound=False, blocking_concerns=["unreachable"], reasoning="r")

    class _WS:
        def diff(self):
            return "+x"

        def discard(self):
            pass

        def changed_files(self):
            return []

    plan = _plan()
    result = ArmResult(plan=plan, workspace=_WS())
    verdict = await adversarial_verify(Solution(intent="i"), plan, result, llm=_LLM())

    assert verdict.source == "critic", "the arm's repair() branches on this — it must be set"
