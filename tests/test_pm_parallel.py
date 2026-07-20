# tests/test_pm_parallel.py
"""Tests for parallel work item execution with conflict prediction gates."""

import asyncio
from unittest.mock import AsyncMock, MagicMock

import pytest


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
async def test_execute_parallel_group_clean():
    """Parallel group with no high-severity conflicts elevates to Team pattern."""
    from unittest.mock import patch

    from core.engine.orchestration.agent import AgentResult
    from core.engine.pm.parallel import ParallelExecutor

    mock_pattern_result = MagicMock()
    mock_pattern_result.agent_results = [
        AgentResult(agent_id="a1", status="completed", output="Done 1"),
        AgentResult(agent_id="a2", status="completed", output="Done 2"),
    ]
    mock_orch_result = MagicMock()
    mock_orch_result.pattern_result = mock_pattern_result
    mock_orch_result.status = "completed"
    mock_orch_result.error = None

    executor = ParallelExecutor()

    work_items = [
        {"id": "wi:1", "files_touched": ["src/components/button.py"], "parallel_group": 1},
        {"id": "wi:2", "files_touched": ["src/models/user.py"], "parallel_group": 1},
    ]

    with patch("core.engine.orchestration.orchestrate", new_callable=AsyncMock, return_value=mock_orch_result):
        results = await executor.execute_parallel_group(work_items, product_id="product:test")

    assert len(results) == 2
    assert all(r["status"] == "completed" for r in results)


@pytest.mark.asyncio
async def test_execute_parallel_group_conflict():
    """Parallel group with file overlap falls back to sequential."""
    from core.engine.pm.parallel import ParallelExecutor

    execution_order = []

    async def mock_execute_wi(wi, product_id):
        execution_order.append(wi["id"])
        await asyncio.sleep(0.01)
        return {"id": wi["id"], "status": "completed"}

    executor = ParallelExecutor()
    executor._execute_single_work_item = mock_execute_wi

    work_items = [
        {"id": "wi:1", "files_touched": ["src/main.py", "src/utils.py"], "parallel_group": 1},
        {"id": "wi:2", "files_touched": ["src/main.py", "src/other.py"], "parallel_group": 1},
    ]

    results = await executor.execute_parallel_group(work_items, product_id="product:test")
    assert len(results) == 2
    # Sequential means wi:1 finishes before wi:2 starts
    assert execution_order == ["wi:1", "wi:2"]


@pytest.mark.asyncio
async def test_concurrency_cap_work_items():
    """Multiple non-conflicting WIs elevate to Team pattern (concurrency managed by orchestration layer)."""
    from unittest.mock import patch

    from core.engine.orchestration.agent import AgentResult
    from core.engine.pm.parallel import ParallelExecutor

    # 5 work items, all different files -> Team pattern elevation
    work_items = [{"id": f"wi:{i}", "files_touched": [f"src/file{i}.py"], "parallel_group": 1} for i in range(5)]

    mock_pattern_result = MagicMock()
    mock_pattern_result.agent_results = [
        AgentResult(agent_id=f"a{i}", status="completed", output=f"Done {i}") for i in range(5)
    ]
    mock_orch_result = MagicMock()
    mock_orch_result.pattern_result = mock_pattern_result
    mock_orch_result.status = "completed"
    mock_orch_result.error = None

    executor = ParallelExecutor(max_parallel_work_items=3)

    with patch("core.engine.orchestration.orchestrate", new_callable=AsyncMock, return_value=mock_orch_result):
        results = await executor.execute_parallel_group(work_items, product_id="product:test")

    assert len(results) == 5
    assert all(r["status"] == "completed" for r in results)


@pytest.mark.asyncio
async def test_execute_milestone_groups():
    """Execute milestone with multiple parallel groups in sequence.

    Group 1 (2 WIs, no conflicts) elevates to Team pattern via orchestrate().
    Group 2 (1 WI) runs directly via _execute_single_work_item.
    Groups execute in order: group 1 completes before group 2 starts.
    """
    from unittest.mock import patch

    from core.engine.orchestration.agent import AgentResult
    from core.engine.pm.parallel import ParallelExecutor

    group_completion_order = []

    async def mock_execute_wi(wi, product_id):
        group_completion_order.append(wi["id"])
        await asyncio.sleep(0.01)
        return {"id": wi["id"], "status": "completed"}

    # Mock orchestrate for the Team pattern path (group 1 with 2 WIs)
    mock_pattern_result = MagicMock()
    mock_pattern_result.agent_results = [
        AgentResult(agent_id="a1", status="completed", output="Done 1"),
        AgentResult(agent_id="a2", status="completed", output="Done 2"),
    ]
    mock_orch_result = MagicMock()
    mock_orch_result.pattern_result = mock_pattern_result
    mock_orch_result.status = "completed"
    mock_orch_result.error = None

    async def mock_orchestrate(request):
        group_completion_order.append("team:group1")
        return mock_orch_result

    executor = ParallelExecutor()
    executor._execute_single_work_item = mock_execute_wi

    work_items = [
        {"id": "wi:1", "files_touched": ["src/a.py"], "parallel_group": 1},
        {"id": "wi:2", "files_touched": ["src/b.py"], "parallel_group": 1},
        {"id": "wi:3", "files_touched": ["src/c.py"], "parallel_group": 2},
    ]

    with patch("core.engine.orchestration.orchestrate", side_effect=mock_orchestrate):
        results = await executor.execute_milestone_work_items(work_items, product_id="product:test")

    assert len(results) == 3
    # Group 1 (team pattern) completes before group 2 (single WI)
    idx_3 = group_completion_order.index("wi:3")
    assert "team:group1" in group_completion_order[:idx_3]


@pytest.mark.asyncio
async def test_post_task_hooks():
    """Post-task hooks (type-check, lint, unit-test, format) run after task execution."""
    from core.engine.pm.parallel import run_post_task_hooks

    hook_log = []

    async def mock_run_hook(hook_name, work_dir=None):
        hook_log.append(hook_name)
        return {"hook": hook_name, "passed": True}

    results = await run_post_task_hooks(
        hooks=["type-check", "lint", "unit-test", "format"],
        run_hook_fn=mock_run_hook,
    )

    assert len(results) == 4
    assert hook_log == ["type-check", "lint", "unit-test", "format"]
    assert all(r["passed"] for r in results)


@pytest.mark.asyncio
async def test_post_task_hook_failure():
    """Failed hook returns failure without blocking other hooks."""
    from core.engine.pm.parallel import run_post_task_hooks

    async def mock_run_hook(hook_name, work_dir=None):
        if hook_name == "lint":
            return {"hook": hook_name, "passed": False, "error": "lint errors found"}
        return {"hook": hook_name, "passed": True}

    results = await run_post_task_hooks(
        hooks=["type-check", "lint", "unit-test", "format"],
        run_hook_fn=mock_run_hook,
    )

    assert len(results) == 4
    lint_result = next(r for r in results if r["hook"] == "lint")
    assert lint_result["passed"] is False


@pytest.mark.asyncio
async def test_single_work_item_no_parallel():
    """Single work item runs directly without parallel overhead."""
    from core.engine.pm.parallel import ParallelExecutor

    async def mock_execute_wi(wi, product_id):
        return {"id": wi["id"], "status": "completed"}

    executor = ParallelExecutor()
    executor._execute_single_work_item = mock_execute_wi

    work_items = [
        {"id": "wi:1", "files_touched": ["src/main.py"], "parallel_group": 1},
    ]

    results = await executor.execute_parallel_group(work_items, product_id="product:test")
    assert len(results) == 1
    assert results[0]["status"] == "completed"
