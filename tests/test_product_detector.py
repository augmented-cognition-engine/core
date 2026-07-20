# tests/test_product_detector.py
"""Unit tests for product_detector.detect_product_id."""

from unittest.mock import AsyncMock, patch

import pytest


@pytest.mark.asyncio
async def test_detect_returns_match_when_project_found():
    """Returns the product from the matching project record."""
    with (
        patch("core.engine.runtime.product_detector._get_git_root", return_value="/projects/trading"),
        patch("core.engine.runtime.product_detector.pool") as mock_pool,
    ):
        mock_conn = AsyncMock()
        mock_pool.init = AsyncMock()
        mock_pool.connection.return_value.__aenter__ = AsyncMock(return_value=mock_conn)
        mock_pool.connection.return_value.__aexit__ = AsyncMock(return_value=False)
        mock_conn.query = AsyncMock(return_value=[{"product": "product:trading_system"}])

        from core.engine.runtime.product_detector import detect_product_id

        result = await detect_product_id("product:platform")

    assert result == "product:trading_system"


@pytest.mark.asyncio
async def test_detect_returns_default_when_no_project_found():
    """Returns the default when no project matches the git root."""
    with (
        patch("core.engine.runtime.product_detector._get_git_root", return_value="/projects/unknown"),
        patch("core.engine.runtime.product_detector.pool") as mock_pool,
    ):
        mock_conn = AsyncMock()
        mock_pool.init = AsyncMock()
        mock_pool.connection.return_value.__aenter__ = AsyncMock(return_value=mock_conn)
        mock_pool.connection.return_value.__aexit__ = AsyncMock(return_value=False)
        mock_conn.query = AsyncMock(return_value=[])

        from core.engine.runtime.product_detector import detect_product_id

        result = await detect_product_id("product:platform")

    assert result == "product:platform"


@pytest.mark.asyncio
async def test_detect_returns_default_when_not_in_git_repo():
    """Returns the default when git rev-parse fails (not a git repo)."""
    with patch("core.engine.runtime.product_detector._get_git_root", return_value=None):
        from core.engine.runtime.product_detector import detect_product_id

        result = await detect_product_id("product:platform")

    assert result == "product:platform"


@pytest.mark.asyncio
async def test_detect_returns_default_on_db_error():
    """Returns the default when the DB query raises an exception."""
    with (
        patch("core.engine.runtime.product_detector._get_git_root", return_value="/projects/trading"),
        patch("core.engine.runtime.product_detector.pool") as mock_pool,
    ):
        mock_pool.init = AsyncMock()
        mock_pool.connection.side_effect = Exception("DB unavailable")

        from core.engine.runtime.product_detector import detect_product_id

        result = await detect_product_id("product:platform")

    assert result == "product:platform"
