# tests/test_executor_hints.py
"""Tests for executor force_frameworks and frameworks_hint parameters."""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest


@pytest.mark.asyncio
async def test_force_frameworks_skips_complexity_gate():
    """force_frameworks=True enables framework selection even for simple/reactive tasks."""
    from core.engine.orchestration.composition_scorer import ScoredComposition
    from core.engine.orchestrator.executor import execute_task

    single_perspective = ScoredComposition(
        perspectives=["practitioner"],
        perspective_weights={"practitioner": 1.0},
        engagement_type="single",
        specialties=[],
        framework_hints=[],
    )

    with (
        patch("core.engine.orchestrator.executor.classify_task", new_callable=AsyncMock) as mock_classify,
        patch("core.engine.orchestrator.executor.load_intelligence", new_callable=AsyncMock) as mock_load,
        patch("core.engine.orchestrator.executor.llm") as mock_llm,
        patch("core.engine.orchestrator.executor.pool") as mock_pool,
        patch("core.engine.orchestration.composition_scorer.score_composition", new_callable=AsyncMock) as mock_score,
        patch("core.engine.graph.context.load_graph_context", new_callable=AsyncMock, return_value={}),
        patch("core.engine.skills.selector.select_skill", new_callable=AsyncMock, return_value=None),
        patch("core.engine.reasoning.selector.select_frameworks", new_callable=AsyncMock) as mock_fw_sel,
        patch("core.engine.reasoning.executor.execute_with_frameworks", new_callable=AsyncMock) as mock_fw_exec,
    ):
        mock_classify.return_value = {
            "discipline": "architecture",
            "archetype": "executor",
            "mode": "reactive",
            "complexity": "simple",
        }
        mock_load.return_value = {"insights": [], "total_count": 0}
        mock_score.return_value = single_perspective

        mock_fw_sel.return_value = MagicMock()
        mock_fw_exec.return_value = {
            "output": "Framework-powered result",
            "frameworks_used": ["first_principles"],
            "composition_pattern": "single",
        }

        mock_conn = AsyncMock()
        mock_conn.query = AsyncMock(return_value=[[{"id": "task:1"}]])
        mock_pool.connection.return_value.__aenter__ = AsyncMock(return_value=mock_conn)
        mock_pool.connection.return_value.__aexit__ = AsyncMock(return_value=False)

        result = await execute_task(
            description="Simple task",
            product_id="product:test",
            workspace_id="workspace:test",
            user_id="user:test",
            force_frameworks=True,
        )

    assert result["output"] == "Framework-powered result"
    assert result["strategies_used"] == ["first_principles"]
    mock_fw_sel.assert_called_once()
    call_kwargs = mock_fw_sel.call_args[1]
    assert call_kwargs.get("force") is True


@pytest.mark.asyncio
async def test_frameworks_hint_bypasses_auto_selection():
    """frameworks_hint loads specified frameworks instead of auto-selecting."""
    from core.engine.orchestration.composition_scorer import ScoredComposition
    from core.engine.orchestrator.executor import execute_task

    single_perspective = ScoredComposition(
        perspectives=["practitioner"],
        perspective_weights={"practitioner": 1.0},
        engagement_type="single",
        specialties=[],
        framework_hints=[],
    )

    with (
        patch("core.engine.orchestrator.executor.classify_task", new_callable=AsyncMock) as mock_classify,
        patch("core.engine.orchestrator.executor.load_intelligence", new_callable=AsyncMock) as mock_load,
        patch("core.engine.orchestrator.executor.llm") as mock_llm,
        patch("core.engine.orchestrator.executor.pool") as mock_pool,
        patch("core.engine.orchestration.composition_scorer.score_composition", new_callable=AsyncMock) as mock_score,
        patch("core.engine.graph.context.load_graph_context", new_callable=AsyncMock, return_value={}),
        patch("core.engine.skills.selector.select_skill", new_callable=AsyncMock, return_value=None),
        patch("core.engine.orchestrator.executor._load_frameworks_by_slug", new_callable=AsyncMock) as mock_load_fw,
        patch("core.engine.reasoning.executor.execute_with_frameworks", new_callable=AsyncMock) as mock_fw_exec,
    ):
        mock_classify.return_value = {
            "discipline": "architecture",
            "archetype": "advisor",
            "mode": "deliberative",
            "complexity": "moderate",
        }
        mock_load.return_value = {"insights": [], "total_count": 0}
        mock_score.return_value = single_perspective

        mock_load_fw.return_value = MagicMock()
        mock_fw_exec.return_value = {
            "output": "Hinted framework result",
            "frameworks_used": ["first_principles", "pre_mortem"],
            "composition_pattern": "stacked",
        }

        mock_conn = AsyncMock()
        mock_conn.query = AsyncMock(return_value=[[{"id": "task:2"}]])
        mock_pool.connection.return_value.__aenter__ = AsyncMock(return_value=mock_conn)
        mock_pool.connection.return_value.__aexit__ = AsyncMock(return_value=False)

        result = await execute_task(
            description="Design the API",
            product_id="product:test",
            workspace_id="workspace:test",
            user_id="user:test",
            frameworks_hint=["first_principles", "pre_mortem"],
        )

    assert result["strategies_used"] == ["first_principles", "pre_mortem"]
    mock_load_fw.assert_called_once_with(["first_principles", "pre_mortem"], "product:test")


@pytest.mark.asyncio
async def test_no_hints_uses_existing_behavior():
    """Without hints, executor uses existing auto-selection (unchanged behavior)."""
    from core.engine.orchestration.composition_scorer import ScoredComposition
    from core.engine.orchestrator.executor import execute_task

    single_perspective = ScoredComposition(
        perspectives=["practitioner"],
        perspective_weights={"practitioner": 1.0},
        engagement_type="single",
        specialties=[],
        framework_hints=[],
    )

    with (
        patch("core.engine.orchestrator.executor.classify_task", new_callable=AsyncMock) as mock_classify,
        patch("core.engine.orchestrator.executor.load_intelligence", new_callable=AsyncMock) as mock_load,
        patch("core.engine.orchestrator.executor.llm") as mock_llm,
        patch("core.engine.orchestrator.executor.pool") as mock_pool,
        patch("core.engine.orchestration.composition_scorer.score_composition", new_callable=AsyncMock) as mock_score,
        patch("core.engine.graph.context.load_graph_context", new_callable=AsyncMock, return_value={}),
        patch("core.engine.skills.selector.select_skill", new_callable=AsyncMock, return_value=None),
    ):
        mock_classify.return_value = {
            "discipline": "architecture",
            "archetype": "executor",
            "mode": "reactive",
            "complexity": "simple",
        }
        mock_load.return_value = {"insights": [], "total_count": 0}
        mock_score.return_value = single_perspective
        mock_llm.complete = AsyncMock(return_value="Vanilla result")

        mock_conn = AsyncMock()
        mock_conn.query = AsyncMock(return_value=[[{"id": "task:3"}]])
        mock_pool.connection.return_value.__aenter__ = AsyncMock(return_value=mock_conn)
        mock_pool.connection.return_value.__aexit__ = AsyncMock(return_value=False)

        result = await execute_task(
            description="Simple task",
            product_id="product:test",
            workspace_id="workspace:test",
            user_id="user:test",
        )

    assert result["output"] == "Vanilla result"
    assert "strategies_used" not in result
