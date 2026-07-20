"""ScaffoldArm — the reference arm. Proves the contract end-to-end with SIMULATED
execution (describes the file write; does not touch disk). The real worktree
execution layer (Plan 2) replaces simulate() with a sandboxed runner."""

from __future__ import annotations

from core.engine.arms.base import (
    Action,
    ActionPlan,
    Arm,
    ArmResult,
    AutonomyTier,
    RiskTier,
    Verdict,
    score_domain_match,
)
from core.engine.arms.registry import register_arm
from core.engine.solution import Solution

_SCAFFOLD_TERMS = ("scaffold",)


@register_arm
class ScaffoldArm(Arm):
    domain = "scaffold"
    autonomy = AutonomyTier.REVERSIBLE

    def match_score(self, solution: Solution) -> int:
        return score_domain_match(solution, domain="scaffold", terms=_SCAFFOLD_TERMS)

    def can_handle(self, solution: Solution) -> bool:
        return self.match_score(solution) > 0

    async def plan(self, solution: Solution) -> ActionPlan:
        # Trivial parse: "...file <name>...body <text>" — the reference doesn't need real NLP.
        path = "scaffold.txt"
        body = solution.intent
        return ActionPlan(
            summary=f"write {path}",
            actions=[Action(verb="write_file", args={"path": path, "content": body}, risk=RiskTier.REVERSIBLE)],
        )

    async def execute(self, plan: ActionPlan) -> ArmResult:
        # Real execution in an isolated, reversible worktree (Plan 2).
        from core.engine.arms.execution.runtime import ExecutionRuntime
        from core.engine.arms.execution.workspace import Workspace

        workspace = Workspace.create(label=self.domain)
        return await ExecutionRuntime().run(plan, workspace)

    async def verify(self, result: ArmResult, plan: ActionPlan) -> Verdict:
        # Verify against the real workspace: every planned (non-mutating) action ran and
        # the written file is readable back from the worktree.
        from core.engine.arms.execution.executors import read_file

        if result.simulated or result.workspace is None:
            return Verdict(passed=False, reason="no real execution workspace")
        planned = [a for a in plan.actions if a.risk != RiskTier.MUTATING]
        if [a.verb for a in result.performed] != [a.verb for a in planned]:
            return Verdict(passed=False, reason="not all planned actions performed")
        for a in result.performed:
            if a.verb == "write_file":
                try:
                    read_file(result.workspace.path, {"path": a.args["path"]})
                except Exception:
                    return Verdict(passed=False, reason=f"written file missing: {a.args.get('path')}")
        return Verdict(passed=True, reason="executed in workspace; outputs present")
