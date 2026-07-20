"""DataArm — the third MAKE arm, on the BrainHandArm base. A systems-thinking data engineer:
writes safe, additive SurrealDB migrations grounded in the existing schema, gated by the
migration-safety battery (in-process mirror in-loop + make test-fast / schema-idempotency at
merge). Phase library = data's depth. Completes the BrainHandArm template across code/design/data."""

from __future__ import annotations

from core.engine.arms.base import score_domain_match
from core.engine.arms.brain_hand_arm import BrainHandArm
from core.engine.arms.registry import register_arm
from core.engine.solution import Solution

_DATA_TERMS = ("migration", "schema", "backfill", "table", "field", "column", "index", "enum")


@register_arm
class DataArm(BrainHandArm):
    domain = "data"
    description = (
        "Changes DATA STRUCTURES: schema migrations, tables, fields, indexes, enums, backfills and "
        "the safety of moving existing rows between shapes."
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
        from core.engine.arms import data_planner as dp

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
        return score_domain_match(solution, domain="data", terms=_DATA_TERMS)

    def can_handle(self, solution: Solution) -> bool:
        return self.match_score(solution) > 0

    async def _phase_ground_scan(self, solution, profile, ctx):
        ctx["scan"] = await self._load(solution.intent if solution else ctx.get("intent", ""))
        return ctx

    async def _phase_explore(self, solution, profile, ctx):
        from core.engine.arms import data_planner as dp

        ctx["approach"] = await dp.default_explore(solution.intent if solution else "", ctx, reasoner=self._reason)
        return ctx

    async def _phase_generate(self, solution, profile, ctx):
        intent = solution.intent if solution is not None else ctx.get("intent", "")
        context = ctx.get("scan") or await self._load(intent)
        base = ctx.get("approach") or await self._reason(intent, context)
        reasoning = self._compose_reasoning(ctx, base)
        if ctx.get("repair"):
            reasoning = f"PRIOR MIGRATION FAILED THE SAFETY GATE: {ctx['repair']}. Fix EVERY violation.\n{reasoning}"
        files, test_cmd, concerns = await self._codegen(intent, reasoning, context)
        # On repair (solution is None; `profile` is the original ActionPlan per BrainHandArm.verify),
        # OVERWRITE the original migration file rather than letting the LLM pick a new filename — a
        # different name at the same version would leave the failed attempt behind, and BOTH files
        # would merge + apply (the leftover shipping its bug). Reuse the path so the fix replaces it.
        orig_actions = getattr(profile, "actions", None) if solution is None else None
        if orig_actions and files:
            orig_path = orig_actions[0].args.get("path")
            if orig_path:
                files[0]["path"] = orig_path
        ctx["files"], ctx["test_cmd"], ctx["concerns"] = files, test_cmd, concerns
        return ctx

    async def _phase_integrate(self, solution, profile, ctx):
        return ctx  # additive migration: no extra wiring in the first cut
