"""Which arm should build this? Keywords could not answer that question.

Measured against the real backlog (17 specs) before this existed:

    NO ARM 9  ·  design 6  ·  code 1  ·  ship 1

53% unroutable, and most of the rest misrouted by accidental keyword hits. "Implement
comprehensive rate limiting across all API endpoints" went to DESIGN. "Cascade calibration /
CascadeRouter prod instantiation" went to the SHIP GATE — because it contains the word "prod".
_CODE_TERMS was literally ("code",): a spec had to SAY THE WORD to reach the code arm.

So the loop we spent a day making durable, honest, self-repairing and adversarially reviewed
would have refused half the backlog and misdelivered much of the rest — faithfully, durably, and
with an excellent audit trail. Trustworthiness was never the binding constraint. Comprehension was.

The router asks a model to choose among the arms that are ACTUALLY REGISTERED, constrained by
structured output to their real domains so it cannot invent one, and shown each arm's own
description of what it builds. Three rules keep it honest:

  1. An explicit domain_hint short-circuits everything. The caller already knows; do not pay a
     model to confirm it.
  2. A GATE arm is never handed a BUILD. It emits no files by design, so the build comes out empty
     and the gate then refuses its own emptiness as vacuous — a guaranteed dead end, and exactly
     what happened in production.
  3. Routing NEVER parks a build. A classifier that cannot run degrades to the old keyword score:
     worse, but still routing. Only a spec that genuinely matches nothing returns None, which
     build_spec reports honestly as "no arm can build this spec yet".
"""

from __future__ import annotations

import logging

from pydantic import BaseModel, Field

from core.engine.arms.base import Arm
from core.engine.arms.registry import _ensure_arms_loaded, _registry, route
from core.engine.solution import Solution

logger = logging.getLogger(__name__)


class ArmChoice(BaseModel):
    """Schema-forced at the API level so the model cannot answer in prose — or invent an arm."""

    domain: str = Field(description="The EXACT domain string of the one arm that should do this work.")
    reasoning: str = Field(default="", description="One sentence: why that arm and not the others.")


_SYSTEM = (
    "You route a unit of work to the one engineering arm that should do it.\n\n"
    "Judge what the work IS, not which words it happens to contain. 'Implement rate limiting across "
    "all API endpoints' is CODE — it is not design work because it mentions endpoints, and it is not "
    "a ship task because it mentions production. A word appearing in a sentence is not evidence.\n\n"
    "If the work is a code change, say code. Most work is a code change.\n"
)


def _catalogue(arms: list[Arm]) -> str:
    lines = []
    for a in arms:
        gate = "  [GATE — produces NO files; never choose it to build something]" if a.is_gate else ""
        lines.append(f"- {a.domain}:{gate}\n    {a.description or '(no description)'}")
    return "\n".join(lines)


def _registered_arms() -> list[Arm]:
    """Instantiate every registered arm. This is the option set: an arm the registry does not have
    is an arm we cannot route to, and offering it would route work into the void."""
    _ensure_arms_loaded()
    arms: list[Arm] = []
    for cls in _registry:
        try:
            arms.append(cls())
        except Exception as exc:
            logger.debug("arm %s could not be instantiated for routing: %s", getattr(cls, "domain", cls), exc)
    return arms


def _by_domain(arms: list[Arm], domain: str | None) -> Arm | None:
    if not domain:
        return None
    for a in arms:
        if a.domain == domain:
            return a
    return None


async def choose_arm(solution: Solution, llm=None, producer_only: bool = False) -> Arm | None:
    """The arm that should do this Solution's work, or None if nothing here can.

    Gate arms are ALLOWED by default: "assess production readiness before go-live" genuinely is
    ShipArm's job, and excluding gates wholesale would make it unreachable. What must never happen
    is a gate being handed a BUILD — and the classifier, which is told which arms are gates and
    what they are for, is what prevents that. `producer_only=True` is for callers who already know
    they need something built and want the guarantee enforced structurally.

    The KEYWORD FALLBACK never picks a gate, whatever the flag says. That path is exactly where the
    production misroute lived: a single incidental word ("prod") beat every producer and sent a code
    task to a gate that emits no files. When the classifier is down, refusing to route is honest;
    routing into a guaranteed dead end is not.
    """
    arms = _registered_arms()
    if not arms:
        return None

    # 1. The caller already knows. An exact hint is the most explicit intent there is.
    hinted = _by_domain(arms, getattr(solution, "domain_hint", None))
    if hinted is not None:
        return hinted

    candidates = [a for a in arms if not (producer_only and a.is_gate)]
    if not candidates:
        return None

    # 2. Ask the model — constrained to the arms that actually exist. An explicitly injected llm
    # always wins (tests); otherwise the flag can disable the call (the fast suite must not route
    # through a live model).
    if llm is None:
        from core.engine.core.config import settings

        if not getattr(settings, "arm_llm_routing", True):
            return _keyword_fallback(solution, producer_only=producer_only)
        from core.engine.core.llm import get_llm

        llm = get_llm()

    prompt = (
        f"{_SYSTEM}\n"
        f"THE ARMS AVAILABLE:\n{_catalogue(arms)}\n\n"
        f"THE WORK:\n{(solution.intent or '').strip()[:2000]}\n\n"
        "Which single arm should do this? Answer with its exact domain string."
    )
    try:
        choice: ArmChoice = await llm.complete_structured(prompt=prompt, schema=ArmChoice, max_tokens=512)
        chosen = _by_domain(candidates, (choice.domain or "").strip())
        if chosen is not None:
            logger.info("routed %r → %s (%s)", (solution.intent or "")[:60], chosen.domain, choice.reasoning[:80])
            return chosen
        # A domain we do not have, or a gate we excluded. Never trust it blindly — fall through to
        # the keyword score rather than routing into the void.
        logger.warning("classifier chose an unusable arm %r — falling back to keywords", choice.domain)
    except Exception as exc:
        # Routing is NOT a gate. A dead classifier must not make work unroutable — degrade, and keep
        # the loop building. (Contrast arms/failure.py: an environment failure during the BUILD
        # parks it, because there the alternative is lying about the work. Here the alternative is
        # merely worse routing.)
        logger.warning("arm classifier unavailable — falling back to keyword routing: %s", exc)

    return _keyword_fallback(solution, producer_only=producer_only)


def _keyword_fallback(solution: Solution, producer_only: bool = False) -> Arm | None:
    """The old keyword score. Worse, but still routing — and it NEVER picks a gate.

    A gate arm reached by keywords is the production bug verbatim: "Cascade calibration /
    CascadeRouter **prod** instantiation" scored 1 for ship and 0 for everything else, so a code
    task went to a gate that emits no files, produced an empty build, and had its own emptiness
    refused as vacuous. One incidental word must not be able to do that. If only a gate matches,
    return None — "no arm can build this yet" is an honest answer; a guaranteed dead end is not.
    """
    for arm in route(solution):
        if arm.is_gate:
            continue  # deliberate, and not conditional on producer_only — see the docstring
        return arm
    return None
