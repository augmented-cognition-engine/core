# tests/test_agent_orchestrator.py
"""Tests for AgentOrchestrator — cross-agent execution with blocker cascades and progress tracking."""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest


def _make_pool(db=None):
    if db is None:
        db = AsyncMock()
        db.query = AsyncMock(return_value=[])
    pool = MagicMock()
    cm = AsyncMock()
    cm.__aenter__ = AsyncMock(return_value=db)
    cm.__aexit__ = AsyncMock(return_value=None)
    pool.connection.return_value = cm
    return pool


def _make_plan(*unit_specs, spec_id="agent_spec:test"):
    """Build a minimal plan_dict from unit specs.

    Each unit_spec is a dict with optional keys:
      id, title, depends_on, archetype
    Batches are inferred: units without deps go in batch 0 (parallel),
    units with deps go in batch 1 (sequential).
    """
    units = []
    for i, spec in enumerate(unit_specs):
        uid = spec.get("id", f"unit-{i + 1}")
        units.append(
            {
                "id": uid,
                "title": spec.get("title", f"Unit {i + 1}"),
                "description": spec.get("description", "Do something"),
                "depends_on": spec.get("depends_on", []),
                "archetype": spec.get("archetype", "creator"),
                "mode": spec.get("mode", "deliberative"),
                "files_create": spec.get("files_create", []),
                "files_modify": spec.get("files_modify", []),
            }
        )

    # Build simple batches: independent first (parallel), dependents second (sequential)
    independent_ids = [u["id"] for u in units if not u["depends_on"]]
    dependent_ids = [u["id"] for u in units if u["depends_on"]]

    batches = []
    if independent_ids:
        batches.append({"task_ids": independent_ids, "mode": "parallel"})
    if dependent_ids:
        batches.append({"task_ids": dependent_ids, "mode": "sequential"})

    return {
        "spec_id": spec_id,
        "units": units,
        "batches": batches,
        "conflicts": [],
    }


# ── test 1 ─────────────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_execute_plan_all_complete():
    """All units succeed → completed count matches total, spec_status is 'verifying'."""
    pool = _make_pool()
    plan = _make_plan(
        {"id": "unit-1", "title": "Setup DB schema"},
        {"id": "unit-2", "title": "Implement API"},
        {"id": "unit-3", "title": "Write tests"},
    )

    with patch(
        "core.engine.orchestrator.executor.execute_task",
        new_callable=AsyncMock,
        return_value={"id": "task:1", "output": "done"},
    ):
        from core.engine.product.agent_orchestrator import AgentOrchestrator

        orch = AgentOrchestrator(db_pool=pool)
        summary = await orch.execute_plan(plan, product_id="product:test")

    assert summary["completed"] == 3
    assert summary["failed"] == 0
    assert summary["blocked"] == 0
    assert summary["total_units"] == 3
    assert summary["spec_status"] == "verifying"


# ── test 2 ─────────────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_execute_plan_with_failure():
    """One unit fails → downstream dependents are blocked, not executed."""
    pool = _make_pool()
    plan = _make_plan(
        {"id": "unit-1", "title": "Build core"},
        {"id": "unit-2", "title": "Build tests", "depends_on": ["unit-1"]},
        {"id": "unit-3", "title": "Deploy", "depends_on": ["unit-2"]},
    )

    from core.engine.product.agent_orchestrator import AgentOrchestrator, UnitStatus

    orch = AgentOrchestrator(db_pool=pool)

    # Patch _execute_unit to fail for unit-1
    original_execute = orch._execute_unit

    async def failing_execute(unit_id, unit, product_id, **kwargs):
        if unit_id == "unit-1":
            raise RuntimeError("Build core failed")
        return await original_execute(unit_id, unit, product_id, **kwargs)

    orch._execute_unit = failing_execute

    summary = await orch.execute_plan(plan, product_id="product:test")

    assert summary["failed"] >= 1
    assert summary["blocked"] >= 1
    # unit-2 and unit-3 should not have completed
    assert summary["unit_status"]["unit-2"] != UnitStatus.COMPLETED
    assert summary["unit_status"]["unit-3"] != UnitStatus.COMPLETED
    assert summary["spec_status"] == "failed"


