# tests/test_executor.py
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

_DEFAULT_CLASSIFICATION = {
    "discipline": "engineering",
    "archetype": "executor",
    "mode": "reactive",
    "complexity": "simple",
}
_DEFAULT_SNAPSHOT = {
    "discipline": "engineering",
    "insights": [],
    "total_count": 0,
    "recent_signals": [],
    "raw_context": [],
}


def _mock_pool(return_value):
    """Helper: create a mock pool with a single query return value."""
    mock_pool = MagicMock()
    mock_conn = AsyncMock()
    mock_conn.query = AsyncMock(return_value=return_value)
    mock_pool.connection.return_value.__aenter__ = AsyncMock(return_value=mock_conn)
    mock_pool.connection.return_value.__aexit__ = AsyncMock(return_value=False)
    return mock_pool


def _common_patches(classification=None, snapshot=None, pool_return=None):
    """Return a list of common patches for executor tests."""
    return [
        # Prevent real DB/LLM calls in the graph context and composition paths
        patch("core.engine.graph.context.load_graph_context", new_callable=AsyncMock, return_value={}),
        patch("core.engine.orchestration.composition_scorer.score_composition", side_effect=Exception("skip")),
        patch(
            "core.engine.orchestrator.executor.classify_task",
            new_callable=AsyncMock,
            return_value=classification or _DEFAULT_CLASSIFICATION,
        ),
        patch(
            "core.engine.orchestrator.executor.load_intelligence",
            new_callable=AsyncMock,
            return_value=snapshot or _DEFAULT_SNAPSHOT,
        ),
        patch("core.engine.orchestrator.executor.pool", _mock_pool(pool_return or [{"id": "task:abc"}])),
        patch("core.engine.skills.selector.pool", _mock_pool([[]])),  # No skills in DB
    ]


@pytest.mark.asyncio
async def test_executor_runs_task_end_to_end():
    """Executor classifies, loads intelligence, executes, returns result."""
    from core.engine.orchestrator.executor import execute_task

    snapshot = {
        **_DEFAULT_SNAPSHOT,
        "insights": [
            {
                "content": "Use pytest for testing",
                "confidence": 0.9,
                "tier": "subdomain",
                "insight_type": "fact",
                "id": "insight:1",
            }
        ],
        "total_count": 1,
    }

    with (
        patch("core.engine.graph.context.load_graph_context", new_callable=AsyncMock, return_value={}),
        patch("core.engine.orchestration.composition_scorer.score_composition", side_effect=Exception("skip")),
        patch(
            "core.engine.orchestrator.executor.classify_task",
            new_callable=AsyncMock,
            return_value=_DEFAULT_CLASSIFICATION,
        ),
        patch("core.engine.orchestrator.executor.load_intelligence", new_callable=AsyncMock, return_value=snapshot),
        patch("core.engine.orchestrator.executor.llm") as mock_llm,
        patch("core.engine.orchestrator.executor.pool", _mock_pool([{"id": "task:abc"}])),
        patch("core.engine.skills.selector.pool", _mock_pool([[]])),
        patch("core.engine.reasoning.selector.pool", _mock_pool([[]])),
    ):
        mock_llm.complete = AsyncMock(return_value="Here is the test file...")
        result = await execute_task("Write a test", "product:test", "workspace:test", "user:test")

    assert result["discipline"] == "engineering"
    assert result["domain_path"] == "engineering"
    assert result["output"] == "Here is the test file..."


@pytest.mark.asyncio
async def test_executor_handles_nested_list_result():
    """Executor handles SurrealDB result format: [[{"id": "task:xyz"}]]"""
    from core.engine.orchestrator.executor import execute_task

    with (
        patch("core.engine.graph.context.load_graph_context", new_callable=AsyncMock, return_value={}),
        patch("core.engine.orchestration.composition_scorer.score_composition", side_effect=Exception("skip")),
        patch(
            "core.engine.orchestrator.executor.classify_task",
            new_callable=AsyncMock,
            return_value=_DEFAULT_CLASSIFICATION,
        ),
        patch(
            "core.engine.orchestrator.executor.load_intelligence",
            new_callable=AsyncMock,
            return_value=_DEFAULT_SNAPSHOT,
        ),
        patch("core.engine.orchestrator.executor.llm") as mock_llm,
        patch("core.engine.orchestrator.executor.pool", _mock_pool([[{"id": "task:xyz"}]])),
        patch("core.engine.skills.selector.pool", _mock_pool([[]])),
        patch("core.engine.reasoning.selector.pool", _mock_pool([[]])),
    ):
        mock_llm.complete = AsyncMock(return_value="output")
        result = await execute_task("test", "product:test", "workspace:test", "user:test")

    assert result["id"] == "task:xyz"


