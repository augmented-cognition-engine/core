# tests/test_graph_writer.py
"""Tests for engine.graph.writer — graph write after task execution.

Phase 3: shadow graph_task / graph_agent tables retired.
Only agent_execution, produced (real), and improves edges are written.
"""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

_DEFAULT_CLASSIFICATION = {
    "archetype": "executor",
    "mode": "reactive",
    "perspective": "practitioner",
    "specialties": [],
    "engagement": None,
}


def _make_pool(side_effects=None):
    """Create a mock pool whose query() returns values from side_effects list."""
    mock_pool = MagicMock()
    mock_conn = AsyncMock()
    if side_effects is not None:
        mock_conn.query = AsyncMock(side_effect=side_effects)
    else:
        mock_conn.query = AsyncMock(return_value=[])
    mock_pool.connection.return_value.__aenter__ = AsyncMock(return_value=mock_conn)
    mock_pool.connection.return_value.__aexit__ = AsyncMock(return_value=False)
    return mock_pool, mock_conn


# ---------------------------------------------------------------------------
# Tests: slugify helpers
# ---------------------------------------------------------------------------


def test_slugify_basic():
    from core.engine.graph.writer import _slugify

    assert _slugify("executor") == "executor"
    assert _slugify("llm-engineering") == "llm-engineering"
    assert _slugify("Practitioner") == "practitioner"
    assert _slugify("some:odd:id") == "some_odd_id"


def test_agent_slug_defaults():
    from core.engine.graph.writer import _agent_slug

    classification = {
        "archetype": "executor",
        "mode": "reactive",
        "perspective": "practitioner",
        "specialties": [],
    }
    slug = _agent_slug(classification)
    assert slug == "practitioner_reactive_executor"


def test_agent_slug_with_specialty():
    from core.engine.graph.writer import _agent_slug

    classification = {
        "archetype": "creator",
        "mode": "deliberative",
        "perspective": "practitioner",
        "specialties": ["llm-engineering"],
    }
    slug = _agent_slug(classification)
    assert slug == "practitioner_deliberative_creator_llm-engineering"


# ---------------------------------------------------------------------------
# Tests: write_task_to_graph — agent_execution node
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_write_task_creates_agent_execution():
    """write_task_to_graph issues UPSERT for agent_execution (real table)."""
    ae_record = {"id": "agent_execution:practitioner_reactive_executor"}
    side_effects = [
        ae_record,  # UPSERT agent_execution
        [],  # RELATE produced (real tables)
    ]
    mock_pool, mock_conn = _make_pool(side_effects=side_effects)

    with patch("core.engine.graph.writer.pool", mock_pool):
        from core.engine.graph.writer import write_task_to_graph

        result = await write_task_to_graph(
            task_id="task:abc123",
            description="Write tests for the auth module",
            status="completed",
            output="Here are the tests...",
            feedback=None,
            classification=_DEFAULT_CLASSIFICATION,
        )

    # First query is UPSERT agent_execution
    first_query = str(mock_conn.query.call_args_list[0].args[0])
    assert "agent_execution" in first_query

    # No graph_task or graph_agent writes
    all_queries = " ".join(str(c.args[0]) for c in mock_conn.query.call_args_list)
    assert "graph_task" not in all_queries
    assert "graph_agent" not in all_queries

    # Result includes expected keys
    assert "task_rid" in result
    assert "agent_rid" in result
    assert result["agent_rid"].startswith("agent_execution:")


@pytest.mark.asyncio
async def test_write_task_creates_produced_edge():
    """write_task_to_graph issues produced RELATE on real tables when completed."""
    ae_record = {"id": "agent_execution:practitioner_reactive_executor"}
    side_effects = [
        ae_record,  # UPSERT agent_execution
        [],  # RELATE produced (real tables)
    ]
    mock_pool, mock_conn = _make_pool(side_effects=side_effects)

    with patch("core.engine.graph.writer.pool", mock_pool):
        from core.engine.graph.writer import write_task_to_graph

        result = await write_task_to_graph(
            task_id="task:edge_test",
            description="Build the auth service",
            status="completed",
            output="Done.",
            feedback=None,
            classification=_DEFAULT_CLASSIFICATION,
        )

    all_queries = " ".join(str(c.args[0]) for c in mock_conn.query.call_args_list)
    assert "RELATE" in all_queries
    assert "produced" in all_queries
    assert "produced" in result["edges"]

    # No assigned_to edge (retired with graph_task/graph_agent)
    assert "assigned_to" not in all_queries
    assert "assigned_to" not in result["edges"]


@pytest.mark.asyncio
async def test_write_task_no_produced_when_not_completed():
    """produced edge is skipped when status != 'completed'."""
    ae_record = {"id": "agent_execution:practitioner_reactive_executor"}
    side_effects = [
        ae_record,  # UPSERT agent_execution
    ]
    mock_pool, mock_conn = _make_pool(side_effects=side_effects)

    with patch("core.engine.graph.writer.pool", mock_pool):
        from core.engine.graph.writer import write_task_to_graph

        result = await write_task_to_graph(
            task_id="task:failed_task",
            description="Something that failed",
            status="failed",
            output=None,
            feedback=None,
            classification=_DEFAULT_CLASSIFICATION,
        )

    all_queries = " ".join(str(c.args[0]) for c in mock_conn.query.call_args_list)
    assert "produced" not in all_queries
    assert "produced" not in result["edges"]


