# tests/test_flow_config.py
from unittest.mock import AsyncMock, patch

import pytest


def test_defaults_when_no_config():
    from core.engine.flow.config import FlowDefaults

    defaults = FlowDefaults()
    assert defaults.default_clearance == "open"
    assert defaults.insight_propagation is True
    assert defaults.consume_org_intelligence is True
    assert defaults.contribute_org_intelligence is True


@pytest.mark.asyncio
async def test_get_flow_config_returns_defaults_when_missing():
    from core.engine.flow.config import get_flow_config

    with patch("core.engine.flow.config.pool") as mock_pool:
        mock_conn = AsyncMock()
        mock_conn.query = AsyncMock(return_value=[[]])
        mock_pool.connection.return_value.__aenter__ = AsyncMock(return_value=mock_conn)
        mock_pool.connection.return_value.__aexit__ = AsyncMock(return_value=False)

        config = await get_flow_config("domain:legal", "product:test")

    assert config.default_clearance == "open"
    assert config.contribute_org_intelligence is True


@pytest.mark.asyncio
async def test_get_flow_config_returns_db_values():
    from core.engine.flow.config import get_flow_config

    db_record = {
        "default_clearance": "domain",
        "insight_propagation": True,
        "consume_org_intelligence": True,
        "contribute_org_intelligence": False,
    }

    with patch("core.engine.flow.config.pool") as mock_pool:
        mock_conn = AsyncMock()
        mock_conn.query = AsyncMock(return_value=[[db_record]])
        mock_pool.connection.return_value.__aenter__ = AsyncMock(return_value=mock_conn)
        mock_pool.connection.return_value.__aexit__ = AsyncMock(return_value=False)

        config = await get_flow_config("domain:legal", "product:test")

    assert config.default_clearance == "domain"
    assert config.contribute_org_intelligence is False
