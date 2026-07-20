# tests/test_specialty_deepener.py
from unittest.mock import AsyncMock, patch

import pytest


def test_specialty_deepener_module_imports():
    from core.engine.sentinel.engines.specialty_deepener import run_specialty_deepener

    assert callable(run_specialty_deepener)


def test_is_thin_specialty():
    from core.engine.sentinel.engines.specialty_deepener import is_thin_specialty

    assert is_thin_specialty(task_count=10, insight_count=3) is True
    assert is_thin_specialty(task_count=10, insight_count=5) is False
    assert is_thin_specialty(task_count=6, insight_count=2) is True
    assert is_thin_specialty(task_count=3, insight_count=1) is False
    assert is_thin_specialty(task_count=0, insight_count=0) is False


@pytest.mark.asyncio
async def test_no_thin_specialties_returns_zero():
    from core.engine.sentinel.engines.specialty_deepener import run_specialty_deepener

    with (
        patch("core.engine.sentinel.engines.specialty_deepener.pool") as mock_pool,
        patch("core.engine.sentinel.engines.specialty_deepener.llm") as mock_llm,
    ):
        mock_db = AsyncMock()
        mock_db.query = AsyncMock(return_value=[[]])
        mock_pool.connection.return_value.__aenter__ = AsyncMock(return_value=mock_db)
        mock_pool.connection.return_value.__aexit__ = AsyncMock(return_value=False)

        result = await run_specialty_deepener("product:default")

    assert result["thin_specialties_found"] == 0
    assert result["research_queued"] == 0
    mock_llm.complete_json.assert_not_called()


@pytest.mark.asyncio
async def test_finds_thin_specialty_and_queues_research():
    from core.engine.sentinel.engines.specialty_deepener import run_specialty_deepener

    specialty = {
        "id": "specialty:react",
        "slug": "react",
        "name": "React",
        "task_count": 15,
        "insight_count": 3,
    }

    existing_insights = [
        {"content": "React uses a virtual DOM for efficient updates"},
        {"content": "React hooks replace lifecycle methods"},
        {"content": "React 19 includes a compiler"},
    ]

    llm_response = {
        "topics": [
            {"query": "React Server Components architecture", "context": "No RSC insights"},
            {"query": "React 19 compiler strategies", "context": "Only one compiler insight"},
            {"query": "React Suspense patterns", "context": "No Suspense insights"},
            {"query": "State management with Zustand", "context": "No state management insights"},
            {"query": "React testing patterns", "context": "No testing insights"},
        ],
    }

    with (
        patch("core.engine.sentinel.engines.specialty_deepener.pool") as mock_pool,
        patch("core.engine.sentinel.engines.specialty_deepener.llm") as mock_llm,
    ):
        mock_db = AsyncMock()
        mock_db.query = AsyncMock(
            side_effect=[
                [[]],  # bootstrap: scaffolded specialties
                [[specialty]],
                [existing_insights],
                [[{"id": "research_queue:d1"}]],
                [[{"id": "research_queue:d2"}]],
                [[{"id": "research_queue:d3"}]],
            ]
        )
        mock_pool.connection.return_value.__aenter__ = AsyncMock(return_value=mock_db)
        mock_pool.connection.return_value.__aexit__ = AsyncMock(return_value=False)

        mock_llm.complete_json = AsyncMock(return_value=llm_response)

        result = await run_specialty_deepener("product:default")

    assert result["thin_specialties_found"] == 1
    assert result["research_queued"] == 3
    mock_llm.complete_json.assert_called_once()


@pytest.mark.asyncio
async def test_respects_budget():
    from core.engine.sentinel.engines.specialty_deepener import run_specialty_deepener

    specialties = [
        {
            "id": f"specialty:s{i}",
            "slug": f"spec{i}",
            "name": f"Specialty {i}",
            "task_count": 20,
            "insight_count": 2,
        }
        for i in range(10)
    ]

    llm_response = {
        "topics": [
            {"query": "Topic 1", "context": "Context 1"},
            {"query": "Topic 2", "context": "Context 2"},
            {"query": "Topic 3", "context": "Context 3"},
        ],
    }

    with (
        patch("core.engine.sentinel.engines.specialty_deepener.pool") as mock_pool,
        patch("core.engine.sentinel.engines.specialty_deepener.llm") as mock_llm,
    ):
        mock_db = AsyncMock()
        side_effects = [
            [[]],  # bootstrap: scaffolded specialties
            [specialties],
        ]
        for i in range(3):
            side_effects.append([[]])  # existing insights
            side_effects.append([[{"id": f"research_queue:b{i}a"}]])  # queue 1
            side_effects.append([[{"id": f"research_queue:b{i}b"}]])  # queue 2
            side_effects.append([[{"id": f"research_queue:b{i}c"}]])  # queue 3

        mock_db.query = AsyncMock(side_effect=side_effects)
        mock_pool.connection.return_value.__aenter__ = AsyncMock(return_value=mock_db)
        mock_pool.connection.return_value.__aexit__ = AsyncMock(return_value=False)

        mock_llm.complete_json = AsyncMock(return_value=llm_response)

        result = await run_specialty_deepener("product:default", budget=3)

    assert result["thin_specialties_found"] >= 3
    assert mock_llm.complete_json.call_count == 3
