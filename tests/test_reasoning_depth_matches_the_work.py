"""ACE convened a full committee to add a docstring.

The first build ever run to completion PARKED at its 30-minute budget. The log said why:

    SLOW TASK: run_id=run_47be... duration=608529ms  discipline=architecture   <- 10 min, one task
    SLOW TASK: run_id=run_cc01... duration=211259ms  discipline=architecture

...for the intent "Add a module-level docstring to registry.py".

The depth system is not broken — that was my first (wrong) guess. It classifies correctly:

    docstring                     -> risk=isolated  verify=smoke  (4 phases)
    redesign the orchestration    -> risk=systemic  verify=full   (6 phases)

The bug is that the profile drives WHICH PHASES RUN, and then the generate phase ignores it: it
calls default_reasoner, which unconditionally runs the FULL orchestration — committee, disciplines,
EGR — with a prompt demanding security, retries, observability, caching and deployment analysis. For
a docstring. That is where ~20 model calls and a parked build come from.

The line this draws, and it matters: shallow work skips the committee. Everything else keeps the
full systems-thinking treatment, because "handle the cases a vibe-coder would miss" is the entire
point of an arm and must not be traded away for speed. ONLY work the classifier calls isolated AND
smoke-verifiable takes the fast path — and even that path still asks for the concerns, so the
no-slop bar survives. When in doubt (no profile at all), the committee convenes: expensive is a
better failure than shallow.
"""

from __future__ import annotations

import pytest

from core.engine.arms.strategy.profile import WorkProfile


def _shallow() -> WorkProfile:
    return WorkProfile(scope="module", novelty="extend", risk="isolated", verify_depth="smoke")


def _systemic() -> WorkProfile:
    return WorkProfile(scope="repo", novelty="greenfield", risk="systemic", verify_depth="full")


class _SpyLLM:
    def __init__(self):
        self.calls: list[str] = []

    async def complete(self, prompt, **kw):
        self.calls.append(prompt)
        return "a concrete plan that addresses error handling and tests"


@pytest.mark.asyncio
async def test_trivial_work_does_NOT_convene_the_committee(monkeypatch):
    """The 10-minute docstring. One grounded call, not a multi-agent deliberation."""
    import core.engine.arms.code_planner as cp

    convened = {"yes": False}

    async def _orchestrate(req):
        convened["yes"] = True
        raise AssertionError("the committee must not be convened for isolated, smoke-verified work")

    llm = _SpyLLM()
    monkeypatch.setattr(cp, "get_llm", lambda: llm)
    monkeypatch.setattr("core.engine.orchestration.orchestrate", _orchestrate, raising=False)

    out = await cp.default_reasoner("Add a module docstring", {"scan": "..."}, profile=_shallow())

    assert convened["yes"] is False, "a docstring must not cost a 20-call committee"
    assert len(llm.calls) == 1, "shallow work is ONE grounded reasoning call"
    assert out, "and it must still produce reasoning"


@pytest.mark.asyncio
async def test_the_fast_path_still_demands_the_concerns(monkeypatch):
    """Cheap must not mean sloppy. Even the one-call path asks it to reason past the happy path —
    that bar is the whole reason an arm exists and is not negotiable for speed."""
    import core.engine.arms.code_planner as cp

    llm = _SpyLLM()
    monkeypatch.setattr(cp, "get_llm", lambda: llm)

    await cp.default_reasoner("Add a module docstring", {}, profile=_shallow())

    prompt = llm.calls[0].lower()
    assert "error" in prompt or "edge" in prompt, "the fast path must still hunt the unhappy paths"
    assert "test" in prompt, "and still ask for tests"


@pytest.mark.asyncio
async def test_systemic_work_STILL_gets_the_full_committee(monkeypatch):
    """The guard must not gut the engine. Real work keeps the full treatment — that is the product."""
    import core.engine.arms.code_planner as cp

    convened = {"yes": False}

    class _Result:
        output = "deep reasoning"

    async def _orchestrate(req):
        convened["yes"] = True
        return _Result()

    monkeypatch.setattr("core.engine.orchestration.orchestrate", _orchestrate, raising=False)

    out = await cp.default_reasoner("Redesign the orchestration layer", {}, profile=_systemic())

    assert convened["yes"] is True, "systemic work MUST still convene the committee"
    assert out == "deep reasoning"


@pytest.mark.asyncio
async def test_no_profile_means_the_committee_convenes(monkeypatch):
    """When in doubt, deliberate. Expensive is a better failure mode than shallow — a build that
    costs too much is annoying; a build that silently skipped the systems thinking is slop."""
    import core.engine.arms.code_planner as cp

    convened = {"yes": False}

    class _Result:
        output = "deep"

    async def _orchestrate(req):
        convened["yes"] = True
        return _Result()

    monkeypatch.setattr("core.engine.orchestration.orchestrate", _orchestrate, raising=False)

    await cp.default_reasoner("something ambiguous", {})  # no profile at all

    assert convened["yes"] is True, "unknown depth => full depth"


@pytest.mark.asyncio
async def test_the_generate_phase_actually_passes_the_profile_through(monkeypatch):
    """Reachability: the profile is useless if the phase that has it never hands it over. It was
    sitting right there in the signature, unused, the whole time."""
    from core.engine.arms.code_arm import CodeArm
    from core.engine.solution import Solution

    seen = {}

    async def _reason(intent, context, profile=None):
        seen["profile"] = profile
        return "reasoning"

    async def _load(i, product_id="product:platform"):
        return {}

    async def _codegen(i, r, c):
        return ([{"path": "a.py", "content": "x = 1"}], None, [])

    arm = CodeArm(loader=_load, reasoner=_reason, codegen=_codegen)
    profile = _shallow()

    await arm._phase_generate(Solution(intent="add a docstring"), profile, {"profile": profile})

    assert seen["profile"] is profile, "the generate phase must hand the reasoner the depth it was given"
