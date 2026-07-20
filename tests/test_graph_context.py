# tests/test_graph_context.py
"""Tests for engine.graph.context and engine.graph.classifier — graph-aware orchestration."""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_pool(query_return=None):
    """Create a mock pool whose query() always returns the given value."""
    mock_pool = MagicMock()
    mock_conn = AsyncMock()
    mock_conn.query = AsyncMock(return_value=query_return or [])
    mock_pool.connection.return_value.__aenter__ = AsyncMock(return_value=mock_conn)
    mock_pool.connection.return_value.__aexit__ = AsyncMock(return_value=False)
    return mock_pool, mock_conn


def _make_pool_sequence(side_effects):
    """Create a mock pool whose query() returns values from side_effects in order."""
    mock_pool = MagicMock()
    mock_conn = AsyncMock()
    mock_conn.query = AsyncMock(side_effect=side_effects)
    mock_pool.connection.return_value.__aenter__ = AsyncMock(return_value=mock_conn)
    mock_pool.connection.return_value.__aexit__ = AsyncMock(return_value=False)
    return mock_pool, mock_conn


# ---------------------------------------------------------------------------
# Tests: extract_references
# ---------------------------------------------------------------------------


def test_extract_file_references_py():
    from core.engine.graph.context import extract_references

    refs = extract_references("Fix the bug in engine/core/db.py and update auth.py")
    assert "engine/core/db.py" in refs["files"]
    assert "auth.py" in refs["files"]


def test_extract_file_references_multiple_extensions():
    from core.engine.graph.context import extract_references

    refs = extract_references("Update portal/src/App.tsx and config.json")
    assert "portal/src/App.tsx" in refs["files"]
    assert "config.json" in refs["files"]


def test_extract_function_references():
    from core.engine.graph.context import extract_references

    refs = extract_references("The `parse_rows` function in `engine.core.db` is broken")
    assert "parse_rows" in refs["functions"]
    assert "engine.core.db" in refs["functions"]


def test_extract_keywords():
    from core.engine.graph.context import extract_references

    refs = extract_references("Fix the auth database migration")
    assert "auth" in refs["keywords"]
    assert "database" in refs["keywords"]
    assert "migration" in refs["keywords"]


def test_extract_references_empty():
    from core.engine.graph.context import extract_references

    refs = extract_references("Make the app faster")
    assert refs["files"] == []
    # May or may not have keywords, but should not crash


def test_extract_references_deduplicates():
    from core.engine.graph.context import extract_references

    refs = extract_references("Fix db.py and also db.py again")
    assert refs["files"].count("db.py") == 1


# ---------------------------------------------------------------------------
# Tests: load_graph_context — file lookup
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_load_graph_context_finds_files():
    """When graph has matching files, they appear in relevant_files."""
    mock_files = [
        {
            "id": "graph_file:engine_core_db_py",
            "path": "core/engine/core/db.py",
            "name": "db.py",
            "language": "python",
            "function_count": 5,
            "change_frequency": 3,
            "fragility_score": 0.2,
            "line_count": 200,
        }
    ]

    mock_pool, mock_conn = _make_pool()

    # Sequence: _find_files, _get_dependents_count, _get_decisions,
    # _get_dependencies(out), _get_dependencies(in), _get_agent_history,
    # _get_graph_stats (x4)
    call_count = {"n": 0}
    original_query = mock_conn.query

    async def _side_effect(*args, **kwargs):
        call_count["n"] += 1
        if call_count["n"] == 1:
            return mock_files  # _find_files
        if call_count["n"] == 2:
            return [{"cnt": 3}]  # _get_dependents_count
        return []  # everything else

    mock_conn.query = AsyncMock(side_effect=_side_effect)

    with patch("core.engine.graph.context.pool", mock_pool):
        from core.engine.graph.context import load_graph_context

        ctx = await load_graph_context("Fix the bug in engine/core/db.py")

    assert len(ctx["relevant_files"]) == 1
    assert ctx["relevant_files"][0]["path"] == "core/engine/core/db.py"
    assert ctx["relevant_files"][0]["dependent_count"] == 3


