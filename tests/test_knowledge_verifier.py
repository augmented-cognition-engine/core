# tests/test_knowledge_verifier.py
from unittest.mock import AsyncMock, patch

import pytest


def test_knowledge_verifier_module_imports():
    from core.engine.sentinel.engines.knowledge_verifier import run_knowledge_verifier

    assert callable(run_knowledge_verifier)


def test_verification_thresholds_defined():
    from core.engine.sentinel.engines.knowledge_verifier import VERIFICATION_THRESHOLDS

    assert VERIFICATION_THRESHOLDS["version"] == 14
    assert VERIFICATION_THRESHOLDS["personnel"] == 30
    assert VERIFICATION_THRESHOLDS["pricing"] == 30
    assert VERIFICATION_THRESHOLDS["regulation"] == 90
    assert VERIFICATION_THRESHOLDS["process"] == 180
    assert VERIFICATION_THRESHOLDS["fact"] == 90
    assert VERIFICATION_THRESHOLDS["decision"] == 365


def test_get_threshold_for_tags():
    from core.engine.sentinel.engines.knowledge_verifier import get_threshold_for_tags

    assert get_threshold_for_tags(["version", "fact"]) == 14
    assert get_threshold_for_tags(["personnel"]) == 30
    assert get_threshold_for_tags(["some-custom-tag"]) == 90
    assert get_threshold_for_tags([]) == 90


@pytest.mark.asyncio
async def test_no_stale_insights_returns_zero():
    from core.engine.sentinel.engines.knowledge_verifier import run_knowledge_verifier

    with (
        patch("core.engine.sentinel.engines.knowledge_verifier.pool") as mock_pool,
        patch("core.engine.sentinel.engines.knowledge_verifier.llm"),
    ):
        mock_db = AsyncMock()
        mock_db.query = AsyncMock(return_value=[[]])
        mock_pool.connection.return_value.__aenter__ = AsyncMock(return_value=mock_db)
        mock_pool.connection.return_value.__aexit__ = AsyncMock(return_value=False)

        result = await run_knowledge_verifier("product:default")

    assert result["candidates"] == 0
    assert result["confirmed"] == 0
    assert result["updated"] == 0
    assert result["cannot_verify"] == 0


@pytest.mark.asyncio
async def test_confirmed_boosts_confidence():
    from core.engine.sentinel.engines.knowledge_verifier import run_knowledge_verifier

    stale_insight = {
        "id": "insight:stale1",
        "content": "Python 3.12 supports pattern matching",
        "tags": ["fact"],
        "confidence": 0.6,
        "created_at": "2025-01-01T00:00:00Z",
        "last_confirmed": "2025-01-01T00:00:00Z",
    }

    llm_response = {
        "outcome": "confirmed",
        "explanation": "Pattern matching was introduced in Python 3.10",
    }

    with (
        patch("core.engine.sentinel.engines.knowledge_verifier.pool") as mock_pool,
        patch("core.engine.sentinel.engines.knowledge_verifier.llm") as mock_llm,
    ):
        mock_db = AsyncMock()
        _call_count = {"n": 0}

        async def _kv_confirmed_side_effect(query, params=None):
            _call_count["n"] += 1
            if _call_count["n"] == 1:
                return [[stale_insight]]  # stale insights
            if _call_count["n"] == 2:
                return [[]]  # low-confidence insights
            if "UPDATE" in query:
                return [{"id": "insight:stale1"}]
            return []

        mock_db.query = AsyncMock(side_effect=_kv_confirmed_side_effect)
        mock_pool.connection.return_value.__aenter__ = AsyncMock(return_value=mock_db)
        mock_pool.connection.return_value.__aexit__ = AsyncMock(return_value=False)

        mock_llm.complete_json = AsyncMock(return_value=llm_response)

        result = await run_knowledge_verifier("product:default")

    assert result["confirmed"] == 1
    assert result["updated"] == 0
    assert result["cannot_verify"] == 0
    mock_llm.complete_json.assert_called_once()


