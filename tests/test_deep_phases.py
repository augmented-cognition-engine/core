from __future__ import annotations

import pytest

import core.engine.arms.strategy.deep_phases as dp


class _OfflineLLM:
    """Deterministic stand-in for the provider — no network, no `claude` subprocess."""

    async def complete(self, *a, **k):
        return "OFFLINE"

    async def complete_json(self, *a, **k):
        # Superset of the shapes the planners read (pairwise winner, coverage probe).
        return {"winner": 1, "why": "offline test stub", "uncovered": []}

    async def complete_structured(self, *a, **k):
        return {}


@pytest.fixture(autouse=True)
def _offline_planner_llm(monkeypatch):
    """The plan() tests below run the REAL planner phases, and those call get_llm()
    DIRECTLY (data_planner's "Pairwise: pick the SAFER SurrealDB migration strategy",
    and the code/design equivalents). _arm_with_spies stubs the classifier/loader/
    reasoner/codegen/critic — but never the provider — so these tests made a REAL LLM
    CALL. On a dev box a populated .env made that a quiet API round-trip that passed;
    in the export tree's clean room (no .env) it fell through to the `claude` CLI
    subprocess and HUNG the public fast gate indefinitely — caught with the CLI
    spawned mid-run: `claude -p "Pairwise: pick the SAFER SurrealDB migration ..."`.
    Stub the provider in every planner module so plan() is fully offline.
    Assertions are unchanged; this only removes the hidden network dependency."""
    import core.engine.arms.code_planner as _cp
    import core.engine.arms.critic as _cr
    import core.engine.arms.data_planner as _dp
    import core.engine.arms.design_planner as _dsp

    for _mod in (_cp, _dp, _dsp, _cr):
        monkeypatch.setattr(_mod, "get_llm", lambda: _OfflineLLM(), raising=False)


@pytest.mark.asyncio
async def test_architect_returns_reasoner_design():
    async def reasoner(framed, ctx):
        assert "architect" in framed.lower() and "code" in framed.lower()
        return "MODULES: a, b; INTERFACES: ..."

    out = await dp.default_architect("build a parser", "code", {}, reasoner=reasoner)
    assert out.startswith("MODULES")


@pytest.mark.asyncio
async def test_architect_non_fatal():
    async def boom(framed, ctx):
        raise RuntimeError("orchestrate down")

    out = await dp.default_architect("x", "code", {}, reasoner=boom)
    assert out == ""


@pytest.mark.asyncio
async def test_foresight_grounds_in_scan_and_reasons():
    seen = {}

    async def reasoner(framed, ctx):
        seen["framed"] = framed
        return "BREAKS: the auth flow; CONNECTED: 4 modules"

    ctx = {"scan": {"blast_radius": {"total_affected": 9}, "graph_tensions": ["t1"]}}
    out = await dp.default_foresight("change auth", "code", ctx, reasoner=reasoner)
    assert "BREAKS" in out
    assert "total_affected" in seen["framed"]  # grounding from ctx['scan'] reached the prompt


@pytest.mark.asyncio
async def test_foresight_non_fatal():
    async def boom(framed, ctx):
        raise RuntimeError("down")

    out = await dp.default_foresight("x", "code", {}, reasoner=boom)
    assert out == ""


@pytest.mark.asyncio
async def test_foresight_gathers_own_grounding_when_scan_absent(monkeypatch):
    # systemic risk at nearby/none scope -> ground_scan didn't run -> ctx has no 'scan'.
    # foresight must gather its OWN best-effort grounding, not reason on an empty {}.
    async def fake_grounding(intent, product_id):
        return {"blast_radius": {"total_affected": 5}, "graph_tensions": ["t"]}

    monkeypatch.setattr(dp, "_foresight_grounding", fake_grounding)
    seen = {}

    async def reasoner(framed, ctx):
        seen["framed"] = framed
        return "BREAKS: x"

    out = await dp.default_foresight("change auth", "code", {}, reasoner=reasoner)  # no ctx['scan']
    assert "BREAKS" in out
    assert "total_affected" in seen["framed"]  # best-effort grounding reached the prompt


