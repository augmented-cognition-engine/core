# tests/cognition/test_tool_binding.py
from core.engine.cognition.models import (
    CognitiveComposition,
    RecipePhase,
    ToolSpec,
)


def test_toolspec_defaults():
    spec = ToolSpec(fallback_slug="ace_code_context")
    assert spec.fallback_slug == "ace_code_context"
    assert spec.slug is None
    assert spec.family_hint is None


def test_recipephase_tools_defaults_empty():
    phase = RecipePhase(cognitive_function="frame", instruments=[], min_depth=1, output_schema="x")
    assert phase.tools == []


def test_recipephase_accepts_tools():
    phase = RecipePhase(
        cognitive_function="frame",
        instruments=[],
        min_depth=1,
        output_schema="x",
        tools=[ToolSpec(fallback_slug="ace_code_context")],
    )
    assert phase.tools[0].fallback_slug == "ace_code_context"


def test_composition_resolved_tools_defaults_empty():
    comp = CognitiveComposition(
        meta_skills=[],
        depth=1,
        active_phases=[],
        resolved_instruments={},
        prompt_sections=[],
        fusion_mode=True,
    )
    assert comp.resolved_tools == {}


from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from core.engine.cognition.tool_classifier import ToolClassifier


def _mock_pool(query_return):
    db = MagicMock()
    db.query = AsyncMock(return_value=query_return)
    ctx = MagicMock()
    ctx.__aenter__ = AsyncMock(return_value=db)
    ctx.__aexit__ = AsyncMock(return_value=False)
    pool = MagicMock()
    pool.connection.return_value = ctx
    return pool


async def test_resolve_tool_explicit_slug_skips_db():
    tc = ToolClassifier()
    spec = ToolSpec(fallback_slug="fallback", slug="ace_blast_radius")
    out = await tc.resolve_tool(
        spec=spec,
        task_type="review",
        discipline="architecture",
        product_id="product:p",
        cognitive_function="validate",
        meta_skill="coding_intelligence",
    )
    assert out == "ace_blast_radius"


async def test_resolve_tool_cold_start_returns_fallback():
    tc = ToolClassifier()
    spec = ToolSpec(fallback_slug="ace_code_context", family_hint="code_structure")
    with patch("core.engine.cognition.tool_classifier.pool", _mock_pool([])):
        out = await tc.resolve_tool(
            spec=spec,
            task_type="implement",
            discipline="architecture",
            product_id="product:p",
            cognitive_function="frame",
            meta_skill="coding_intelligence",
        )
    assert out == "ace_code_context"


async def test_resolve_tool_learned_wins_when_mature():
    tc = ToolClassifier()
    spec = ToolSpec(fallback_slug="ace_code_context", family_hint="code_structure")
    rows = [{"tool_slug": "ace_blast_radius", "avg_score": 0.9, "sample_count": 25}]
    with (
        patch("core.engine.cognition.tool_classifier.pool", _mock_pool(rows)),
        patch("core.engine.cognition.tool_classifier.parse_rows", return_value=rows),
    ):
        out = await tc.resolve_tool(
            spec=spec,
            task_type="implement",
            discipline="architecture",
            product_id="product:p",
            cognitive_function="frame",
            meta_skill="coding_intelligence",
        )
    assert out == "ace_blast_radius"


async def test_resolve_tool_returns_fallback_on_db_error():
    tc = ToolClassifier()
    spec = ToolSpec(fallback_slug="ace_code_context", family_hint="code_structure")
    pool = MagicMock()
    pool.connection.side_effect = Exception("DB down")
    with patch("core.engine.cognition.tool_classifier.pool", pool):
        out = await tc.resolve_tool(
            spec=spec,
            task_type="implement",
            discipline="architecture",
            product_id="product:p",
            cognitive_function="frame",
            meta_skill="coding_intelligence",
        )
    assert out == "ace_code_context"


from core.engine.cognition.tool_catalog import render_phase_tools


def test_render_phase_tools_empty_returns_empty_string():
    assert render_phase_tools([]) == ""


def test_render_phase_tools_known_slug_includes_description():
    out = render_phase_tools(["ace_code_context"])
    assert "## Tools relevant to this phase" in out
    assert "ace_code_context" in out
    assert "structural code context" in out.lower()


def test_render_phase_tools_unknown_slug_renders_bare():
    out = render_phase_tools(["totally_unknown_tool"])
    assert "totally_unknown_tool" in out
    # no trailing ": " description for unknown slugs
    assert "totally_unknown_tool:" not in out