@pytest.mark.asyncio
async def test_executor_handles_flat_result():
    """Executor handles SurrealDB v3 flat result format: [{"id": "task:env"}]"""
    from core.engine.orchestrator.executor import execute_task

    with (
        patch("core.engine.graph.context.load_graph_context", new_callable=AsyncMock, return_value={}),
        patch("core.engine.orchestration.composition_scorer.score_composition", side_effect=Exception("skip")),
        patch(
            "core.engine.orchestrator.executor.classify_task",
            new_callable=AsyncMock,
            return_value=_DEFAULT_CLASSIFICATION,
        ),
        patch(
            "core.engine.orchestrator.executor.load_intelligence",
            new_callable=AsyncMock,
            return_value=_DEFAULT_SNAPSHOT,
        ),
        patch("core.engine.orchestrator.executor.llm") as mock_llm,
        patch("core.engine.orchestrator.executor.pool", _mock_pool([{"id": "task:env"}])),
        patch("core.engine.skills.selector.pool", _mock_pool([[]])),
        patch("core.engine.reasoning.selector.pool", _mock_pool([[]])),
    ):
        mock_llm.complete = AsyncMock(return_value="output")
        result = await execute_task("test", "product:test", "workspace:test", "user:test")

    assert result["id"] == "task:env"


@pytest.mark.asyncio
async def test_executor_uses_classifier_archetype_and_mode():
    """Executor uses archetype/mode from classifier in prompt and task record."""
    from core.engine.orchestrator.executor import execute_task

    classification = {
        "discipline": "engineering",
        "archetype": "creator",
        "mode": "deliberative",
        "complexity": "moderate",
    }

    with (
        patch("core.engine.graph.context.load_graph_context", new_callable=AsyncMock, return_value={}),
        patch("core.engine.orchestration.composition_scorer.score_composition", side_effect=Exception("skip")),
        patch("core.engine.orchestrator.executor.classify_task", new_callable=AsyncMock, return_value=classification),
        patch(
            "core.engine.orchestrator.executor.load_intelligence",
            new_callable=AsyncMock,
            return_value=_DEFAULT_SNAPSHOT,
        ),
        patch("core.engine.orchestrator.executor.llm") as mock_llm,
        patch("core.engine.orchestrator.executor.pool", _mock_pool([{"id": "task:abc"}])),
        patch("core.engine.skills.selector.pool", _mock_pool([[]])),
        patch("core.engine.reasoning.selector.pool", _mock_pool([[]])),
    ):
        mock_llm.complete = AsyncMock(return_value="output")
        result = await execute_task("Design a new auth module", "product:test", "workspace:test", "user:test")

    assert result["archetype"] == "creator"
    assert result["mode"] == "deliberative"
    call_args = mock_llm.complete.call_args[0][0]
    assert "building something that doesn't exist" in call_args.lower()


@pytest.mark.asyncio
async def test_executor_passes_mode_to_loader():
    """Executor passes cognitive mode to load_intelligence."""
    from core.engine.orchestrator.executor import execute_task

    classification = {
        "discipline": "engineering",
        "archetype": "analyst",
        "mode": "exploratory",
        "complexity": "simple",
    }

    with (
        patch("core.engine.graph.context.load_graph_context", new_callable=AsyncMock, return_value={}),
        patch("core.engine.orchestration.composition_scorer.score_composition", side_effect=Exception("skip")),
        patch("core.engine.orchestrator.executor.classify_task", new_callable=AsyncMock, return_value=classification),
        patch(
            "core.engine.orchestrator.executor.load_intelligence",
            new_callable=AsyncMock,
            return_value=_DEFAULT_SNAPSHOT,
        ) as mock_loader,
        patch("core.engine.orchestrator.executor.llm") as mock_llm,
        patch("core.engine.orchestrator.executor.pool", _mock_pool([{"id": "task:abc"}])),
        patch("core.engine.skills.selector.pool", _mock_pool([[]])),
        patch("core.engine.reasoning.selector.pool", _mock_pool([[]])),
    ):
        mock_llm.complete = AsyncMock(return_value="output")
        await execute_task("Explore auth options", "product:test", "workspace:test", "user:test")

    call_kwargs = mock_loader.call_args
    assert call_kwargs.args == ("engineering", "product:test") or call_kwargs.kwargs.get("discipline") == "engineering"
    assert call_kwargs.kwargs.get("mode") == "exploratory"


