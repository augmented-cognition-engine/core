"""DesignArm — the second MAKE arm, on the BrainHandArm base. A systems-thinking product designer:
composes surfaces from the ACE design system's primitives + tokens, gated by the enforcement
battery (in-process mirror in-loop + canonical TS suite at merge). Phase library = design's depth."""

from __future__ import annotations

from core.engine.arms.base import score_domain_match
from core.engine.arms.brain_hand_arm import BrainHandArm
from core.engine.arms.registry import register_arm
from core.engine.solution import Solution

# Whole-word matched (via score_domain_match) — "ui" no longer needs a trailing space, and
# "component" won't substring-match unrelated words like "componentry" in prose.
_DESIGN_TERMS = ("design", "component", "ui", "screen", "layout", "surface", "panel", "dashboard", "wireframe")


@register_arm
class DesignArm(BrainHandArm):
    domain = "design"
    description = (
        "Designs USER-FACING SURFACES: components, layouts, screens, panels, dashboards, visual "
        "systems, design tokens, interaction and onboarding flows. Choose this only when the work "
        "is what the user SEES — not merely because the word 'design' appears in the sentence."
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
        from core.engine.arms import design_planner as dp

        super().__init__(
            classifier=classifier,
            critic=critic or dp.default_critic,
            conversation=conversation,
            overrides=overrides,
            scorer=scorer,
        )
        self._load = loader or dp.default_ground_scan
        self._reason = reasoner or dp.default_reasoner
        self._codegen = codegen or dp.default_codegen
        self.phase.update(
            {
                "ground_scan": self._phase_ground_scan,
                "explore": self._phase_explore,
                "generate": self._phase_generate,
                "integrate": self._phase_integrate,
            }
        )

    def match_score(self, solution: Solution) -> int:
        return score_domain_match(solution, domain="design", terms=_DESIGN_TERMS)

    def can_handle(self, solution: Solution) -> bool:
        return self.match_score(solution) > 0

    async def _phase_ground_scan(self, solution, profile, ctx):
        ctx["scan"] = await self._load(solution.intent if solution else ctx.get("summary", ""))
        return ctx

    async def _phase_explore(self, solution, profile, ctx):
        from core.engine.arms import design_planner as dp

        ctx["approach"] = await dp.default_explore(solution.intent if solution else "", ctx, reasoner=self._reason)
        return ctx

    async def _phase_generate(self, solution, profile, ctx):
        # Repair path: solution is None; ctx carries the original intent + the failure hint
        # (BrainHandArm.verify threads "intent" through so repair isn't blind — see I1).
        intent = solution.intent if solution is not None else ctx.get("intent", "")
        context = ctx.get("scan") or await self._load(intent)
        base = ctx.get("approach") or await self._reason(intent, context)
        reasoning = self._compose_reasoning(ctx, base)
        if ctx.get("repair"):
            reasoning = f"PRIOR SURFACE FAILED THE ENFORCEMENT GATE: {ctx['repair']}. Fix EVERY violation.\n{reasoning}"
        files, test_cmd, concerns = await self._codegen(intent, reasoning, context)
        ctx["files"], ctx["test_cmd"], ctx["concerns"] = files, test_cmd, concerns
        return ctx

    async def _phase_integrate(self, solution, profile, ctx):
        return ctx  # compose-from-existing: no barrel changes in the first cut