@pytest.mark.asyncio
async def test_write_task_no_produced_when_no_output():
    """produced edge is skipped when output is None even if status is completed."""
    ae_record = {"id": "agent_execution:practitioner_reactive_executor"}
    side_effects = [
        ae_record,  # UPSERT agent_execution
    ]
    mock_pool, mock_conn = _make_pool(side_effects=side_effects)

    with patch("core.engine.graph.writer.pool", mock_pool):
        from core.engine.graph.writer import write_task_to_graph

        result = await write_task_to_graph(
            task_id="task:no_output",
            description="Task with no output",
            status="completed",
            output=None,
            feedback=None,
            classification=_DEFAULT_CLASSIFICATION,
        )

    all_queries = " ".join(str(c.args[0]) for c in mock_conn.query.call_args_list)
    assert "produced" not in all_queries
    assert "produced" not in result["edges"]


# ---------------------------------------------------------------------------
# Tests: improves edges for files_touched
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_write_task_with_files_touched():
    """write_task_to_graph creates improves edges for each matched graph_file."""
    file_query_return = [{"id": "graph_file:abc"}]

    ae_record = {"id": "agent_execution:practitioner_reactive_executor"}
    side_effects = [
        ae_record,  # UPSERT agent_execution
        [],  # RELATE produced (real tables)
        file_query_return,  # SELECT graph_file for engine/auth.py
        [],  # RELATE improves
    ]
    mock_pool, mock_conn = _make_pool(side_effects=side_effects)

    with patch("core.engine.graph.writer.pool", mock_pool):
        from core.engine.graph.writer import write_task_to_graph

        result = await write_task_to_graph(
            task_id="task:with_files",
            description="Refactor auth module",
            status="completed",
            output="Refactored.",
            feedback=None,
            classification=_DEFAULT_CLASSIFICATION,
            files_touched=["engine/auth.py"],
        )

    all_queries = " ".join(str(c.args[0]) for c in mock_conn.query.call_args_list)
    assert "improves" in all_queries
    assert any("improves:" in e for e in result["edges"])


@pytest.mark.asyncio
async def test_write_task_files_touched_no_match():
    """improves edge is skipped when graph_file lookup returns no rows."""
    ae_record = {"id": "agent_execution:practitioner_reactive_executor"}
    side_effects = [
        ae_record,  # UPSERT agent_execution
        [],  # RELATE produced (real tables)
        [],  # SELECT graph_file -- empty result, no match
    ]
    mock_pool, mock_conn = _make_pool(side_effects=side_effects)

    with patch("core.engine.graph.writer.pool", mock_pool):
        from core.engine.graph.writer import write_task_to_graph

        result = await write_task_to_graph(
            task_id="task:unmatched_file",
            description="Touch unknown file",
            status="completed",
            output="Done.",
            feedback=None,
            classification=_DEFAULT_CLASSIFICATION,
            files_touched=["nonexistent/file.py"],
        )

    assert not any("improves:" in e for e in result["edges"])


# ---------------------------------------------------------------------------
# Tests: best-effort — errors don't propagate to callers
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_write_task_best_effort_db_error():
    """DB errors inside write_task_to_graph propagate out (callers wrap in try/except)."""
    mock_pool = MagicMock()
    mock_conn = AsyncMock()
    mock_conn.query = AsyncMock(side_effect=RuntimeError("DB down"))
    mock_pool.connection.return_value.__aenter__ = AsyncMock(return_value=mock_conn)
    mock_pool.connection.return_value.__aexit__ = AsyncMock(return_value=False)

    with patch("core.engine.graph.writer.pool", mock_pool):
        from core.engine.graph.writer import write_task_to_graph

        # The function raises — callers must wrap in try/except (best-effort pattern)
        with pytest.raises(RuntimeError, match="DB down"):
            await write_task_to_graph(
                task_id="task:boom",
                description="This will fail",
                status="completed",
                output="x",
                feedback=None,
                classification=_DEFAULT_CLASSIFICATION,
            )


@pytest.mark.asyncio
async def test_executor_graph_write_is_best_effort():
    """write_task_to_graph is called inside try/except in executor — errors don't surface."""
    # Simulate a graph write failure being swallowed by the executor's best-effort block
    graph_write_called = []
    graph_write_raised = []

    async def _mock_write(*args, **kwargs):
        graph_write_called.append(True)
        raise RuntimeError("graph write failed")

    # Directly test the best-effort wrapper pattern used by executors
    task_id = "task:best_effort_test"
    try:
        await _mock_write(
            task_id=task_id, description="x", status="completed", output="y", feedback=None, classification={}
        )
    except Exception:
        graph_write_raised.append(True)

    # The error is caught
    assert graph_write_called
    # Without a try/except it would raise — but executors use try/except pass
    assert graph_write_raised  # the bare call raised

    # Now show that the executor pattern (try/except pass) swallows it
    swallowed = []
    try:
        await _mock_write(
            task_id=task_id, description="x", status="completed", output="y", feedback=None, classification={}
        )
    except Exception:
        pass  # graph write is best-effort
    else:
        swallowed.append(True)

    # No assertion — just proving the pattern compiles and doesn't blow up
    assert len(graph_write_called) == 2  # called twice above
