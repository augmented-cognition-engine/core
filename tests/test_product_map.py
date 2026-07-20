# tests/test_product_map.py
"""Tests for ProductMap CRUD — capabilities, quality, direction, health summary."""

from unittest.mock import AsyncMock, MagicMock

import pytest


@pytest.fixture
def mock_db():
    db = AsyncMock()
    db.query = AsyncMock(return_value=[])
    return db


@pytest.fixture
def mock_pool(mock_db):
    pool = MagicMock()
    cm = AsyncMock()
    cm.__aenter__ = AsyncMock(return_value=mock_db)
    cm.__aexit__ = AsyncMock(return_value=None)
    pool.connection.return_value = cm
    return pool


@pytest.fixture
def product_map(mock_pool):
    from core.engine.product.map import ProductMap

    return ProductMap(mock_pool)


# ---------------------------------------------------------------------------
# get_capabilities
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_get_capabilities_empty(product_map, mock_db):
    """get_capabilities returns empty list when no capabilities exist."""
    mock_db.query = AsyncMock(return_value=[])

    result = await product_map.get_capabilities("product:test")

    assert result == []
    mock_db.query.assert_called_once()
    call_sql = mock_db.query.call_args[0][0]
    assert "capability" in call_sql.lower()


# ---------------------------------------------------------------------------
# upsert_capability
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_upsert_capability_creates_record(product_map, mock_db):
    """upsert_capability creates and returns the capability record."""
    fake_cap = {
        "id": "capability:auth",
        "slug": "auth",
        "name": "Authentication",
        "status": "built",
        "product": "product:test",
    }
    mock_db.query = AsyncMock(return_value=[fake_cap])

    result = await product_map.upsert_capability(
        {
            "slug": "auth",
            "name": "Authentication",
            "description": "User authentication flows",
            "status": "built",
        },
        "product:test",
    )

    assert result["slug"] == "auth"
    assert result["name"] == "Authentication"
    call_sql = mock_db.query.call_args[0][0].upper()
    assert "UPSERT" in call_sql or "INSERT" in call_sql or "UPDATE" in call_sql


# ---------------------------------------------------------------------------
# get_capability (with enrichment)
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_get_capability_returns_enriched(product_map, mock_db):
    """get_capability returns capability with quality dimensions attached."""
    fake_cap = {
        "id": "capability:auth",
        "slug": "auth",
        "name": "Authentication",
        "status": "built",
    }
    quality_row = {
        "id": "capability_quality:q1",
        "capability": "capability:auth",
        "dimension": "security",
        "score": 0.9,
    }

    # Sequence: 1st call = capability, 2nd = quality, 3rd = deps, 4th = realized files
    mock_db.query = AsyncMock(
        side_effect=[
            [fake_cap],  # get capability
            [quality_row],  # quality dimensions
            [],  # dependencies
            [],  # realized files
        ]
    )

    result = await product_map.get_capability("auth", "product:test")

    assert result is not None
    assert result["slug"] == "auth"
    assert "quality" in result
    assert result["quality"][0]["dimension"] == "security"
    assert "dependencies" in result
    assert "realized_files" in result


# ---------------------------------------------------------------------------
# get_vision / set_vision
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_set_vision_deactivates_previous(product_map, mock_db):
    """set_vision deactivates old active vision and creates a new one."""
    old_vision = {"id": "product_vision:old", "name": "Old vision", "active": True}
    new_vision = {
        "id": "product_vision:new",
        "name": "New vision",
        "active": True,
        "supersedes": "product_vision:old",
    }
    mock_db.query = AsyncMock(
        side_effect=[
            [old_vision],  # fetch current active
            [],  # deactivate old
            [new_vision],  # create new
        ]
    )
    result = await product_map.set_vision(
        {"name": "New vision", "description": "Updated focus"},
        "product:test",
    )
    assert result["name"] == "New vision"
    assert result.get("active") is True
    assert mock_db.query.call_count == 3


@pytest.mark.asyncio
async def test_get_vision_returns_none_when_empty(product_map, mock_db):
    mock_db.query = AsyncMock(return_value=[])
    result = await product_map.get_vision("product:test")
    assert result is None


# ---------------------------------------------------------------------------
# get_themes / create_theme
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_get_themes_empty(product_map, mock_db):
    mock_db.query = AsyncMock(return_value=[])
    result = await product_map.get_themes("product:test")
    assert result == []


@pytest.mark.asyncio
async def test_create_theme(product_map, mock_db):
    new_theme = {"id": "theme:abc", "name": "GTM Strategy", "status": "active"}
    mock_db.query = AsyncMock(return_value=[new_theme])
    result = await product_map.create_theme({"name": "GTM Strategy"}, "product:test")
    assert result["name"] == "GTM Strategy"
    assert result["status"] == "active"


# ---------------------------------------------------------------------------
# update_quality
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_update_quality_upserts_assessment(product_map, mock_db):
    """update_quality upserts a quality assessment for a capability dimension."""
    fake_quality = {
        "id": "capability_quality:q1",
        "capability": "capability:auth",
        "dimension": "testing",
        "score": 0.75,
        "gaps": ["no integration tests"],
    }
    mock_db.query = AsyncMock(return_value=[fake_quality])

    result = await product_map.update_quality(
        "auth",
        "testing",
        {"score": 0.75, "gaps": ["no integration tests"], "assessed_by": "scanner"},
        "product:test",
    )

    assert result["dimension"] == "testing"
    assert result["score"] == 0.75
    call_sql = mock_db.query.call_args[0][0].upper()
    assert "UPSERT" in call_sql or "UPDATE" in call_sql or "CREATE" in call_sql


# ---------------------------------------------------------------------------
# health_summary
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_health_summary_aggregates_by_dimension(product_map, mock_db):
    """health_summary aggregates quality scores across all capabilities."""
    quality_rows = [
        {"dimension": "security", "score": 0.9, "gaps": []},
        {"dimension": "security", "score": 0.7, "gaps": ["missing audit log"]},
        {"dimension": "testing", "score": 0.5, "gaps": ["low coverage", "no e2e"]},
    ]
    caps_rows = [
        {"id": "capability:auth", "status": "built"},
        {"id": "capability:billing", "status": "planned"},
    ]
    mock_db.query = AsyncMock(side_effect=[quality_rows, caps_rows])

    summary = await product_map.health_summary("product:test")

    assert "dimensions" in summary
    assert "security" in summary["dimensions"]
    sec = summary["dimensions"]["security"]
    assert sec["assessed_count"] == 2
    assert abs(sec["avg_score"] - 0.8) < 0.01
    assert sec["min_score"] == 0.7

    assert "testing" in summary["dimensions"]
    tst = summary["dimensions"]["testing"]
    assert tst["total_gaps"] == 2

    assert summary["total_capabilities"] == 2
    assert "by_status" in summary
    assert summary["by_status"]["built"] == 1
    assert summary["by_status"]["planned"] == 1
