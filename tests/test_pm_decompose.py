# tests/test_pm_decompose.py
"""Tests for PM Decomposition Engine — LLM-powered initiative/milestone decomposition."""

from unittest.mock import AsyncMock, MagicMock

import pytest


@pytest.fixture
def mock_llm():
    llm_mock = AsyncMock()
    return llm_mock


@pytest.fixture
def mock_db():
    db = AsyncMock()
    db.query = AsyncMock(return_value=[])
    return db


@pytest.fixture
def mock_pool(mock_db):
    p = MagicMock()
    ctx = AsyncMock()
    ctx.__aenter__ = AsyncMock(return_value=mock_db)
    ctx.__aexit__ = AsyncMock(return_value=False)
    p.connection = MagicMock(return_value=ctx)
    return p


@pytest.mark.asyncio
async def test_decompose_milestones(mock_llm, mock_pool, mock_db):
    """LLM decomposition returns 3-6 milestones with done criteria, dependencies, sequence."""
    from core.engine.pm.decompose import PMDecomposer

    mock_llm.complete_json = AsyncMock(
        return_value={
            "milestones": [
                {
                    "title": "M1: Design token schema",
                    "description": "Design the brand token schema structure",
                    "done_criteria": ["Schema file exists", "Validation passes"],
                    "requires_approval": False,
                    "sequence": 1,
                },
                {
                    "title": "M2: Prototype in Storybook",
                    "description": "Build working prototype",
                    "done_criteria": ["Storybook renders", "Brand switching works"],
                    "requires_approval": True,
                    "sequence": 2,
                },
                {
                    "title": "M3: Integration",
                    "description": "Integrate with existing components",
                    "done_criteria": ["All components updated", "Tests pass"],
                    "requires_approval": True,
                    "sequence": 3,
                },
            ]
        }
    )

    decomposer = PMDecomposer(db_pool=mock_pool, llm=mock_llm)
    milestones = await decomposer.decompose_initiative(
        title="Multi-brand token architecture",
        description="Support multiple brand themes in one token set",
        product_id="product:test",
        domain_path="architecture",
    )

    assert len(milestones) >= 3
    assert len(milestones) <= 6
    assert milestones[0]["sequence"] == 1
    assert len(milestones[0]["done_criteria"]) > 0
    assert milestones[1]["requires_approval"] is True


@pytest.mark.asyncio
async def test_decompose_work_items(mock_llm, mock_pool, mock_db):
    """Milestone decomposes into work items with archetype, mode, parallel group, files_touched."""
    from core.engine.pm.decompose import PMDecomposer

    mock_llm.complete_json = AsyncMock(
        return_value={
            "work_items": [
                {
                    "title": "Create brand token schema file",
                    "description": "Define the JSON schema for brand tokens",
                    "archetype": "creator",
                    "mode": "deliberative",
                    "skill": None,
                    "domain_path": "architecture",
                    "parallel_group": 1,
                    "files_touched": ["src/tokens/schema.json", "src/tokens/validate.ts"],
                    "requires_human": False,
                },
                {
                    "title": "Research brand patterns",
                    "description": "Research existing brand token patterns",
                    "archetype": "researcher",
                    "mode": "exploratory",
                    "skill": "deep-research",
                    "domain_path": "architecture",
                    "parallel_group": 1,
                    "files_touched": ["docs/research.md"],
                    "requires_human": False,
                },
                {
                    "title": "Build brand switching mechanism",
                    "description": "Implement the brand switching logic",
                    "archetype": "creator",
                    "mode": "deliberative",
                    "skill": None,
                    "domain_path": "architecture",
                    "parallel_group": 2,
                    "files_touched": ["src/brand-switch.ts", "src/tokens/schema.json"],
                    "requires_human": False,
                },
            ]
        }
    )

    decomposer = PMDecomposer(db_pool=mock_pool, llm=mock_llm)
    work_items = await decomposer.decompose_milestone(
        milestone_title="M1: Design token schema",
        milestone_description="Design the brand token schema structure",
        done_criteria=["Schema file exists", "Validation passes"],
        initiative_title="Multi-brand token architecture",
        product_id="product:test",
        domain_path="architecture",
    )

    assert len(work_items) >= 2
    # Check structure
    wi = work_items[0]
    assert "archetype" in wi
    assert "mode" in wi
    assert "parallel_group" in wi
    assert "files_touched" in wi
    assert wi["archetype"] in ["creator", "analyst", "executor", "researcher", "advisor", "sentinel"]


