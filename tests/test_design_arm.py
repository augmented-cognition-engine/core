from __future__ import annotations

import pytest

import core.engine.arms.design_planner as dp


def _only(arm):
    """Route to exactly this arm. dispatch now selects via router.choose_arm (the classifier), not
    the old keyword route() — patching route() here would be inert and the test would silently
    verify nothing."""

    async def _choose(solution, llm=None, producer_only=True):
        return arm

    return _choose


class _FakeLLM:
    def __init__(self, payload):
        self._payload = payload

    async def complete_json(self, prompt):
        return self._payload


@pytest.mark.asyncio
async def test_codegen_returns_files_none_testcmd_concerns(monkeypatch):
    monkeypatch.setattr(
        dp,
        "get_llm",
        lambda: _FakeLLM(
            {
                "files": [
                    {"path": "core/ui/canvas/src/app/X.tsx", "content": "import { Card } from '../design/components'\n"}
                ],
                "concerns": ["loading via AmbientWorking"],
            }
        ),
    )
    files, test_cmd, concerns = await dp.default_codegen("a panel", "compose Card", {"catalog": "Card"})
    assert files and files[0]["path"].endswith("X.tsx")
    assert test_cmd is None  # design uses the in-process critic, not a worktree subprocess
    assert concerns == ["loading via AmbientWorking"]


@pytest.mark.asyncio
async def test_critic_flags_mechanical_violation(monkeypatch, tmp_path):
    # Build a fake workspace whose app surface has a hex literal.
    app = tmp_path / "core" / "ui" / "canvas" / "src" / "app"
    app.mkdir(parents=True)
    (app / "Bad.tsx").write_text("export const B = () => <div style={{ color: '#fff000' }} />\n")

    class _WS:  # minimal workspace stub
        path = str(tmp_path)

    monkeypatch.setattr(dp, "get_llm", lambda: _FakeLLM({"uncovered": []}))  # LLM finds nothing
    ok, uncovered = await dp.default_critic(["loading via AmbientWorking"], _WS())
    assert ok is False
    assert any("hex" in u for u in uncovered)  # mechanical scan caught it


@pytest.mark.asyncio
async def test_critic_passes_clean_surface(monkeypatch, tmp_path):
    app = tmp_path / "core" / "ui" / "canvas" / "src" / "app"
    app.mkdir(parents=True)
    (app / "Good.tsx").write_text(
        "import { Card, Button } from '../design/components'\nexport const G = () => <Card><Button>Go</Button></Card>\n"
    )

    class _WS:
        path = str(tmp_path)

    monkeypatch.setattr(dp, "get_llm", lambda: _FakeLLM({"uncovered": []}))
    ok, uncovered = await dp.default_critic([], _WS())
    assert ok is True and uncovered == []


@pytest.mark.asyncio
async def test_critic_surfaces_llm_nonmechanical(monkeypatch, tmp_path):
    app = tmp_path / "core" / "ui" / "canvas" / "src" / "app"
    app.mkdir(parents=True)
    (app / "Good.tsx").write_text("import { Card } from '../design/components'\nexport const G = () => <Card/>\n")

    class _WS:
        path = str(tmp_path)

    monkeypatch.setattr(dp, "get_llm", lambda: _FakeLLM({"uncovered": ["loading state does not use AmbientWorking"]}))
    ok, uncovered = await dp.default_critic(["loading via AmbientWorking"], _WS())
    assert ok is False
    assert any("AmbientWorking" in u for u in uncovered)


from core.engine.solution import Solution


def _stub_design_arm():
    from core.engine.arms.design_arm import DesignArm

    async def classifier(solution, conversation, overrides):
        from core.engine.arms.strategy.profile import WorkProfile

        return WorkProfile(scope="nearby", novelty="extend", risk="isolated", verify_depth="smoke")

    async def loader(i, product_id="product:platform"):
        return {"catalog": "Card, Button, Stack"}

    async def reasoner(i, c, product_id="product:platform"):
        return "compose Card+Button"

    async def codegen(i, r, c):
        return (
            [
                {
                    "path": "core/ui/canvas/src/app/Panel.tsx",
                    "content": "import { Card } from '../design/components'\nexport const P = () => <Card/>\n",
                }
            ],
            None,
            ["composed from primitives"],
        )

    async def critic(concerns, ws):
        return True, []

    return DesignArm(
        classifier=classifier, loader=loader, reasoner=reasoner, codegen=codegen, critic=critic, scorer=None
    )


