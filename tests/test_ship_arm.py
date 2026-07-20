"""ShipArm — the production-readiness GATE (Phase 5). Assesses across security/testing/observability/
devops/scale; vacuous (zero-concern) gate fails; routes over the MAKE arms on ship vocabulary.
See docs/superpowers/specs/2026-06-23-ship-arm-design.md."""

from __future__ import annotations

import pytest

from core.engine.solution import Solution


def _only(arm):
    """Route to exactly this arm. dispatch now selects via router.choose_arm (the classifier), not
    the old keyword route() — patching route() here would be inert and the test would silently
    verify nothing."""

    async def _choose(solution, llm=None, producer_only=True):
        return arm

    return _choose


async def _fake_assess(intent):
    return (
        ["Security: no SBOM / dependency CVE scan", "Observability: no error metrics on the failure path"],
        ["generate an SPDX SBOM and gate on NVD", "emit error-rate metrics"],
    )


# ── ship_planner ────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_assess_returns_concerns_and_actions():
    from core.engine.arms.ship_planner import assess_ship_readiness

    async def reasoner(prompt):
        assert "production-readiness" in prompt.lower()
        return {"concerns": ["Security: injection on $query", " "], "actions": ["parameterize", ""]}

    concerns, actions = await assess_ship_readiness("ship the search endpoint", reasoner=reasoner)
    assert concerns == ["Security: injection on $query"]  # blank stripped
    assert actions == ["parameterize"]


@pytest.mark.asyncio
async def test_assess_fail_safe_and_empty():
    from core.engine.arms.ship_planner import assess_ship_readiness

    async def boom(prompt):
        raise RuntimeError("llm down")

    assert await assess_ship_readiness("x", reasoner=boom) == ([], [])
    assert await assess_ship_readiness("  ", reasoner=boom) == ([], [])  # empty intent → no call


# ── ShipArm routing ───────────────────────────────────────────────────────────


def test_match_score_outscores_code_on_ship_vocab():
    from core.engine.arms.code_arm import CodeArm
    from core.engine.arms.ship_arm import ShipArm

    sol = Solution(intent="harden the auth service for production before go-live")
    ship, code = ShipArm(), CodeArm()
    assert ship.can_handle(sol)
    assert ship.match_score(sol) > code.match_score(sol)


def test_does_not_handle_pure_code_intent():
    from core.engine.arms.ship_arm import ShipArm

    assert not ShipArm().can_handle(Solution(intent="write a function to parse the CSV"))


def test_route_picks_ship_arm_for_ship_solution():
    from core.engine.arms.registry import route

    arms = route(Solution(intent="harden and deploy the payments service to production"))
    assert arms, "expected a routed arm"
    assert arms[0].domain == "ship"


# ── ShipArm phase + gate (execute/verify) ─────────────────────────────────────


@pytest.mark.asyncio
async def test_phase_assess_populates_concerns():
    from core.engine.arms.ship_arm import ShipArm

    arm = ShipArm(assessor=_fake_assess)
    ctx = await arm._phase_assess(Solution(intent="ship the API"), None, {})
    assert ctx["concerns"][0].startswith("Security:")
    assert ctx["ship_actions"]


@pytest.mark.asyncio
async def test_verify_fails_vacuous_gate():
    from core.engine.arms.base import ActionPlan
    from core.engine.arms.ship_arm import ShipArm

    arm = ShipArm(assessor=_fake_assess)
    v = await arm.verify(result=None, plan=ActionPlan(summary="ship: x", surfaced_concerns=[]))
    assert v.passed is False
    assert "vacuous" in v.reason


@pytest.mark.asyncio
async def test_verify_passes_substantive_gate():
    from core.engine.arms.base import ActionPlan
    from core.engine.arms.ship_arm import ShipArm

    arm = ShipArm(assessor=_fake_assess)
    plan = ActionPlan(summary="ship: x", surfaced_concerns=["Security: no SBOM", "Scale: no backoff cap"])
    v = await arm.verify(result=None, plan=plan)
    assert v.passed is True
    assert "2 production-readiness concern" in v.reason


@pytest.mark.asyncio
async def test_execute_is_simulated_no_mutation():
    from core.engine.arms.base import ActionPlan
    from core.engine.arms.ship_arm import ShipArm

    arm = ShipArm(assessor=_fake_assess)
    res = await arm.execute(ActionPlan(summary="ship: x", surfaced_concerns=["Security: gap"]))
    assert res.simulated is True
    assert res.performed == []


# ── through-dispatch integration (the review-found BLOCKER: the gate was unreachable behind the
#    "no actions = nothing to build" guard; a gate produces no file-actions by design) ──────────────


class _FakeGateArm:
    domain = "ship"
    is_gate = True

    async def plan(self, solution):
        from core.engine.arms.base import ActionPlan

        return ActionPlan(summary="ship: x", actions=[], surfaced_concerns=["Security: no SBOM"])

    async def execute(self, plan):
        from core.engine.arms.base import ArmResult

        return ArmResult(plan=plan, performed=[], simulated=True)

    async def verify(self, result, plan):
        from core.engine.arms.base import Verdict

        return Verdict(passed=True, reason="ship gate surfaced 1 concern")


class _FakeProducerArm(_FakeGateArm):
    domain = "code"
    is_gate = False


@pytest.mark.asyncio
async def test_dispatch_honors_gate_arm_verdict_not_empty_actions(monkeypatch):
    """A GATE arm produces no file-actions, but dispatch must run its execute/verify and return the
    surfaced-concerns verdict — NOT the 'no actions produced — nothing to build' short-circuit."""
    import core.engine.arms.dispatch as d

    async def _noop(*a, **k):
        return None

    monkeypatch.setattr(d.router, "choose_arm", _only(_FakeGateArm()))
    monkeypatch.setattr(d, "capture_outcome", _noop)
    out = await d.dispatch_solution(Solution(intent="harden the API for production"), "product:test")
    assert out is not None
    _domain, _result, verdict = out
    assert verdict.passed is True
    assert "ship gate" in verdict.reason
    assert "nothing to build" not in verdict.reason


@pytest.mark.asyncio
async def test_dispatch_producer_empty_actions_still_fails(monkeypatch):
    """The guard must STILL fire for a PRODUCER arm that produced nothing — only gates are exempt."""
    import core.engine.arms.dispatch as d

    async def _noop(*a, **k):
        return None

    monkeypatch.setattr(d.router, "choose_arm", _only(_FakeProducerArm()))
    monkeypatch.setattr(d, "capture_outcome", _noop)
    _domain, _result, verdict = await d.dispatch_solution(Solution(intent="write a parser"), "product:test")
    assert verdict.passed is False
    assert "no actions produced" in verdict.reason
