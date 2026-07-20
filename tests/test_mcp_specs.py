# tests/test_mcp_specs.py
"""Tests for MCP agentic PM tools — ace_create_spec, ace_submit_feedback, ace_verify_spec."""

from unittest.mock import AsyncMock, patch

import pytest

# ---------------------------------------------------------------------------
# ace_create_spec
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_ace_create_spec_human_request():
    """ace_create_spec() generates and returns a spec from a human description."""
    from core.engine.mcp.tools import ace_create_spec

    mock_spec = {
        "id": "agent_spec:spec123",
        "objective": "Add rate limiting to the API",
        "source": "human",
        "status": "draft",
        "acceptance_criteria": [
            {"criterion": "API returns 429 after limit exceeded", "verification": "unit test", "automated": True}
        ],
        "constraints": ["Do not break existing endpoints"],
        "estimated_files": ["core/engine/api/middleware.py"],
        "test_requirements": ["test_rate_limit_exceeded"],
    }

    mock_gen = AsyncMock()
    mock_gen.from_request_with_team = AsyncMock(return_value=mock_spec)

    with patch("core.engine.mcp.tools.pool"):
        with patch("core.engine.product.spec_generator.SpecGenerator", return_value=mock_gen):
            result = await ace_create_spec(
                description="Add rate limiting to the API",
                source="human",
                product_id="product:default",
            )

    assert result["objective"] == "Add rate limiting to the API"
    assert result["status"] == "draft"
    assert "acceptance_criteria" in result
    mock_gen.from_request_with_team.assert_called_once_with("Add rate limiting to the API", "product:default")


@pytest.mark.asyncio
async def test_ace_create_spec_from_gap():
    """ace_create_spec() with source='gap' delegates to gen.from_gap()."""
    from core.engine.mcp.tools import ace_create_spec

    mock_spec = {
        "id": "agent_spec:gap_spec",
        "objective": "Add test coverage for auth module",
        "source": "gap",
        "status": "draft",
        "acceptance_criteria": [
            {"criterion": "Auth module has >80% test coverage", "verification": "pytest --cov", "automated": True}
        ],
    }

    mock_gen = AsyncMock()
    mock_gen.from_gap = AsyncMock(return_value=mock_spec)

    with patch("core.engine.mcp.tools.pool"):
        with patch("core.engine.product.spec_generator.SpecGenerator", return_value=mock_gen):
            result = await ace_create_spec(
                description="Missing test coverage",
                source="gap",
                capability_slug="auth",
                product_id="product:default",
            )

    assert result["objective"] == "Add test coverage for auth module"
    assert result["status"] == "draft"
    mock_gen.from_gap.assert_called_once()
    call_kwargs = mock_gen.from_gap.call_args
    gap_arg = call_kwargs[0][0]
    assert gap_arg["gaps"] == ["Missing test coverage"]
    assert call_kwargs[0][1] == "auth"


@pytest.mark.asyncio
async def test_ace_create_spec_handles_error_gracefully():
    """ace_create_spec() returns error dict when SpecGenerator raises."""
    from core.engine.mcp.tools import ace_create_spec

    mock_gen = AsyncMock()
    mock_gen.from_request_with_team = AsyncMock(side_effect=RuntimeError("LLM unavailable"))

    with patch("core.engine.mcp.tools.pool"):
        with patch("core.engine.product.spec_generator.SpecGenerator", return_value=mock_gen):
            result = await ace_create_spec(
                description="Build something",
                source="human",
                product_id="product:default",
            )

    assert "error" in result
    assert "LLM unavailable" in result["error"]


# ---------------------------------------------------------------------------
# ace_submit_feedback
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_ace_submit_feedback_blocker():
    """ace_submit_feedback() handles blocker feedback and returns action."""
    from core.engine.mcp.tools import ace_submit_feedback

    mock_result = {
        "feedback_id": "agent_feedback:fb001",
        "feedback_type": "blocker",
        "action": {"action": "blocker_flagged", "escalated": True},
    }

    mock_handler = AsyncMock()
    mock_handler.handle = AsyncMock(return_value=mock_result)

    with patch("core.engine.mcp.tools.pool"):
        with patch("core.engine.product.feedback_handler.FeedbackHandler", return_value=mock_handler):
            result = await ace_submit_feedback(
                spec_id="agent_spec:spec123",
                feedback_type="blocker",
                content="Cannot find the rate limit middleware entry point",
                product_id="product:default",
            )

    assert result["feedback_type"] == "blocker"
    assert result["action"]["escalated"] is True
    mock_handler.handle.assert_called_once()


