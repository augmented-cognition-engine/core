# tests/test_perspective_gaps.py
"""Tests for the perspective gap detector sentinel engine."""

from unittest.mock import AsyncMock, patch

import pytest


def test_engine_registered():
    """Importing the module registers 'perspective_gap_detector' in the engine registry."""
    from core.engine.sentinel.registry import engine_registry

    # Clear any stale entry so we can assert a clean registration
    engine_registry.pop("perspective_gap_detector", None)

    import core.engine.sentinel.engines.perspective_gaps  # noqa: F401

    assert "perspective_gap_detector" in engine_registry
    entry = engine_registry["perspective_gap_detector"]
    assert entry["cron"] == "0 5 * * *"
    assert callable(entry["fn"])


@pytest.mark.asyncio
async def test_no_gaps_when_all_perspectives_used():
    """When all available perspectives appear in recent tasks, gaps_found == 0."""
    import importlib

    from core.engine.sentinel.registry import engine_registry

    engine_registry.pop("perspective_gap_detector", None)

    import core.engine.sentinel.engines.perspective_gaps as mod

    importlib.reload(mod)

    used_rows = [
        {"perspective": "practitioner", "count": 10},
        {"perspective": "theorist", "count": 5},
        {"perspective": "critic", "count": 3},
        {"perspective": "advocate", "count": 7},
    ]
    available_rows = [
        {"perspective": "practitioner"},
        {"perspective": "theorist"},
        {"perspective": "critic"},
        {"perspective": "advocate"},
    ]

    with patch("core.engine.sentinel.engines.perspective_gaps.pool") as mock_pool:
        mock_db = AsyncMock()
        mock_db.query = AsyncMock(
            side_effect=[
                [used_rows],  # task perspective usage query
                [available_rows],  # specialty available perspectives query
            ]
        )
        mock_pool.connection.return_value.__aenter__ = AsyncMock(return_value=mock_db)
        mock_pool.connection.return_value.__aexit__ = AsyncMock(return_value=False)

        result = await mod.run_perspective_gap_detector("product:default")

    assert result["gaps_found"] == 0
    assert result["gap_details"] == []
    assert result["perspectives_used"] == {"practitioner", "theorist", "critic", "advocate"}
    assert result["perspectives_available"] == {"practitioner", "theorist", "critic", "advocate"}


@pytest.mark.asyncio
async def test_detects_unused_perspective():
    """When only practitioner is used but theorist is available, theorist is detected as a gap."""
    import importlib

    import core.engine.sentinel.engines.perspective_gaps as mod
    from core.engine.sentinel.registry import engine_registry

    engine_registry.pop("perspective_gap_detector", None)
    importlib.reload(mod)

    used_rows = [
        {"perspective": "practitioner", "count": 8},
    ]
    available_rows = [
        {"perspective": "practitioner"},
        {"perspective": "theorist"},
    ]
    recent_tasks = [
        {"description": "Build a REST API endpoint for user authentication"},
        {"description": "Optimize database query performance"},
    ]
    llm_response = {
        "questions": [
            "What theoretical frameworks underpin the authentication design?",
            "How does the CAP theorem apply to this system's consistency guarantees?",
            "What formal models describe the query optimization choices made?",
        ]
    }

    with (
        patch("core.engine.sentinel.engines.perspective_gaps.pool") as mock_pool,
        patch("core.engine.sentinel.engines.perspective_gaps.llm") as mock_llm,
    ):
        mock_db = AsyncMock()
        mock_db.query = AsyncMock(
            side_effect=[
                [used_rows],  # task perspective usage
                [available_rows],  # available perspectives
                [recent_tasks],  # recent task descriptions for context
                # CREATE insight for the gap prompt
                [[{"id": "insight:gap1"}]],
            ]
        )
        mock_pool.connection.return_value.__aenter__ = AsyncMock(return_value=mock_db)
        mock_pool.connection.return_value.__aexit__ = AsyncMock(return_value=False)

        mock_llm.complete_json = AsyncMock(return_value=llm_response)

        result = await mod.run_perspective_gap_detector("product:default", budget=5)

    assert result["gaps_found"] == 1
    assert len(result["gap_details"]) == 1

    gap = result["gap_details"][0]
    assert gap["perspective"] == "theorist"
    assert "prompt" in gap
    assert isinstance(gap["prompt"], str)
    assert len(gap["prompt"]) > 0

    assert "practitioner" in result["perspectives_used"]
    assert "theorist" in result["perspectives_available"]

    mock_llm.complete_json.assert_called_once()