@pytest.mark.asyncio
async def test_updated_creates_new_insight():
    from core.engine.sentinel.engines.knowledge_verifier import run_knowledge_verifier

    stale_insight = {
        "id": "insight:outdated1",
        "content": "React 17 is the latest version",
        "tags": ["version", "frontend"],
        "confidence": 0.7,
        "created_at": "2024-06-01T00:00:00Z",
        "last_confirmed": "2024-06-01T00:00:00Z",
        "insight_type": "fact",
        "tier": "subdomain",
    }

    llm_response = {
        "outcome": "updated",
        "explanation": "React 19 is now the latest stable version",
        "updated_content": "React 19 is the latest stable version",
        "confidence": 0.95,
    }

    with (
        patch("core.engine.sentinel.engines.knowledge_verifier.pool") as mock_pool,
        patch("core.engine.sentinel.engines.knowledge_verifier.llm") as mock_llm,
    ):
        mock_db = AsyncMock()
        _call_count = {"n": 0}

        async def _kv_updated_side_effect(query, params=None):
            _call_count["n"] += 1
            if _call_count["n"] == 1:
                return [[stale_insight]]  # stale insights
            if _call_count["n"] == 2:
                return [[]]  # low-confidence insights
            if "CREATE insight" in query:
                return [[{"id": "insight:new1"}]]
            if "UPDATE" in query and "contradicted" in query:
                return [{"id": "insight:outdated1"}]
            return []  # domain/subdomain/specialty resolution

        mock_db.query = AsyncMock(side_effect=_kv_updated_side_effect)
        mock_pool.connection.return_value.__aenter__ = AsyncMock(return_value=mock_db)
        mock_pool.connection.return_value.__aexit__ = AsyncMock(return_value=False)

        mock_llm.complete_json = AsyncMock(return_value=llm_response)

        result = await run_knowledge_verifier("product:default")

    assert result["updated"] == 1


@pytest.mark.asyncio
async def test_cannot_verify_decays_confidence():
    from core.engine.sentinel.engines.knowledge_verifier import run_knowledge_verifier

    stale_insight = {
        "id": "insight:unclear1",
        "content": "Company X uses Kubernetes 1.28",
        "tags": ["version"],
        "confidence": 0.5,
        "created_at": "2024-09-01T00:00:00Z",
        "last_confirmed": "2024-09-01T00:00:00Z",
    }

    llm_response = {
        "outcome": "cannot_verify",
        "explanation": "Cannot verify current Kubernetes version used by Company X",
    }

    with (
        patch("core.engine.sentinel.engines.knowledge_verifier.pool") as mock_pool,
        patch("core.engine.sentinel.engines.knowledge_verifier.llm") as mock_llm,
    ):
        mock_db = AsyncMock()
        _call_count = {"n": 0}

        async def _kv_cannot_verify_side_effect(query, params=None):
            _call_count["n"] += 1
            if _call_count["n"] == 1:
                return [[stale_insight]]  # stale insights
            if _call_count["n"] == 2:
                return [[]]  # low-confidence insights
            if "UPDATE" in query:
                return [{"id": "insight:unclear1"}]
            return []

        mock_db.query = AsyncMock(side_effect=_kv_cannot_verify_side_effect)
        mock_pool.connection.return_value.__aenter__ = AsyncMock(return_value=mock_db)
        mock_pool.connection.return_value.__aexit__ = AsyncMock(return_value=False)

        mock_llm.complete_json = AsyncMock(return_value=llm_response)

        result = await run_knowledge_verifier("product:default")

    assert result["cannot_verify"] == 1


@pytest.mark.asyncio
async def test_respects_budget():
    from core.engine.sentinel.engines.knowledge_verifier import run_knowledge_verifier

    stale_insights = [
        {
            "id": f"insight:s{i}",
            "content": f"Stale fact {i}",
            "tags": ["fact"],
            "confidence": 0.6,
            "created_at": "2024-01-01T00:00:00Z",
            "last_confirmed": "2024-01-01T00:00:00Z",
        }
        for i in range(30)
    ]

    llm_response = {"outcome": "confirmed", "explanation": "Confirmed"}

    with (
        patch("core.engine.sentinel.engines.knowledge_verifier.pool") as mock_pool,
        patch("core.engine.sentinel.engines.knowledge_verifier.llm") as mock_llm,
    ):
        mock_db = AsyncMock()
        _call_count = {"n": 0}
        _update_counter = {"n": 0}

        async def _kv_budget_side_effect(query, params=None):
            _call_count["n"] += 1
            if _call_count["n"] == 1:
                return [stale_insights]  # stale insights
            if _call_count["n"] == 2:
                return [[]]  # low-confidence insights
            if "UPDATE" in query:
                i = _update_counter["n"]
                _update_counter["n"] += 1
                return [{"id": f"insight:s{i}"}]
            return []

        mock_db.query = AsyncMock(side_effect=_kv_budget_side_effect)
        mock_pool.connection.return_value.__aenter__ = AsyncMock(return_value=mock_db)
        mock_pool.connection.return_value.__aexit__ = AsyncMock(return_value=False)

        mock_llm.complete_json = AsyncMock(return_value=llm_response)

        result = await run_knowledge_verifier("product:default", budget=5)

    assert result["candidates"] >= 5
    assert mock_llm.complete_json.call_count == 5
