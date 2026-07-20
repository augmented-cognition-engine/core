# tests/test_mcp_product.py
"""Tests for MCP product awareness tools — ace_product_health, ace_gaps,
ace_recommend, ace_scan_repo, ace_ask_product."""

from unittest.mock import AsyncMock, patch

import pytest

# ---------------------------------------------------------------------------
# ace_product_health
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_ace_product_health_returns_dimensions():
    """ace_product_health() returns a dict with a 'dimensions' key."""
    from core.engine.mcp.tools import ace_product_health

    mock_health = {
        "dimensions": {
            "testing": {"avg_score": 0.8, "min_score": 0.6, "assessed_count": 3, "total_gaps": 2},
            "security": {"avg_score": 0.4, "min_score": 0.2, "assessed_count": 2, "total_gaps": 5},
        },
        "total_capabilities": 5,
        "by_status": {"active": 3, "planned": 2},
    }

    with patch("core.engine.mcp.tools.pool") as mock_pool:
        mock_pm = AsyncMock()
        mock_pm.health_summary = AsyncMock(return_value=mock_health)

        with patch("core.engine.product.map.ProductMap") as MockProductMap:
            MockProductMap.return_value = mock_pm

            # Patch the import inside the function
            import core.engine.mcp.tools as tools_module

            with patch.object(tools_module, "_get_product_map", return_value=mock_pm, create=True):
                # Call via direct mock of ProductMap constructor
                with patch("core.engine.mcp.tools.pool", mock_pool):
                    # Patch the class used inside ace_product_health
                    with patch("core.engine.product.map.ProductMap", return_value=mock_pm):
                        result = await ace_product_health(product_id="product:default")

    assert "dimensions" in result
    assert result["total_capabilities"] == 5


# ---------------------------------------------------------------------------
# ace_gaps
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_ace_gaps_returns_gaps_and_count():
    """ace_gaps() returns a dict with 'gaps' list and 'count'."""
    from core.engine.mcp.tools import ace_gaps

    gap_rows = [
        {"id": "capability_quality:1", "dimension": "testing", "score": 0.3},
        {"id": "capability_quality:2", "dimension": "security", "score": 0.5},
    ]

    with patch("core.engine.mcp.tools.pool") as mock_pool:
        mock_conn = AsyncMock()
        mock_conn.query = AsyncMock(return_value=[gap_rows])
        mock_pool.connection.return_value.__aenter__ = AsyncMock(return_value=mock_conn)
        mock_pool.connection.return_value.__aexit__ = AsyncMock(return_value=False)

        result = await ace_gaps(product_id="product:default")

    assert "gaps" in result
    assert "count" in result
    assert result["count"] == 2
    assert len(result["gaps"]) == 2


@pytest.mark.asyncio
async def test_ace_gaps_filters_by_dimension():
    """ace_gaps() passes dimension to DB query when provided."""
    from core.engine.mcp.tools import ace_gaps

    gap_rows = [
        {"id": "capability_quality:1", "dimension": "testing", "score": 0.3},
    ]

    with patch("core.engine.mcp.tools.pool") as mock_pool:
        mock_conn = AsyncMock()
        mock_conn.query = AsyncMock(return_value=[gap_rows])
        mock_pool.connection.return_value.__aenter__ = AsyncMock(return_value=mock_conn)
        mock_pool.connection.return_value.__aexit__ = AsyncMock(return_value=False)

        result = await ace_gaps(product_id="product:default", dimension="testing")

    assert result["count"] == 1
    call_args = mock_conn.query.call_args
    params = call_args[0][1] if len(call_args[0]) > 1 else call_args[1]
    assert params.get("dim") == "testing"


# ---------------------------------------------------------------------------
# ace_recommend
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_ace_recommend_returns_recommendations():
    """ace_recommend() returns a dict with 'recommendations' list."""
    from core.engine.mcp.tools import ace_recommend

    mock_recs = [
        {"title": "Improve test coverage", "priority": "high", "score": 0.9},
        {"title": "Add security audit", "priority": "medium", "score": 0.7},
    ]

    with patch("core.engine.mcp.tools.pool") as mock_pool:
        mock_prioritizer = AsyncMock()
        mock_prioritizer.prioritize = AsyncMock(return_value=mock_recs)

        with patch("core.engine.product.strategic_prioritizer.StrategicPrioritizer", return_value=mock_prioritizer):
            result = await ace_recommend(product_id="product:default")

    assert "recommendations" in result
    assert isinstance(result["recommendations"], list)


@pytest.mark.asyncio
async def test_ace_recommend_handles_error_gracefully():
    """ace_recommend() returns empty recommendations on error, not an exception."""
    from core.engine.mcp.tools import ace_recommend

    with patch("core.engine.mcp.tools.pool") as mock_pool:
        mock_prioritizer = AsyncMock()
        mock_prioritizer.prioritize = AsyncMock(side_effect=RuntimeError("DB down"))

        with patch("core.engine.product.strategic_prioritizer.StrategicPrioritizer", return_value=mock_prioritizer):
            result = await ace_recommend(product_id="product:default")

    assert "recommendations" in result
    assert result["recommendations"] == []
    assert "error" in result


# ---------------------------------------------------------------------------
# ace_scan_repo
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_ace_scan_repo_returns_started_status():
    """ace_scan_repo() launches background scan and returns status=started."""
    from core.engine.mcp.tools import ace_scan_repo

    with patch("core.engine.scanner.scanner.scan_repo", new_callable=AsyncMock):
        result = await ace_scan_repo(repo_path=".", product_id="product:default")

    assert result["status"] == "started"
    assert result["graph_id"] == "default"
    assert "background" in result["message"].lower()


@pytest.mark.asyncio
async def test_ace_scan_repo_handles_error_gracefully():
    """ace_scan_repo() returns error dict when path does not exist."""
    from core.engine.mcp.tools import ace_scan_repo

    result = await ace_scan_repo(repo_path="/nonexistent/path/xyz", product_id="product:default")

    assert "error" in result
    assert "not found" in result["error"].lower()


# ---------------------------------------------------------------------------
# ace_ask_product
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_ace_ask_product_returns_question_id_and_status():
    """ace_ask_product() creates a product_question and returns question_id and status."""
    from core.engine.mcp.tools import ace_ask_product

    with patch("core.engine.mcp.tools.pool") as mock_pool:
        mock_conn = AsyncMock()
        mock_conn.query = AsyncMock(return_value=[[{"id": "product_question:abc123", "question": "How many users?"}]])
        mock_pool.connection.return_value.__aenter__ = AsyncMock(return_value=mock_conn)
        mock_pool.connection.return_value.__aexit__ = AsyncMock(return_value=False)

        result = await ace_ask_product(
            question="How many users do we have?",
            product_id="product:default",
        )

    assert "question_id" in result
    assert "status" in result
    assert result["status"] == "open"
    assert "question" in result
    assert result["question"] == "How many users do we have?"
