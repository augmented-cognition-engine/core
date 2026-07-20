# tests/test_review_impact.py
"""Tests for PRImpactAnalyzer — graph-based PR blast-radius analysis."""

from unittest.mock import AsyncMock, patch

import pytest

from core.engine.review.impact import PRImpactAnalyzer


@pytest.mark.asyncio
async def test_find_affected_capabilities():
    analyzer = PRImpactAnalyzer()
    mock_rows = [
        {"capability_slug": "auth", "capability_name": "Authentication"},
        {"capability_slug": "api", "capability_name": "REST API"},
    ]
    with patch("core.engine.review.impact.pool") as mock_pool:
        mock_conn = AsyncMock()
        mock_conn.query = AsyncMock(return_value=[[mock_rows[0], mock_rows[1]]])
        mock_pool.connection.return_value.__aenter__ = AsyncMock(return_value=mock_conn)
        mock_pool.connection.return_value.__aexit__ = AsyncMock(return_value=False)
        caps = await analyzer.affected_capabilities(["core/engine/core/auth.py", "engine/api/routes.py"])
    assert len(caps) == 2
    assert caps[0]["capability_slug"] == "auth"


@pytest.mark.asyncio
async def test_find_dependent_files():
    analyzer = PRImpactAnalyzer()
    mock_rows = [{"path": "core/engine/api/middleware.py", "strength": 0.85}]
    with patch("core.engine.review.impact.pool") as mock_pool:
        mock_conn = AsyncMock()
        mock_conn.query = AsyncMock(return_value=[[mock_rows[0]]])
        mock_pool.connection.return_value.__aenter__ = AsyncMock(return_value=mock_conn)
        mock_pool.connection.return_value.__aexit__ = AsyncMock(return_value=False)
        deps = await analyzer.dependent_files(["core/engine/core/auth.py"])
    assert len(deps) == 1
    assert deps[0]["path"] == "core/engine/api/middleware.py"


@pytest.mark.asyncio
async def test_find_quality_scores():
    analyzer = PRImpactAnalyzer()
    mock_rows = [
        {"slug": "auth", "dimension": "security", "score": 0.4},
        {"slug": "auth", "dimension": "testing", "score": 0.7},
    ]
    with patch("core.engine.review.impact.pool") as mock_pool:
        mock_conn = AsyncMock()
        mock_conn.query = AsyncMock(return_value=[[mock_rows[0], mock_rows[1]]])
        mock_pool.connection.return_value.__aenter__ = AsyncMock(return_value=mock_conn)
        mock_pool.connection.return_value.__aexit__ = AsyncMock(return_value=False)
        scores = await analyzer.quality_scores(["auth"])
    assert len(scores) == 2
    assert scores[0]["dimension"] == "security"


@pytest.mark.asyncio
async def test_empty_files_returns_empty():
    analyzer = PRImpactAnalyzer()
    caps = await analyzer.affected_capabilities([])
    assert caps == []


@pytest.mark.asyncio
async def test_empty_files_returns_empty_dependent_files():
    analyzer = PRImpactAnalyzer()
    deps = await analyzer.dependent_files([])
    assert deps == []


@pytest.mark.asyncio
async def test_empty_slugs_returns_empty_quality_scores():
    analyzer = PRImpactAnalyzer()
    scores = await analyzer.quality_scores([])
    assert scores == []


@pytest.mark.asyncio
async def test_full_impact_surfaces_risk_flags():
    analyzer = PRImpactAnalyzer()
    caps_rows = [{"capability_slug": "auth", "capability_name": "Authentication"}]
    deps_rows = [{"path": "core/engine/api/middleware.py", "strength": 0.9}]
    scores_rows = [
        {"slug": "auth", "dimension": "security", "score": 0.3},
        {"slug": "auth", "dimension": "testing", "score": 0.8},
    ]

    call_count = 0

    async def fake_query(q, params=None):
        nonlocal call_count
        call_count += 1
        if call_count == 1:
            return [caps_rows]
        if call_count == 2:
            return [deps_rows]
        return [scores_rows]

    with patch("core.engine.review.impact.pool") as mock_pool:
        mock_conn = AsyncMock()
        mock_conn.query = AsyncMock(side_effect=fake_query)
        mock_pool.connection.return_value.__aenter__ = AsyncMock(return_value=mock_conn)
        mock_pool.connection.return_value.__aexit__ = AsyncMock(return_value=False)
        result = await analyzer.full_impact(["core/engine/core/auth.py"])

    assert "affected_capabilities" in result
    assert "dependent_files" in result
    assert "quality_scores" in result
    assert "risk_flags" in result

    assert len(result["affected_capabilities"]) == 1
    assert len(result["dependent_files"]) == 1
    assert len(result["quality_scores"]) == 2
    # Only the security score (0.3) is below 0.5 — one risk flag expected
    assert len(result["risk_flags"]) == 1
    assert "security" in result["risk_flags"][0]
    assert "0.30" in result["risk_flags"][0]


@pytest.mark.asyncio
async def test_full_impact_empty_paths_returns_empty():
    analyzer = PRImpactAnalyzer()
    result = await analyzer.full_impact([])
    assert result["affected_capabilities"] == []
    assert result["dependent_files"] == []
    assert result["quality_scores"] == []
    assert result["risk_flags"] == []
