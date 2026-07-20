# tests/test_gap_analyzer_engine.py
"""Tests for the gap analyzer overnight engine.

TDD: tests written before implementation.
"""

from unittest.mock import AsyncMock, patch

import pytest


def test_gap_analyzer_registers():
    """gap_analyzer should be present in engine_registry after import."""
    from core.engine.sentinel.engines.gap_analyzer import run_gap_analyzer  # noqa: F401
    from core.engine.sentinel.registry import engine_registry

    assert "gap_analyzer" in engine_registry
    entry = engine_registry["gap_analyzer"]
    assert entry["cron"] == "0 3 * * *"
    assert callable(entry["fn"])


@pytest.mark.asyncio
async def test_gap_analyzer_returns_results():
    """Mock DB + LLM — verify returned dict has expected structure."""
    from core.engine.sentinel.engines.gap_analyzer import run_gap_analyzer

    capability = {
        "id": "capability:cap1",
        "slug": "auth",
        "description": "Authentication and authorization",
        "status": "built",
        "tags": ["platform"],
        "intent": {"tier": "platform"},
        "reality": {"files": ["src/auth.py", "src/middleware.py"], "file_glob": ""},
    }

    # Batch response — array of assessments
    llm_response = [
        {
            "dimension": "security",
            "score": 0.3,
            "gaps": ["No rate limiting on login endpoint", "Missing MFA support"],
            "evidence": ["src/auth.py reviewed", "No rate limit middleware found"],
        },
    ]

    with (
        patch("core.engine.sentinel.engines.gap_analyzer.pool") as mock_pool,
        patch("core.engine.sentinel.engines.gap_analyzer.llm") as mock_llm,
    ):
        mock_db = AsyncMock()

        async def _side_effect(query, params=None):
            if "FROM capability WHERE" in query:
                return [[capability]]
            if "active_discipline" in query:
                return [[{"discipline": "security"}]]
            if "insight" in query and "best_practice" in query:
                return [[{"content": "Use rate limiting", "confidence": 0.9}]]
            if "graph_file" in query:
                return [[]]  # no graph files
            return [[{"id": "capability_quality:q1"}]]

        mock_db.query = AsyncMock(side_effect=_side_effect)
        mock_pool.connection.return_value.__aenter__ = AsyncMock(return_value=mock_db)
        mock_pool.connection.return_value.__aexit__ = AsyncMock(return_value=False)

        mock_llm.complete_json = AsyncMock(return_value=llm_response)

        result = await run_gap_analyzer("product:default")

    assert isinstance(result, dict)
    assert "capabilities_scanned" in result
    assert "gaps_found" in result
    assert "questions_generated" in result
    assert "llm_calls" in result
    assert result["capabilities_scanned"] == 1
    assert result["gaps_found"] == 2
    # score < 0.4 with 2 gaps → should generate up to 2 questions
    assert result["questions_generated"] == 2


@pytest.mark.asyncio
async def test_gap_analyzer_respects_budget():
    """With 10 capabilities but budget=2, only 2 capabilities are processed."""
    from core.engine.sentinel.engines.gap_analyzer import run_gap_analyzer

    capabilities = [
        {
            "id": f"capability:cap{i}",
            "slug": f"feature_{i}",
            "description": f"Feature {i}",
            "status": "built",
            "tags": [],
            "intent": {},
            "reality": {"files": [f"src/feature_{i}.py"], "file_glob": ""},
        }
        for i in range(10)
    ]

    # Batch response
    llm_response = [
        {"dimension": "testing", "score": 0.8, "gaps": [], "evidence": ["tests found"]},
    ]

    with (
        patch("core.engine.sentinel.engines.gap_analyzer.pool") as mock_pool,
        patch("core.engine.sentinel.engines.gap_analyzer.llm") as mock_llm,
    ):
        mock_db = AsyncMock()

        async def _side_effect(query, params=None):
            if "FROM capability WHERE" in query:
                return [[*capabilities]]
            if "active_discipline" in query:
                return [[{"discipline": "testing"}]]
            if "insight" in query and "best_practice" in query:
                return [[{"content": "Write unit tests", "confidence": 0.85}]]
            if "graph_file" in query:
                return [[]]
            return [[]]

        mock_db.query = AsyncMock(side_effect=_side_effect)
        mock_pool.connection.return_value.__aenter__ = AsyncMock(return_value=mock_db)
        mock_pool.connection.return_value.__aexit__ = AsyncMock(return_value=False)

        mock_llm.complete_json = AsyncMock(return_value=llm_response)

        result = await run_gap_analyzer("product:default", budget=2)

    assert result["capabilities_scanned"] == 2
    # 2 capabilities × 1 batch each = 2 LLM calls
    assert mock_llm.complete_json.call_count == 2
