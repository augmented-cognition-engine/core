"""BrainHandArm — the shared brain+hand loop every MAKE arm inherits. classify_work →
assemble → run the arm's domain phase impls → ActionPlan; execute in a worktree; verify
with a no-slop gate + bounded repair at the profile's depth. Depth-aware by construction."""

from __future__ import annotations

import logging

from core.engine.arms.base import Action, ActionPlan, Arm, ArmResult, AutonomyTier, RiskTier, Verdict
from core.engine.arms.strategy.assemble import assemble
from core.engine.arms.strategy.classify import classify_work
from core.engine.arms.strategy.depth_scorer import score_depth
from core.engine.arms.strategy.graph_classifier import graph_grounded_classifier

logger = logging.getLogger(__name__)


class BrainHandArm(Arm):
    autonomy = AutonomyTier.REVERSIBLE
    max_repair_passes = 3

    def __init__(self, *, classifier=None, critic=None, conversation=None, overrides=None, scorer=None):
        self._classifier = classifier or graph_grounded_classifier
        self._scorer = scorer if scorer is not None else score_depth
        self._conversation = conversation
        self._overrides = overrides
        self._critic = critic
        self._intent = ""  # stashed in plan() so the repair loop (solution=None) isn't blind
        # Seed the shared deep phases; subclasses .update() their domain phases onto this.
        self.phase = {"architect": self._phase_architect, "foresight": self._phase_foresight}

    @staticmethod
    def _to_actions(files: list[dict]) -> list[Action]:
        return [
            Action(
                verb="write_file", args={"path": f["path"], "content": f.get("content", "")}, risk=RiskTier.REVERSIBLE
            )
            for f in (files or [])
        ]

    @staticmethod
    def _files_from_plan(plan) -> list[dict]:
        """Reconstruct [{path, content}] from a plan's write_file actions — the shape every
        registered verify check expects. Re-derived every verify() pass so a repair's
        regenerated files get re-checked, not just the original plan."""
        return [
            {"path": a.args.get("path", ""), "content": a.args.get("content", "")}
            for a in plan.actions
            if a.verb == "write_file"
        ]

    async def _phase_architect(self, solution, profile, ctx):
        from core.engine.arms.strategy import deep_phases

        reasoner = getattr(self, "_reason", None)
        if reasoner is None:
            return ctx
        intent = solution.intent if solution is not None else ctx.get("intent", "")
        ctx["architecture"] = await deep_phases.default_architect(intent, self.domain, ctx, reasoner=reasoner)
        return ctx

    async def _phase_foresight(self, solution, profile, ctx):
        from core.engine.arms.strategy import deep_phases

        reasoner = getattr(self, "_reason", None)
        if reasoner is None:
            return ctx
        intent = solution.intent if solution is not None else ctx.get("intent", "")
        ctx["foresight"] = await deep_phases.default_foresight(intent, self.domain, ctx, reasoner=reasoner)
        return ctx

    @staticmethod
    def _compose_reasoning(ctx: dict, base: str) -> str:
        """Fold architect/foresight output into the reasoning that generate passes to codegen."""
        parts = [base or ""]
        if ctx.get("architecture"):
            parts.append(f"ARCHITECTURE (implement this structure):\n{ctx['architecture']}")
        if ctx.get("foresight"):
            parts.append(f"FORESIGHT (address these consequences):\n{ctx['foresight']}")
        return "\n\n".join(p for p in parts if p)

    async def plan(self, solution) -> ActionPlan:
        self._intent = getattr(solution, "intent", "") or ""  # so repair can regenerate on-target
        profile = await classify_work(
            solution,
            conversation=self._conversation,
            overrides=self._overrides,
            classifier=self._classifier,
            scorer=self._scorer,
            arm_domain=self.domain,
        )
        pipeline = assemble(profile)
        ctx: dict = {"profile": profile, "ran": []}
        for category in pipeline:
            impl = self.phase.get(category)
            if impl is None:
                continue  # not implemented by this arm — skip, non-fatal
            try:
                ctx = await impl(solution, profile, ctx)
                ctx.setdefault("ran", []).append(category)
            except Exception as exc:
                # Skipping a flaky OPTIONAL phase is why this catch exists, and that is still right.
                # But skipping a phase the MODEL killed is not: the plan then carries no files, and
                # dispatch reports "no actions produced — nothing to build" — blaming the work for
                # the model's death, and quietly requeueing the spec as if it were merely a bad one.
                # A dead environment must park, so let it out.
                from core.engine.arms.failure import is_environmental

                if is_environmental(exc):
                    logger.warning("phase %s: environment failed — PARKING rather than planning blind", category)
                    raise
                logger.warning("phase %s failed (non-fatal): %s", category, exc)
                # REMEMBER it. A skipped phase produces no files, and dispatch then reports "no
                # actions produced — nothing to build" — which blames the WORK for a bug in the
                # ENGINE. That is the same laundering the parked state exists to prevent, one layer
                # down, and it hid a TypeError in this very file for an entire build.
                ctx.setdefault("phase_failures", []).append(f"{category}: {type(exc).__name__}: {exc}")

        # An empty plan is a fact; WHY it is empty is the fact that matters. If a phase blew up, say
        # so — otherwise "nothing to build" reads as "the arm had nothing to do".
        failures = ctx.get("phase_failures") or []
        summary = f"{self.domain}: {(solution.intent or '')[:48]}"
        if failures and not ctx.get("files"):
            summary = f"{summary} — PHASE FAILED: {'; '.join(failures)[:200]}"
        return ActionPlan(
            summary=summary,
            actions=self._to_actions(ctx.get("files", [])),
            test_cmd=ctx.get("test_cmd"),
            surfaced_concerns=(ctx.get("concerns", []) or []) + [f"phase failure — {f}" for f in failures],
            profile=profile,
            pipeline=pipeline,
        )

    async def execute(self, plan: ActionPlan) -> ArmResult:
        from core.engine.arms.execution.runtime import ExecutionRuntime
        from core.engine.arms.execution.workspace import Workspace

        return await ExecutionRuntime().run(plan, Workspace.create(label=self.domain))

    async def repair(self, result: ArmResult, plan: ActionPlan, verdict: Verdict) -> ActionPlan | None:
        """The OUTER repair: regenerate against the ADVERSARIAL CRITIC's refutation.

        verify() below already runs an inner repair loop against everything the arm can see for
        itself — failing tests, uncovered concerns — and spends up to max_repair_passes on it. The
        critic runs AFTER that returns, so its refutation ("this is never registered, it is
        unreachable in prod") is a defect the inner loop has never once been shown. That is the
        signal worth another pass, and dispatch gives us the budget to take it.

        We decline everything else on purpose. A verdict the arm sourced itself means the inner
        loop already exhausted its passes against those exact signals; re-running the same
        generation against them is a token furnace that changes nothing. Repair NEW information
        or do not repair at all.

        Returns a fresh ActionPlan (dispatch executes it in a NEW worktree — the failed one is
        discarded first). Non-fatal: any error means no repair, not a crash.
        """
        if verdict.source != "critic" or verdict.parked:
            return None
        regen = self.phase.get("generate")
        if regen is None:
            return None
        try:
            # The PROFILE, not the plan. This slot is `profile` — passing the ActionPlan here made
            # the reasoner ask "is an ActionPlan shallow?", get None for `risk`, and convene an
            # 11-agent committee to repair a docstring. Repair carries the depth of the work it is
            # repairing: a docstring does not become an architecture problem because attempt #1 failed.
            rctx = await regen(
                None,
                plan.profile,
                {
                    "repair": f"An adversarial reviewer REFUTED this build: {verdict.reason}",
                    "intent": self._intent,
                    "profile": plan.profile,
                },
            )
        except Exception as exc:
            logger.warning("outer repair (critic) failed (non-fatal): %s", exc)
            return None
        files = rctx.get("files") or []
        if not files:
            return None  # nothing regenerated — an empty plan is not a repair
        return ActionPlan(
            summary=plan.summary,
            actions=self._to_actions(files),
            test_cmd=rctx.get("test_cmd") or plan.test_cmd,
            surfaced_concerns=rctx.get("concerns") or plan.surfaced_concerns,
            profile=plan.profile,  # carry the depth profile + pipeline so the learning signal survives
            pipeline=plan.pipeline,
        )

    async def verify(self, result: ArmResult, plan: ActionPlan) -> Verdict:
        from core.engine.arms.execution.runtime import ExecutionRuntime

        rt = ExecutionRuntime()
        ws = result.workspace
        if ws is None:
            return Verdict(passed=False, reason="no execution workspace")
        concerns = plan.surfaced_concerns
        for attempt in range(self.max_repair_passes + 1):
            tests_ok, out = (True, "")
            if plan.test_cmd:
                tests_ok, out = await rt.run_tests(plan.test_cmd, ws)
            covered, uncovered = await self._critic(concerns, ws)

            # Registered verify-check gate — FAIL CLOSED. Re-run every pass over the CURRENT
            # plan's generated files (not just the original), so a repair's regenerated output
            # is re-checked instead of trusted blind. Enforced violations block the pass exactly
            # like a failing test; advisory ones never block — they only need a human's eyes,
            # so they ride along in the reason on the branch that already passes. Checks are
            # extension-contributed (see core/engine/extensions/registry.py) — verify() has no
            # hardcoded policy of its own.
            from core.engine.extensions.registry import registered_verify_checks

            files = self._files_from_plan(plan)
            raw: list = []
            for check in registered_verify_checks():
                try:
                    raw.extend(check(files) or [])
                except Exception as exc:  # a bad check must never crash a build
                    logger.warning("verify check %r failed (non-fatal): %s", getattr(check, "__name__", check), exc)
            # NORMALIZE before the enforced/advisory split. A check that RETURNS (doesn't
            # raise) a malformed violation — missing a key, or a severity outside the two
            # known values — must not KeyError out of verify() below and crash the build.
            # `line` may legitimately be None; only its PRESENCE is required here.
            violations: list[dict] = []
            for v in raw:
                if (
                    isinstance(v, dict)
                    and v.get("severity") in ("enforced", "advisory")
                    and all(k in v for k in ("rule", "file", "line"))
                ):
                    violations.append(v)
                else:
                    logger.warning("verify check returned a malformed violation (skipped): %r", v)
            enforced = [v for v in violations if v["severity"] == "enforced"]
            advisory = [v for v in violations if v["severity"] == "advisory"]
            enforced_desc = [v["rule"] + "@" + v["file"] + ":" + str(v["line"]) for v in enforced]
            adv_note = f" (advisory conventions: {[v['rule'] + '@' + v['file'] for v in advisory]})" if advisory else ""

            if tests_ok and covered and not enforced:
                return Verdict(
                    passed=True, reason="tested + all surfaced concerns covered + conventions clean" + adv_note
                )
            if attempt >= self.max_repair_passes:
                # SAY WHY. "tests_ok=False" is a shrug: it tells a human the build failed and
                # withholds the one fact that would let them fix it — while the repair loop, which
                # is fed `out` on every pass, has been reading the error the whole time. The person
                # who has to act on this deserves at least what the loop already had.
                detail = []
                if not tests_ok:
                    detail.append(f"TESTS FAILED — ran {plan.test_cmd}:\n{(out or '(no output)')[-1200:]}")
                if uncovered:
                    detail.append(f"UNCOVERED CONCERNS: {uncovered}")
                if enforced:
                    detail.append(f"CONVENTION VIOLATIONS (enforced): {enforced_desc}")
                return Verdict(
                    passed=False,
                    reason=(
                        f"unresolved after {attempt} repair(s). " + "\n\n".join(detail)
                        if detail
                        else f"unresolved after {attempt} repair(s)"
                    ),
                )
            try:
                regen = self.phase.get("generate")
                if regen is None:
                    return Verdict(passed=False, reason="no generate phase to repair with")
                # The PROFILE, not the plan (see repair() above). THIS is the site that actually ran:
                # 11 committee calls per repair pass, three passes, 60 minutes, parked. The bug was
                # harmless until the profile became load-bearing this morning — which is the honest
                # price of a positional argument nobody was type-checking.
                rctx = await regen(
                    None,
                    plan.profile,
                    {
                        "repair": (
                            f"tests={out!r}; uncovered={uncovered}"
                            + (f"; CONVENTION VIOLATIONS to fix: {enforced_desc}" if enforced else "")
                        ),
                        "intent": self._intent,
                        "profile": plan.profile,
                    },
                )
                if not rctx.get("files"):
                    # Mirror repair()'s own `if not files: return None` guard. Falling through
                    # here would build the next rplan from an empty files list, so the NEXT
                    # pass scans zero files, finds zero violations, and returns passed=True —
                    # shipping the ORIGINAL, untouched, still-violating plan under a clean
                    # verdict. Fail closed now instead of laundering silence into a pass.
                    detail = []
                    if enforced:
                        detail.append(
                            "CONVENTION VIOLATIONS (enforced, unresolved — "
                            f"regeneration produced no files): {enforced_desc}"
                        )
                    if uncovered:
                        detail.append(f"UNCOVERED CONCERNS: {uncovered}")
                    reason = f"repair produced no files after {attempt + 1} repair attempt(s)"
                    if detail:
                        reason += ". " + "\n\n".join(detail)
                    return Verdict(passed=False, reason=reason)
                rplan = ActionPlan(
                    # Carry the profile (and pipeline) FORWARD. Without it, repair pass #2 reads
                    # plan.profile == None, decides the work is not shallow, and convenes the
                    # committee anyway — fixing pass #1 while leaving passes #2 and #3 broken.
                    profile=plan.profile,
                    pipeline=plan.pipeline,
                    summary=plan.summary,
                    actions=self._to_actions(rctx.get("files", [])),
                    test_cmd=rctx.get("test_cmd") or plan.test_cmd,
                    surfaced_concerns=rctx.get("concerns") or concerns,
                )
                await rt.run(rplan, ws)
                plan, concerns = rplan, rplan.surfaced_concerns
            except Exception as exc:
                logger.warning("repair failed (non-fatal): %s", exc)
                return Verdict(passed=False, reason=f"repair error: {exc}")
        return Verdict(passed=False, reason="repair exhausted")
