from __future__ import annotations


def test_actionplan_new_fields_default():
    from core.engine.arms.base import ActionPlan

    p = ActionPlan(summary="x")
    assert p.test_cmd is None
    assert p.surfaced_concerns == []
    p2 = ActionPlan(summary="x", test_cmd=["pytest", "-q"], surfaced_concerns=["security"])
    assert p2.test_cmd == ["pytest", "-q"]
    assert p2.surfaced_concerns == ["security"]


def test_codegen_parses_structured_files(monkeypatch):
    import asyncio

    import core.engine.arms.code_planner as cp

    class FakeLLM:
        async def complete_json(self, prompt, **kw):
            return {
                "files": [{"path": "a.py", "content": "x=1\n"}],
                "test_cmd": ["python", "-c", "import a"],
                "concerns": ["error-handling"],
            }

    monkeypatch.setattr(cp, "get_llm", lambda: FakeLLM())

    files, test_cmd, concerns = asyncio.run(cp.default_codegen("intent", "reasoning", {}))
    assert files == [{"path": "a.py", "content": "x=1\n"}]
    assert test_cmd == ["python", "-c", "import a"]
    assert concerns == ["error-handling"]


def test_critic_returns_covered_when_no_concerns():
    import asyncio

    import core.engine.arms.code_planner as cp

    class WS:
        path = "/tmp/nope"

    covered, uncovered = asyncio.run(cp.default_critic([], WS()))
    assert covered is True and uncovered == []


def _stub_arm(**over):
    from core.engine.arms.code_arm import CodeArm
    from core.engine.arms.strategy.profile import WorkProfile

    async def classifier(solution, conversation, overrides):
        return WorkProfile(scope="nearby", novelty="modify", risk="connected", verify_depth="unit")

    async def loader(intent, product_id="product:platform"):
        return {"ctx": "graph"}

    async def reasoner(intent, context, product_id="product:platform", profile=None):
        return "reasoned: cover errors+tests"

    async def codegen(intent, reasoning, context):
        return (
            [{"path": "m.py", "content": "def f():\n    return 1\n"}],
            ["python", "-c", "import m"],
            ["error-handling", "tests"],
        )

    async def critic(concerns, workspace):
        return True, []

    kw = dict(classifier=classifier, loader=loader, reasoner=reasoner, codegen=codegen, critic=critic, scorer=None)
    kw.update(over)
    return CodeArm(**kw)


def test_code_arm_can_handle():
    from core.engine.solution import Solution

    arm = _stub_arm()
    assert arm.can_handle(Solution(intent="write a code module", domain_hint="code")) is True
    assert arm.can_handle(Solution(intent="add code for X")) is True
    assert arm.can_handle(Solution(intent="paint a mural")) is False


def test_code_arm_plan_grounds_reasons_generates():
    import asyncio

    from core.engine.solution import Solution

    arm = _stub_arm()
    plan = asyncio.run(arm.plan(Solution(intent="add a helper", domain_hint="code")))
    assert plan.actions and plan.actions[0].verb == "write_file"
    assert plan.actions[0].args["path"] == "m.py"
    assert plan.test_cmd == ["python", "-c", "import m"]
    assert plan.surfaced_concerns == ["error-handling", "tests"]


import pytest


class _WS:
    branch = "arm/code-x"

    def __init__(self, tmp):
        self.path = str(tmp)


def _result_for(arm, plan, tmp):
    from core.engine.arms.base import ArmResult

    return ArmResult(plan=plan, performed=plan.actions, simulated=False, logs=[], workspace=_WS(tmp))


@pytest.mark.asyncio
async def test_verify_passes_when_tests_green_and_covered(tmp_path):
    from core.engine.arms.base import ActionPlan

    arm = _stub_arm()  # critic returns covered=True
    plan = ActionPlan(summary="code: x", test_cmd=["true"], surfaced_concerns=["tests"])
    v = await arm.verify(_result_for(arm, plan, tmp_path), plan)
    assert v.passed is True


@pytest.mark.asyncio
async def test_verify_repairs_then_passes(tmp_path):
    from core.engine.arms.base import ActionPlan

    calls = {"n": 0}

    async def codegen(intent, reasoning, context):
        calls["n"] += 1
        return ([{"path": "m.py", "content": "ok\n"}], ["true"], ["tests"])

    seq = [(False, ["tests"]), (True, [])]  # uncovered → repair → covered

    async def critic(concerns, ws):
        return seq.pop(0)

    arm = _stub_arm(codegen=codegen, critic=critic)
    plan = ActionPlan(summary="code: x", test_cmd=["true"], surfaced_concerns=["tests"])
    v = await arm.verify(_result_for(arm, plan, tmp_path), plan)
    assert v.passed is True
    assert calls["n"] == 1  # exactly one repair regenerate


@pytest.mark.asyncio
async def test_verify_fails_honestly_after_bounded_repairs(tmp_path):
    from core.engine.arms.base import ActionPlan

    async def codegen(intent, reasoning, context):
        return ([{"path": "m.py", "content": "still bad\n"}], ["false"], ["tests"])

    async def critic(concerns, ws):
        return False, ["tests"]  # never covered

    arm = _stub_arm(codegen=codegen, critic=critic)
    plan = ActionPlan(summary="code: x", test_cmd=["false"], surfaced_concerns=["tests"])
    v = await arm.verify(_result_for(arm, plan, tmp_path), plan)
    assert v.passed is False
    r = v.reason.lower()
    # the failure must be ACTIONABLE: what was run, and what it said
    assert "uncovered" in r and "tests" in r


def test_code_arm_default_classifier_is_graph_grounded():
    from core.engine.arms.code_arm import CodeArm
    from core.engine.arms.strategy.graph_classifier import graph_grounded_classifier

    assert CodeArm()._classifier is graph_grounded_classifier  # registered arms get real depth

    async def stub(solution, conversation, overrides):
        return None

    assert CodeArm(classifier=stub)._classifier is stub  # injection still wins
