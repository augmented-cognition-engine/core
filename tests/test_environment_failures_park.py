"""A dead model must not be able to disguise itself as bad work.

The live run that exposed this: a real spec went through ShipArm, the LLM returned garbage
(complete_json raised after 3 attempts), ship_planner CAUGHT it and returned zero concerns, the
ship gate then correctly refused a build with no concerns as "vacuous"... and the session reported:

    failed: "ship gate surfaced no production-readiness concerns — vacuous"
    needs_human: False

Every word of which blames the WORK. The truth was that the model never answered. The spec went
back in the queue as retryable, nobody was told, and the parked machinery — built precisely for
this — never got to see the LLMError, because a fail-open `except Exception` upstream had already
swallowed it.

That is the failure mode in general form: a fail-open catch inside an arm LAUNDERS an environment
failure into a work failure, and defeats the parked state from underneath. The catch has to know
the difference: degrade on bad data, PROPAGATE on a dead environment.
"""

from __future__ import annotations

import json

import pytest

from core.engine.core.exceptions import DatabaseError, LLMError


def _only(arm):
    """Route to exactly this arm. dispatch now selects via router.choose_arm (the classifier), not
    the old keyword route() — patching route() here would be inert and the test would silently
    verify nothing."""

    async def _choose(solution, llm=None, producer_only=True):
        return arm

    return _choose


@pytest.mark.parametrize(
    "exc",
    [
        LLMError("model unreachable"),
        DatabaseError("db refused"),
        TimeoutError("hung"),
        ConnectionError("socket died"),
        # The one that actually bit: complete_json gives up after 3 attempts of non-JSON. A model
        # that cannot produce parseable output three times running is a broken model, not a hard
        # question — we never found out anything, which is the definition of parked.
        json.JSONDecodeError("Failed after 3 attempts", "", 0),
    ],
)
def test_environmental_failures_are_recognised(exc):
    from core.engine.arms.failure import is_environmental

    assert is_environmental(exc) is True


@pytest.mark.parametrize("exc", [ValueError("bad plan"), KeyError("path"), AssertionError("wrong output")])
def test_work_failures_are_not_environmental(exc):
    from core.engine.arms.failure import is_environmental

    assert is_environmental(exc) is False


@pytest.mark.asyncio
async def test_ship_planner_propagates_a_dead_model_instead_of_reporting_no_concerns():
    """The exact production incident. An empty concern list from a DEAD model is not the same fact
    as an empty concern list from a model that looked and found nothing."""
    from core.engine.arms.ship_planner import assess_ship_readiness

    async def _dead_model(prompt):
        raise json.JSONDecodeError("Failed after 3 attempts", "", 0)

    with pytest.raises(json.JSONDecodeError):
        await assess_ship_readiness("ship the thing", reasoner=_dead_model)


@pytest.mark.asyncio
async def test_ship_planner_still_degrades_on_merely_bad_data():
    """The guard must not over-fire: a model that answers with junk SHAPE is a work-ish problem and
    the planner may still degrade to empty rather than parking the whole build."""
    from core.engine.arms.ship_planner import assess_ship_readiness

    async def _junk_shape(prompt):
        return "not a dict at all"

    concerns, actions = await assess_ship_readiness("ship the thing", reasoner=_junk_shape)
    assert concerns == [] and actions == []


@pytest.mark.asyncio
async def test_a_dead_model_during_planning_PARKS_the_build_end_to_end(monkeypatch):
    """The whole point: through dispatch, a dead model must come out as PARKED with a diagnosis —
    not as 'nothing to build' or 'vacuous gate', which both read as 'your work was bad'."""
    import core.engine.arms.dispatch as dispatch
    from core.engine.arms.base import Arm, AutonomyTier
    from core.engine.solution import Solution

    class _ModelDiesWhilePlanning(Arm):
        domain = "code"
        autonomy = AutonomyTier.REVERSIBLE

        def can_handle(self, s):
            return True

        async def plan(self, s):
            raise json.JSONDecodeError("Failed after 3 attempts", "", 0)

        async def execute(self, plan):
            raise AssertionError("must never execute — the model was dead")

        async def verify(self, result, plan):
            raise AssertionError("must never verify")

    monkeypatch.setattr(dispatch.router, "choose_arm", _only(_ModelDiesWhilePlanning()))

    async def _noop(*a, **kw):
        return None

    monkeypatch.setattr(dispatch, "capture_outcome", _noop)

    sol = Solution(intent="build the thing")
    _domain, _result, verdict = await dispatch.dispatch_solution(sol)

    assert verdict.parked is True, "a dead model is PARKED — we never found out whether the work was good"
    assert sol.status == "parked"
    assert verdict.passed is False
    assert "JSONDecodeError" in verdict.diagnosis or "Failed after 3 attempts" in verdict.diagnosis


@pytest.mark.asyncio
async def test_a_phase_killed_by_a_dead_model_does_not_become_nothing_to_build(monkeypatch):
    """BrainHandArm skips a failed phase non-fatally. That is right for a flaky optional phase and
    WRONG for a dead model: the plan then has no files, and dispatch reports 'no actions produced —
    nothing to build', which blames the work for the model's death."""
    from core.engine.arms.brain_hand_arm import BrainHandArm
    from core.engine.solution import Solution

    class _Arm(BrainHandArm):
        domain = "code"

        def can_handle(self, s):
            return True

    arm = _Arm()

    async def _dead_generate(solution, profile, ctx):
        raise LLMError("the model never answered")

    arm.phase["generate"] = _dead_generate
    monkeypatch.setattr("core.engine.arms.strategy.assemble.assemble", lambda p: ["generate"])

    with pytest.raises(LLMError):
        await arm.plan(Solution(intent="build the thing"))


@pytest.mark.asyncio
async def test_a_phase_that_fails_for_a_NON_environmental_reason_is_still_skipped(monkeypatch):
    """The guard must not make every flaky optional phase fatal — that was the reason the broad
    catch existed in the first place."""
    from core.engine.arms.brain_hand_arm import BrainHandArm
    from core.engine.solution import Solution

    class _Arm(BrainHandArm):
        domain = "code"

        def can_handle(self, s):
            return True

    arm = _Arm()

    async def _buggy_phase(solution, profile, ctx):
        raise ValueError("this optional phase has a bug")

    async def _good_generate(solution, profile, ctx):
        ctx["files"] = [{"path": "a.py", "content": "x = 1"}]
        return ctx

    arm.phase["architect"] = _buggy_phase
    arm.phase["generate"] = _good_generate
    monkeypatch.setattr("core.engine.arms.strategy.assemble.assemble", lambda p: ["architect", "generate"])

    plan = await arm.plan(Solution(intent="build the thing"))
    assert plan.actions, "a buggy optional phase must not kill a build the model could still do"
