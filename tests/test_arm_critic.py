"""The adversarial critic — the builder does not grade its own homework.

arm.verify() is written by the same reasoning that wrote the plan, so it inherits the
plan's blind spots (green tests, silent prod bug — the failure mode that showed up in
EVERY build of the June 22 session). The critic is a FRESH context with a refutation
stance: it never sees the builder's reasoning, only the intent and the diff.

Fail CLOSED: a critic that cannot run has not approved anything.
"""

from __future__ import annotations

import pytest

from core.engine.arms.base import Action, ActionPlan, ArmResult, RiskTier, Verdict
from core.engine.solution import Solution


def _only(arm):
    """Route to exactly this arm. dispatch now selects via router.choose_arm (the classifier), not
    the old keyword route() — patching route() here would be inert and the test would silently
    verify nothing."""

    async def _choose(solution, llm=None, producer_only=True):
        return arm

    return _choose


class _FakeWorkspace:
    def __init__(self, diff="+ def foo(): pass"):
        self._diff = diff
        self.discarded = False
        self.branch = "arm/x"
        self.path = "/tmp/fake"
        self.repo_root = "/tmp/repo"

    def diff(self):
        return self._diff

    def discard(self):
        self.discarded = True

    def commit(self, message):
        return "deadbeef"  # a verified build commits its work onto its branch

    def changed_files(self):
        return ["a.py"]


def _result():
    plan = ActionPlan(
        summary="add foo", actions=[Action(verb="write_file", args={"path": "a.py"}, risk=RiskTier.REVERSIBLE)]
    )
    return plan, ArmResult(plan=plan, performed=list(plan.actions), simulated=False, workspace=_FakeWorkspace())


class _FakeLLM:
    """Records the prompt it was given so we can assert on the refutation stance."""

    def __init__(self, verdict=None, raises=None):
        self._verdict = verdict
        self._raises = raises
        self.prompts: list[str] = []
        self.models: list[str | None] = []

    async def complete_structured(self, prompt, schema, model=None, max_tokens=4096):
        self.prompts.append(prompt)
        self.models.append(model)
        if self._raises:
            raise self._raises
        return self._verdict


@pytest.mark.asyncio
async def test_critic_confirms_a_sound_build():
    from core.engine.arms.critic import CriticVerdict, adversarial_verify

    llm = _FakeLLM(CriticVerdict(sound=True, blocking_concerns=[], reasoning="the diff does what the intent says"))
    plan, result = _result()

    verdict = await adversarial_verify(Solution(intent="add foo"), plan, result, llm=llm)

    assert verdict.passed is True
    assert verdict.parked is False


@pytest.mark.asyncio
async def test_critic_refutes_and_the_verdict_carries_the_concerns():
    from core.engine.arms.critic import CriticVerdict, adversarial_verify

    llm = _FakeLLM(
        CriticVerdict(
            sound=False,
            blocking_concerns=["the new tool is never registered — it is unreachable in prod"],
            reasoning="grepped the registry; no call site",
        )
    )
    plan, result = _result()

    verdict = await adversarial_verify(Solution(intent="add foo"), plan, result, llm=llm)

    assert verdict.passed is False
    assert verdict.parked is False, "a refuted build is repairable, not parked"
    assert "unreachable in prod" in verdict.reason


@pytest.mark.asyncio
async def test_critic_failure_parks_it_fails_closed():
    """A critic that cannot reach the model has NOT approved the work. Never fail open."""
    from core.engine.arms.critic import adversarial_verify
    from core.engine.core.exceptions import LLMError

    llm = _FakeLLM(raises=LLMError("model unreachable"))
    plan, result = _result()

    verdict = await adversarial_verify(Solution(intent="add foo"), plan, result, llm=llm)

    assert verdict.passed is False, "FAIL CLOSED — an unavailable critic must never pass a build"
    assert verdict.parked is True
    assert "review unavailable" in verdict.diagnosis.lower()


@pytest.mark.asyncio
async def test_critic_prompt_takes_a_refutation_stance_and_carries_the_diff():
    from core.engine.arms.critic import CriticVerdict, adversarial_verify

    llm = _FakeLLM(CriticVerdict(sound=True, blocking_concerns=[], reasoning="ok"))
    plan, result = _result()

    await adversarial_verify(Solution(intent="add foo"), plan, result, llm=llm)

    prompt = llm.prompts[0].lower()
    assert "refute" in prompt, "the critic must be asked to REFUTE, not to review"
    assert "def foo" in llm.prompts[0], "the critic reviews the actual diff, not a description of it"
    assert "reachab" in prompt, "the standing lesson: green tests are necessary, not sufficient"


@pytest.mark.asyncio
async def test_critic_can_run_on_a_different_model_than_the_builder(monkeypatch):
    """A different model reviewing is a stronger check than the same model second-guessing."""
    from core.engine.arms.critic import CriticVerdict, adversarial_verify
    from core.engine.core.config import settings

    monkeypatch.setattr(settings, "arm_critic_model", "qwen2.5-coder:14b")
    llm = _FakeLLM(CriticVerdict(sound=True, blocking_concerns=[], reasoning="ok"))
    plan, result = _result()

    await adversarial_verify(Solution(intent="add foo"), plan, result, llm=llm)

    assert llm.models[0] == "qwen2.5-coder:14b"


@pytest.mark.asyncio
async def test_dispatch_runs_the_critic_on_a_passing_build_and_a_refutation_blocks_it(monkeypatch):
    """Reachability check: the critic is not an orphan module — dispatch actually calls it."""
    import core.engine.arms.critic as critic_mod
    import core.engine.arms.dispatch as dispatch
    from core.engine.arms.base import Arm, AutonomyTier
    from core.engine.core.config import settings

    monkeypatch.setattr(settings, "arm_adversarial_review", True)
    monkeypatch.setattr(settings, "arm_repair_budget", 0)

    class _GoodArm(Arm):
        domain = "good"
        autonomy = AutonomyTier.REVERSIBLE

        def can_handle(self, s):
            return True

        async def plan(self, s):
            return ActionPlan(summary="x", actions=[Action(verb="write_file", args={}, risk=RiskTier.REVERSIBLE)])

        async def execute(self, plan):
            return ArmResult(plan=plan, performed=list(plan.actions), simulated=False, workspace=_FakeWorkspace())

        async def verify(self, result, plan):
            return Verdict(passed=True, reason="my own tests are green")  # the builder's self-assessment

    called = {}

    async def _refuting_critic(solution, plan, result, llm=None):
        called["yes"] = True
        return Verdict(passed=False, reason="adversarial review: the arm is never registered")

    monkeypatch.setattr(critic_mod, "adversarial_verify", _refuting_critic)
    monkeypatch.setattr(dispatch.router, "choose_arm", _only(_GoodArm()))

    async def _noop(*a, **kw):
        return None

    monkeypatch.setattr(dispatch, "capture_outcome", _noop)

    sol = Solution(intent="build")
    _domain, _result, verdict = await dispatch.dispatch_solution(sol)

    assert called.get("yes") is True, "dispatch must actually invoke the critic — an uncalled gate is a vacuous gate"
    assert verdict.passed is False, "the critic's refutation overrides the builder's self-approval"
    assert sol.status == "failed"
