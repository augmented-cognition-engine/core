"""ShipArm — the SHIP arm: a production-readiness GATE (Phase 5, the build→ship loop's missing limb).

The MAKE arms (code/design/data) produce work; the SHIP arm GATES it. It assesses built/proposed work
across the five production dimensions and surfaces the gaps as ActionPlan.surfaced_concerns with a
pass/fail Verdict. First increment = assess + gate (auto-generating the hardening is a follow-up).

On the BrainHandArm base (consistent with the MAKE arms — inherits depth-aware classify→assemble→plan),
but it OVERRIDES execute/verify: a gate proposes, it never mutates (autonomy NONE), and "valid" means a
substantive assessment — a non-trivial ship gate that surfaces ZERO concerns is itself suspect (the
happy-path blind spot is real), so that vacuous pass FAILS the gate.
"""

from __future__ import annotations

from core.engine.arms.base import ArmResult, AutonomyTier, Verdict, score_domain_match
from core.engine.arms.brain_hand_arm import BrainHandArm
from core.engine.arms.registry import register_arm
from core.engine.solution import Solution

_SHIP_TERMS = ("ship", "deploy", "release", "harden", "production", "prod", "go-live", "rollout")


@register_arm
class ShipArm(BrainHandArm):
    domain = "ship"
    description = (
        "GATE — produces NO files. Assesses PRODUCTION READINESS (security, tests, observability, "
        "devops, scale) of work that already exists. Choose ONLY when the task IS the readiness "
        "assessment itself. Never choose it to BUILD something: it cannot, and the empty build "
        "would then be refused as vacuous."
    )
    autonomy = AutonomyTier.NONE  # a gate proposes; it never auto-mutates
    is_gate = True  # produces no file-actions — dispatch must run execute/verify, not "nothing to build"

    def __init__(self, *, classifier=None, assessor=None, conversation=None, overrides=None, scorer=None):
        from core.engine.arms import ship_planner as sp

        super().__init__(
            classifier=classifier, critic=None, conversation=conversation, overrides=overrides, scorer=scorer
        )
        self._assess = assessor or sp.assess_ship_readiness
        # Only the assess phase runs — drop the base architect/foresight (generation phases). "generate"
        # is always in assemble()'s pipeline, so the gate fires for any non-trivial ship intent.
        self.phase = {"generate": self._phase_assess}

    def match_score(self, solution: Solution) -> int:
        return score_domain_match(solution, domain="ship", terms=_SHIP_TERMS)

    def can_handle(self, solution: Solution) -> bool:
        return self.match_score(solution) > 0

    async def _phase_assess(self, solution, profile, ctx):
        intent = solution.intent if solution is not None else ctx.get("intent", "")
        concerns, actions = await self._assess(intent)
        ctx["concerns"], ctx["ship_actions"] = concerns, actions
        return ctx

    async def execute(self, plan) -> ArmResult:
        # A GATE: assesses + proposes hardening; never mutates. Simulated, no workspace.
        n = len(plan.surfaced_concerns or [])
        return ArmResult(
            plan=plan,
            performed=[],
            simulated=True,
            logs=[f"ship gate: surfaced {n} production-readiness concern(s); proposing hardening (no mutation)"],
        )

    async def verify(self, result, plan) -> Verdict:
        concerns = plan.surfaced_concerns or []
        # No-slop / vacuous-pass guard: a ship gate that surfaces nothing didn't actually assess —
        # real production work always has unhappy-path gaps. Fail it so the gate can't rubber-stamp.
        if not concerns:
            return Verdict(
                passed=False,
                reason="ship gate surfaced no production-readiness concerns — vacuous (the happy-path "
                "blind spot is real); re-assess",
            )
        return Verdict(
            passed=True,
            reason=f"ship gate surfaced {len(concerns)} production-readiness concern(s) "
            "across security/testing/observability/devops/scale",
        )