@pytest.mark.asyncio
async def test_load_graph_context_empty_when_no_references():
    """When description has no code references, relevant_files is empty."""
    mock_pool, _ = _make_pool()

    with patch("core.engine.graph.context.pool", mock_pool):
        from core.engine.graph.context import load_graph_context

        ctx = await load_graph_context("Improve team morale")

    assert ctx["relevant_files"] == []
    assert ctx["decisions"] == []


@pytest.mark.asyncio
async def test_load_graph_context_empty_when_no_graph_data():
    """When graph has no matching files, relevant_files is empty."""
    mock_pool, _ = _make_pool(query_return=[])

    with patch("core.engine.graph.context.pool", mock_pool):
        from core.engine.graph.context import load_graph_context

        ctx = await load_graph_context("Fix engine/core/db.py")

    assert ctx["relevant_files"] == []


# ---------------------------------------------------------------------------
# Tests: load_graph_context — decisions
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_load_graph_context_gets_decisions():
    """Decisions from the graph appear in the context."""
    mock_file = {
        "id": "graph_file:x",
        "path": "x.py",
        "name": "x.py",
        "language": "python",
        "function_count": 0,
        "change_frequency": 0,
        "fragility_score": 0.0,
        "line_count": 10,
    }
    mock_decision = {
        "title": "Use SurrealDB v3",
        "description": "Migrated to v3 for better performance",
        "outcome": "worked",
        "timestamp": "2025-01-01T00:00:00Z",
    }

    call_count = {"n": 0}

    async def _side_effect(*args, **kwargs):
        call_count["n"] += 1
        if call_count["n"] == 1:
            return [mock_file]  # _find_files
        if call_count["n"] == 2:
            return [{"cnt": 0}]  # _get_dependents_count
        if call_count["n"] == 3:
            return [mock_decision]  # _get_decisions
        return []

    mock_pool, mock_conn = _make_pool()
    mock_conn.query = AsyncMock(side_effect=_side_effect)

    with patch("core.engine.graph.context.pool", mock_pool):
        from core.engine.graph.context import load_graph_context

        ctx = await load_graph_context("Update x.py")

    assert len(ctx["decisions"]) == 1
    assert ctx["decisions"][0]["title"] == "Use SurrealDB v3"


# ---------------------------------------------------------------------------
# Tests: load_graph_context — risk flags
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_load_graph_context_computes_risk_high_change_freq():
    """Files with change_frequency > 5 get a risk flag."""
    mock_file = {
        "id": "graph_file:hot",
        "path": "engine/hot.py",
        "name": "hot.py",
        "language": "python",
        "function_count": 10,
        "change_frequency": 12,
        "fragility_score": 0.3,
        "line_count": 500,
    }

    call_count = {"n": 0}

    async def _side_effect(*args, **kwargs):
        call_count["n"] += 1
        if call_count["n"] == 1:
            return [mock_file]
        if call_count["n"] == 2:
            return [{"cnt": 2}]
        return []

    mock_pool, mock_conn = _make_pool()
    mock_conn.query = AsyncMock(side_effect=_side_effect)

    with patch("core.engine.graph.context.pool", mock_pool):
        from core.engine.graph.context import load_graph_context

        ctx = await load_graph_context("Fix engine/hot.py")

    assert len(ctx["risk_flags"]) >= 1
    assert "fragile" in ctx["risk_flags"][0].lower() or "changed" in ctx["risk_flags"][0].lower()


@pytest.mark.asyncio
async def test_load_graph_context_computes_risk_many_dependents():
    """Files with > 20 dependents get a risk flag."""
    mock_file = {
        "id": "graph_file:core",
        "path": "engine/core.py",
        "name": "core.py",
        "language": "python",
        "function_count": 20,
        "change_frequency": 2,
        "fragility_score": 0.1,
        "line_count": 1000,
    }

    call_count = {"n": 0}

    async def _side_effect(*args, **kwargs):
        call_count["n"] += 1
        if call_count["n"] == 1:
            return [mock_file]
        if call_count["n"] == 2:
            return [{"cnt": 25}]  # 25 dependents
        return []

    mock_pool, mock_conn = _make_pool()
    mock_conn.query = AsyncMock(side_effect=_side_effect)

    with patch("core.engine.graph.context.pool", mock_pool):
        from core.engine.graph.context import load_graph_context

        ctx = await load_graph_context("Refactor engine/core.py")

    assert len(ctx["risk_flags"]) >= 1
    assert "dependents" in ctx["risk_flags"][0].lower() or "impact" in ctx["risk_flags"][0].lower()


