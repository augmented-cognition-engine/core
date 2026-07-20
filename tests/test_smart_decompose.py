# tests/test_smart_decompose.py
"""Tests for SmartDecomposer — DAG-based spec decomposition with conflict-aware scheduling."""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest


def _make_pool(db):
    pool = MagicMock()
    cm = AsyncMock()
    cm.__aenter__ = AsyncMock(return_value=db)
    cm.__aexit__ = AsyncMock(return_value=None)
    pool.connection.return_value = cm
    return pool


# test_work_unit_to_dict: verify WorkUnit serialization
def test_work_unit_to_dict():
    from core.engine.product.smart_decompose import WorkUnit

    wu = WorkUnit(
        id="unit-1",
        title="Write tests",
        description="TDD",
        files_create=["tests/test_foo.py"],
        archetype="sentinel",
        mode="procedural",
    )
    d = wu.to_dict()
    assert d["id"] == "unit-1"
    assert d["archetype"] == "sentinel"
    assert d["files_create"] == ["tests/test_foo.py"]


# test_decomposition_plan_to_dict: verify plan serialization
def test_decomposition_plan_to_dict():
    from core.engine.orchestration.dispatch_planner import DispatchBatch, DispatchSchedule
    from core.engine.product.smart_decompose import DecompositionPlan, WorkUnit

    units = [WorkUnit(id="unit-1", title="Build", description="Build it")]
    schedule = DispatchSchedule(batches=[DispatchBatch(task_ids=["unit-1"], mode="sequential")])
    plan = DecompositionPlan(spec_id="agent_spec:123", units=units, schedule=schedule)
    d = plan.to_dict()
    assert d["total_units"] == 1
    assert d["spec_id"] == "agent_spec:123"


# test_decompose_calls_llm_and_planner: mock LLM + DB, verify decompose produces plan
@pytest.mark.asyncio
async def test_decompose_calls_llm_and_planner():
    db = AsyncMock()
    db.query.return_value = [
        {
            "id": "agent_spec:123",
            "objective": "Add rate limiting",
            "acceptance_criteria": [{"criterion": "Returns 429"}],
            "estimated_files": ["core/engine/api/main.py"],
            "constraints": ["Don't break auth"],
        }
    ]
    pool = _make_pool(db)

    with patch("core.engine.product.smart_decompose.get_llm") as mock_llm_fn:
        mock_llm = MagicMock()
        mock_llm.complete_json = AsyncMock(
            return_value=[
                {
                    "id": "unit-1",
                    "title": "Implement rate limiter",
                    "description": "Add slowapi",
                    "files_create": [],
                    "files_modify": ["core/engine/api/main.py"],
                    "depends_on": [],
                    "archetype": "creator",
                    "mode": "deliberative",
                },
                {
                    "id": "unit-2",
                    "title": "Write tests",
                    "description": "Test 429 response",
                    "files_create": ["tests/test_rate_limit.py"],
                    "files_modify": [],
                    "depends_on": ["unit-1"],
                    "archetype": "sentinel",
                    "mode": "procedural",
                },
            ]
        )
        mock_llm_fn.return_value = mock_llm

        from core.engine.product.smart_decompose import SmartDecomposer

        decomposer = SmartDecomposer(pool)
        plan = await decomposer.decompose("agent_spec:123", "product:platform")

        assert len(plan.units) == 2
        assert plan.units[0].archetype == "creator"
        assert plan.units[1].depends_on == ["unit-1"]
        assert plan.schedule.total_tasks == 2


# test_decompose_spec_not_found: raises DecompositionError
@pytest.mark.asyncio
async def test_decompose_spec_not_found():
    from core.engine.core.exceptions import DecompositionError

    db = AsyncMock()
    db.query.return_value = []
    pool = _make_pool(db)

    with patch("core.engine.product.smart_decompose.get_llm"):
        from core.engine.product.smart_decompose import SmartDecomposer

        decomposer = SmartDecomposer(pool)
        with pytest.raises(DecompositionError, match="not found"):
            await decomposer.decompose("agent_spec:nonexistent", "product:platform")


# test_llm_decompose_parses_rejection_traces: chosen/rejected format parsed correctly
@pytest.mark.asyncio
async def test_llm_decompose_parses_rejection_traces():
    db = AsyncMock()
    db.query.return_value = [
        {
            "id": "agent_spec:999",
            "objective": "Add caching",
            "acceptance_criteria": [],
            "estimated_files": [],
            "constraints": [],
        }
    ]
    pool = _make_pool(db)

    with patch("core.engine.product.smart_decompose.get_llm") as mock_llm_fn:
        mock_llm = MagicMock()
        mock_llm.complete_json = AsyncMock(
            return_value={
                "chosen": [
                    {
                        "id": "unit-1",
                        "title": "Implement cache",
                        "description": "Add Redis cache",
                        "files_create": ["engine/cache.py"],
                        "files_modify": [],
                        "depends_on": [],
                        "archetype": "creator",
                        "mode": "deliberative",
                        "reasoning": "New module",
                    }
                ],
                "rejected": [{"summary": "In-memory dict cache", "reason": "Not persistent across restarts"}],
            }
        )
        mock_llm_fn.return_value = mock_llm

        with patch("core.engine.product.smart_decompose._write_rejection_traces", new=AsyncMock()) as mock_write:
            from core.engine.product.smart_decompose import SmartDecomposer

            decomposer = SmartDecomposer(pool)
            plan = await decomposer.decompose("agent_spec:999", "product:platform")

            assert len(plan.units) == 1
            assert plan.units[0].title == "Implement cache"
            mock_write.assert_called_once()
            args = mock_write.call_args[0]
            assert args[2] == "agent_spec:999"  # spec_id
            assert len(args[3]) == 1  # one rejection
            assert args[3][0]["summary"] == "In-memory dict cache"


