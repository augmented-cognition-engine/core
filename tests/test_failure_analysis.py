# tests/test_failure_analysis.py
from unittest.mock import AsyncMock, patch

import pytest


def test_failure_analysis_module_imports():
    from core.engine.sentinel.engines.failure_analysis import run_failure_analysis

    assert callable(run_failure_analysis)


@pytest.mark.asyncio
async def test_no_failures_returns_zero_counts():
    from core.engine.sentinel.engines.failure_analysis import run_failure_analysis

    with patch("core.engine.sentinel.engines.failure_analysis.pool") as mock_pool:
        mock_db = AsyncMock()
        mock_db.query = AsyncMock(return_value=[[]])
        mock_pool.connection.return_value.__aenter__ = AsyncMock(return_value=mock_db)
        mock_pool.connection.return_value.__aexit__ = AsyncMock(return_value=False)

        result = await run_failure_analysis("product:default")

    assert result["failures_analyzed"] == 0
    assert result["corrections_written"] == 0
    assert result["research_queued"] == 0


@pytest.mark.asyncio
async def test_analyzes_rejected_task():
    from core.engine.sentinel.engines.failure_analysis import run_failure_analysis

    rejected_task = {
        "id": "task:abc",
        "description": "Write a React 19 component using class syntax",
        "discipline": "frontend",
        "output": "Here is a class component...",
        "feedback_human": "rejected",
        "feedback_score": 0.2,
        "self_assessment": 0.3,
        "intelligence_loaded": ["insight:old1"],
    }

    llm_response = {
        "failure_type": "wrong_assumption",
        "root_cause": "Assumed React 19 still supports class components as primary pattern",
        "correction": "React 19 favors function components with hooks; class components are legacy",
        "confidence": 0.9,
        "should_research": False,
    }

    with (
        patch("core.engine.sentinel.engines.failure_analysis.pool") as mock_pool,
        patch("core.engine.sentinel.engines.failure_analysis.llm") as mock_llm,
    ):
        mock_db = AsyncMock()
        _call_count = {"n": 0}

        async def _fa_rejected_side_effect(query, params=None):
            _call_count["n"] += 1
            if _call_count["n"] == 1:
                return [[rejected_task]]  # fetch rejected tasks
            if "CREATE insight" in query:
                return [[{"id": "insight:corr1"}]]
            return []  # domain/subdomain/specialty/flow config resolution

        mock_db.query = AsyncMock(side_effect=_fa_rejected_side_effect)
        mock_pool.connection.return_value.__aenter__ = AsyncMock(return_value=mock_db)
        mock_pool.connection.return_value.__aexit__ = AsyncMock(return_value=False)

        mock_llm.complete_json = AsyncMock(return_value=llm_response)

        result = await run_failure_analysis("product:default")

    assert result["failures_analyzed"] == 1
    assert result["corrections_written"] == 1
    assert result["research_queued"] == 0
    mock_llm.complete_json.assert_called_once()


@pytest.mark.asyncio
async def test_queues_research_for_knowledge_gap():
    from core.engine.sentinel.engines.failure_analysis import run_failure_analysis

    failed_task = {
        "id": "task:gap1",
        "description": "Configure Kubernetes HPA with custom metrics",
        "discipline": "devops",
        "output": "Here is the HPA config...",
        "feedback_human": "rejected",
        "feedback_score": 0.1,
        "self_assessment": 0.2,
        "intelligence_loaded": [],
    }

    llm_response = {
        "failure_type": "knowledge_gap",
        "root_cause": "No knowledge of custom metrics adapter for HPA",
        "correction": "Kubernetes HPA requires a metrics-server or custom metrics adapter",
        "confidence": 0.75,
        "should_research": True,
        "research_query": "Kubernetes HPA custom metrics adapter setup and configuration",
    }

    with (
        patch("core.engine.sentinel.engines.failure_analysis.pool") as mock_pool,
        patch("core.engine.sentinel.engines.failure_analysis.llm") as mock_llm,
    ):
        mock_db = AsyncMock()
        _call_count = {"n": 0}

        async def _fa_gap_side_effect(query, params=None):
            _call_count["n"] += 1
            if _call_count["n"] == 1:
                return [[failed_task]]  # fetch rejected tasks
            if "CREATE insight" in query:
                return [[{"id": "insight:corr2"}]]
            if "CREATE research_queue" in query:
                return [[{"id": "research_queue:rq1"}]]
            return []  # domain/subdomain/specialty/flow config resolution

        mock_db.query = AsyncMock(side_effect=_fa_gap_side_effect)
        mock_pool.connection.return_value.__aenter__ = AsyncMock(return_value=mock_db)
        mock_pool.connection.return_value.__aexit__ = AsyncMock(return_value=False)

        mock_llm.complete_json = AsyncMock(return_value=llm_response)

        result = await run_failure_analysis("product:default")

    assert result["failures_analyzed"] == 1
    assert result["corrections_written"] == 1
    assert result["research_queued"] == 1


