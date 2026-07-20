from __future__ import annotations

import pytest


def test_workprofile_defaults():
    from core.engine.arms.strategy.profile import WorkProfile

    p = WorkProfile()
    assert (p.scope, p.novelty, p.risk, p.verify_depth) == ("nearby", "modify", "connected", "unit")


def test_assemble_bugfix_is_shallow():
    from core.engine.arms.strategy.assemble import assemble
    from core.engine.arms.strategy.profile import WorkProfile

    bug = WorkProfile(scope="none", novelty="fix", risk="isolated", verify_depth="smoke")
    cats = assemble(bug)
    assert "ground_scan" not in cats and "explore" not in cats and "architect" not in cats
    assert cats[-1] == "verify" and "generate" in cats


def test_assemble_new_capability_scans_and_explores():
    from core.engine.arms.strategy.assemble import assemble
    from core.engine.arms.strategy.profile import WorkProfile

    cap = WorkProfile(scope="module", novelty="extend", risk="connected", verify_depth="unit")
    cats = assemble(cap)
    assert "ground_scan" in cats and "explore" in cats and "integrate" in cats
    assert cats.index("ground_scan") < cats.index("explore") < cats.index("generate") < cats.index("verify")


def test_assemble_greenfield_architects_systemic_foresees():
    from core.engine.arms.strategy.assemble import assemble
    from core.engine.arms.strategy.profile import WorkProfile

    gf = WorkProfile(scope="repo", novelty="greenfield", risk="systemic", verify_depth="full")
    cats = assemble(gf)
    assert "explore" in cats and "architect" in cats and "foresight" in cats
    assert cats.index("architect") < cats.index("generate")
    assert cats.index("foresight") < cats.index("generate")


def test_classify_work_no_classifier_is_static_default():
    import asyncio

    from core.engine.arms.strategy.classify import STATIC_DEFAULT_PROFILE, classify_work
    from core.engine.solution import Solution

    p = asyncio.run(classify_work(Solution(intent="do a thing")))  # no classifier injected
    assert (p.scope, p.novelty) == (STATIC_DEFAULT_PROFILE.scope, STATIC_DEFAULT_PROFILE.novelty)


def test_classify_work_uses_injected_classifier():
    import asyncio

    from core.engine.arms.strategy.classify import classify_work
    from core.engine.arms.strategy.profile import WorkProfile
    from core.engine.solution import Solution

    async def clf(solution, conversation, overrides):
        return WorkProfile(scope="module", novelty="extend", task_type="new-capability")

    p = asyncio.run(classify_work(Solution(intent="add capability"), classifier=clf))
    assert p.scope == "module" and p.task_type == "new-capability"


def test_classify_work_overrides_win():
    import asyncio

    from core.engine.arms.strategy.classify import classify_work
    from core.engine.arms.strategy.profile import WorkProfile
    from core.engine.solution import Solution

    async def clf(solution, conversation, overrides):
        p = WorkProfile(scope="nearby", novelty="fix")
        if overrides and overrides.get("scope"):
            p.scope = overrides["scope"]
        if overrides and overrides.get("novelty"):
            p.novelty = overrides["novelty"]
        return p

    p = asyncio.run(
        classify_work(Solution(intent="rethink"), overrides={"scope": "repo", "novelty": "greenfield"}, classifier=clf)
    )
    assert p.scope == "repo" and p.novelty == "greenfield"  # "full scan" / "new design system"


def test_default_explore_picks_an_approach():
    import asyncio

    import core.engine.arms.code_planner as cp

    calls = {"n": 0}

    async def reasoner(intent, context, product_id="product:platform"):
        calls["n"] += 1
        return f"approach {calls['n']}"

    approach = asyncio.run(cp.default_explore("add feature", {}, reasoner=reasoner))
    assert isinstance(approach, str) and approach
    assert calls["n"] >= 2  # fanned out at least two candidates


def test_default_ground_scan_returns_dict_nonfatal():
    import asyncio

    import core.engine.arms.code_planner as cp

    out = asyncio.run(cp.default_ground_scan("scan the auth module"))
    assert isinstance(out, dict)


def test_codearm_runs_assembled_phases_for_new_capability():
    import asyncio

    from core.engine.arms.code_arm import CodeArm
    from core.engine.arms.strategy.profile import WorkProfile
    from core.engine.solution import Solution

    async def classifier(solution, conversation, overrides):
        return WorkProfile(scope="module", novelty="extend", risk="connected", verify_depth="unit")

    async def loader(i, product_id="product:platform"):
        return {}

    async def reasoner(i, c, product_id="product:platform"):
        return "r"

    async def codegen(i, r, c):
        return ([{"path": "x.py", "content": "y\n"}], ["true"], ["c"])

    async def critic(c, ws):
        return True, []

    arm = CodeArm(
        classifier=classifier, loader=loader, reasoner=reasoner, codegen=codegen, critic=critic, scorer=None
    )  # scorer=None keeps this unit test off the DB
    seen = []

    async def gs(s, p, ctx):
        seen.append("ground_scan")
        ctx["scan"] = {}
        return ctx

    async def ex(s, p, ctx):
        seen.append("explore")
        ctx["approach"] = "chosen"
        return ctx

    arm.phase["ground_scan"] = gs
    arm.phase["explore"] = ex
    orig_gen = arm.phase["generate"]

    async def gen(s, p, ctx):
        seen.append("generate")
        return await orig_gen(s, p, ctx)

    arm.phase["generate"] = gen

    plan = asyncio.run(arm.plan(Solution(intent="add capability", domain_hint="code")))
    assert seen == ["ground_scan", "explore", "generate"]  # scanned + explored BEFORE generate
    assert plan.actions[0].args["path"] == "x.py"


@pytest.mark.asyncio
async def test_classify_work_applies_depth_nudge_before_overrides():
    from core.engine.arms.strategy.classify import classify_work
    from core.engine.arms.strategy.depth_scorer import DepthSignal
    from core.engine.arms.strategy.profile import WorkProfile

    async def classifier(s, c, o):
        return WorkProfile(scope="none", novelty="fix", risk="isolated", verify_depth="smoke")

    async def escalating_scorer(profile, arm_domain, product_id):
        return DepthSignal(escalate=True, reason="t")

    class _Sol:
        intent = "x"
        product_id = "product:platform"

    # nudge fires -> scope deepened one notch (none -> nearby)
    p = await classify_work(_Sol(), classifier=classifier, scorer=escalating_scorer, arm_domain="code")
    assert p.scope == "nearby"

    # user override WINS over the nudge (applied after) — override scope back to 'none'
    p2 = await classify_work(
        _Sol(), classifier=classifier, scorer=escalating_scorer, arm_domain="code", overrides={"scope": "none"}
    )
    assert p2.scope == "none"


@pytest.mark.asyncio
async def test_classify_work_no_scorer_unchanged_and_nonfatal():
    from core.engine.arms.strategy.classify import classify_work
    from core.engine.arms.strategy.profile import WorkProfile

    async def classifier(s, c, o):
        return WorkProfile(scope="none", novelty="fix", risk="isolated")

    class _Sol:
        intent = "x"
        product_id = "product:platform"

    # no scorer -> unchanged
    p = await classify_work(_Sol(), classifier=classifier)
    assert p.scope == "none"

    # scorer raises -> non-fatal, unchanged
    async def boom(profile, arm_domain, product_id):
        raise RuntimeError("scorer down")

    p2 = await classify_work(_Sol(), classifier=classifier, scorer=boom, arm_domain="code")
    assert p2.scope == "none"