@pytest.mark.asyncio
async def test_composer_resolves_phase_tools_into_resolved_tools(monkeypatch):
    from unittest.mock import AsyncMock
    from unittest.mock import patch as _patch

    from core.engine.cognition.composer import CognitiveComposer
    from core.engine.cognition.models import MetaSkill, MetaSkillRecipe

    classification = {
        "discipline": "architecture",
        "task_type": "code",
        "mode": "reactive",
        "complexity": "simple",  # depth 1
    }
    composer = CognitiveComposer()
    phase = RecipePhase(
        cognitive_function="frame",
        instruments=[],
        min_depth=1,
        output_schema="x",
        tools=[ToolSpec(fallback_slug="ace_code_context")],
    )
    skill = MetaSkill(
        slug="coding_intelligence",
        name="Coding",
        description="",
        domain_intelligences=[],
        recipe=MetaSkillRecipe(phases=[phase]),
    )
    monkeypatch.setattr(composer, "_load_recipe", lambda slug: skill)
    # _selected_with_scores is what _compose_inner calls — stub it to return our single
    # skill plus its per-task score (the (slugs, scores) contract the blend consumes).
    monkeypatch.setattr(
        composer, "_selected_with_scores", lambda *a, **k: (["coding_intelligence"], {"coding_intelligence": 1.0})
    )
    with _patch.object(composer._classifier, "resolve_instrument", new=AsyncMock(return_value="first-principles")):
        composition = await composer.compose(classification, "product:test")

    assert composition.resolved_tools.get("0") == ["ace_code_context"]
    sec0 = next(s for s in composition.prompt_sections if s.get("phase_idx") == "0")
    assert sec0["tool_slugs"] == ["ace_code_context"]


from core.engine.cognition.fusion import PromptFusion


def _section_with_tools(idx, fn, tool_slugs):
    return {
        "phase_idx": str(idx),
        "cognitive_function": fn,
        "framework_slugs": [],
        "output_schema": "x",
        "pattern": "solo",
        "fusion_label": f"[{fn.upper()}]",
        "tool_slugs": tool_slugs,
    }


def test_fusion_renders_advisory_tool_section():
    comp = CognitiveComposition(
        meta_skills=["coding_intelligence"],
        depth=1,
        active_phases=[RecipePhase(cognitive_function="frame", instruments=[], min_depth=1, output_schema="x")],
        resolved_instruments={"0": []},
        prompt_sections=[_section_with_tools(0, "frame", ["ace_code_context"])],
        fusion_mode=True,
        resolved_tools={"0": ["ace_code_context"]},
    )
    out = PromptFusion().fuse(comp, framework_prompts={})
    assert "## Tools relevant to this phase" in out
    assert "ace_code_context" in out


def test_fusion_no_tool_section_when_phase_has_no_tools():
    comp = CognitiveComposition(
        meta_skills=["coding_intelligence"],
        depth=1,
        active_phases=[RecipePhase(cognitive_function="frame", instruments=[], min_depth=1, output_schema="x")],
        resolved_instruments={"0": []},
        prompt_sections=[_section_with_tools(0, "frame", [])],
        fusion_mode=True,
        resolved_tools={"0": []},
    )
    out = PromptFusion().fuse(comp, framework_prompts={})
    assert "## Tools relevant to this phase" not in out


@pytest.mark.asyncio
async def test_multiphase_renders_advisory_tool_section():
    import json

    from core.engine.cognition.multiphase import MultiPhaseExecutor

    captured_systems = []

    async def _llm(system, user):
        text = "\n".join(b.get("text", "") for b in system) if isinstance(system, list) else str(system)
        captured_systems.append(text)
        return json.dumps({"output": "o", "confidence": 0.9, "evidence": [], "gaps": []})

    comp = CognitiveComposition(
        meta_skills=["coding_intelligence"],
        depth=3,
        active_phases=[RecipePhase(cognitive_function="frame", instruments=[], min_depth=1, output_schema="x")],
        resolved_instruments={"0": []},
        prompt_sections=[_section_with_tools(0, "frame", ["ace_blast_radius"])],
        fusion_mode=False,
        resolved_tools={"0": ["ace_blast_radius"]},
    )
    executor = MultiPhaseExecutor(llm_call=_llm, on_phase=None)
    await executor.execute(
        description="t",
        composition=comp,
        framework_prompts={},
        intel_context="",
        product_id="product:test",
    )
    assert any("## Tools relevant to this phase" in s and "ace_blast_radius" in s for s in captured_systems)


async def test_resolve_tool_query_excludes_unscored_rows():
    """The learned query must exclude outcome_score=None rows (AND outcome_score >= 0)
    so unscored rows can't cross the cold-start threshold and rank arbitrarily."""
    tc = ToolClassifier()
    spec = ToolSpec(fallback_slug="ace_code_context", family_hint="x")
    pool = _mock_pool([])
    with patch("core.engine.cognition.tool_classifier.pool", pool):
        await tc.resolve_tool(
            spec=spec,
            task_type="implement",
            discipline="architecture",
            product_id="product:p",
            cognitive_function="frame",
            meta_skill="coding_intelligence",
        )
    db = pool.connection.return_value.__aenter__.return_value
    sql = db.query.call_args[0][0]
    assert "outcome_score >= 0" in sql, "learned query must exclude unscored rows"
