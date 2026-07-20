# tests/test_gap_researcher.py
from unittest.mock import AsyncMock, patch

import pytest


def test_gap_researcher_module_imports():
    from core.engine.sentinel.engines.gap_researcher import run_gap_researcher

    assert callable(run_gap_researcher)


@pytest.mark.asyncio
async def test_no_research_items_returns_zero():
    from core.engine.sentinel.engines.gap_researcher import run_gap_researcher

    with (
        patch("core.engine.sentinel.engines.gap_researcher.pool") as mock_pool,
        patch("core.engine.sentinel.engines.gap_researcher.llm"),
    ):
        mock_db = AsyncMock()
        mock_db.query = AsyncMock(
            side_effect=[
                [[]],  # bootstrap: scaffolded specialties
                [[]],  # research_queue
                [[]],  # low-confidence tasks
                [[]],  # thin specialties
            ]
        )
        mock_pool.connection.return_value.__aenter__ = AsyncMock(return_value=mock_db)
        mock_pool.connection.return_value.__aexit__ = AsyncMock(return_value=False)

        result = await run_gap_researcher("product:default")

    assert result["research_conducted"] == 0
    assert result["insights_written"] == 0


@pytest.mark.asyncio
async def test_consumes_research_queue():
    from core.engine.sentinel.engines.gap_researcher import run_gap_researcher

    queue_item = {
        "id": "research_queue:rq1",
        "query": "Kubernetes HPA custom metrics setup",
        "context": "Failure analysis: missing knowledge about custom metrics",
        "priority": "high",
        "source": "failure-analysis",
        "related_task": "task:abc",
    }

    llm_findings = {
        "findings": [
            {
                "content": "Kubernetes HPA supports custom metrics via the metrics.k8s.io API.",
                "insight_type": "fact",
                "confidence": 0.85,
                "tier": "specialty",
                "discipline": "devops",
            },
        ],
    }

    with (
        patch("core.engine.sentinel.engines.gap_researcher.pool") as mock_pool,
        patch("core.engine.sentinel.engines.gap_researcher.llm") as mock_llm,
    ):
        mock_db = AsyncMock()
        _call_count = {"n": 0}

        async def _gr_queue_side_effect(query, params=None):
            _call_count["n"] += 1
            if _call_count["n"] == 1:
                return [[]]  # bootstrap: scaffolded specialties
            if _call_count["n"] == 2:
                return [[queue_item]]  # research_queue items
            if _call_count["n"] == 3:
                return [[]]  # low-confidence tasks
            if _call_count["n"] == 4:
                return [[]]  # thin specialties
            if "CREATE insight" in query:
                return [[{"id": "insight:gr1"}]]
            if "UPDATE" in query and "research_queue" in query:
                return [[{"id": "research_queue:rq1"}]]
            return []  # domain/subdomain/specialty resolution

        mock_db.query = AsyncMock(side_effect=_gr_queue_side_effect)
        mock_pool.connection.return_value.__aenter__ = AsyncMock(return_value=mock_db)
        mock_pool.connection.return_value.__aexit__ = AsyncMock(return_value=False)

        mock_llm.complete_json = AsyncMock(return_value=llm_findings)

        result = await run_gap_researcher("product:default")

    assert result["research_conducted"] == 1
    assert result["insights_written"] == 1
    mock_llm.complete_json.assert_called_once()


@pytest.mark.asyncio
async def test_identifies_low_confidence_tasks():
    from core.engine.sentinel.engines.gap_researcher import run_gap_researcher

    low_conf_task = {
        "id": "task:low1",
        "discipline": "backend",
        "description": "Design a REST API for user management",
        "self_assessment": 0.4,
    }

    llm_findings = {
        "findings": [
            {
                "content": "REST API design should follow resource-oriented patterns",
                "insight_type": "pattern",
                "confidence": 0.8,
                "tier": "subdomain",
                "discipline": "backend",
            },
        ],
    }

    with (
        patch("core.engine.sentinel.engines.gap_researcher.pool") as mock_pool,
        patch("core.engine.sentinel.engines.gap_researcher.llm") as mock_llm,
    ):
        mock_db = AsyncMock()
        _call_count = {"n": 0}

        async def _gr_lowconf_side_effect(query, params=None):
            _call_count["n"] += 1
            if _call_count["n"] == 1:
                return [[]]  # bootstrap: scaffolded specialties
            if _call_count["n"] == 2:
                return [[]]  # no research_queue items
            if _call_count["n"] == 3:
                return [[low_conf_task]]  # low-confidence task
            if _call_count["n"] == 4:
                return [[]]  # no thin specialties
            if "CREATE insight" in query:
                return [[{"id": "insight:lc1"}]]
            return []  # domain/subdomain/specialty resolution

        mock_db.query = AsyncMock(side_effect=_gr_lowconf_side_effect)
        mock_pool.connection.return_value.__aenter__ = AsyncMock(return_value=mock_db)
        mock_pool.connection.return_value.__aexit__ = AsyncMock(return_value=False)

        mock_llm.complete_json = AsyncMock(return_value=llm_findings)

        result = await run_gap_researcher("product:default")

    assert result["research_conducted"] == 1
    assert result["insights_written"] == 1


