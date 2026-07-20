from unittest.mock import AsyncMock, MagicMock, patch

import pytest


@pytest.mark.asyncio
async def test_ace_capture_sets_product_field():
    """ace_capture must write product = <record>$product — not leave it NONE."""
    captured_sql = []
    captured_params = {}

    async def fake_query(sql, params=None):
        captured_sql.append(sql)
        captured_params.update(params or {})
        mock_id = MagicMock()
        mock_id.__str__ = lambda self: "observation:test123"
        return [[{"id": mock_id}]]

    mock_db = AsyncMock()
    mock_db.query = fake_query

    class FakeConn:
        async def __aenter__(self):
            return mock_db

        async def __aexit__(self, *a):
            pass

    with patch("core.engine.mcp.tools.pool") as mock_pool:
        mock_pool.connection.return_value = FakeConn()
        from core.engine.mcp.tools import ace_capture

        await ace_capture(
            observation_type="pattern",
            content="test observation",
            domain_path="architecture",
            product_id="product:platform",
        )

    assert any("$product" in sql for sql in captured_sql), "SQL must reference $product"
    assert "product" in captured_params, "product must be in params"
