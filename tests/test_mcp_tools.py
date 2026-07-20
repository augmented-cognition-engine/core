# tests/test_mcp_tools.py
"""Tests for MCP tool implementations — each tool wraps an existing engine subsystem."""

from unittest.mock import AsyncMock, patch

import pytest


@pytest.mark.asyncio
async def test_ace_start_returns_session_context():
    """ace_start() returns briefing availability and session metadata."""
    from core.engine.mcp.tools import ace_start

    with patch("core.engine.mcp.tools.pool") as mock_pool:
        mock_conn = AsyncMock()
        mock_conn.query = AsyncMock(
            side_effect=[
                [[{"id": "briefing:1", "created_at": "2026-03-22T08:00:00Z"}]],
                [[{"c": 2}]],
                [[{"c": 3}]],
            ]
        )
        mock_pool.connection.return_value.__aenter__ = AsyncMock(return_value=mock_conn)
        mock_pool.connection.return_value.__aexit__ = AsyncMock(return_value=False)

        result = await ace_start(product_id="product:default")

    assert result["briefing_available"] is True
    assert result["active_initiatives"] == 2
    assert result["ideas_ready"] == 3


@pytest.mark.asyncio
async def test_ace_start_no_briefing():
    """ace_start() handles no briefing gracefully."""
    from core.engine.mcp.tools import ace_start

    with patch("core.engine.mcp.tools.pool") as mock_pool:
        mock_conn = AsyncMock()
        mock_conn.query = AsyncMock(
            side_effect=[
                [[]],  # no briefing
                [[]],  # no initiatives
                [[]],  # no ideas
            ]
        )
        mock_pool.connection.return_value.__aenter__ = AsyncMock(return_value=mock_conn)
        mock_pool.connection.return_value.__aexit__ = AsyncMock(return_value=False)

        result = await ace_start(product_id="product:default")

    assert result["briefing_available"] is False
    assert result["active_initiatives"] == 0


@pytest.mark.asyncio
async def test_ace_load_returns_partitioned_intelligence():
    """ace_load() returns insights partitioned into general, corrections, preferences."""
    from core.engine.mcp.tools import ace_load

    with patch("core.engine.mcp.tools.load_intelligence", new_callable=AsyncMock) as mock_load:
        mock_load.return_value = {
            "insights": [
                {"content": "Use flat namespace", "confidence": 0.9, "insight_type": "pattern"},
                {"content": "Never use px for spacing", "confidence": 0.85, "insight_type": "correction"},
                {"content": "Prefer TypeScript", "confidence": 0.8, "insight_type": "preference"},
            ],
            "total_count": 3,
        }

        result = await ace_load(topic="design tokens", product_id="product:default")

    assert result["domain_path"] == "design_tokens"
    assert len(result["insights"]) == 1
    assert len(result["corrections"]) == 1
    assert len(result["preferences"]) == 1
    assert result["total_count"] == 3


@pytest.mark.asyncio
async def test_ace_load_normalizes_topic():
    """ace_load() normalizes space-separated topics to domain_path format."""
    from core.engine.mcp.tools import ace_load

    with patch("core.engine.mcp.tools.load_intelligence", new_callable=AsyncMock) as mock_load:
        mock_load.return_value = {"insights": [], "total_count": 0}

        result = await ace_load(topic="Design Systems Tokens", product_id="product:default")

    assert result["domain_path"] == "design_systems_tokens"
    mock_load.assert_called_once_with("design_systems_tokens", "product:default", mode="reactive")


