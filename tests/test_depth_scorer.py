from __future__ import annotations

import pytest

from core.engine.arms.base import ActionPlan


def test_action_plan_carries_profile_and_pipeline():
    p = ActionPlan(summary="x", profile={"novelty": "fix"}, pipeline=["generate", "verify"])
    assert p.profile == {"novelty": "fix"}
    assert p.pipeline == ["generate", "verify"]
    # additive: defaults when omitted
    assert ActionPlan(summary="y").profile is None
    assert ActionPlan(summary="y").pipeline is None


def test_v127_migration_is_additive_and_safe():
    # Dogfood the data arm's own migration-safety mirror on this migration.
    from core.engine.arms.migration_safety import scan_migration_violations

    with open("core/schema/v127_action_outcome_profile.surql", encoding="utf-8") as fh:
        sql = fh.read()
    v = scan_migration_violations(
        sql,
        existing_max_version=126,
        filename="v127_action_outcome_profile.surql",
        prior_tables={"action_outcome"},
        prior_enums={},
    )
    assert v == [], v  # additive option<> fields on an existing table -> no v126 violation


import core.engine.arms.strategy.depth_scorer as ds
from core.engine.arms.strategy.profile import WorkProfile


def test_escalate_profile_walks_ladder_scope_first():
    p = WorkProfile(scope="none", novelty="fix", risk="isolated", verify_depth="smoke")
    out = ds.escalate_profile(p)
    assert out.scope == "nearby" and out.risk == "isolated"  # scope bumps first
    assert p.scope == "none"  # original untouched (new object)


def test_escalate_profile_moves_to_risk_then_verify_when_scope_maxed():
    p = WorkProfile(scope="repo", novelty="fix", risk="isolated", verify_depth="smoke")
    assert ds.escalate_profile(p).risk == "connected"  # scope maxed -> risk
    p2 = WorkProfile(scope="repo", novelty="fix", risk="systemic", verify_depth="smoke")
    assert ds.escalate_profile(p2).verify_depth == "unit"  # scope+risk maxed -> verify


def test_escalate_profile_capped_when_all_maxed():
    p = WorkProfile(scope="repo", novelty="fix", risk="systemic", verify_depth="full")
    out = ds.escalate_profile(p)
    assert (out.scope, out.risk, out.verify_depth) == ("repo", "systemic", "full")  # bounded, unchanged


class _Pool:
    def __init__(self, rows):
        self._rows = rows

    def connection(self):
        rows = self._rows

        class Ctx:
            async def __aenter__(self):
                class _DB:
                    async def query(self, q, params=None):
                        return rows

                return _DB()

            async def __aexit__(self, *a):
                return False

        return Ctx()


@pytest.mark.asyncio
async def test_score_depth_escalates_when_failing_over_min_signals():
    rows = [{"passed": False}] * 6 + [{"passed": True}] * 2  # 8 signals, 75% fail
    sig = await ds.score_depth(
        WorkProfile(novelty="fix", risk="isolated"), "code", "product:platform", min_signals=8, pool=_Pool(rows)
    )
    assert sig.escalate is True


@pytest.mark.asyncio
async def test_score_depth_neutral_under_min_signals_coldstart():
    rows = [{"passed": False}] * 3  # below min_signals
    sig = await ds.score_depth(
        WorkProfile(novelty="fix", risk="isolated"), "code", "product:platform", min_signals=8, pool=_Pool(rows)
    )
    assert sig.escalate is False


@pytest.mark.asyncio
async def test_score_depth_neutral_when_mostly_passing():
    rows = [{"passed": True}] * 9 + [{"passed": False}] * 1  # 10% fail, over min_signals
    sig = await ds.score_depth(
        WorkProfile(novelty="fix", risk="isolated"), "code", "product:platform", min_signals=8, pool=_Pool(rows)
    )
    assert sig.escalate is False


@pytest.mark.asyncio
async def test_score_depth_non_fatal_on_db_error():
    class _BoomPool:
        def connection(self):
            class Ctx:
                async def __aenter__(self):
                    raise RuntimeError("db down")

                async def __aexit__(self, *a):
                    return False

            return Ctx()

    sig = await ds.score_depth(WorkProfile(), "code", "product:platform", pool=_BoomPool())
    assert sig.escalate is False


@pytest.mark.asyncio
async def test_brain_hand_arm_plan_records_profile_and_pipeline(monkeypatch):
    from core.engine.arms.code_arm import CodeArm
    from core.engine.arms.strategy.profile import WorkProfile
    from core.engine.solution import Solution

    async def classifier(s, c, o):
        return WorkProfile(scope="module", novelty="extend", risk="connected", verify_depth="unit")

    async def codegen(i, r, c):
        return ([{"path": "x", "content": "c"}], None, [])

    async def loader(i, product_id="product:platform"):
        return {}

    async def reasoner(i, c, product_id="product:platform"):
        return "r"

    async def critic(c, ws):
        return True, []

    arm = CodeArm(classifier=classifier, codegen=codegen, loader=loader, reasoner=reasoner, critic=critic, scorer=None)
    plan = await arm.plan(Solution(intent="add a thing", domain_hint="code"))
    assert plan.profile is not None and plan.profile.novelty == "extend"
    assert plan.pipeline and "generate" in plan.pipeline


@pytest.mark.asyncio
async def test_capture_outcome_writes_profile_fields():
    from core.engine.arms.base import Action, ActionPlan, ArmResult, RiskTier, Verdict
    from core.engine.arms.outcome import capture_outcome
    from core.engine.arms.strategy.profile import WorkProfile
    from core.engine.solution import Solution

    captured = {}

    class _DB:
        async def query(self, q, params=None):
            if q.strip().upper().startswith("CREATE"):
                captured.update(params)
            return []

    class _Pool:
        def connection(self):
            db = _DB()

            class Ctx:
                async def __aenter__(self):
                    return db

                async def __aexit__(self, *a):
                    return False

            return Ctx()

    plan = ActionPlan(summary="x", profile=WorkProfile(novelty="fix", risk="isolated"), pipeline=["generate", "verify"])
    res = ArmResult(
        plan=plan, performed=[Action(verb="write_file", args={}, risk=RiskTier.REVERSIBLE)], simulated=False
    )
    await capture_outcome(
        Solution(intent="x"), "code", res, Verdict(passed=False, reason="r"), "product:platform", pool=_Pool()
    )
    assert captured.get("pnovelty") == "fix" and captured.get("prisk") == "isolated"
    assert captured.get("pipeline") == ["generate", "verify"]