@pytest.mark.asyncio
async def test_ace_submit_feedback_progress():
    """ace_submit_feedback() handles progress feedback and returns action."""
    from core.engine.mcp.tools import ace_submit_feedback

    mock_result = {
        "feedback_id": "agent_feedback:fb002",
        "feedback_type": "progress",
        "action": {"action": "progress_noted"},
    }

    mock_handler = AsyncMock()
    mock_handler.handle = AsyncMock(return_value=mock_result)

    with patch("core.engine.mcp.tools.pool"):
        with patch("core.engine.product.feedback_handler.FeedbackHandler", return_value=mock_handler):
            result = await ace_submit_feedback(
                spec_id="agent_spec:spec123",
                feedback_type="progress",
                content="Middleware skeleton created, writing tests next",
                product_id="product:default",
            )

    assert result["feedback_id"] == "agent_feedback:fb002"
    assert result["action"]["action"] == "progress_noted"


@pytest.mark.asyncio
async def test_ace_submit_feedback_handles_error_gracefully():
    """ace_submit_feedback() returns error dict when FeedbackHandler raises."""
    from core.engine.mcp.tools import ace_submit_feedback

    mock_handler = AsyncMock()
    mock_handler.handle = AsyncMock(side_effect=RuntimeError("DB connection failed"))

    with patch("core.engine.mcp.tools.pool"):
        with patch("core.engine.product.feedback_handler.FeedbackHandler", return_value=mock_handler):
            result = await ace_submit_feedback(
                spec_id="agent_spec:spec123",
                feedback_type="progress",
                content="Some update",
                product_id="product:default",
            )

    assert "error" in result
    assert "DB connection failed" in result["error"]


# ---------------------------------------------------------------------------
# ace_verify_spec
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_ace_verify_spec_fully_met():
    """ace_verify_spec() returns verification result with overall status."""
    from core.engine.mcp.tools import ace_verify_spec

    mock_verification = {
        "spec_id": "agent_spec:spec123",
        "overall": "fully_met",
        "criteria_results": [
            {"criterion": "API returns 429 after limit exceeded", "status": "met", "evidence": "Test passes"}
        ],
        "quality_delta": None,
        "follow_up_needed": False,
        "met": 1,
        "total": 1,
    }

    mock_verifier = AsyncMock()
    mock_verifier.verify = AsyncMock(return_value=mock_verification)

    with patch("core.engine.mcp.tools.pool"):
        with patch("core.engine.product.acceptance.AcceptanceVerifier", return_value=mock_verifier):
            result = await ace_verify_spec(
                spec_id="agent_spec:spec123",
                product_id="product:default",
            )

    assert result["overall"] == "fully_met"
    assert result["follow_up_needed"] is False
    assert result["met"] == 1
    assert result["total"] == 1
    mock_verifier.verify.assert_called_once_with("agent_spec:spec123", "product:default")


@pytest.mark.asyncio
async def test_ace_verify_spec_partially_met():
    """ace_verify_spec() returns unmet_criteria when partially met."""
    from core.engine.mcp.tools import ace_verify_spec

    mock_verification = {
        "spec_id": "agent_spec:spec456",
        "overall": "partially_met",
        "criteria_results": [
            {"criterion": "Returns 429 on exceeded", "status": "met", "evidence": "Passes"},
            {"criterion": "Headers include Retry-After", "status": "not_met", "evidence": "Header missing"},
        ],
        "unmet_criteria": [
            {"criterion": "Headers include Retry-After", "status": "not_met", "evidence": "Header missing"}
        ],
        "quality_delta": None,
        "follow_up_needed": True,
        "met": 1,
        "total": 2,
    }

    mock_verifier = AsyncMock()
    mock_verifier.verify = AsyncMock(return_value=mock_verification)

    with patch("core.engine.mcp.tools.pool"):
        with patch("core.engine.product.acceptance.AcceptanceVerifier", return_value=mock_verifier):
            result = await ace_verify_spec(
                spec_id="agent_spec:spec456",
                product_id="product:default",
            )

    assert result["overall"] == "partially_met"
    assert result["follow_up_needed"] is True
    assert len(result["unmet_criteria"]) == 1


@pytest.mark.asyncio
async def test_ace_verify_spec_handles_error_gracefully():
    """ace_verify_spec() returns error dict when AcceptanceVerifier raises."""
    from core.engine.mcp.tools import ace_verify_spec

    mock_verifier = AsyncMock()
    mock_verifier.verify = AsyncMock(side_effect=RuntimeError("Spec not found in DB"))

    with patch("core.engine.mcp.tools.pool"):
        with patch("core.engine.product.acceptance.AcceptanceVerifier", return_value=mock_verifier):
            result = await ace_verify_spec(
                spec_id="agent_spec:missing",
                product_id="product:default",
            )

    assert "error" in result
    assert "Spec not found in DB" in result["error"]