@pytest.mark.asyncio
async def test_ace_capture_records_observation():
    """ace_capture() writes observation to DB with source='mcp'."""
    from core.engine.mcp.tools import ace_capture

    with patch("core.engine.mcp.tools.pool") as mock_pool:
        mock_conn = AsyncMock()
        mock_conn.query = AsyncMock(return_value=[[{"id": "observation:abc123"}]])
        mock_pool.connection.return_value.__aenter__ = AsyncMock(return_value=mock_conn)
        mock_pool.connection.return_value.__aexit__ = AsyncMock(return_value=False)

        result = await ace_capture(
            observation_type="correction",
            content="Use rem not px for spacing",
            domain_path="design_systems.tokens",
            confidence=0.85,
            product_id="product:default",
        )

    assert result["status"] == "captured"
    assert result["id"] == "observation:abc123"
    # Verify params passed to query
    call_args = mock_conn.query.call_args
    params = call_args[0][1] if len(call_args[0]) > 1 else call_args[1]
    assert params["type"] == "correction"


@pytest.mark.asyncio
async def test_ace_task_routes_through_orchestrator():
    """ace_task() routes through orchestrate() and returns output + status."""
    from core.engine.mcp.tools import ace_task
    from core.engine.orchestration.executor import OrchestrationResult

    mock_result = OrchestrationResult(
        task_id="task:1",
        output="Analysis complete.",
        classification={"discipline": "architecture", "archetype": "analyst", "mode": "deliberative"},
        snapshot={},
        status="completed",
    )

    with patch("core.engine.orchestration.orchestrate", new_callable=AsyncMock) as mock_orch:
        mock_orch.return_value = mock_result
        result = await ace_task(
            description="Audit our token naming conventions",
            product_id="product:default",
            workspace_id="workspace:default",
            user_id="user:default",
        )

    assert result["output"] == "Analysis complete."
    assert result["status"] == "completed"
    mock_orch.assert_called_once()


@pytest.mark.asyncio
async def test_ace_task_with_skill_hint():
    """ace_task() passes skill_hint to orchestrate as force_skill."""
    from core.engine.mcp.tools import ace_task
    from core.engine.orchestration.executor import OrchestrationResult

    mock_result = OrchestrationResult(
        task_id="task:2",
        output="Done.",
        classification={"discipline": "architecture", "archetype": "executor", "mode": "reactive"},
        snapshot={},
        status="completed",
    )

    with patch("core.engine.orchestration.orchestrate", new_callable=AsyncMock) as mock_orch:
        mock_orch.return_value = mock_result
        await ace_task(
            description="Review this PR",
            skill_hint="code_review",
            product_id="product:default",
            workspace_id="workspace:default",
            user_id="user:default",
        )

    call_args = mock_orch.call_args[0][0]  # OrchestrationRequest
    assert call_args.force_skill == "code_review"


@pytest.mark.asyncio
async def test_ace_task_with_frameworks_hint():
    """ace_task() passes frameworks_hint to orchestrate."""
    from core.engine.mcp.tools import ace_task
    from core.engine.orchestration.executor import OrchestrationResult

    mock_result = OrchestrationResult(
        task_id="task:3",
        output="Done.",
        classification={"discipline": "architecture", "archetype": "advisor", "mode": "deliberative"},
        snapshot={},
        status="completed",
    )

    with patch("core.engine.orchestration.orchestrate", new_callable=AsyncMock) as mock_orch:
        mock_orch.return_value = mock_result
        await ace_task(
            description="Design the API",
            frameworks_hint=["first_principles", "pre_mortem"],
            product_id="product:default",
            workspace_id="workspace:default",
            user_id="user:default",
        )

    call_args = mock_orch.call_args[0][0]  # OrchestrationRequest
    assert call_args.frameworks_hint == ["first_principles", "pre_mortem"]


@pytest.mark.asyncio
async def test_ace_status_returns_jobs():
    """ace_status() returns active initiatives and pending items."""
    from core.engine.mcp.tools import ace_status

    with patch("core.engine.mcp.tools.pool") as mock_pool:
        mock_conn = AsyncMock()
        mock_conn.query = AsyncMock(
            side_effect=[
                [[{"id": "initiative:1", "status": "active", "name": "Token system redesign"}]],
                [[{"c": 5}]],
            ]
        )
        mock_pool.connection.return_value.__aenter__ = AsyncMock(return_value=mock_conn)
        mock_pool.connection.return_value.__aexit__ = AsyncMock(return_value=False)

        result = await ace_status(product_id="product:default")

    assert len(result["initiatives"]) == 1
    assert result["ideas_ready"] == 5


