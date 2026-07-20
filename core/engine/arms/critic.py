"""The adversarial critic — a fresh context whose job is to REFUTE the build.

arm.verify() is written by the same reasoning that produced the plan, so it inherits the
plan's blind spots. Green tests are necessary, not sufficient: an orphaned MCP tool, an
unregistered arm, a substring-routing shadow and a vacuous gate ALL pass their own tests.
Every one of those shipped green and was caught only by an adversarial pass.

So the critic:
  - never sees the builder's reasoning — only the intent and the actual diff (fresh context),
  - is asked to REFUTE, not to review (default-to-refuted is cheap; a false pass is not),
  - can run on a DIFFERENT model than the builder (settings.arm_critic_model — a local peer
    is a genuinely independent check, not the same model second-guessing itself),
  - FAILS CLOSED: a critic that could not run has not approved anything → PARKED.

A refutation is not a park: the build is repairable, so it flows back into the repair loop
as a normal failure with the concerns attached as evidence.
"""

from __future__ import annotations

import logging

from pydantic import BaseModel, Field

from core.engine.arms.base import ActionPlan, ArmResult, Verdict
from core.engine.core.config import settings
from core.engine.solution import Solution

logger = logging.getLogger(__name__)

# The diff is the subject of review. Cap it — a sweeping refactor must not blow the context
# window (and a truncated review is honest about being partial; see _build_prompt).
_MAX_DIFF_CHARS = 12000


class CriticVerdict(BaseModel):
    """Schema-forced at the API level (complete_structured) — the critic cannot answer in prose."""

    sound: bool = Field(description="True ONLY if you could not find a blocking defect.")
    blocking_concerns: list[str] = Field(
        default_factory=list,
        description="Defects that must be fixed before this ships. Empty iff sound.",
    )
    reasoning: str = Field(default="", description="How you tried to break it.")


_SYSTEM = (
    "You are an adversarial reviewer. Your job is to REFUTE the claim that this change is "
    "correct and complete. You did not write it and you owe it nothing. Assume the tests pass — "
    "that is not evidence of correctness, it is the baseline.\n\n"
    "Hunt specifically for the defects that pass their own tests:\n"
    "  - REACHABILITY: is the new code actually wired in? A tool nobody registers, an arm nobody "
    "dispatches to, a branch nobody takes, a gate nobody calls — all green, all dead in prod.\n"
    "  - VACUOUS GATES: does a check that looks like a gate actually assert anything, and does it "
    "fail CLOSED when its dependency is unavailable?\n"
    "  - SHADOWING: does this silently take precedence over (or get shadowed by) existing routing, "
    "registration or config?\n"
    "  - THE CASES A VIBE-CODER MISSES: error paths, empty/None, concurrency, partial failure, "
    "the second call, the migration of existing rows.\n\n"
    "If you find nothing blocking, say so plainly — but look hard first. A false pass is far more "
    "expensive than a false alarm."
)


def _build_prompt(solution: Solution, plan: ActionPlan, result: ArmResult) -> str:
    diff = ""
    ws = getattr(result, "workspace", None)
    if ws is not None:
        try:
            diff = ws.diff() or ""
        except Exception as exc:  # a workspace that cannot produce a diff is a review we cannot do
            logger.debug("critic: diff unavailable: %s", exc)
            diff = ""
    truncated = len(diff) > _MAX_DIFF_CHARS
    if truncated:
        diff = diff[:_MAX_DIFF_CHARS]

    verbs = ", ".join(a.verb for a in result.performed) or "(none)"
    concerns = "\n".join(f"  - {c}" for c in (plan.surfaced_concerns or [])) or "  (none surfaced)"
    return (
        f"INTENT (what this was supposed to do):\n{solution.intent}\n\n"
        f"PLAN SUMMARY: {plan.summary}\n"
        f"ACTIONS PERFORMED: {verbs}\n"
        f"CONCERNS THE BUILDER CLAIMS TO HAVE HANDLED:\n{concerns}\n\n"
        f"THE DIFF{' (TRUNCATED — judge only what you can see, and say so)' if truncated else ''}:\n"
        f"```diff\n{diff or '(empty diff — nothing was actually changed)'}\n```\n\n"
        "Refute it. Is this change actually correct, complete, and REACHABLE in production?"
    )


async def adversarial_verify(
    solution: Solution,
    plan: ActionPlan,
    result: ArmResult,
    llm=None,
) -> Verdict:
    """Review a build that its own arm just passed. Returns the verdict that overrides it.

    FAIL CLOSED: any error (model unreachable, malformed response, timeout) → parked. The build
    is not approved by a review that did not happen.
    """
    if llm is None:
        from core.engine.core.llm import get_llm

        llm = get_llm()

    prompt = _build_prompt(solution, plan, result)
    model = getattr(settings, "arm_critic_model", "") or None
    try:
        verdict: CriticVerdict = await llm.complete_structured(
            prompt=f"{_SYSTEM}\n\n{prompt}",
            schema=CriticVerdict,
            model=model,
            max_tokens=2048,
        )
    except Exception as exc:
        logger.warning("adversarial review unavailable — PARKING the build (fail-closed): %s", exc)
        return Verdict(
            passed=False,
            reason="adversarial review could not run",
            parked=True,
            source="environment",
            diagnosis=(
                f"Adversarial review unavailable ({type(exc).__name__}: {exc}). The build was NOT "
                "approved — it was never reviewed. Fix the reviewer (model reachability/credentials) "
                "and re-run, or inspect the preserved workspace by hand."
            ),
        )

    if verdict.sound and not verdict.blocking_concerns:
        return Verdict(passed=True, reason=f"adversarial review passed: {verdict.reasoning[:300]}", source="critic")

    # Refuted. Repairable — the concerns ARE the evidence the repair loop feeds back to the arm, and
    # source="critic" is what tells the arm this is a signal its inner loop never saw.
    concerns = "; ".join(verdict.blocking_concerns) or verdict.reasoning or "unspecified"
    return Verdict(passed=False, reason=f"adversarial review: {concerns}"[:2000], source="critic")