@pytest.mark.asyncio
async def test_handles_none_perspective_in_tasks():
    """Tasks with perspective=None are excluded gracefully — None is not counted as a used perspective."""
    import importlib

    import core.engine.sentinel.engines.perspective_gaps as mod
    from core.engine.sentinel.registry import engine_registry

    engine_registry.pop("perspective_gap_detector", None)
    importlib.reload(mod)

    # SurrealDB GROUP BY with NONE filter should already exclude them,
    # but test defensive handling if a None slips through
    used_rows = [
        {"perspective": None, "count": 3},  # should be ignored
        {"perspective": "practitioner", "count": 6},
    ]
    available_rows = [
        {"perspective": "practitioner"},
        {"perspective": "critic"},
    ]
    recent_tasks = [{"description": "Review a system architecture proposal"}]
    llm_response = {"questions": ["From a critic lens, what risks exist here?"]}

    with (
        patch("core.engine.sentinel.engines.perspective_gaps.pool") as mock_pool,
        patch("core.engine.sentinel.engines.perspective_gaps.llm") as mock_llm,
    ):
        mock_db = AsyncMock()
        mock_db.query = AsyncMock(
            side_effect=[
                [used_rows],
                [available_rows],
                [recent_tasks],
                [[{"id": "insight:gap2"}]],
            ]
        )
        mock_pool.connection.return_value.__aenter__ = AsyncMock(return_value=mock_db)
        mock_pool.connection.return_value.__aexit__ = AsyncMock(return_value=False)

        mock_llm.complete_json = AsyncMock(return_value=llm_response)

        result = await mod.run_perspective_gap_detector("product:default", budget=5)

    # None should NOT appear in perspectives_used
    assert None not in result["perspectives_used"]
    assert "practitioner" in result["perspectives_used"]
    # critic is available but not used → gap detected
    assert result["gaps_found"] == 1
    assert result["gap_details"][0]["perspective"] == "critic"


@pytest.mark.asyncio
async def test_respects_budget():
    """Only `budget` LLM calls are made even when more gaps exist."""
    import importlib

    import core.engine.sentinel.engines.perspective_gaps as mod
    from core.engine.sentinel.registry import engine_registry

    engine_registry.pop("perspective_gap_detector", None)
    importlib.reload(mod)

    used_rows: list = []  # nothing used
    available_rows = [
        {"perspective": "practitioner"},
        {"perspective": "theorist"},
        {"perspective": "critic"},
        {"perspective": "advocate"},
        {"perspective": "skeptic"},
    ]
    recent_tasks = [{"description": "A sample task"}]
    llm_response = {"questions": ["Question A?", "Question B?"]}

    budget = 2

    # Build side_effects: usage + available, then for each gap up to budget:
    # recent_tasks query + (no CREATE insight here since we don't write insights in this engine)
    side_effects = [
        [used_rows],  # usage
        [available_rows],  # available
    ]
    for _ in range(budget):
        side_effects.append([recent_tasks])
        side_effects.append([[{"id": "insight:gapX"}]])

    with (
        patch("core.engine.sentinel.engines.perspective_gaps.pool") as mock_pool,
        patch("core.engine.sentinel.engines.perspective_gaps.llm") as mock_llm,
    ):
        mock_db = AsyncMock()
        mock_db.query = AsyncMock(side_effect=side_effects)
        mock_pool.connection.return_value.__aenter__ = AsyncMock(return_value=mock_db)
        mock_pool.connection.return_value.__aexit__ = AsyncMock(return_value=False)

        mock_llm.complete_json = AsyncMock(return_value=llm_response)

        result = await mod.run_perspective_gap_detector("product:default", budget=budget)

    assert mock_llm.complete_json.call_count == budget
    assert result["gaps_found"] == 5  # total gaps found
    assert len(result["gap_details"]) == budget  # only `budget` processed


@pytest.mark.asyncio
async def test_db_error_returns_safe_result():
    """If the DB query fails, the engine returns zeros rather than crashing."""
    import importlib

    import core.engine.sentinel.engines.perspective_gaps as mod
    from core.engine.sentinel.registry import engine_registry

    engine_registry.pop("perspective_gap_detector", None)
    importlib.reload(mod)

    with patch("core.engine.sentinel.engines.perspective_gaps.pool") as mock_pool:
        mock_db = AsyncMock()
        mock_db.query = AsyncMock(side_effect=Exception("DB connection refused"))
        mock_pool.connection.return_value.__aenter__ = AsyncMock(return_value=mock_db)
        mock_pool.connection.return_value.__aexit__ = AsyncMock(return_value=False)

        result = await mod.run_perspective_gap_detector("product:default")

    assert result["gaps_found"] == 0
    assert result["gap_details"] == []