@pytest.mark.asyncio
async def test_load_graph_context_computes_risk_high_fragility():
    """Files with fragility_score > 0.7 get a risk flag."""
    mock_file = {
        "id": "graph_file:brittle",
        "path": "engine/brittle.py",
        "name": "brittle.py",
        "language": "python",
        "function_count": 3,
        "change_frequency": 1,
        "fragility_score": 0.85,
        "line_count": 100,
    }

    call_count = {"n": 0}

    async def _side_effect(*args, **kwargs):
        call_count["n"] += 1
        if call_count["n"] == 1:
            return [mock_file]
        if call_count["n"] == 2:
            return [{"cnt": 1}]
        return []

    mock_pool, mock_conn = _make_pool()
    mock_conn.query = AsyncMock(side_effect=_side_effect)

    with patch("core.engine.graph.context.pool", mock_pool):
        from core.engine.graph.context import load_graph_context

        ctx = await load_graph_context("Update engine/brittle.py")

    assert len(ctx["risk_flags"]) >= 1
    assert "fragility" in ctx["risk_flags"][0].lower()


# ---------------------------------------------------------------------------
# Tests: load_graph_context — best-effort on DB errors
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_load_graph_context_survives_db_error():
    """DB errors don't crash the loader — returns empty context."""
    mock_pool = MagicMock()
    mock_conn = AsyncMock()
    mock_conn.query = AsyncMock(side_effect=RuntimeError("DB down"))
    mock_pool.connection.return_value.__aenter__ = AsyncMock(return_value=mock_conn)
    mock_pool.connection.return_value.__aexit__ = AsyncMock(return_value=False)

    with patch("core.engine.graph.context.pool", mock_pool):
        from core.engine.graph.context import load_graph_context

        ctx = await load_graph_context("Fix engine/core/db.py")

    # Should not raise, returns empty
    assert ctx["relevant_files"] == []


# ---------------------------------------------------------------------------
# Tests: classify_with_graph
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_classify_with_graph_uses_context():
    """classify_with_graph sends graph context to the LLM prompt."""
    graph_context = {
        "relevant_files": [
            {"path": "core/engine/core/db.py", "function_count": 5, "dependent_count": 10, "change_frequency": 8},
        ],
        "decisions": [{"title": "Use SurrealDB v3", "outcome": "worked"}],
        "risk_flags": ["engine/core/db.py is fragile (changed 8 times)"],
        "agent_history": [
            {"archetype": "executor", "mode": "deliberative", "perspective": "practitioner"},
        ],
    }

    mock_llm_result = {
        "domain_path": "architecture",
        "archetype": "executor",
        "mode": "deliberative",
        "complexity": "moderate",
        "perspective": "practitioner",
        "specialties": [],
        "org_context": [],
        "engagement": {"perspectives": ["practitioner"], "adversarial_pair": None, "rationale": ""},
    }

    with patch("core.engine.graph.classifier.llm") as mock_llm:
        mock_llm.complete_json = AsyncMock(return_value=mock_llm_result)

        from core.engine.graph.classifier import classify_with_graph

        result = await classify_with_graph("Fix engine/core/db.py", graph_context)

    # Verify the LLM was called with a prompt containing graph context
    call_args = mock_llm.complete_json.call_args
    prompt = call_args.args[0]
    assert "core/engine/core/db.py" in prompt
    assert "fragile" in prompt.lower()
    assert "SurrealDB v3" in prompt

    # Verify the classification result
    assert result["mode"] == "deliberative"
    assert result["archetype"] == "executor"


@pytest.mark.asyncio
async def test_classify_with_graph_fallback_on_error():
    """When LLM fails, classify_with_graph returns sensible defaults."""
    graph_context = {
        "relevant_files": [{"path": "x.py", "function_count": 1, "dependent_count": 0, "change_frequency": 0}],
        "risk_flags": ["something risky"],
    }

    with patch("core.engine.graph.classifier.llm") as mock_llm:
        mock_llm.complete_json = AsyncMock(side_effect=RuntimeError("LLM down"))

        from core.engine.graph.classifier import classify_with_graph

        result = await classify_with_graph("Fix x.py", graph_context)

    # Should return defaults, biased by risk flags
    assert result["mode"] == "deliberative"  # risk flags present
    assert result["archetype"] == "executor"


