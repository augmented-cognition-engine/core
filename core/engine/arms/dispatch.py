"""Dispatch a Solution to an arm and run its plan → execute → verify → review lifecycle.

This is the build state machine, and it is DURABLE: an arm_run row exists before any work
starts, every completed phase is an immutable checkpoint, and the run always reaches a named
terminal state — verified, failed, or PARKED.

Three properties earn their keep here:

  1. PARKED ≠ FAILED. "the work was wrong" (discard it, maybe repair it) and "we never found
     out because the environment broke" (keep it, get a human) are different facts and demand
     different responses. Collapsing them into `failed` is what makes an unattended run
     un-reviewable — you cannot tell a bad diff from a dead model.

  2. A BOUNDED REPAIR LOOP. verify() failing is a signal, not a verdict on the run. The arm
     gets settings.arm_repair_budget attempts to read the failure and fix it. Without this,
     an arm's success rate IS its first-try rate.

  3. AN ADVERSARIAL CRITIC. The builder does not grade its own homework: a passing verify is
     re-judged in a fresh context by a reviewer paid to refute it (and the refutation feeds
     the repair loop). Green tests are necessary, not sufficient.

Fully non-fatal: any failure yields a Verdict, never raises.
"""

from __future__ import annotations

import asyncio
import logging
import time

from core.engine.arms import critic as critic_mod
from core.engine.arms import router, run_ledger
from core.engine.arms.base import ActionPlan, Arm, ArmResult, Verdict
from core.engine.arms.failure import ENVIRONMENTAL as _ENVIRONMENTAL  # noqa: F401  (kept for callers)
from core.engine.arms.failure import is_environmental as _is_environmental
from core.engine.arms.outcome import capture_outcome
from core.engine.arms.registry import route  # noqa: F401  (the keyword fallback; tests monkeypatch it)
from core.engine.core.config import settings
from core.engine.solution import Solution

logger = logging.getLogger(__name__)


def _park(exc: BaseException) -> Verdict:
    if isinstance(exc, (TimeoutError, asyncio.TimeoutError)):
        budget = int(getattr(settings, "arm_build_timeout_s", 1800))
        return Verdict(
            passed=False,
            reason=f"build exceeded its {budget}s budget",
            parked=True,
            diagnosis=(
                f"The build ran past its {budget}s ({budget // 60} min) budget and was stopped. It was "
                "NOT judged — the workspace is preserved.\n\n"
                "This is usually the model, not the work. A build makes ~20 model calls, and on the "
                "subprocess provider (CLIProvider) they degrade from ~10s to ~90s each as the build "
                "proceeds — 15-25 minutes for one build, measured. If you are on that provider, either "
                "raise ARM_BUILD_TIMEOUT_S or move to the API path (`claude setup-token` + "
                "CLAUDE_CODE_OAUTH_TOKEN), which is far quicker. If you are already on the API path, "
                "something really is stuck and the run is worth a look."
            ),
        )
    return Verdict(
        passed=False,
        reason=f"environment failure: {exc}",
        parked=True,
        diagnosis=(
            f"{type(exc).__name__}: {exc}\n"
            "The build was NOT judged — the environment failed under it. The workspace is preserved. "
            "Fix the environment and re-run; do not read this as a bad change."
        ),
    )


async def _judge(arm: Arm, solution: Solution, plan: ActionPlan, result: ArmResult) -> Verdict:
    """The arm's own verify, then — on a pass — the adversarial critic that overrides it.

    The critic is skipped for GATE arms (SHIP already IS the adversarial pass; double-gating
    buys nothing) and when there is nothing to look at (no workspace = no diff = no subject).
    """
    verdict = await arm.verify(result, plan)
    if not verdict.passed or verdict.parked:
        return verdict
    if not getattr(settings, "arm_adversarial_review", True):
        return verdict
    if getattr(arm, "is_gate", False) or getattr(result, "workspace", None) is None:
        return verdict
    return await critic_mod.adversarial_verify(solution, plan, result)


