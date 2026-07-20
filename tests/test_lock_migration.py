# tests/test_lock_migration.py
"""Tests for resource_lock explicit lifecycle — state field replaces TTL-only expiry."""

from unittest.mock import AsyncMock, MagicMock, patch

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
def lock_mgr(mock_pool):
    from core.engine.pm.locks import FileLockManager

    return FileLockManager(db_pool=mock_pool)


# ---------------------------------------------------------------------------
# acquire — CREATE includes state='held' and acquired_at
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_acquire_creates_with_state_held(lock_mgr, mock_db):
    """acquire() CREATE query must include state='held' and acquired_at."""
    created_row = {"id": "resource_lock:t1", "state": "held", "held_by": "task:1"}
    # Calls: SELECT active (empty), DELETE inactive, CREATE (success)
    mock_db.query = AsyncMock(side_effect=[[], [], [created_row]])

    with patch("core.engine.events.bus.bus") as mock_bus:
        mock_bus.emit = AsyncMock()
        result = await lock_mgr.acquire("file", "src/main.py", "task:1", "product:test")

    assert result is True
    # Third call (index 2) is the CREATE
    create_call = mock_db.query.call_args_list[2]
    query_str = create_call[0][0]
    assert "state = 'held'" in query_str
    assert "acquired_at = time::now()" in query_str


@pytest.mark.asyncio
async def test_acquire_emits_state_changed_event(lock_mgr, mock_db):
    """acquire() emits lock.state_changed event on success."""
    created_row = {"id": "resource_lock:t1", "state": "held", "held_by": "task:1"}
    mock_db.query = AsyncMock(side_effect=[[], [], [created_row]])

    with patch("core.engine.events.bus.bus") as mock_bus:
        mock_bus.emit = AsyncMock()
        await lock_mgr.acquire("file", "src/main.py", "task:1", "product:test")

        mock_bus.emit.assert_called_once()
        event_type = mock_bus.emit.call_args[0][0]
        payload = mock_bus.emit.call_args[0][1]
        assert event_type == "lock.state_changed"
        assert payload["state"] == "held"
        assert payload["resource_id"] == "src/main.py"
        assert payload["held_by"] == "task:1"


# ---------------------------------------------------------------------------
# release — UPDATE with state='released' instead of DELETE
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_release_updates_state_instead_of_delete(lock_mgr, mock_db):
    """release() must UPDATE with state='released', not DELETE."""
    with patch("core.engine.events.bus.bus") as mock_bus:
        mock_bus.emit = AsyncMock()
        await lock_mgr.release("file", "src/main.py", "product:test")

    query_str = mock_db.query.call_args[0][0]
    assert "UPDATE" in query_str
    assert "state = 'released'" in query_str
    assert "released_at = time::now()" in query_str
    assert "DELETE" not in query_str


@pytest.mark.asyncio
async def test_release_emits_state_changed_event(lock_mgr, mock_db):
    """release() emits lock.state_changed event."""
    with patch("core.engine.events.bus.bus") as mock_bus:
        mock_bus.emit = AsyncMock()
        await lock_mgr.release("file", "src/main.py", "product:test")

        mock_bus.emit.assert_called_once()
        event_type = mock_bus.emit.call_args[0][0]
        payload = mock_bus.emit.call_args[0][1]
        assert event_type == "lock.state_changed"
        assert payload["state"] == "released"


# ---------------------------------------------------------------------------
# release_all — UPDATE instead of DELETE
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_release_all_updates_state(lock_mgr, mock_db):
    """release_all() must UPDATE to released, not DELETE."""
    with patch("core.engine.events.bus.bus") as mock_bus:
        mock_bus.emit = AsyncMock()
        await lock_mgr.release_all("task:1", "product:test")

    query_str = mock_db.query.call_args[0][0]
    assert "UPDATE" in query_str
    assert "state = 'released'" in query_str
    assert "DELETE" not in query_str


# ---------------------------------------------------------------------------
# is_locked — checks state field
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_is_locked_checks_state_field(lock_mgr, mock_db):
    """is_locked() must check state is in active states."""
    from datetime import datetime, timedelta, timezone

    future = (datetime.now(timezone.utc) + timedelta(hours=1)).isoformat()
    mock_db.query = AsyncMock(return_value=[{"id": "resource_lock:1", "expires_at": future, "state": "released"}])

    with patch(
        "core.engine.core.db.parse_rows",
        return_value=[{"id": "resource_lock:1", "expires_at": future, "state": "released"}],
    ):
        result = await lock_mgr.is_locked("file", "src/main.py", "product:test")

    # Even though expiry is in the future, state=released means not locked
    assert result is False


@pytest.mark.asyncio
async def test_is_locked_true_when_held(lock_mgr, mock_db):
    """is_locked() returns True when state='held' and not expired."""
    from datetime import datetime, timedelta, timezone

    future = (datetime.now(timezone.utc) + timedelta(hours=1)).isoformat()
    row = {"id": "resource_lock:1", "expires_at": future, "state": "held"}
    mock_db.query = AsyncMock(return_value=[row])

    with patch("core.engine.core.db.parse_rows", return_value=[row]):
        result = await lock_mgr.is_locked("file", "src/main.py", "product:test")

    assert result is True


# ---------------------------------------------------------------------------
# _try_steal_expired — marks old lock as stolen
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_steal_expired_marks_old_lock_stolen(lock_mgr, mock_db):
    """Stealing an expired lock UPDATEs old record to state='stolen'."""
    from datetime import datetime, timedelta, timezone

    past = (datetime.now(timezone.utc) - timedelta(hours=1)).isoformat()
    existing_lock = {
        "id": "resource_lock:abc",
        "expires_at": past,
        "held_by": "task:old",
        "state": "held",
    }

    # First call: SELECT returns existing expired lock
    # Second call: UPDATE old lock to stolen
    # Third call: CREATE new lock
    mock_db.query = AsyncMock(
        side_effect=[
            [existing_lock],  # SELECT
            [],  # UPDATE (stolen)
            [],  # CREATE new
        ]
    )

    with patch("core.engine.core.db.parse_rows", return_value=[existing_lock]):
        with patch("core.engine.events.bus.bus") as mock_bus:
            mock_bus.emit = AsyncMock()
            result = await lock_mgr._try_steal_expired(mock_db, "file", "src/main.py", "task:new", "product:test", 60)

    assert result is True
    # Second call should be the UPDATE to stolen
    update_call = mock_db.query.call_args_list[1]
    update_query = update_call[0][0]
    assert "UPDATE" in update_query
    assert "state = 'stolen'" in update_query
    assert "stolen_by" in update_query
