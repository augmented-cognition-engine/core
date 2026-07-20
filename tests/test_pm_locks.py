# tests/test_pm_locks.py
"""Tests for FileLockManager — resource_lock table with explicit lifecycle."""

from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock, MagicMock

import pytest


@pytest.fixture
def mock_db():
    db = AsyncMock()
    db.query = AsyncMock(return_value=[])
    return db


@pytest.fixture
def mock_pool(mock_db):
    p = MagicMock()
    ctx = AsyncMock()
    ctx.__aenter__ = AsyncMock(return_value=mock_db)
    ctx.__aexit__ = AsyncMock(return_value=False)
    p.connection = MagicMock(return_value=ctx)
    return p


@pytest.fixture
def lock_manager(mock_pool):
    from core.engine.pm.locks import FileLockManager

    return FileLockManager(db_pool=mock_pool)


@pytest.mark.asyncio
async def test_file_lock_acquire_release(lock_manager, mock_db):
    """Lock acquired, work executes, lock released in finally block."""

    # SELECT returns empty (no existing lock), CREATE succeeds
    async def side_effect(query, params=None):
        if "SELECT" in query:
            return []
        if "CREATE" in query:
            return [{"id": "resource_lock:abc"}]
        return []

    mock_db.query = AsyncMock(side_effect=side_effect)

    acquired = await lock_manager.acquire(
        resource_type="file",
        resource_id="src/main.py",
        held_by="work_item:wi1",
        product_id="product:test",
        ttl_minutes=60,
    )
    assert acquired is True

    # Release
    mock_db.query = AsyncMock(return_value=[])
    await lock_manager.release(
        resource_type="file",
        resource_id="src/main.py",
        product_id="product:test",
    )
    # Verify UPDATE to released was called (not DELETE)
    call_args = mock_db.query.call_args
    assert "UPDATE" in call_args[0][0]
    assert "state = 'released'" in call_args[0][0]


@pytest.mark.asyncio
async def test_file_lock_contention(lock_manager, mock_db):
    """Second acquire returns False when lock held by another work item."""
    # SELECT finds existing non-expired lock held by another work item
    future_time = (datetime.now(timezone.utc) + timedelta(hours=1)).isoformat()

    async def side_effect(query, params=None):
        if "SELECT" in query:
            return [
                {
                    "id": "resource_lock:existing",
                    "expires_at": future_time,
                    "held_by": "work_item:other",
                }
            ]
        return []

    mock_db.query = AsyncMock(side_effect=side_effect)

    acquired = await lock_manager.acquire(
        resource_type="file",
        resource_id="src/main.py",
        held_by="work_item:wi2",
        product_id="product:test",
        ttl_minutes=60,
    )
    assert acquired is False


@pytest.mark.asyncio
async def test_file_lock_ttl_expiry(lock_manager, mock_db):
    """Expired lock can be stolen by a new acquire."""
    past_time = (datetime.now(timezone.utc) - timedelta(hours=1)).isoformat()
    create_count = 0

    async def side_effect(query, params=None):
        nonlocal create_count
        if "CREATE" in query:
            create_count += 1
            # CREATE after UPDATE (stolen) succeeds
            return [{"id": "resource_lock:new"}]
        if "SELECT" in query:
            return [
                {
                    "id": "resource_lock:expired",
                    "expires_at": past_time,
                    "held_by": "work_item:old",
                }
            ]
        if "UPDATE" in query:
            return []
        return []

    mock_db.query = AsyncMock(side_effect=side_effect)

    acquired = await lock_manager.acquire(
        resource_type="file",
        resource_id="src/main.py",
        held_by="work_item:wi3",
        product_id="product:test",
        ttl_minutes=60,
    )
    assert acquired is True


@pytest.mark.asyncio
async def test_file_lock_acquire_multiple_files(lock_manager, mock_db):
    """Can acquire locks on multiple different files."""

    async def side_effect(query, params=None):
        if "SELECT" in query:
            return []  # No existing locks
        if "CREATE" in query:
            return [{"id": "resource_lock:abc"}]
        return []

    mock_db.query = AsyncMock(side_effect=side_effect)

    files = ["src/a.py", "src/b.py", "src/c.py"]
    results = await lock_manager.acquire_many(
        resource_type="file",
        resource_ids=files,
        held_by="work_item:wi1",
        product_id="product:test",
        ttl_minutes=60,
    )
    assert all(results)
    assert len(results) == 3


@pytest.mark.asyncio
async def test_file_lock_release_all(lock_manager, mock_db):
    """Release all locks held by a specific work item."""
    mock_db.query = AsyncMock(return_value=[])

    await lock_manager.release_all(
        held_by="work_item:wi1",
        product_id="product:test",
    )
    call_args = mock_db.query.call_args
    assert "UPDATE" in call_args[0][0]
    assert "state = 'released'" in call_args[0][0]
    assert "held_by" in call_args[0][0]