def test_design_can_handle_design_not_code():
    arm = _stub_design_arm()
    assert arm.can_handle(Solution(intent="design a settings panel", domain_hint=None)) is True
    assert arm.can_handle(Solution(intent="x", domain_hint="design")) is True
    assert arm.can_handle(Solution(intent="fix a python bug", domain_hint="code")) is False


@pytest.mark.asyncio
async def test_design_plan_composes_surface_with_no_test_cmd():
    arm = _stub_design_arm()
    plan = await arm.plan(Solution(intent="design a panel", domain_hint="design"))
    assert plan.test_cmd is None  # gate is the critic, not a subprocess
    assert plan.actions and plan.actions[0].args["path"].endswith("Panel.tsx")
    assert "composed from primitives" in plan.surfaced_concerns


def test_design_arm_default_wires_planner_and_classifier():
    import core.engine.arms.design_planner as dp
    from core.engine.arms.design_arm import DesignArm
    from core.engine.arms.strategy.graph_classifier import graph_grounded_classifier

    arm = DesignArm()
    assert arm._classifier is graph_grounded_classifier
    assert arm._critic is dp.default_critic


def test_design_not_shadowed_by_code_substring_in_routing():
    # C1: a real design spec mentioning "code" (domain_hint None, as in prod) must route to
    # DesignArm, not be shadowed by the earlier-registered CodeArm's weaker match.
    import core.engine.arms.registry as reg

    reg._registry.clear()
    reg._loaded = False
    arms = reg.route(Solution(intent="design the code review panel", domain_hint=None))
    assert arms and arms[0].domain == "design", [a.domain for a in arms]


def test_routing_score_whole_word_not_substring():
    # "encoder" must NOT match CodeArm's "code" (substring would; whole-word doesn't).
    from core.engine.arms.code_arm import CodeArm

    assert CodeArm().match_score(Solution(intent="tune the encoder settings", domain_hint=None)) == 0


@pytest.mark.asyncio
async def test_critic_fails_closed_when_mechanical_scan_errors(monkeypatch, tmp_path):
    # C2: if the mechanical scan raises, the gate must FAIL (never silently pass slop).
    import core.engine.arms.design_enforce as de

    def boom(root):
        raise RuntimeError("scanner exploded")

    monkeypatch.setattr(de, "scan_design_violations", boom)
    monkeypatch.setattr(dp, "get_llm", lambda: _FakeLLM({"uncovered": []}))

    class _WS:
        path = str(tmp_path)

    ok, uncovered = await dp.default_critic([], _WS())
    assert ok is False
    assert any("did not run" in u for u in uncovered)


@pytest.mark.asyncio
async def test_dispatch_fails_on_empty_build(monkeypatch):
    # C3: an arm that produces no actions must NOT be marked "built" — dispatch fails it
    # (at the lifecycle layer) and never runs execute/verify.
    import core.engine.arms.dispatch as dispatch
    from core.engine.arms.base import ActionPlan, Arm, AutonomyTier

    class _EmptyArm(Arm):
        domain = "code"
        autonomy = AutonomyTier.REVERSIBLE

        def can_handle(self, solution):
            return True

        async def plan(self, solution):
            return ActionPlan(summary="x", actions=[])

        async def execute(self, plan):
            raise AssertionError("execute must not run for an empty build")

        async def verify(self, result, plan):
            raise AssertionError("verify must not run for an empty build")

    captured = {}

    async def fake_capture(solution, domain, result, verdict, product_id, **kw):
        captured["verdict"] = verdict

    monkeypatch.setattr(dispatch.router, "choose_arm", _only(_EmptyArm()))
    monkeypatch.setattr(dispatch, "capture_outcome", fake_capture)

    domain, result, verdict = await dispatch.dispatch_solution(
        Solution(intent="design a panel"), product_id="product:platform"
    )
    assert verdict.passed is False
    assert "nothing to build" in verdict.reason
    assert captured["verdict"].passed is False  # outcome recorded as a failed build