async def _attempt(arm: Arm, solution: Solution, plan: ActionPlan) -> tuple[ArmResult, Verdict]:
    """One execute → judge cycle. Environmental blowups become PARKED verdicts, not exceptions,
    so the caller's loop sees a uniform Verdict and the workspace survives."""
    result = await arm.execute(plan)
    try:
        verdict = await _judge(arm, solution, plan, result)
    except Exception as exc:
        if _is_environmental(exc):
            logger.warning("arm %s: environment failed during verify — PARKING: %s", arm.domain, exc)
            return result, _park(exc)
        logger.info("arm %s: verify failed (the work, not the environment): %s", arm.domain, exc)
        verdict = Verdict(passed=False, reason=str(exc))
    return result, verdict


def _discard(workspace) -> None:
    if workspace is None:
        return
    try:
        workspace.discard()
    except Exception as exc:  # a workspace we cannot clean is not a build we should fail
        logger.debug("workspace discard failed (non-fatal): %s", exc)


async def dispatch_solution(
    solution: Solution, product_id: str = "product:platform"
) -> tuple[str, ArmResult, Verdict] | None:
    """Route + run the durable lifecycle for the right arm. None if no arm can build this.

    Routing goes through the CLASSIFIER (arms/router.py), not raw keyword matching: keywords could
    not route 53% of the real backlog, and misdelivered much of the rest. It degrades to keywords
    if the classifier is unavailable — routing must never park a build.
    """
    arm = await router.choose_arm(solution)
    if arm is None:
        return None
    solution.product_id = product_id  # authoritative product for graph-scoped classification/grounding

    # The run is durable BEFORE any work happens — that is the whole point. A process killed
    # during execute leaves a 'running' row behind (get_runs_needing_attention), not nothing at all.
    run_id = await run_ledger.create_run(
        product_id=product_id,
        intent=solution.intent,
        arm_domain=arm.domain,
        spec_id=getattr(solution, "spec_id", None),
    )
    solution.run_id = run_id
    seq = 0

    async def _mark(phase: str, payload: dict) -> None:
        nonlocal seq
        seq += 1
        await run_ledger.checkpoint(run_id, phase, payload, seq=seq)

    def _next_seq() -> int:
        nonlocal seq
        seq += 1
        return seq

    result: ArmResult | None = None
    verdict: Verdict | None = None
    attempts = 0
    workspace = None

    # The build's wall-clock budget. A build makes ~20 model calls (measured), and on the subprocess
    # provider they degrade from 10s to 90s apiece — a legitimate build runs 15-25 minutes. That is
    # fine; what is NOT fine is a build with no ceiling at all, which is indistinguishable from a
    # hang and is exactly what cost an afternoon here. On timeout the TimeoutError falls through to
    # the handler below, where _is_environmental() sees it and PARKS: nobody judged that work, so it
    # is not a failure — it is a build we never got an answer from.
    deadline = time.monotonic() + max(1, int(getattr(settings, "arm_build_timeout_s", 1800)))

    def _left() -> float:
        return max(0.0, deadline - time.monotonic())

    try:
        plan = await asyncio.wait_for(arm.plan(solution), timeout=_left())
        solution.plan = plan
        await _mark("planned", {"summary": plan.summary, "n_actions": len(plan.actions)})

        if not plan.actions and not getattr(arm, "is_gate", False):
            # A PRODUCER arm produced no change — not a build. Fail honestly; never mark an empty
            # change "built". A GATE arm (SHIP) legitimately produces no file-actions — it surfaces
            # concerns + a verdict — so it falls through to execute/verify, which honor that verdict.
            solution.status = "failed"
            empty = ArmResult(plan=plan)
            verdict = Verdict(passed=False, reason="no actions produced — nothing to build")
            await _finish(solution, arm, empty, verdict, product_id, run_id, 0, _next_seq())
            return arm.domain, empty, verdict

        solution.status = "planned"
        attempts = 1
        result, verdict = await asyncio.wait_for(_attempt(arm, solution, plan), timeout=_left())
        workspace = getattr(result, "workspace", None)
        solution.outcome = result
        await _mark("executed", {"attempt": attempts, "verbs": [a.verb for a in result.performed]})

        # The bounded repair loop. A PARKED verdict short-circuits it: a dead environment does not
        # heal by retrying, and burning the budget against it is a token furnace.
        budget = max(0, int(getattr(settings, "arm_repair_budget", 1)))
        while not verdict.passed and not verdict.parked and attempts <= budget:
            repaired = await arm.repair(result, plan, verdict)
            if repaired is None:
                break  # the arm has no fix to offer — accept the failure, leave the budget unspent
            await _mark("repair_attempt", {"attempt": attempts + 1, "because": verdict.reason[:500]})
            _discard(workspace)  # the failed attempt is reversible — throw it away before retrying
            plan = repaired
            solution.plan = plan
            attempts += 1
            result, verdict = await asyncio.wait_for(_attempt(arm, solution, plan), timeout=_left())
            workspace = getattr(result, "workspace", None)
            solution.outcome = result
            await _mark("executed", {"attempt": attempts, "verbs": [a.verb for a in result.performed]})

        # A VERIFIED build must COMMIT its work onto its branch. Without this the arm's change exists
        # only as uncommitted files in a throwaway worktree: the branch carries nothing, promotion
        # runs `git merge <branch>`, is told "Already up to date", exits 0, and reports a successful
        # promotion having shipped NOTHING. Every gate passes and the diff evaporates.
        #
        # Build #7 — the first build ACE ever completed — did exactly that: verified, critic-approved,
        # and a branch with nothing on it.
        if verdict.passed and workspace is not None:
            sha = workspace.commit(f"{arm.domain}: {(solution.intent or '')[:60]}")
            if sha:
                await _mark("committed", {"sha": sha, "branch": getattr(workspace, "branch", None)})
            else:
                # Verified, but nothing to commit. That is not a success — a build that changed
                # nothing has nothing to promote, and saying "verified" would be a lie with a branch
                # name attached.
                logger.warning("arm %s: verified but produced NO committed change — failing honestly", arm.domain)
                verdict = Verdict(
                    passed=False,
                    reason="verified but nothing was committed — the branch is empty, so there is nothing to promote",
                )

        if verdict.parked:
            solution.status = "parked"
        else:
            solution.status = "verified" if verdict.passed else "failed"
        await _finish(solution, arm, result, verdict, product_id, run_id, attempts, _next_seq())

        # Reversible: throw away a failed attempt. NEVER discard a parked one — that workspace is
        # the evidence the human needs, and nothing about it has been judged.
        if not verdict.passed and not verdict.parked:
            _discard(workspace)
        return arm.domain, result, verdict

    except Exception as exc:
        # A blowup OUTSIDE the judged path (plan(), execute(), the ledger). Same distinction.
        parked = _is_environmental(exc)
        logger.warning("arm %s lifecycle %s (non-fatal): %s", arm.domain, "PARKED" if parked else "failed", exc)
        solution.status = "parked" if parked else "failed"
        if not parked:
            _discard(workspace)
        failed_result = result or ArmResult(plan=solution.plan or ActionPlan(summary="(no plan)"))
        verdict = _park(exc) if parked else Verdict(passed=False, reason=str(exc))
        await _finish(solution, arm, failed_result, verdict, product_id, run_id, max(attempts, 1), _next_seq())
        return arm.domain, failed_result, verdict