# test_write_rejection_traces_stores_to_db: writes failure_memory records
@pytest.mark.asyncio
async def test_write_rejection_traces_stores_to_db():
    db = AsyncMock()
    db.query = AsyncMock()
    pool = _make_pool(db)

    from core.engine.product.smart_decompose import _write_rejection_traces

    traces = [
        {"summary": "Monolithic approach", "reason": "Can't parallelize"},
        {"summary": "Over-decomposed", "reason": "Too many dependencies"},
    ]
    await _write_rejection_traces(pool, "product:test", "agent_spec:abc", traces)

    assert db.query.call_count == 2
    first_call_params = db.query.call_args_list[0][0][1]
    assert first_call_params["data"]["discipline"] == "decomposition"
    assert first_call_params["data"]["type"] == "decomposition_rejection"
    assert first_call_params["data"]["summary"] == "Monolithic approach"


# test_write_rejection_traces_skips_empty: no DB calls when traces is empty
@pytest.mark.asyncio
async def test_write_rejection_traces_skips_empty():
    db = AsyncMock()
    pool = _make_pool(db)

    from core.engine.product.smart_decompose import _write_rejection_traces

    await _write_rejection_traces(pool, "product:test", "agent_spec:abc", [])

    db.query.assert_not_called()


# test_decompose_best_of_n_returns_highest_scoring_plan: with evaluator, picks best
@pytest.mark.asyncio
async def test_decompose_best_of_n_returns_highest_scoring_plan():
    db = AsyncMock()
    db.query.return_value = [
        {
            "id": "agent_spec:42",
            "objective": "Add auth",
            "acceptance_criteria": [],
            "estimated_files": [],
            "constraints": [],
        }
    ]
    pool = _make_pool(db)

    # LLM returns different plans on each call
    call_count = 0

    def make_plan(n):
        return {
            "chosen": [
                {
                    "id": f"unit-{n}",
                    "title": f"Plan {n}",
                    "description": f"approach {n}",
                    "files_create": [],
                    "files_modify": [],
                    "depends_on": [],
                    "archetype": "creator",
                    "mode": "deliberative",
                    "reasoning": f"reason {n}",
                }
            ],
            "rejected": [],
        }

    async def _multi_plan(*args, **kwargs):
        nonlocal call_count
        call_count += 1
        return make_plan(call_count)

    with patch("core.engine.product.smart_decompose.get_llm") as mock_llm_fn:
        mock_llm = MagicMock()
        mock_llm.complete_json = AsyncMock(side_effect=_multi_plan)
        mock_llm_fn.return_value = mock_llm

        from unittest.mock import AsyncMock as AM

        from core.engine.product.smart_decompose import SmartDecomposer

        # Scores: plan 1 = 0.5, plan 2 = 0.9, plan 3 = 0.3 → plan 2 wins
        mock_evaluator = MagicMock()
        mock_evaluator.evaluate = AM(side_effect=[0.5, 0.9, 0.3])

        with patch("core.engine.product.smart_decompose._write_rejection_traces", new=AM()):
            decomposer = SmartDecomposer(pool, plan_evaluator=mock_evaluator, branch_count=3)
            plan = await decomposer.decompose("agent_spec:42", "product:platform")

    # Plan 2 scored 0.9 (highest)
    assert plan.units[0].title == "Plan 2"
    assert mock_evaluator.evaluate.call_count == 3


# test_decompose_uses_single_call_when_no_evaluator: no evaluator → single _llm_decompose call
@pytest.mark.asyncio
async def test_decompose_uses_single_call_when_no_evaluator():
    db = AsyncMock()
    db.query.return_value = [
        {
            "id": "agent_spec:1",
            "objective": "Simple task",
            "acceptance_criteria": [],
            "estimated_files": [],
            "constraints": [],
        }
    ]
    pool = _make_pool(db)

    with patch("core.engine.product.smart_decompose.get_llm") as mock_llm_fn:
        mock_llm = MagicMock()
        mock_llm.complete_json = AsyncMock(
            return_value=[
                {
                    "id": "unit-1",
                    "title": "Do it",
                    "description": "Just do it",
                    "files_create": [],
                    "files_modify": [],
                    "depends_on": [],
                    "archetype": "creator",
                    "mode": "deliberative",
                }
            ]
        )
        mock_llm_fn.return_value = mock_llm

        with patch("core.engine.product.smart_decompose._write_rejection_traces", new=AsyncMock()):
            from core.engine.product.smart_decompose import SmartDecomposer

            decomposer = SmartDecomposer(pool)  # no plan_evaluator
            plan = await decomposer.decompose("agent_spec:1", "product:platform")

    assert len(plan.units) == 1
    assert mock_llm.complete_json.call_count == 1  # single call


def test_smart_decomposer_accepts_plan_evaluator_via_init():
    """SmartDecomposer init stores plan_evaluator for use in decompose."""
    from unittest.mock import MagicMock

    from core.engine.product.smart_decompose import SmartDecomposer

    mock_pool = MagicMock()
    mock_evaluator = MagicMock()
    decomposer = SmartDecomposer(mock_pool, plan_evaluator=mock_evaluator, branch_count=5)

    assert decomposer._plan_evaluator is mock_evaluator
    assert decomposer._branch_count == 5