# ── test 3 ─────────────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_execute_plan_parallel_batch():
    """Parallel batch executes all units; all complete with status 'verifying'."""
    pool = _make_pool()
    plan = {
        "spec_id": "agent_spec:parallel",
        "units": [
            {
                "id": "a",
                "title": "Task A",
                "description": "do A",
                "depends_on": [],
                "archetype": "creator",
                "mode": "deliberative",
                "files_create": [],
                "files_modify": [],
            },
            {
                "id": "b",
                "title": "Task B",
                "description": "do B",
                "depends_on": [],
                "archetype": "analyst",
                "mode": "deliberative",
                "files_create": [],
                "files_modify": [],
            },
            {
                "id": "c",
                "title": "Task C",
                "description": "do C",
                "depends_on": [],
                "archetype": "sentinel",
                "mode": "procedural",
                "files_create": [],
                "files_modify": [],
            },
        ],
        "batches": [
            {"task_ids": ["a", "b", "c"], "mode": "parallel"},
        ],
        "conflicts": [],
    }

    with patch(
        "core.engine.orchestrator.executor.execute_task",
        new_callable=AsyncMock,
        return_value={"id": "task:1", "output": "done"},
    ):
        from core.engine.product.agent_orchestrator import AgentOrchestrator, UnitStatus

        orch = AgentOrchestrator(db_pool=pool)
        summary = await orch.execute_plan(plan, product_id="product:test")

    assert summary["completed"] == 3
    assert summary["failed"] == 0
    assert summary["spec_status"] == "verifying"
    for uid in ["a", "b", "c"]:
        assert summary["unit_status"][uid] == UnitStatus.COMPLETED


# ── test 4 ─────────────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_get_progress():
    """get_progress returns accurate counts and percentage after partial execution."""
    pool = _make_pool()
    plan = _make_plan(
        {"id": "u1"},
        {"id": "u2"},
        {"id": "u3", "depends_on": ["u1"]},
        {"id": "u4", "depends_on": ["u2"]},
    )

    with patch(
        "core.engine.orchestrator.executor.execute_task",
        new_callable=AsyncMock,
        return_value={"id": "task:1", "output": "done"},
    ):
        from core.engine.product.agent_orchestrator import AgentOrchestrator

        orch = AgentOrchestrator(db_pool=pool)

        # Patch to fail u2 so u4 is blocked
        original_execute = orch._execute_unit

        async def selective_execute(unit_id, unit, product_id, **kwargs):
            if unit_id == "u2":
                raise RuntimeError("u2 failed")
            return await original_execute(unit_id, unit, product_id, **kwargs)

        orch._execute_unit = selective_execute
        await orch.execute_plan(plan, product_id="product:test")

    progress = orch.get_progress()

    assert progress["total"] == 4
    assert progress["completed"] == 2  # u1, u3
    assert progress["failed"] == 1  # u2
    assert progress["blocked"] == 1  # u4
    assert progress["pct"] == 50


# ── test 5 ─────────────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_empty_plan():
    """Empty plan → no errors, all counts are zero, progress returns empty state."""
    pool = _make_pool()
    plan = {
        "spec_id": "agent_spec:empty",
        "units": [],
        "batches": [],
        "conflicts": [],
    }

    from core.engine.product.agent_orchestrator import AgentOrchestrator

    orch = AgentOrchestrator(db_pool=pool)
    summary = await orch.execute_plan(plan, product_id="product:test")

    assert summary["total_units"] == 0
    assert summary["completed"] == 0
    assert summary["failed"] == 0
    assert summary["blocked"] == 0

    progress = orch.get_progress()
    assert progress["total"] == 0
    assert progress["pct"] == 0