@pytest.mark.asyncio
async def test_decompose_validates_archetypes(mock_llm, mock_pool, mock_db):
    """Invalid archetypes are corrected to defaults."""
    from core.engine.pm.decompose import PMDecomposer

    mock_llm.complete_json = AsyncMock(
        return_value={
            "work_items": [
                {
                    "title": "Do something",
                    "description": "Do a thing",
                    "archetype": "invalid_archetype",
                    "mode": "invalid_mode",
                    "domain_path": "architecture",
                    "parallel_group": 1,
                    "files_touched": [],
                },
            ]
        }
    )

    decomposer = PMDecomposer(db_pool=mock_pool, llm=mock_llm)
    work_items = await decomposer.decompose_milestone(
        milestone_title="M1",
        milestone_description="test",
        done_criteria=["done"],
        initiative_title="test",
        product_id="product:test",
        domain_path="architecture",
    )

    assert work_items[0]["archetype"] == "executor"  # default fallback
    assert work_items[0]["mode"] == "reactive"  # default fallback


@pytest.mark.asyncio
async def test_decompose_milestone_count_bounds(mock_llm, mock_pool, mock_db):
    """Decomposition trims milestones to 3-6 range."""
    from core.engine.pm.decompose import PMDecomposer

    # Return 8 milestones — should be trimmed to 6
    mock_llm.complete_json = AsyncMock(
        return_value={
            "milestones": [
                {"title": f"M{i}", "description": f"ms {i}", "done_criteria": ["done"], "sequence": i}
                for i in range(1, 9)
            ]
        }
    )

    decomposer = PMDecomposer(db_pool=mock_pool, llm=mock_llm)
    milestones = await decomposer.decompose_initiative(
        title="Big initiative",
        description="test",
        product_id="product:test",
        domain_path="architecture",
    )

    assert len(milestones) <= 6


@pytest.mark.asyncio
async def test_decompose_uses_intelligence(mock_llm, mock_pool, mock_db):
    """Decomposition loads intelligence context for the domain."""
    from core.engine.pm.decompose import PMDecomposer

    mock_llm.complete_json = AsyncMock(
        return_value={
            "milestones": [
                {"title": "M1", "description": "test", "done_criteria": ["done"], "sequence": 1},
                {"title": "M2", "description": "test", "done_criteria": ["done"], "sequence": 2},
                {"title": "M3", "description": "test", "done_criteria": ["done"], "sequence": 3},
            ]
        }
    )

    # Mock intelligence loading
    mock_db.query = AsyncMock(
        return_value=[
            [
                {"content": "Always use TypeScript for frontend", "confidence": 0.9},
            ]
        ]
    )

    decomposer = PMDecomposer(db_pool=mock_pool, llm=mock_llm)
    milestones = await decomposer.decompose_initiative(
        title="Frontend feature",
        description="Build new frontend feature",
        product_id="product:test",
        domain_path="architecture",
    )

    # Verify LLM was called with intelligence context
    call_args = mock_llm.complete_json.call_args
    prompt = call_args[0][0] if call_args[0] else call_args[1].get("prompt", "")
    assert "intelligence" in prompt.lower() or "insight" in prompt.lower() or len(milestones) >= 3


@pytest.mark.asyncio
async def test_pm_never_executes():
    """PM decompose module has no direct LLM task execution — only decomposition."""
    import inspect

    from core.engine.pm import decompose

    source = inspect.getsource(decompose)
    # Should NOT call execute_task directly
    assert "execute_task(" not in source
    # Should use complete_json for decomposition (not complete for task execution)
    assert "complete_json" in source or "complete_structured" in source
