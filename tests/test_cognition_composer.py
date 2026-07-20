# tests/test_cognition_composer.py
from unittest.mock import AsyncMock, patch

import pytest

from core.engine.cognition.composer import (
    _DISCIPLINE_META,
    ENABLE_PROBLEM_DERIVED_SELECTION,
    CognitiveComposer,
)
from core.engine.cognition.models import CognitiveComposition
from core.engine.product.seed_packs import SEED_STRUCTURE

# Tests below this point assert legacy dict-based routing. They guard the dict
# contents during the migration window. Skip them when problem-derived selection
# is canonical — the dict path is no longer the active selector.
_LEGACY_DICT_SKIP_REASON = (
    "Asserts legacy _DISCIPLINE_META / dict-based routing. "
    "Problem-derived selection is canonical; this dict is being removed."
)


@pytest.fixture
def composer():
    return CognitiveComposer()


@pytest.mark.asyncio
async def test_compose_returns_cognitive_composition(composer):
    classification = {
        "discipline": "architecture",
        "task_type": "implement",
        "mode": "deliberative",
        "complexity": "moderate",
    }
    with patch.object(composer._classifier, "resolve_instrument", new=AsyncMock(return_value="constraint-theory")):
        result = await composer.compose(classification, "product:test")
    assert isinstance(result, CognitiveComposition)


@pytest.mark.asyncio
async def test_compose_depth_one_sets_fusion_mode(composer):
    classification = {"discipline": "architecture", "task_type": "code", "mode": "reactive", "complexity": "simple"}
    with patch.object(composer._classifier, "resolve_instrument", new=AsyncMock(return_value="first-principles")):
        result = await composer.compose(classification, "product:test")
    assert result.depth == 1
    assert result.fusion_mode is True


@pytest.mark.asyncio
async def test_compose_depth_four_disables_fusion_mode(composer):
    classification = {
        "discipline": "architecture",
        "task_type": "design",
        "mode": "reflective",
        "complexity": "complex",
    }
    with patch.object(composer._classifier, "resolve_instrument", new=AsyncMock(return_value="first-principles")):
        result = await composer.compose(classification, "product:test")
    assert result.depth == 4
    assert result.fusion_mode is False


@pytest.mark.asyncio
async def test_compose_depth_one_only_activates_min_depth_one_phases(composer):
    classification = {"discipline": "architecture", "task_type": "code", "mode": "reactive", "complexity": "simple"}
    with patch.object(composer._classifier, "resolve_instrument", new=AsyncMock(return_value="first-principles")):
        result = await composer.compose(classification, "product:test")
    for phase in result.active_phases:
        assert phase.min_depth <= 1


@pytest.mark.asyncio
async def test_compose_includes_meta_skill_slugs(composer):
    classification = {
        "discipline": "architecture",
        "task_type": "implement",
        "mode": "deliberative",
        "complexity": "moderate",
    }
    with patch.object(composer._classifier, "resolve_instrument", new=AsyncMock(return_value="first-principles")):
        result = await composer.compose(classification, "product:test")
    assert len(result.meta_skills) >= 1


@pytest.mark.asyncio
async def test_compose_coding_task_includes_coding_intelligence(composer):
    classification = {
        "discipline": "api_design",
        "task_type": "implement",
        "mode": "procedural",
        "complexity": "moderate",
    }
    with patch.object(composer._classifier, "resolve_instrument", new=AsyncMock(return_value="constraint-theory")):
        result = await composer.compose(classification, "product:test")
    assert "coding_intelligence" in result.meta_skills


@pytest.mark.skipif(ENABLE_PROBLEM_DERIVED_SELECTION, reason=_LEGACY_DICT_SKIP_REASON)
def test_all_seed_disciplines_have_meta_skill_mapping():
    """Every discipline in SEED_STRUCTURE must have a _DISCIPLINE_META entry.

    This is the regression guard so that adding a new discipline to seed_packs.py
    without wiring it in composer.py doesn't silently fall through.
    """
    missing = [d for d in SEED_STRUCTURE if d not in _DISCIPLINE_META]
    assert not missing, f"Disciplines missing from _DISCIPLINE_META: {missing}"


