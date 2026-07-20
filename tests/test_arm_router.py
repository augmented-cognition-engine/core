"""Routing by keyword cannot understand what it is being asked to build.

Measured against the REAL backlog (17 specs) before this existed:

    NO ARM 9  ·  design 6  ·  code 1  ·  ship 1

53% unroutable, and most of the rest misrouted by accidental keyword hits — "Implement
comprehensive rate limiting across all API endpoints" went to DESIGN; "Cascade calibration /
CascadeRouter prod instantiation" went to the SHIP GATE because it contains the word "prod".
_CODE_TERMS was literally ("code",): a spec had to SAY THE WORD to reach the code arm.

So the loop we spent all day making trustworthy would have refused half the backlog and
misdelivered much of the rest — faithfully, durably, and with an excellent audit trail.

The router asks a model to choose among the REGISTERED arms, constrained to their actual domains
so it cannot invent one. Keywords survive as the fallback for when the model is unavailable:
degraded routing still beats no routing.

Two rules that keep it honest:
  - A GATE arm (ship) is never chosen to BUILD something. It produces no files by design; picking
    it for a code task guarantees an empty build the gate then refuses as vacuous. It is only for
    work that genuinely IS a production-readiness assessment.
  - Routing NEVER parks a build. A classifier that cannot run degrades to keywords; only a spec
    that truly matches nothing returns None (honestly: "no arm can build this yet").
"""

from __future__ import annotations

import pytest

from core.engine.solution import Solution


class _FakeLLM:
    def __init__(self, domain=None, raises=None):
        self._domain = domain
        self._raises = raises
        self.prompts: list[str] = []

    async def complete_structured(self, prompt, schema, model=None, max_tokens=4096):
        self.prompts.append(prompt)
        if self._raises:
            raise self._raises
        return schema(domain=self._domain, reasoning="because")


@pytest.mark.asyncio
async def test_a_code_task_that_never_says_the_word_code_still_reaches_the_code_arm():
    """The headline failure: keywords needed the literal word. A model does not."""
    from core.engine.arms.router import choose_arm

    llm = _FakeLLM(domain="code")
    arm = await choose_arm(Solution(intent="Implement rate limiting across all API endpoints"), llm=llm)

    assert arm is not None
    assert arm.domain == "code"


@pytest.mark.asyncio
async def test_the_classifier_is_offered_the_real_registered_arms_and_their_jobs():
    """It must choose from what actually EXISTS. A router that can name an arm the registry does
    not have is a router that routes into the void."""
    from core.engine.arms.router import choose_arm

    llm = _FakeLLM(domain="code")
    await choose_arm(Solution(intent="add retry logic"), llm=llm)

    prompt = llm.prompts[0]
    for domain in ("code", "design", "data", "ship"):
        assert domain in prompt, f"the arm '{domain}' must be offered as an option"
    assert "GATE" in prompt, "the classifier must be told which arms are gates and cannot build"


@pytest.mark.asyncio
async def test_a_gate_arm_is_never_chosen_to_build_a_producer_task(monkeypatch):
    """The exact production misroute. 'prod' in the text sent a CODE task to the SHIP gate, which
    produces no files — so the build was empty and the gate refused it as vacuous. If a classifier
    (or a keyword) picks a gate for something that is not a readiness assessment, override it."""
    from core.engine.arms.router import choose_arm

    # The model gets it wrong and says "ship" for a code task. The router must not comply blindly.
    llm = _FakeLLM(domain="ship")
    arm = await choose_arm(
        Solution(intent="Cascade calibration / CascadeRouter prod instantiation"),
        llm=llm,
        producer_only=True,
    )

    assert arm is None or arm.domain != "ship", (
        "a gate arm must never be handed a build. It emits no files by design, so the build is "
        "empty and the gate then refuses its own emptiness as vacuous — a guaranteed dead end."
    )


@pytest.mark.asyncio
async def test_a_genuine_ship_task_still_reaches_the_ship_gate():
    """The guard must not make the gate unreachable — assessing production readiness IS its job."""
    from core.engine.arms.router import choose_arm

    llm = _FakeLLM(domain="ship")
    arm = await choose_arm(Solution(intent="assess production readiness before we go live"), llm=llm)

    assert arm is not None and arm.domain == "ship"


@pytest.mark.asyncio
async def test_an_explicit_domain_hint_wins_without_spending_a_call():
    """The caller already knows. Do not pay a model to confirm it."""
    from core.engine.arms.router import choose_arm

    llm = _FakeLLM(domain="design")
    arm = await choose_arm(Solution(intent="anything at all", domain_hint="data"), llm=llm)

    assert arm.domain == "data"
    assert llm.prompts == [], "an explicit hint must short-circuit the classifier entirely"


@pytest.mark.asyncio
async def test_a_dead_classifier_degrades_to_keywords_and_never_parks_the_build():
    """Routing is not a gate. A model that cannot run must not stop the loop — it falls back to the
    old keyword score, which is worse but is still routing."""
    from core.engine.arms.failure import ENVIRONMENTAL  # noqa: F401  (documents the contrast)
    from core.engine.arms.router import choose_arm
    from core.engine.core.exceptions import LLMError

    llm = _FakeLLM(raises=LLMError("model unreachable"))
    arm = await choose_arm(Solution(intent="design the settings panel"), llm=llm)

    assert arm is not None, "a dead classifier must not make work unroutable"
    assert arm.domain == "design", "the keyword fallback still handles the cases it always handled"


@pytest.mark.asyncio
async def test_a_hallucinated_arm_is_rejected():
    """Structured output constrains the model, but never trust it: an unknown domain is no domain."""
    from core.engine.arms.router import choose_arm

    llm = _FakeLLM(domain="quantum_arm")
    arm = await choose_arm(Solution(intent="something exotic"), llm=llm)

    assert arm is None or arm.domain != "quantum_arm"


@pytest.mark.asyncio
async def test_dispatch_routes_through_the_classifier(monkeypatch):
    """Reachability: an unrouted router is just a module. dispatch must actually use it."""
    import core.engine.arms.dispatch as dispatch
    import core.engine.arms.router as router

    called = {}

    async def _choose(solution, llm=None, producer_only=True):
        called["intent"] = solution.intent
        return None  # no arm handles it

    monkeypatch.setattr(router, "choose_arm", _choose)

    out = await dispatch.dispatch_solution(Solution(intent="Implement rate limiting on the API"))

    assert called.get("intent") == "Implement rate limiting on the API", "dispatch must route via the classifier"
    assert out is None, "no arm → None, which build_spec reports honestly"
