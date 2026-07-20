# tests/test_conductor_grooming.py
"""Tests for backlog grooming."""

from unittest.mock import AsyncMock, MagicMock

import pytest

from core.engine.conductor.grooming import BacklogGroomer


def _make_pool(db):
    pool = MagicMock()
    cm = AsyncMock()
    cm.__aenter__ = AsyncMock(return_value=db)
    cm.__aexit__ = AsyncMock(return_value=None)
    pool.connection.return_value = cm
    return pool


@pytest.mark.asyncio
async def test_detect_stale_ideas_returns_old_ideas():
    stale = [{"id": "idea:1", "title": "Old idea", "status": "captured"}]
    db = AsyncMock()
    db.query = AsyncMock(return_value=stale)
    groomer = BacklogGroomer(_make_pool(db))
    result = await groomer.detect_stale_ideas("product:test")
    assert len(result) == 1


@pytest.mark.asyncio
async def test_detect_stale_ideas_empty():
    db = AsyncMock()
    db.query = AsyncMock(return_value=[])
    groomer = BacklogGroomer(_make_pool(db))
    result = await groomer.detect_stale_ideas("product:test")
    assert result == []


@pytest.mark.asyncio
async def test_heartbeat_counter_increments():
    db = AsyncMock()
    db.query = AsyncMock(return_value=[])
    groomer = BacklogGroomer(_make_pool(db))
    # Should not groom on first 5 heartbeats
    for _ in range(5):
        ran = await groomer.maybe_groom("product:test")
        assert ran is False
    # Should groom on 6th
    ran = await groomer.maybe_groom("product:test")
    assert ran is True
