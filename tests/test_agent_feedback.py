# tests/test_agent_feedback.py
"""Tests for FeedbackHandler — 6-type agent feedback with auto-response logic."""

from unittest.mock import AsyncMock, MagicMock

import pytest

from core.engine.product.spec_models import AgentFeedbackCreate


@pytest.fixture
def mock_db():
    db = AsyncMock()
    db.query = AsyncMock(return_value=[{"id": "agent_feedback:abc123", "feedback_type": "blocker"}])
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
def handler(mock_pool):
    from core.engine.product.feedback_handler import FeedbackHandler

    return FeedbackHandler(db_pool=mock_pool)


# ── test 1 ─────────────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_handle_blocker_creates_question(handler, mock_db):
    """Blocker feedback → product_question created with priority='critical'."""
    feedback = AgentFeedbackCreate(
        spec_id="spec:s1",
        feedback_type="blocker",
        content="Cannot resolve import cycle between modules A and B",
    )

    result = await handler.handle(feedback, product_id="product:test")

    assert result["feedback_type"] == "blocker"
    assert result["action"]["action"] == "blocker_flagged"
    assert result["action"]["escalated"] is True

    # Check that a product_question was created with priority='critical'
    all_queries = [str(c[0][0]) for c in mock_db.query.call_args_list]
    question_queries = [q for q in all_queries if "product_question" in q]
    assert question_queries, "Expected at least one product_question CREATE query"

    # Verify the critical priority param was passed
    critical_calls = [
        c
        for c in mock_db.query.call_args_list
        if "product_question" in str(c[0][0]) and c[0][1].get("priority") == "critical"
    ]
    assert critical_calls, "product_question should be created with priority='critical'"


# ── test 2 ─────────────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_handle_discovery_captures_observation(handler, mock_db):
    """Discovery feedback → observation record created in DB."""
    feedback = AgentFeedbackCreate(
        spec_id="spec:s1",
        feedback_type="discovery",
        content="The auth module already implements JWT refresh — no need to add it in this spec",
    )

    result = await handler.handle(feedback, product_id="product:test")

    assert result["feedback_type"] == "discovery"
    assert result["action"]["action"] == "discovery_captured"
    assert result["action"]["fed_to_intelligence"] is True

    # Check that an observation was created
    observation_calls = [c for c in mock_db.query.call_args_list if "observation" in str(c[0][0]).lower()]
    assert observation_calls, "Expected an observation CREATE query"

    # Verify the discovery content was passed
    obs_call = observation_calls[0]
    params = obs_call[0][1]
    assert feedback.content in params.get("content", "")


# ── test 3 ─────────────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_handle_completion_updates_spec_status(handler, mock_db):
    """Completion feedback → spec status updated to 'verifying'."""
    feedback = AgentFeedbackCreate(
        spec_id="spec:s2",
        feedback_type="completion",
        content="All acceptance criteria implemented and tests passing",
    )

    result = await handler.handle(feedback, product_id="product:test")

    assert result["feedback_type"] == "completion"
    assert result["action"]["action"] == "completion_received"
    assert result["action"]["verification_queued"] is True

    # Check that spec status was updated to 'verifying'
    update_calls = [c for c in mock_db.query.call_args_list if "UPDATE" in str(c[0][0]) and "verifying" in str(c[0][0])]
    assert update_calls, "Expected UPDATE query setting status to 'verifying'"

    # Verify the spec_id was passed as parameter
    update_call = update_calls[0]
    params = update_call[0][1]
    assert params.get("spec_id") == "spec:s2"


# ── test 4 ─────────────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_handle_progress_no_side_effects(handler, mock_db):
    """Progress feedback → returns action, no extra DB writes beyond the feedback record."""
    feedback = AgentFeedbackCreate(
        spec_id="spec:s3",
        feedback_type="progress",
        content="Completed 3 of 7 acceptance criteria",
    )

    result = await handler.handle(feedback, product_id="product:test")

    assert result["feedback_type"] == "progress"
    assert result["action"]["action"] == "progress_noted"

    # Only one DB query should have been made: the initial CREATE agent_feedback
    # (no extra side-effect writes for progress)
    assert mock_db.query.call_count == 1, (
        f"Progress should only write the feedback record, got {mock_db.query.call_count} queries"
    )
    persist_query = mock_db.query.call_args_list[0][0][0]
    assert "agent_feedback" in persist_query


# ── test 5 ─────────────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_feedback_persisted(handler, mock_db):
    """Any feedback type → agent_feedback record is always created in DB."""
    for fb_type in ("blocker", "discovery", "trade_off", "scope_question", "completion", "progress"):
        mock_db.query.reset_mock()
        # Return a feedback record on the first call so fb_id is populated
        mock_db.query = AsyncMock(return_value=[{"id": f"agent_feedback:{fb_type}_1", "feedback_type": fb_type}])

        feedback = AgentFeedbackCreate(
            spec_id="spec:sx",
            feedback_type=fb_type,
            content=f"Test content for {fb_type}",
        )

        result = await handler.handle(feedback, product_id="product:test")

        # feedback_id should be populated from the persisted record
        assert result["feedback_id"] is not None, f"feedback_id missing for type={fb_type}"

        # The very first query must create the agent_feedback record
        first_query = mock_db.query.call_args_list[0][0][0]
        assert "agent_feedback" in first_query, f"First query should CREATE agent_feedback, got: {first_query!r}"