@pytest.mark.asyncio
async def test_foresight_grounding_is_best_effort_non_fatal(monkeypatch):
    # ace_load works, ace_blast_radius fails (cold graph) -> keep the load grounding, swallow blast.
    import core.engine.mcp.tools as tools

    async def fake_load(topic, product_id="product:platform"):
        return {"graph_tensions": ["t"]}

    async def boom_blast(target, product_id="product:platform"):
        raise RuntimeError("cold graph")

    monkeypatch.setattr(tools, "ace_load", fake_load)
    monkeypatch.setattr(tools, "ace_blast_radius", boom_blast)
    g = await dp._foresight_grounding("intent", "product:platform")
    assert g.get("graph_tensions") == ["t"]  # load grounding kept; blast failure non-fatal


def test_compose_reasoning_folds_when_present():
    from core.engine.arms.brain_hand_arm import BrainHandArm

    base = "base reasoning"
    # no deep keys -> base only
    assert BrainHandArm._compose_reasoning({}, base) == base
    # architecture + foresight folded in
    out = BrainHandArm._compose_reasoning({"architecture": "MODS: a,b", "foresight": "BREAKS: x"}, base)
    assert "base reasoning" in out and "MODS: a,b" in out and "BREAKS: x" in out
    assert "ARCHITECTURE" in out and "FORESIGHT" in out


def test_brain_hand_arm_seeds_deep_phases():
    from core.engine.arms.brain_hand_arm import BrainHandArm

    class _Bare(BrainHandArm):
        domain = "x"

        def can_handle(self, s):
            return True

    arm = _Bare()
    assert "architect" in arm.phase and "foresight" in arm.phase  # seeded by the base


from core.engine.arms.strategy.profile import WorkProfile
from core.engine.solution import Solution


def _greenfield():
    return WorkProfile(scope="repo", novelty="greenfield", risk="connected", verify_depth="unit")


def _systemic():
    return WorkProfile(scope="module", novelty="modify", risk="systemic", verify_depth="full")


def _arm_with_spies(ArmCls):
    """An arm whose reasoner/codegen are stubs; returns (arm, recorder)."""
    rec = {"reason_framings": [], "codegen_reasoning": None}

    async def classifier(s, c, o):
        return _greenfield()

    async def loader(i, product_id="product:platform"):
        return {}

    async def reasoner(framed, ctx, product_id="product:platform"):
        rec["reason_framings"].append(framed)
        return f"REASONED({framed[:20]})"

    async def codegen(i, reasoning, ctx):
        rec["codegen_reasoning"] = reasoning
        return ([{"path": "x", "content": "c"}], None, [])

    async def critic(c, ws):
        return True, []

    arm = ArmCls(classifier=classifier, loader=loader, reasoner=reasoner, codegen=codegen, critic=critic, scorer=None)
    return arm, rec


@pytest.mark.parametrize("mod,cls", [("code_arm", "CodeArm"), ("design_arm", "DesignArm"), ("data_arm", "DataArm")])
def test_all_arms_have_deep_phases(mod, cls):
    import importlib

    ArmCls = getattr(importlib.import_module(f"core.engine.arms.{mod}"), cls)
    arm, _ = _arm_with_spies(ArmCls)
    # .update kept the seeded deep phases AND added the domain phases
    for cat in ("architect", "foresight", "generate", "ground_scan"):
        assert cat in arm.phase, (cls, cat, list(arm.phase))


@pytest.mark.asyncio
@pytest.mark.parametrize("mod,cls", [("code_arm", "CodeArm"), ("design_arm", "DesignArm"), ("data_arm", "DataArm")])
async def test_greenfield_plan_runs_architect_and_generate_consumes_it(mod, cls):
    # Real end-to-end (no phase spies) for EVERY arm: architect runs AND its output reaches
    # codegen — so a future per-arm generate edit that drops _compose_reasoning is caught.
    import importlib

    ArmCls = getattr(importlib.import_module(f"core.engine.arms.{mod}"), cls)
    arm, rec = _arm_with_spies(ArmCls)
    plan = await arm.plan(Solution(intent="build a new parser", domain_hint=None))
    # architect ran (an architecture-framed reasoner call happened) ...
    assert any("architect" in f.lower() for f in rec["reason_framings"]), (cls, rec["reason_framings"])
    # ... and its output reached codegen's reasoning (consumed, not just produced)
    assert "ARCHITECTURE" in (rec["codegen_reasoning"] or ""), (cls, rec["codegen_reasoning"])
    assert plan.actions