@pytest.mark.asyncio
async def test_ace_status_with_filter():
    """ace_status() applies filter when provided."""
    from core.engine.mcp.tools import ace_status

    with patch("core.engine.mcp.tools.pool") as mock_pool:
        mock_conn = AsyncMock()
        mock_conn.query = AsyncMock(
            side_effect=[
                [[]],  # filtered initiatives
                [[]],  # ideas count
            ]
        )
        mock_pool.connection.return_value.__aenter__ = AsyncMock(return_value=mock_conn)
        mock_pool.connection.return_value.__aexit__ = AsyncMock(return_value=False)

        result = await ace_status(product_id="product:default", filter="blocked")

    assert result["initiatives"] == []
    # Verify the filter was used in the query
    first_query_call = mock_conn.query.call_args_list[0]
    params = first_query_call[0][1] if len(first_query_call[0]) > 1 else first_query_call[1]
    assert params.get("status") == "blocked"


@pytest.mark.asyncio
async def test_ace_capture_idea_sends_to_incubator():
    """ace_capture_idea() creates an idea record via capture_idea."""
    from core.engine.mcp.tools import ace_capture_idea

    with patch("core.engine.mcp.tools.capture_idea", new_callable=AsyncMock) as mock_capture:
        mock_capture.return_value = {
            "id": "idea:1",
            "status": "captured",
            "qualifying_questions": ["What problem does this solve?"],
        }

        result = await ace_capture_idea(
            raw_idea="What if we used runtime-assembled agents instead of named agents?",
            product_id="product:default",
            user_id="user:default",
        )

    assert result["status"] == "captured"
    assert result["id"] == "idea:1"


@pytest.mark.asyncio
async def test_ace_capture_idea_with_context():
    """ace_capture_idea() appends context to raw_idea."""
    from core.engine.mcp.tools import ace_capture_idea

    with patch("core.engine.mcp.tools.capture_idea", new_callable=AsyncMock) as mock_capture:
        mock_capture.return_value = {"id": "idea:2", "status": "captured"}

        await ace_capture_idea(
            raw_idea="Token versioning system",
            context="Inspired by SemVer but for design tokens",
            product_id="product:default",
            user_id="user:default",
        )

    call_args = mock_capture.call_args[1]
    assert "Inspired by SemVer" in call_args["raw_input"]


@pytest.mark.asyncio
async def test_ace_search_queries_graph():
    """ace_search() returns matching insights from the graph."""
    from core.engine.mcp.tools import ace_search

    with patch("core.engine.mcp.tools.pool") as mock_pool:
        mock_conn = AsyncMock()
        mock_conn.query = AsyncMock(
            return_value=[
                [
                    {
                        "id": "insight:a1",
                        "content": "Token naming should use flat namespace",
                        "confidence": 0.9,
                        "insight_type": "pattern",
                    },
                    {
                        "id": "insight:a2",
                        "content": "Always test token changes",
                        "confidence": 0.75,
                        "insight_type": "preference",
                    },
                ]
            ]
        )
        mock_pool.connection.return_value.__aenter__ = AsyncMock(return_value=mock_conn)
        mock_pool.connection.return_value.__aexit__ = AsyncMock(return_value=False)

        result = await ace_search(query="token naming", product_id="product:default")

    assert result["count"] == 2
    assert len(result["results"]) == 2
    assert result["query"] == "token naming"