@pytest.mark.asyncio
async def test_classify_with_graph_no_risk_default_reactive():
    """When LLM fails and no risk flags, default mode is reactive."""
    graph_context = {
        "relevant_files": [{"path": "x.py", "function_count": 1, "dependent_count": 0, "change_frequency": 0}],
        "risk_flags": [],
    }

    with patch("core.engine.graph.classifier.llm") as mock_llm:
        mock_llm.complete_json = AsyncMock(side_effect=RuntimeError("LLM down"))

        from core.engine.graph.classifier import classify_with_graph

        result = await classify_with_graph("Fix x.py", graph_context)

    assert result["mode"] == "reactive"


# ---------------------------------------------------------------------------
# Tests: _build_graph_intel_context
# ---------------------------------------------------------------------------


def test_build_graph_intel_context_with_files():
    """Graph intel context includes file info."""
    from core.engine.orchestrator.context_assembler import _build_graph_section as _build_graph_intel_context

    graph_context = {
        "relevant_files": [
            {"path": "core/engine/core/db.py", "function_count": 5, "dependent_count": 10},
        ],
        "decisions": [],
        "risk_flags": [],
        "dependencies": [],
    }
    result = _build_graph_intel_context(graph_context)
    assert "core/engine/core/db.py" in result
    assert "5 functions" in result
    assert "10 dependents" in result


def test_build_graph_intel_context_with_decisions():
    """Graph intel context includes decision history."""
    from core.engine.orchestrator.context_assembler import _build_graph_section as _build_graph_intel_context

    graph_context = {
        "relevant_files": [],
        "decisions": [
            {"title": "Use async DB pool", "description": "Better throughput"},
        ],
        "risk_flags": [],
        "dependencies": [],
    }
    result = _build_graph_intel_context(graph_context)
    assert "Use async DB pool" in result
    assert "Decision History" in result


def test_build_graph_intel_context_with_risk_flags():
    """Graph intel context includes risk flags."""
    from core.engine.orchestrator.context_assembler import _build_graph_section as _build_graph_intel_context

    graph_context = {
        "relevant_files": [],
        "decisions": [],
        "risk_flags": ["db.py has 25 dependents -- changes have wide impact"],
        "dependencies": [],
    }
    result = _build_graph_intel_context(graph_context)
    assert "Risk Flags" in result
    assert "25 dependents" in result


def test_build_graph_intel_context_empty():
    """Empty graph context returns empty string."""
    from core.engine.orchestrator.context_assembler import _build_graph_section as _build_graph_intel_context

    result = _build_graph_intel_context(
        {
            "relevant_files": [],
            "decisions": [],
            "risk_flags": [],
            "dependencies": [],
        }
    )
    assert result == ""


def test_build_intel_context_includes_graph():
    """_build_intel_context renders graph_context when present in snapshot."""
    from core.engine.orchestrator.executor import _build_intel_context

    snapshot = {
        "insights": [],
        "graph_context": {
            "relevant_files": [
                {"path": "core/engine/core/db.py", "function_count": 5, "dependent_count": 10},
            ],
            "decisions": [],
            "risk_flags": ["engine/core/db.py is fragile"],
            "dependencies": [],
        },
    }
    result = _build_intel_context(snapshot)
    assert "core/engine/core/db.py" in result
    assert "fragile" in result


