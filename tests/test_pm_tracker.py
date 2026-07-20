# tests/test_pm_tracker.py
"""Tests for initiative lifecycle and tracker."""

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
def tracker(mock_pool):
    from core.engine.pm.tracker import InitiativeTracker

    return InitiativeTracker(db_pool=mock_pool)


@pytest.mark.asyncio
async def test_create_initiative(tracker, mock_db):
    """Initiative created with correct status (planning), owner, cost defaults."""
    mock_db.query = AsyncMock(
        return_value=[
            [
                {
                    "id": "initiative:abc",
                    "title": "Multi-brand tokens",
                    "status": "planning",
                    "total_cost": 0.0,
                    "priority": "high",
                }
            ]
        ]
    )

    result = await tracker.create_initiative(
        title="Multi-brand tokens",
        description="Support multiple brand themes",
        product_id="product:test",
        workspace_id="workspace:test",
        user_id="user:edwin",
        priority="high",
        cost_budget=100.0,
    )

    assert result["status"] == "planning"
    assert result["title"] == "Multi-brand tokens"
    # Verify CREATE was called
    call_args = mock_db.query.call_args_list[0]
    assert "CREATE initiative" in call_args[0][0]


@pytest.mark.asyncio
async def test_activate_initiative(tracker, mock_db):
    """Status transitions from ready to active."""
    # First call: SELECT returns initiative in 'ready' state
    # Second call: UPDATE sets status to 'active'
    mock_db.query = AsyncMock(
        side_effect=[
            [{"id": "initiative:abc", "status": "ready", "title": "Test"}],
            [{"id": "initiative:abc", "status": "active", "title": "Test"}],
        ]
    )

    result = await tracker.activate_initiative(
        initiative_id="initiative:abc",
        product_id="product:test",
    )

    assert result["status"] == "active"


@pytest.mark.asyncio
async def test_pause_initiative(tracker, mock_db):
    """Active initiative can be paused."""
    mock_db.query = AsyncMock(
        return_value=[
            [
                {
                    "id": "initiative:abc",
                    "status": "active",
                }
            ]
        ]
    )

    result = await tracker.pause_initiative(
        initiative_id="initiative:abc",
        product_id="product:test",
    )

    assert result["status"] == "paused"


@pytest.mark.asyncio
async def test_cancel_initiative(tracker, mock_db):
    """Cancellation cleans up and sets status to cancelled."""
    mock_db.query = AsyncMock(
        return_value=[
            [
                {
                    "id": "initiative:abc",
                    "status": "active",
                }
            ]
        ]
    )

    result = await tracker.cancel_initiative(
        initiative_id="initiative:abc",
        product_id="product:test",
    )

    assert result["status"] == "cancelled"


@pytest.mark.asyncio
async def test_complete_initiative(tracker, mock_db):
    """Complete initiative when all milestones are done."""
    mock_db.query = AsyncMock(
        return_value=[
            [
                {
                    "id": "initiative:abc",
                    "status": "active",
                }
            ]
        ]
    )

    result = await tracker.complete_initiative(
        initiative_id="initiative:abc",
        product_id="product:test",
    )

    assert result["status"] == "completed"


@pytest.mark.asyncio
async def test_status_rollup():
    """Status roll-up from milestones to initiative."""
    from core.engine.pm.tracker import compute_status_rollup

    # All completed → completed
    milestones = [
        {"status": "completed"},
        {"status": "completed"},
        {"status": "completed"},
    ]
    assert compute_status_rollup(milestones) == "completed"

    # Any active → active
    milestones = [
        {"status": "completed"},
        {"status": "active"},
        {"status": "pending"},
    ]
    assert compute_status_rollup(milestones) == "active"

    # Any blocked → blocked
    milestones = [
        {"status": "completed"},
        {"status": "blocked"},
        {"status": "pending"},
    ]
    assert compute_status_rollup(milestones) == "blocked"

    # All pending → pending
    milestones = [
        {"status": "pending"},
        {"status": "pending"},
    ]
    assert compute_status_rollup(milestones) == "pending"

    # Review state
    milestones = [
        {"status": "completed"},
        {"status": "review"},
        {"status": "pending"},
    ]
    assert compute_status_rollup(milestones) == "review"


@pytest.mark.asyncio
async def test_cost_budget_enforcement():
    """Cost budget enforcement: warn at 80%, pause at 90%."""
    from core.engine.pm.tracker import check_cost_budget

    # Under 80% — ok
    result = check_cost_budget(total_cost=70.0, budget=100.0)
    assert result["status"] == "ok"

    # At 80% — warn
    result = check_cost_budget(total_cost=80.0, budget=100.0)
    assert result["status"] == "warn"

    # At 90% — pause
    result = check_cost_budget(total_cost=90.0, budget=100.0)
    assert result["status"] == "pause"

    # At 100% — require override
    result = check_cost_budget(total_cost=100.0, budget=100.0)
    assert result["status"] == "override_required"

    # No budget set — always ok
    result = check_cost_budget(total_cost=999.0, budget=None)
    assert result["status"] == "ok"


@pytest.mark.asyncio
async def test_quick_task_bypasses_initiative():
    """Simple/moderate tasks go through execute_task directly, no initiative."""
    from core.engine.pm.tracker import should_use_initiative

    assert should_use_initiative("simple") is False
    assert should_use_initiative("moderate") is False
    assert should_use_initiative("complex") is True


@pytest.mark.asyncio
async def test_progress_percentage():
    """Progress percentage based on completed milestones."""
    from core.engine.pm.tracker import compute_progress

    milestones = [
        {"status": "completed"},
        {"status": "active"},
        {"status": "pending"},
    ]
    assert compute_progress(milestones) == pytest.approx(33.33, abs=1)

    milestones = [
        {"status": "completed"},
        {"status": "completed"},
    ]
    assert compute_progress(milestones) == 100.0

    assert compute_progress([]) == 0.0
