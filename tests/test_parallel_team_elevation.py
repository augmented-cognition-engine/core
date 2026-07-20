# tests/test_parallel_team_elevation.py
"""Tests for PM parallel group elevation to Team pattern."""

from unittest.mock import AsyncMock, MagicMock

import pytest

from core.engine.orchestration.agent import AgentConfig, AgentResult
from core.engine.orchestration.patterns.base import PatternConfig


@pytest.mark.asyncio
async def test_team_skip_synthesis():
    """Team pattern skips synthesis when metadata.skip_synthesis is True."""
    from core.engine.orchestration.patterns.team import TeamPattern

    mock_bus = MagicMock()
    mock_bus.publish = AsyncMock()
    mock_bus.subscribe_global = MagicMock()
    mock_bus.unsubscribe = MagicMock()

    agent_results = [
        AgentResult(agent_id="a1", status="completed", output="Output A"),
        AgentResult(agent_id="a2", status="completed", output="Output B"),
    ]

    mock_factory = MagicMock()
    mock_agents = []
    for ar in agent_results:
        agent = MagicMock()
        agent.agent_id = ar.agent_id
        agent.execute = AsyncMock(return_value=ar)
        mock_agents.append(agent)

    mock_factory.create = MagicMock(side_effect=mock_agents)

    pattern = TeamPattern(bus=mock_bus, factory=mock_factory)

    config = PatternConfig(
        run_id="test-run",
        product_id="product:test",
        metadata={"skip_synthesis": True},
    )
    agent_configs = [
        AgentConfig(role="worker-a", system_prompt="Do A"),
        AgentConfig(role="worker-b", system_prompt="Do B"),
    ]

    result = await pattern.execute("Test task", config, agent_configs)

    assert result.status == "completed"
    # Synthesis agent should NOT have been created (only 2 agents, not 3)
    assert mock_factory.create.call_count == 2
    assert "Output A" in result.output
    assert "Output B" in result.output
    assert result.metadata.get("synthesis_skipped") is True


def test_wi_to_agent_config():
    """Work item dict maps to AgentConfig correctly."""
    from core.engine.pm.parallel import wi_to_agent_config

    wi = {
        "id": "wi:abc",
        "title": "Implement OAuth2",
        "archetype": "creator",
        "mode": "deliberative",
        "domain_path": "security",
        "files_touched": ["engine/auth.py"],
        "description": "Add OAuth2 support",
    }
    config = wi_to_agent_config(wi)

    assert config.role == "Implement OAuth2"
    assert "building something that doesn't exist" in config.system_prompt.lower()
    assert "reasoning carefully" in config.system_prompt.lower()
    assert config.metadata["work_item_id"] == "wi:abc"
    assert config.metadata["files_touched"] == ["engine/auth.py"]
    assert config.metadata["archetype"] == "creator"


def test_wi_to_agent_config_defaults():
    """Missing archetype/mode default to executor/reactive."""
    from core.engine.pm.parallel import wi_to_agent_config

    wi = {"id": "wi:1", "title": "Fix bug", "description": "Fix it"}
    config = wi_to_agent_config(wi)

    assert config.metadata["archetype"] == "executor"
    assert config.metadata["mode"] == "reactive"


def test_build_milestone_task():
    """Builds milestone context string with WI summaries."""
    from core.engine.pm.parallel import build_milestone_task

    wis = [
        {"title": "Backend API", "domain_path": "architecture", "files_touched": ["api.py"]},
        {"title": "Frontend UI", "domain_path": "ux", "files_touched": ["App.tsx"]},
    ]
    context = {"title": "M1: Auth System", "description": "Build auth"}
    result = build_milestone_task(wis, context)

    assert "M1: Auth System" in result
    assert "Backend API" in result
    assert "Frontend UI" in result
    assert "api.py" in result


def test_max_severity_import():
    """max_severity is importable from parallel module."""
    from core.engine.pm.parallel import max_severity as ms

    assert ms([]) == "none"
    assert ms([{"severity": "low"}, {"severity": "high"}]) == "high"


@pytest.mark.asyncio
async def test_single_wi_fallback():
    """Single work item uses existing single orchestrate() path."""

    from core.engine.pm.parallel import ParallelExecutor

    executor = ParallelExecutor(
        product_id="product:test",
        workspace_id="workspace:default",
        user_id="user:test",
    )
    call_log = []

    async def mock_execute_single(wi, product_id):
        call_log.append(wi["id"])
        return {"id": wi["id"], "output": "done", "status": "completed"}

    executor._execute_single_work_item = mock_execute_single

    results = await executor.execute_parallel_group([{"id": "wi:1", "title": "Solo task"}], "product:test")
    assert len(results) == 1
    assert call_log == ["wi:1"]


@pytest.mark.asyncio
async def test_high_severity_sequential_fallback():
    """High severity conflicts use sequential execution."""

    from core.engine.pm.parallel import ParallelExecutor

    executor = ParallelExecutor(
        product_id="product:test",
        workspace_id="workspace:default",
        user_id="user:test",
    )
    executed = []

    async def mock_execute_single(wi, product_id):
        executed.append(wi["id"])
        return {"id": wi["id"], "output": "done", "status": "completed"}

    executor._execute_single_work_item = mock_execute_single

    wis = [
        {"id": "wi:1", "title": "A", "files_touched": ["core/engine/api/main.py"]},
        {"id": "wi:2", "title": "B", "files_touched": ["core/engine/api/main.py"]},
    ]
    results = await executor.execute_parallel_group(wis, "product:test")

    assert len(results) == 2
    assert executed == ["wi:1", "wi:2"]


@pytest.mark.asyncio
async def test_team_pattern_elevation():
    """Multiple WIs with no conflicts -> single orchestrate() call with team pattern."""
    from unittest.mock import patch

    from core.engine.pm.parallel import ParallelExecutor

    executor = ParallelExecutor(
        product_id="product:test",
        workspace_id="workspace:default",
        user_id="user:test",
    )

    mock_pattern_result = MagicMock()
    mock_pattern_result.agent_results = [
        AgentResult(agent_id="a1", status="completed", output="Done A"),
        AgentResult(agent_id="a2", status="completed", output="Done B"),
    ]
    mock_pattern_result.status = "completed"

    mock_orch_result = MagicMock()
    mock_orch_result.pattern_result = mock_pattern_result
    mock_orch_result.status = "completed"
    mock_orch_result.error = None

    with patch("core.engine.orchestration.orchestrate", new_callable=AsyncMock) as mock_orch:
        mock_orch.return_value = mock_orch_result

        wis = [
            {
                "id": "wi:1",
                "title": "Backend",
                "files_touched": ["api.py"],
                "archetype": "creator",
                "mode": "deliberative",
            },
            {
                "id": "wi:2",
                "title": "Frontend",
                "files_touched": ["app.tsx"],
                "archetype": "creator",
                "mode": "reactive",
            },
        ]
        results = await executor.execute_parallel_group(wis, "product:test")

    mock_orch.assert_called_once()
    call_args = mock_orch.call_args
    request = call_args[0][0]
    assert request.pattern == "team"
    assert len(request.agent_configs) == 2
    assert len(results) == 2
