# tests/test_pm_approvals.py
"""Tests for milestone approval gates and human handoff workflows."""

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
def approvals(mock_pool):
    from core.engine.pm.approvals import ApprovalManager

    return ApprovalManager(db_pool=mock_pool)


@pytest.mark.asyncio
async def test_milestone_approval_gate(approvals, mock_db):
    """Milestone with requires_approval pauses and records pending approval."""
    milestone = {
        "id": "milestone:ms1",
        "requires_approval": True,
        "approver": "user:edwin",
        "title": "M1: Design Complete",
        "initiative": "initiative:init1",
        "product": "product:test",
    }

    mock_db.query = AsyncMock(return_value=[[milestone]])

    result = await approvals.request_approval(
        milestone_id="milestone:ms1",
        product_id="product:test",
    )

    assert result["status"] == "awaiting_approval"
    assert result["approver"] == "user:edwin"


@pytest.mark.asyncio
async def test_milestone_approve(approvals, mock_db):
    """Approve a milestone — status transitions to approved."""
    mock_db.query = AsyncMock(
        return_value=[
            [
                {
                    "id": "milestone:ms1",
                    "status": "review",
                    "requires_approval": True,
                }
            ]
        ]
    )

    result = await approvals.approve_milestone(
        milestone_id="milestone:ms1",
        approver_id="user:edwin",
        product_id="product:test",
    )

    assert result["action"] == "approved"


@pytest.mark.asyncio
async def test_milestone_reject_with_feedback(approvals, mock_db):
    """Rejected milestone returns with feedback."""
    mock_db.query = AsyncMock(
        return_value=[
            [
                {
                    "id": "milestone:ms1",
                    "status": "review",
                    "requires_approval": True,
                }
            ]
        ]
    )

    result = await approvals.reject_milestone(
        milestone_id="milestone:ms1",
        rejector_id="user:edwin",
        feedback="Missing accessibility tests for the brand switching component",
        product_id="product:test",
    )

    assert result["action"] == "rejected"
    assert result["feedback"] == "Missing accessibility tests for the brand switching component"


@pytest.mark.asyncio
async def test_escalation_timer():
    """Escalation timers: remind 24h, escalate 72h."""
    from core.engine.pm.approvals import check_escalation

    now = datetime.now(timezone.utc)

    # Just created — no escalation
    result = check_escalation(now, now)
    assert result is None

    # After 24h — reminder
    result = check_escalation(now - timedelta(hours=25), now)
    assert result == "remind"

    # After 72h — escalate
    result = check_escalation(now - timedelta(hours=73), now)
    assert result == "escalate"


@pytest.mark.asyncio
async def test_handoff_context_package(approvals, mock_db):
    """Handoff builds context package with prior outputs and intelligence."""
    mock_db.query = AsyncMock(
        return_value=[
            [
                {
                    "id": "work_item:wi1",
                    "title": "Manual review needed",
                    "description": "Review brand guidelines alignment",
                    "requires_human": True,
                    "domain_path": "ux",
                    "initiative": "initiative:init1",
                    "milestone": "milestone:ms1",
                }
            ]
        ]
    )

    result = await approvals.create_handoff(
        work_item_id="work_item:wi1",
        assigned_to="user:reviewer",
        product_id="product:test",
    )

    assert result["type"] == "handoff"
    assert result["assigned_to"] == "user:reviewer"
    assert "work_item" in result["context"]


@pytest.mark.asyncio
async def test_blocker_escalation(approvals, mock_db):
    """Blocker runtime_events trigger human escalation."""
    mock_db.query = AsyncMock(return_value=[])

    result = await approvals.escalate_blocker(
        work_item_id="work_item:wi1",
        reason="LLM confidence too low for automated resolution",
        product_id="product:test",
    )

    assert result["type"] == "blocker_escalation"
    assert "confidence" in result["reason"].lower()