@pytest.mark.asyncio
async def test_respects_budget():
    from core.engine.sentinel.engines.gap_researcher import run_gap_researcher

    queue_items = [
        {
            "id": f"research_queue:rq{i}",
            "query": f"Research topic {i}",
            "context": f"Context {i}",
            "priority": "medium",
            "source": "specialty-deepener",
        }
        for i in range(30)
    ]

    llm_findings = {
        "findings": [
            {
                "content": "Finding",
                "insight_type": "fact",
                "confidence": 0.7,
                "tier": "subdomain",
                "discipline": "backend",
            },
        ],
    }

    with (
        patch("core.engine.sentinel.engines.gap_researcher.pool") as mock_pool,
        patch("core.engine.sentinel.engines.gap_researcher.llm") as mock_llm,
    ):
        mock_db = AsyncMock()
        _call_count = {"n": 0}
        _insight_counter = {"n": 0}
        _queue_counter = {"n": 0}

        async def _gr_budget_side_effect(query, params=None):
            _call_count["n"] += 1
            if _call_count["n"] == 1:
                return [[]]  # bootstrap: scaffolded specialties
            if _call_count["n"] == 2:
                return [queue_items]  # research_queue items
            if _call_count["n"] == 3:
                return [[]]  # low-confidence tasks
            if _call_count["n"] == 4:
                return [[]]  # thin specialties
            if "CREATE insight" in query:
                i = _insight_counter["n"]
                _insight_counter["n"] += 1
                return [[{"id": f"insight:b{i}"}]]
            if "UPDATE" in query and "research_queue" in query:
                i = _queue_counter["n"]
                _queue_counter["n"] += 1
                return [[{"id": f"research_queue:rq{i}"}]]
            return []  # domain/subdomain/specialty resolution

        mock_db.query = AsyncMock(side_effect=_gr_budget_side_effect)
        mock_pool.connection.return_value.__aenter__ = AsyncMock(return_value=mock_db)
        mock_pool.connection.return_value.__aexit__ = AsyncMock(return_value=False)

        mock_llm.complete_json = AsyncMock(return_value=llm_findings)

        result = await run_gap_researcher("product:default", budget=5)

    assert result["research_conducted"] == 5
    assert mock_llm.complete_json.call_count == 5


@pytest.mark.asyncio
async def test_low_confidence_gate_uses_calibrated_value():
    """The low-confidence gate must prefer (calibrated_assessment ?? self_assessment) so the calibrated
    confidence — not the raw self-report — decides which tasks get gap-researched (closes the loop)."""
    from core.engine.sentinel.engines.gap_researcher import run_gap_researcher

    captured: list[str] = []

    with (
        patch("core.engine.sentinel.engines.gap_researcher.pool") as mock_pool,
        patch("core.engine.sentinel.engines.gap_researcher.llm"),
    ):
        mock_db = AsyncMock()

        async def _cap(query, params=None):
            captured.append(query)
            return [[]]

        mock_db.query = AsyncMock(side_effect=_cap)
        mock_pool.connection.return_value.__aenter__ = AsyncMock(return_value=mock_db)
        mock_pool.connection.return_value.__aexit__ = AsyncMock(return_value=False)

        await run_gap_researcher("product:default")

    task_selects = [q for q in captured if "FROM task" in q]
    assert task_selects, "expected a SELECT ... FROM task"
    assert any("(calibrated_assessment ?? self_assessment) < 0.6" in q for q in task_selects), (
        "gap_researcher must gate low-confidence tasks on the calibrated value, not raw self_assessment"
    )