# ---------------------------------------------------------------------------
# Tests: fallback behavior in executor
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_fallback_to_old_classifier_when_graph_empty():
    """When graph context has no relevant_files, old classify_task is used."""
    empty_graph = {
        "relevant_files": [],
        "decisions": [],
        "dependencies": [],
        "agent_history": [],
        "risk_flags": [],
        "graph_stats": {"files": 0, "functions": 0, "decisions": 0, "imports": 0},
        "references_extracted": {"files": [], "functions": [], "keywords": []},
    }

    old_classification = {
        "domain_path": "architecture",
        "archetype": "executor",
        "mode": "reactive",
        "complexity": "simple",
        "perspective": "practitioner",
        "specialties": [],
        "org_context": [],
        "engagement": {"perspectives": ["practitioner"], "adversarial_pair": None, "rationale": ""},
    }

    with (
        patch(
            "core.engine.graph.context.load_graph_context", new_callable=AsyncMock, return_value=empty_graph
        ) as mock_graph,
        patch("core.engine.graph.classifier.classify_with_graph", new_callable=AsyncMock) as mock_graph_classify,
        patch(
            "core.engine.orchestrator.classifier.classify_task", new_callable=AsyncMock, return_value=old_classification
        ) as mock_old_classify,
    ):
        # Import here to pick up the patched modules
        # We test the logic directly rather than calling execute_task (which has many deps)
        from core.engine.graph.context import load_graph_context

        graph_context = await load_graph_context("Do something generic")

        # The decision logic: if no relevant_files, use old classifier
        if graph_context and graph_context.get("relevant_files"):
            from core.engine.graph.classifier import classify_with_graph

            classification = await classify_with_graph("Do something", graph_context)
        else:
            from core.engine.orchestrator.classifier import classify_task

            classification = await classify_task("Do something", "product:default")

    # Old classifier was used (graph was empty)
    mock_old_classify.assert_called_once()
    mock_graph_classify.assert_not_called()
    assert classification["mode"] == "reactive"


@pytest.mark.asyncio
async def test_graph_classifier_used_when_files_found():
    """When graph context has relevant_files, classify_with_graph is used."""
    graph_with_files = {
        "relevant_files": [
            {"path": "core/engine/core/db.py", "function_count": 5, "dependent_count": 10, "change_frequency": 3},
        ],
        "decisions": [],
        "risk_flags": [],
        "graph_stats": {"files": 100, "functions": 300, "decisions": 50, "imports": 200},
        "references_extracted": {"files": ["core/engine/core/db.py"], "functions": [], "keywords": ["db"]},
    }

    graph_classification = {
        "domain_path": "data_modeling",
        "archetype": "executor",
        "mode": "deliberative",
        "complexity": "moderate",
        "perspective": "practitioner",
        "specialties": [],
        "org_context": [],
        "engagement": {"perspectives": ["practitioner"], "adversarial_pair": None, "rationale": ""},
    }

    with (
        patch("core.engine.graph.context.load_graph_context", new_callable=AsyncMock, return_value=graph_with_files),
        patch(
            "core.engine.graph.classifier.classify_with_graph",
            new_callable=AsyncMock,
            return_value=graph_classification,
        ) as mock_graph_classify,
        patch("core.engine.orchestrator.classifier.classify_task", new_callable=AsyncMock) as mock_old_classify,
    ):
        from core.engine.graph.context import load_graph_context

        graph_context = await load_graph_context("Fix engine/core/db.py")

        if graph_context and graph_context.get("relevant_files"):
            from core.engine.graph.classifier import classify_with_graph

            classification = await classify_with_graph("Fix engine/core/db.py", graph_context, "product:default")
        else:
            from core.engine.orchestrator.classifier import classify_task

            classification = await classify_task("Fix engine/core/db.py", "product:default")

    mock_graph_classify.assert_called_once()
    mock_old_classify.assert_not_called()
    assert classification["mode"] == "deliberative"


# ---------------------------------------------------------------------------
# Tests: _build_graph_context_section (classifier prompt builder)
# ---------------------------------------------------------------------------


def test_build_graph_context_section_full():
    """_build_graph_context_section renders all sections."""
    from core.engine.graph.classifier import _build_graph_context_section

    ctx = {
        "relevant_files": [
            {"path": "a.py", "function_count": 3, "dependent_count": 5, "change_frequency": 10},
        ],
        "decisions": [{"title": "Use pools", "outcome": "worked"}],
        "risk_flags": ["a.py is fragile"],
        "agent_history": [
            {"perspective": "practitioner", "mode": "deliberative", "archetype": "executor"},
        ],
    }
    result = _build_graph_context_section(ctx)
    assert "a.py" in result
    assert "Use pools" in result
    assert "fragile" in result
    assert "practitioner/deliberative/executor" in result


def test_build_graph_context_section_empty():
    """Empty graph context returns empty string."""
    from core.engine.graph.classifier import _build_graph_context_section

    result = _build_graph_context_section(
        {
            "relevant_files": [],
            "decisions": [],
            "risk_flags": [],
            "agent_history": [],
        }
    )
    assert result == ""