@pytest.mark.asyncio
async def test_ace_search_with_knowledge_type_filter():
    """ace_search() filters by knowledge_type when provided."""
    from core.engine.mcp.tools import ace_search

    with patch("core.engine.mcp.tools.pool") as mock_pool:
        mock_conn = AsyncMock()
        mock_conn.query = AsyncMock(
            return_value=[
                [
                    {"content": "Use rem not px", "confidence": 0.85, "insight_type": "correction"},
                ]
            ]
        )
        mock_pool.connection.return_value.__aenter__ = AsyncMock(return_value=mock_conn)
        mock_pool.connection.return_value.__aexit__ = AsyncMock(return_value=False)

        result = await ace_search(query="spacing", knowledge_type="correction", product_id="product:default")

    assert result["count"] == 1
    call_args = mock_conn.query.call_args
    params = call_args[0][1] if len(call_args[0]) > 1 else call_args[1]
    assert params["type"] == "correction"


@pytest.mark.asyncio
async def test_ace_briefing_returns_latest():
    """ace_briefing() returns the most recent briefing."""
    from core.engine.mcp.tools import ace_briefing

    with patch("core.engine.mcp.tools.pool") as mock_pool:
        mock_conn = AsyncMock()
        mock_conn.query = AsyncMock(
            return_value=[
                [
                    {
                        "id": "briefing:1",
                        "content": "## Weekly Briefing\nThis week ACE learned 5 new patterns.",
                        "period": "weekly",
                        "created_at": "2026-03-22T05:00:00Z",
                        "metrics": {"insights_created": 5, "corrections": 2},
                    }
                ]
            ]
        )
        mock_pool.connection.return_value.__aenter__ = AsyncMock(return_value=mock_conn)
        mock_pool.connection.return_value.__aexit__ = AsyncMock(return_value=False)

        result = await ace_briefing(product_id="product:default")

    assert result["available"] is True
    assert "Weekly Briefing" in result["content"]
    assert result["period"] == "weekly"


@pytest.mark.asyncio
async def test_ace_briefing_no_briefing_available():
    """ace_briefing() returns available=False when no briefings exist."""
    from core.engine.mcp.tools import ace_briefing

    with patch("core.engine.mcp.tools.pool") as mock_pool:
        mock_conn = AsyncMock()
        mock_conn.query = AsyncMock(return_value=[[]])
        mock_pool.connection.return_value.__aenter__ = AsyncMock(return_value=mock_conn)
        mock_pool.connection.return_value.__aexit__ = AsyncMock(return_value=False)

        result = await ace_briefing(product_id="product:default")

    assert result["available"] is False
    assert result["content"] is None


@pytest.mark.asyncio
async def test_ace_task_trace_includes_verification_when_gate_ran():
    """Verification block appears in trace when gate produced a meaningful verdict."""
    from core.engine.mcp.tools import ace_task
    from core.engine.orchestration.executor import OrchestrationResult

    mock_result = OrchestrationResult(
        task_id="task:verify1",
        output="Analysis complete.",
        classification={"discipline": "testing", "archetype": "analyst", "mode": "deliberative"},
        snapshot={
            "verified": True,
            "verification_verdict": "clean",
            "verification_gaps": [],
        },
        status="completed",
    )

    with patch("core.engine.orchestration.orchestrate", new_callable=AsyncMock) as mock_orch:
        mock_orch.return_value = mock_result
        result = await ace_task(
            description="Verify this implementation",
            product_id="product:default",
            workspace_id="workspace:default",
            user_id="user:default",
        )

    assert "verification" in result["trace"]
    assert result["trace"]["verification"]["verdict"] == "clean"
    assert result["trace"]["verification"]["verified"] is True
    assert result["trace"]["verification"]["gaps"] == []


@pytest.mark.asyncio
async def test_ace_task_trace_excludes_verification_when_skipped():
    """Verification block is absent from trace when verdict is 'skipped'."""
    from core.engine.mcp.tools import ace_task
    from core.engine.orchestration.executor import OrchestrationResult

    mock_result = OrchestrationResult(
        task_id="task:skip1",
        output="Done.",
        classification={"discipline": "architecture", "archetype": "analyst", "mode": "reactive"},
        snapshot={
            "verification_verdict": "skipped",
        },
        status="completed",
    )

    with patch("core.engine.orchestration.orchestrate", new_callable=AsyncMock) as mock_orch:
        mock_orch.return_value = mock_result
        result = await ace_task(
            description="Quick question",
            product_id="product:default",
            workspace_id="workspace:default",
            user_id="user:default",
        )

    assert "verification" not in result["trace"]


