# tests/test_runtime_product_id.py
"""Tests that Runtime stores product_id and close() uses it."""

from unittest.mock import AsyncMock, patch

import pytest


@pytest.mark.asyncio
async def test_runtime_stores_product_id():
    """Runtime exposes product_id as an attribute."""
    from core.engine.runtime.runtime import Runtime

    rt = Runtime(product_id="product:trading_system")
    assert rt.product_id == "product:trading_system"


@pytest.mark.asyncio
async def test_runtime_close_uses_stored_product_id():
    """close() flushes session memory to the product_id set at construction."""
    from core.engine.runtime.runtime import Runtime

    rt = Runtime(product_id="product:trading_system", enable_intelligence=True)
    with patch.object(rt._session_memory, "promote_to_graph", new_callable=AsyncMock) as mock_promote:
        mock_promote.return_value = 0
        await rt.close()
        mock_promote.assert_called_once_with("product:trading_system")


@pytest.mark.asyncio
async def test_runtime_close_default_fallback():
    """close() falls back to 'product:platform' when no product_id was given."""
    from core.engine.runtime.runtime import Runtime

    rt = Runtime(enable_intelligence=True)  # default product_id
    with patch.object(rt._session_memory, "promote_to_graph", new_callable=AsyncMock) as mock_promote:
        mock_promote.return_value = 0
        await rt.close()
        mock_promote.assert_called_once_with("product:platform")
