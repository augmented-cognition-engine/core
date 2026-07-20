"""CodeArm — the first MAKE arm, on the BrainHandArm base. A systems-thinking brain+hand:
depth-aware (classify → assemble → phase impls). Phase library = code's domain depth."""

from __future__ import annotations

from core.engine.arms.base import score_domain_match
from core.engine.arms.brain_hand_arm import BrainHandArm
from core.engine.arms.registry import register_arm
from core.engine.solution import Solution

_CODE_TERMS = ("code",)  # word-boundaried via score_domain_match (was a bare substring match)


@register_arm
class CodeArm(BrainHandArm):
    domain = "code"
    description = (
        "Writes and changes application CODE: features, refactors, bug fixes, APIs, endpoints, "
        "handlers, business logic, algorithms, configuration, instrumentation and their tests. "
        "The default for anything that ends as a code change."
    )

    def __init__(
        self,
        *,
        classifier=None,
        loader=None,
        reasoner=None,
        codegen=None,
        critic=None,
        conversation=None,
        overrides=None,
        scorer=None,
    ):
        from core.engine.arms import code_planner as cp

        super().__init__(
            classifier=classifier,
            critic=critic or cp.default_critic,
            conversation=conversation,
            overrides=overrides,
            scorer=scorer,
        )
        self._load = loader or cp.default_loader
        self._reason = reasoner or cp.default_reasoner
        self._codegen = codegen or cp.default_codegen
        self.phase.update(
            {
                "ground_scan": self._phase_ground_scan,
                "explore": self._phase_explore,
                "generate": self._phase_generate,
                "integrate": self._phase_integrate,
            }
        )

    def match_score(self, solution: Solution) -> int:
        return score_domain_match(solution, domain="code", terms=_CODE_TERMS)

    def can_handle(self, solution: Solution) -> bool:
        return self.match_score(solution) > 0

    async def _phase_ground_scan(self, solution, profile, ctx):
        from core.engine.arms import code_planner as cp

        scan_fn = getattr(cp, "default_ground_scan", None)
        if scan_fn is not None:
            ctx["scan"] = await scan_fn(solution.intent if solution else ctx.get("summary", ""))
        return ctx

    async def _phase_explore(self, solution, profile, ctx):
        from core.engine.arms import code_planner as cp

        explore_fn = getattr(cp, "default_explore", None)
        if explore_fn is not None:
            ctx["approach"] = await explore_fn(solution.intent if solution else "", ctx, reasoner=self._reason)
        return ctx

    async def _phase_generate(self, solution, profile, ctx):
        # Repair path: solution is None; ctx carries the original intent + the failure hint
        # (BrainHandArm.verify threads "intent" through so repair isn't blind — see I1).
        intent = solution.intent if solution is not None else ctx.get("intent", "")
        context = ctx.get("scan") or await self._load(intent)
        # Hand the reasoner the depth it was classified at. This argument was sitting unused in the
        # signature while ACE convened a full committee to add a docstring — 20 model calls, a
        # 608-second orchestration task, and a build that parked at its 30-minute budget.
        base = ctx.get("approach") or await self._reason(intent, context, profile=profile or ctx.get("profile"))
        reasoning = self._compose_reasoning(ctx, base)
        if ctx.get("repair"):
            reasoning = f"PRIOR ATTEMPT FAILED. {ctx['repair']}. Fix it.\n{reasoning}"
        files, test_cmd, concerns = await self._codegen(intent, reasoning, context)
        ctx["files"], ctx["test_cmd"], ctx["concerns"] = files, test_cmd, concerns
        return ctx

    async def _phase_integrate(self, solution, profile, ctx):
        return ctx