@pytest.mark.asyncio
async def test_respects_budget():
    from core.engine.sentinel.engines.failure_analysis import run_failure_analysis

    tasks = [
        {
            "id": f"task:t{i}",
            "description": f"Task {i}",
            "discipline": "frontend",
            "output": f"Output {i}",
            "feedback_human": "rejected",
            "feedback_score": 0.2,
            "self_assessment": 0.3,
            "intelligence_loaded": [],
        }
        for i in range(30)
    ]

    llm_response = {
        "failure_type": "other",
        "root_cause": "Unknown",
        "correction": "Correction",
        "confidence": 0.5,
        "should_research": False,
    }

    with (
        patch("core.engine.sentinel.engines.failure_analysis.pool") as mock_pool,
        patch("core.engine.sentinel.engines.failure_analysis.llm") as mock_llm,
    ):
        mock_db = AsyncMock()
        _call_count = {"n": 0}
        _insight_counter = {"n": 0}

        async def _fa_budget_side_effect(query, params=None):
            _call_count["n"] += 1
            if _call_count["n"] == 1:
                return [tasks]  # fetch rejected tasks
            if "CREATE insight" in query:
                i = _insight_counter["n"]
                _insight_counter["n"] += 1
                return [[{"id": f"insight:b{i}"}]]
            return []  # domain/subdomain/specialty/flow config resolution

        mock_db.query = AsyncMock(side_effect=_fa_budget_side_effect)
        mock_pool.connection.return_value.__aenter__ = AsyncMock(return_value=mock_db)
        mock_pool.connection.return_value.__aexit__ = AsyncMock(return_value=False)

        mock_llm.complete_json = AsyncMock(return_value=llm_response)

        result = await run_failure_analysis("product:default", budget=20)

    assert result["failures_analyzed"] == 20
    assert mock_llm.complete_json.call_count == 20


def test_failure_type_tags():
    from core.engine.sentinel.engines.failure_analysis import _build_correction_tags

    assert "auto-correction" in _build_correction_tags("knowledge_gap")
    assert "knowledge_gap" in _build_correction_tags("knowledge_gap")
    assert "wrong_assumption" in _build_correction_tags("wrong_assumption")
    assert "framework-issue" in _build_correction_tags("framework_mismatch")
    assert "other" in _build_correction_tags("other")


@pytest.mark.asyncio
async def test_failure_gate_uses_calibrated_value():
    """The failure gate must prefer (calibrated_assessment ?? self_assessment) so a task in an
    overconfident domain (raw high, calibrated low) is correctly flagged as a likely failure."""
    from core.engine.sentinel.engines.failure_analysis import run_failure_analysis

    captured: list[str] = []

    with patch("core.engine.sentinel.engines.failure_analysis.pool") as mock_pool:
        mock_db = AsyncMock()

        async def _cap(query, params=None):
            captured.append(query)
            return [[]]

        mock_db.query = AsyncMock(side_effect=_cap)
        mock_pool.connection.return_value.__aenter__ = AsyncMock(return_value=mock_db)
        mock_pool.connection.return_value.__aexit__ = AsyncMock(return_value=False)

        await run_failure_analysis("product:default")

    task_selects = [q for q in captured if "FROM task" in q]
    assert task_selects, "expected a SELECT ... FROM task"
    assert any("(calibrated_assessment ?? self_assessment) < 0.4" in q for q in task_selects), (
        "failure_analysis must gate on the calibrated value, not raw self_assessment"
    )
