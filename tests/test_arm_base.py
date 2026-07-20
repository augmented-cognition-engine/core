from core.engine.arms.base import (
    Action,
    ActionPlan,
    ArmResult,
    AutonomyTier,
    RiskTier,
    Verdict,
)
from core.engine.solution import Solution


def test_solution_shape():
    s = Solution(intent="add a healthcheck endpoint")
    assert s.intent == "add a healthcheck endpoint"
    assert s.reasoning == "" and s.connections == [] and s.foresight == [] and s.status == "open"
    s.reasoning = "committee says: small, low-risk"
    assert s.reasoning.startswith("committee")


def test_contract_shapes():
    action = Action(verb="write_file", args={"path": "x.py", "content": "ok"}, risk=RiskTier.REVERSIBLE)
    plan = ActionPlan(summary="write x.py", actions=[action])
    result = ArmResult(plan=plan, performed=[action], simulated=True, logs=["wrote x.py (sim)"])
    verdict = Verdict(passed=True, reason="plan satisfied")
    assert plan.actions[0].verb == "write_file"
    assert result.simulated is True
    assert verdict.passed is True
    assert AutonomyTier.REVERSIBLE.value == "reversible"
    assert RiskTier.MUTATING.value == "mutating"