@pytest.mark.asyncio
async def test_executor_includes_recent_signals_in_prompt():
    """Executor includes recent observations in the prompt when present."""
    from core.engine.orchestrator.executor import execute_task

    snapshot = {
        **_DEFAULT_SNAPSHOT,
        "recent_signals": [
            {"content": "APCA replacing WCAG contrast", "observation_type": "discovery", "confidence": 0.8}
        ],
    }

    with (
        patch("core.engine.graph.context.load_graph_context", new_callable=AsyncMock, return_value={}),
        patch("core.engine.orchestration.composition_scorer.score_composition", side_effect=Exception("skip")),
        patch(
            "core.engine.orchestrator.executor.classify_task",
            new_callable=AsyncMock,
            return_value=_DEFAULT_CLASSIFICATION,
        ),
        patch("core.engine.orchestrator.executor.load_intelligence", new_callable=AsyncMock, return_value=snapshot),
        patch("core.engine.orchestrator.executor.llm") as mock_llm,
        patch("core.engine.orchestrator.executor.pool", _mock_pool([{"id": "task:abc"}])),
        patch("core.engine.skills.selector.pool", _mock_pool([[]])),
        patch("core.engine.reasoning.selector.pool", _mock_pool([[]])),
    ):
        mock_llm.complete = AsyncMock(return_value="output")
        await execute_task("test", "product:test", "workspace:test", "user:test")

    prompt_used = mock_llm.complete.call_args[0][0]
    assert "Recent Observations" in prompt_used
    assert "APCA" in prompt_used


@pytest.mark.asyncio
async def test_load_code_context_returns_file_content(tmp_path):
    """_load_code_context reads matched files and returns their content."""
    from unittest.mock import patch

    from core.engine.orchestrator.executor import _load_code_context

    f = tmp_path / "my_module.py"
    f.write_text("class Foo:\n    pass\n")

    with patch("core.engine.orchestrator.executor._extract_matched_files") as mock_extract:
        mock_extract.return_value = [str(f)]
        result = await _load_code_context("tell me about Foo", root=str(tmp_path))

    assert "files" in result
    assert len(result["files"]) == 1
    assert "Foo" in result["files"][0]["content"]
    assert result["files"][0]["path"] == str(f)


@pytest.mark.asyncio
async def test_load_code_context_returns_empty_on_failure():
    """_load_code_context returns empty dict when TreeSitter fails."""
    from unittest.mock import patch

    from core.engine.orchestrator.executor import _load_code_context

    with patch("core.engine.orchestrator.executor._extract_matched_files", side_effect=Exception("boom")):
        result = await _load_code_context("any task")

    assert result == {"files": []}


def test_extract_matched_files_skips_installed_runtime(tmp_path):
    """A packaged runtime must not native-scan its install/work directory."""
    from unittest.mock import patch

    from core.engine.orchestrator.executor import _extract_matched_files

    (tmp_path / "pyproject.toml").write_text("[project]\nname = 'installed'\n")
    with patch("core.engine.orchestrator.executor._get_or_build_graph") as build:
        assert _extract_matched_files("release reliability", root=str(tmp_path)) == []
    build.assert_not_called()


def test_extract_matched_files_resolves_nested_checkout(tmp_path):
    from unittest.mock import MagicMock, patch

    from core.engine.orchestrator.executor import _extract_matched_files

    (tmp_path / ".git").mkdir()
    (tmp_path / "pyproject.toml").write_text("[project]\nname = 'checkout'\n")
    nested = tmp_path / "nested"
    nested.mkdir()
    builder = MagicMock()
    with (
        patch("core.engine.orchestrator.executor._get_or_build_graph", return_value=(builder, {})) as build,
        patch("core.engine.intelligence.queries.code_context", return_value={"matched_files": []}),
    ):
        assert _extract_matched_files("release reliability", root=str(nested)) == []
    build.assert_called_once_with(str(tmp_path))


@pytest.mark.asyncio
@pytest.mark.parametrize("bad_product", ["", "platform", None])
async def test_execute_task_rejects_invalid_product_id(bad_product):
    """execute_task fails closed on an empty/colon-less product_id BEFORE the CREATE — otherwise the
    `product = <record>$product` cast would write a product-orphan task (invisible to calibration/
    grading/briefing) or error opaquely. Guard mirrors orchestration.executor:75."""
    from core.engine.core.exceptions import ValidationError
    from core.engine.orchestrator.executor import execute_task

    with pytest.raises(ValidationError):
        await execute_task("do something", bad_product, "workspace:test", "user:test")