@pytest.mark.asyncio
async def test_ace_task_returns_dict_with_pattern_result():
    """ace_task() returns a complete dict when result includes a PatternResult (regression: return was inside elif)."""
    from dataclasses import dataclass

    from core.engine.mcp.tools import ace_task
    from core.engine.orchestration.executor import OrchestrationResult

    @dataclass
    class _FakePatternResult:
        pattern_name: str = "single_agent"

    mock_result = OrchestrationResult(
        task_id="task:pr1",
        output="Pattern output.",
        classification={"discipline": "testing", "archetype": "executor", "mode": "reactive"},
        snapshot={},
        status="completed",
        pattern_result=_FakePatternResult(pattern_name="single_agent"),
    )

    with patch("core.engine.orchestration.orchestrate", new_callable=AsyncMock) as mock_orch:
        mock_orch.return_value = mock_result
        result = await ace_task(
            description="Run the tests",
            product_id="product:default",
            workspace_id="workspace:default",
            user_id="user:default",
        )

    assert result is not None, "ace_task returned None — return statement is inside elif branch"
    assert result["output"] == "Pattern output."
    assert result["trace"]["pattern"] == "single_agent"


@pytest.mark.asyncio
async def test_ace_briefing_by_date():
    """ace_briefing() filters by date when provided."""
    from core.engine.mcp.tools import ace_briefing

    with patch("core.engine.mcp.tools.pool") as mock_pool:
        mock_conn = AsyncMock()
        mock_conn.query = AsyncMock(
            return_value=[
                [
                    {
                        "content": "Monday briefing",
                        "period": "daily",
                        "created_at": "2026-03-20T05:00:00Z",
                        "metrics": {},
                    }
                ]
            ]
        )
        mock_pool.connection.return_value.__aenter__ = AsyncMock(return_value=mock_conn)
        mock_pool.connection.return_value.__aexit__ = AsyncMock(return_value=False)

        result = await ace_briefing(product_id="product:default", date="2026-03-20")

    assert result["available"] is True
    # _build_pm_central makes subsequent queries; inspect the first call for the date filter
    first_call = mock_conn.query.call_args_list[0]
    params = first_call[0][1] if len(first_call[0]) > 1 else first_call[1]
    assert params["date"] == "2026-03-20"


@pytest.mark.asyncio
async def test_ace_capture_wires_db_pool_to_synthesizer():
    """ace_capture inline synthesis must set synth._db_pool — without it _write_insight silently no-ops."""
    from core.engine.mcp.tools import ace_capture

    mock_conn = AsyncMock()
    mock_conn.query = AsyncMock(return_value=[[{"id": "observation:reg001"}]])

    class FakeConn:
        async def __aenter__(self):
            return mock_conn

        async def __aexit__(self, *a):
            pass

    captured = {}

    with patch("core.engine.mcp.tools.pool") as mock_pool:
        mock_pool.connection.return_value = FakeConn()
        with patch("core.engine.capture.synthesizer.Synthesizer") as MockSynth:
            mock_synth = AsyncMock()
            mock_synth.add_observation = AsyncMock()
            mock_synth.flush = AsyncMock()
            MockSynth.return_value = mock_synth

            await ace_capture(
                observation_type="pattern",
                content="always use get_llm() not raw ClaudeProvider",
                domain_path="architecture",
                product_id="product:default",
            )
            captured["synth"] = mock_synth

    assert captured["synth"]._db_pool is mock_pool, (
        "ace_capture did not wire _db_pool to synthesizer — inline synthesis silently no-ops"
    )