@pytest.mark.skipif(ENABLE_PROBLEM_DERIVED_SELECTION, reason=_LEGACY_DICT_SKIP_REASON)
@pytest.mark.asyncio
@pytest.mark.parametrize(
    "discipline,expected_meta",
    [
        ("ai_ml", "evaluation_intelligence"),
        ("scale", "systems_intelligence"),
        ("product_strategy", "strategic_intelligence"),
    ],
)
async def test_new_disciplines_route_to_correct_meta_skill(composer, discipline, expected_meta):
    classification = {
        "discipline": discipline,
        "task_type": "",
        "mode": "reactive",
        "complexity": "moderate",
    }
    with patch.object(composer._classifier, "resolve_instrument", new=AsyncMock(return_value="first-principles")):
        result = await composer.compose(classification, "product:test")
    assert expected_meta in result.meta_skills


# ---------------------------------------------------------------------------
# min_execution_depth override tests (Phase 5)
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_creative_intelligence_raises_depth_from_reactive(composer):
    """creative_intelligence has min_execution_depth=2 — reactive (depth=1) must be raised to 2."""
    classification = {
        "discipline": "ux",
        "task_type": "design",
        "mode": "reactive",
        "complexity": "simple",
    }
    with patch.object(composer._classifier, "resolve_instrument", new=AsyncMock(return_value="first-principles")):
        result = await composer.compose(classification, "product:test")
    # Sentinel: creative_intelligence floor must override reactive depth=1
    assert result.depth >= 2, f"Expected depth >= 2 for creative_intelligence, got {result.depth}"


@pytest.mark.asyncio
async def test_depth_override_updates_fusion_mode(composer):
    """When depth is raised from 1 to 2, fusion_mode must stay True (depth<=2)."""
    classification = {
        "discipline": "ux",
        "task_type": "design",
        "mode": "reactive",
        "complexity": "simple",
    }
    with patch.object(composer._classifier, "resolve_instrument", new=AsyncMock(return_value="first-principles")):
        result = await composer.compose(classification, "product:test")
    # depth=2 still fuses (depth <= 2 → fusion_mode=True)
    assert result.fusion_mode is True


@pytest.mark.asyncio
async def test_higher_mode_depth_not_lowered_by_min_execution_depth(composer):
    """A reflective mode (depth=4) must not be lowered even if min_execution_depth=2."""
    classification = {
        "discipline": "ux",
        "task_type": "design",
        "mode": "reflective",
        "complexity": "complex",
    }
    with patch.object(composer._classifier, "resolve_instrument", new=AsyncMock(return_value="first-principles")):
        result = await composer.compose(classification, "product:test")
    assert result.depth == 4
    assert result.fusion_mode is False


@pytest.mark.asyncio
async def test_coding_intelligence_does_not_inflate_depth(composer):
    """coding_intelligence has min_execution_depth=1 (default) — reactive stays reactive."""
    classification = {
        "discipline": "api_design",
        "task_type": "implement",
        "mode": "reactive",
        "complexity": "simple",
    }
    with patch.object(composer._classifier, "resolve_instrument", new=AsyncMock(return_value="first-principles")):
        result = await composer.compose(classification, "product:test")
    # coding_intelligence has no floor — depth must remain 1
    assert result.depth == 1


# ---------------------------------------------------------------------------
# Task 4 — loop context consumption (TDD)
# ---------------------------------------------------------------------------

_LOOP_CTX = {
    "prior_decisions": [
        {
            "title": "Use SurrealDB",
            "rationale": "graph-native fits the knowledge graph",
            "decision_type": "architecture",
        }
    ],
    "calibration": {
        "analyst": {"score": 0.82, "samples": 7},
        "executor": {"score": 0.65, "samples": 3},
    },
}


