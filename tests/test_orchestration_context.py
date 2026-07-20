import asyncio
from unittest.mock import MagicMock

import pytest

from core.engine.orchestration.context import get_active_bus, reset_active_bus, set_active_bus


def test_default_is_none():
    assert get_active_bus() is None


def test_set_and_get():
    bus = MagicMock()
    token = set_active_bus(bus)
    assert get_active_bus() is bus
    reset_active_bus(token)
    assert get_active_bus() is None


def test_reset_restores_previous():
    bus1 = MagicMock()
    bus2 = MagicMock()
    token1 = set_active_bus(bus1)
    token2 = set_active_bus(bus2)
    assert get_active_bus() is bus2
    reset_active_bus(token2)
    assert get_active_bus() is bus1
    reset_active_bus(token1)
    assert get_active_bus() is None


@pytest.mark.asyncio
async def test_isolation_across_tasks():
    """ContextVar values are task-local: sibling tasks don't see each other's bus."""
    bus = MagicMock()
    results = {}

    async def setter():
        token = set_active_bus(bus)
        await asyncio.sleep(0)
        results["setter"] = get_active_bus()
        reset_active_bus(token)

    async def reader():
        await asyncio.sleep(0)
        results["reader"] = get_active_bus()

    await asyncio.gather(setter(), reader())
    assert results["setter"] is bus
    assert results["reader"] is None