async def _finish(
    solution: Solution,
    arm: Arm,
    result: ArmResult,
    verdict: Verdict,
    product_id: str,
    run_id: str | None,
    attempts: int,
    seq: int,
) -> None:
    """Close both ledgers: the run (durable state machine) and the outcome (the learning loop).
    Never raises — a bookkeeping failure must not change what happened to the build."""
    status = "parked" if verdict.parked else ("verified" if verdict.passed else "failed")
    try:
        await run_ledger.checkpoint(run_id, status, {"reason": verdict.reason[:500], "attempts": attempts}, seq=seq)
        await run_ledger.finalize_run(
            run_id=run_id,
            status=status,
            reason=verdict.reason,
            attempts=attempts,
            diagnosis=verdict.diagnosis,
        )
    except Exception as exc:
        # Non-fatal, but NOT invisible: a ledger that silently stops recording is a lying
        # instrument, and the run it failed to close looks "running" forever to get_runs_needing_attention.
        logger.warning("run ledger finalize failed (non-fatal, run left open): %s", exc)
    try:
        await capture_outcome(solution, arm.domain, result, verdict, product_id, run_id=run_id, attempts=attempts)
    except Exception as exc:
        # capture_outcome swallows its own DB errors, so reaching here means the CALL itself broke
        # (signature drift). That silently severs the learning loop — warn, never whisper.
        logger.warning("capture_outcome failed (non-fatal, outcome NOT recorded): %s", exc)