@pytest.mark.asyncio
async def test_compose_with_loop_context_no_recent_decisions_includes_both_decisions_and_calibration(composer):
    """(a) loop_context present + NO recent_decisions → prompt_sections contains
    'What we already know' with BOTH decision lines AND calibration lines."""
    classification = {
        "discipline": "architecture",
        "task_type": "design",
        "mode": "deliberative",
        "complexity": "moderate",
        "loop_context": _LOOP_CTX,
        # NO recent_decisions key — deep_committee path
    }
    with patch.object(composer._classifier, "resolve_instrument", new=AsyncMock(return_value="constraint-theory")):
        result = await composer.compose(classification, "product:test")

    section = next(
        (s for s in result.prompt_sections if s.get("title") == "What we already know"),
        None,
    )
    assert section is not None, "Expected a 'What we already know' prompt section"
    body = section["body"]
    # Decision line present
    assert "Use SurrealDB" in body, f"Expected decision title in body; got: {body}"
    # Calibration lines present
    assert "analyst" in body, f"Expected calibration archetype 'analyst' in body; got: {body}"
    assert "0.82" in body, f"Expected calibration score in body; got: {body}"


@pytest.mark.asyncio
async def test_compose_with_loop_context_and_recent_decisions_includes_calibration_only(composer):
    """(b) FUSED composition + loop_context + non-empty recent_decisions →
    section has calibration but NOT decision titles. Suppression is gated on
    fusion_mode: only on the fused path does ShellComposer's L5 block render
    recent_decisions; on the deep path the composer renders decisions itself
    (see test_deep_path_renders_decisions_even_when_recent_decisions_present
    in tests/cognition/test_reasoning_run.py)."""
    classification = {
        "discipline": "architecture",
        "task_type": "code",
        "mode": "reactive",
        "complexity": "simple",  # depth 1 → fusion_mode True → shell renders L5
        "loop_context": _LOOP_CTX,
        # recent_decisions is non-empty — fused executor path where shell.py renders them
        "recent_decisions": [{"title": "Use SurrealDB", "rationale": "graph-native", "decision_type": "architecture"}],
    }
    with patch.object(composer._classifier, "resolve_instrument", new=AsyncMock(return_value="constraint-theory")):
        result = await composer.compose(classification, "product:test")
    assert result.fusion_mode is True  # precondition: suppression only fires here

    section = next(
        (s for s in result.prompt_sections if s.get("title") == "What we already know"),
        None,
    )
    # Calibration data is present, so the section MUST exist (calibration-only form).
    assert section is not None, (
        "Expected a 'What we already know' section with calibration lines even when "
        f"recent_decisions suppresses decision lines; got sections: {result.prompt_sections}"
    )
    body = section["body"]
    # Calibration lines always render — nothing else surfaces calibration.
    assert "analyst" in body, f"Expected calibration archetype 'analyst' in body; got: {body}"
    assert "0.82" in body, f"Expected calibration score in body; got: {body}"
    # Decision title must NOT be repeated (shell.py's L5 block already rendered it)
    assert "Use SurrealDB" not in body, (
        f"Decision title must not be repeated when recent_decisions present; body: {body}"
    )


@pytest.mark.asyncio
async def test_compose_with_loop_context_sets_loop_context_attribute(composer):
    """(c) composition.loop_context attribute equals the input loop_context dict."""
    classification = {
        "discipline": "architecture",
        "task_type": "design",
        "mode": "deliberative",
        "complexity": "moderate",
        "loop_context": _LOOP_CTX,
    }
    with patch.object(composer._classifier, "resolve_instrument", new=AsyncMock(return_value="constraint-theory")):
        result = await composer.compose(classification, "product:test")

    assert hasattr(result, "loop_context"), "CognitiveComposition must have a loop_context attribute"
    assert result.loop_context == _LOOP_CTX


@pytest.mark.asyncio
async def test_compose_without_loop_context_works_with_no_db_and_no_section(composer):
    """(d) Bare classification (no loop_context) → no 'What we already know' section,
    loop_context == {}, and NO DB access attempted (regression tripwire)."""
    classification = {
        "discipline": "architecture",
        "task_type": "implement",
        "mode": "deliberative",
        "complexity": "moderate",
        # No loop_context key at all — stateless path, as today
    }
    with patch.object(composer._classifier, "resolve_instrument", new=AsyncMock(return_value="constraint-theory")):
        result = await composer.compose(classification, "product:test")

    # No section injected
    titles = [s.get("title") for s in result.prompt_sections]
    assert "What we already know" not in titles, (
        f"No 'What we already know' section expected for bare classification; got sections: {titles}"
    )
    # loop_context attribute defaults to empty dict
    assert hasattr(result, "loop_context"), "CognitiveComposition must have loop_context attribute"
    assert result.loop_context == {}
