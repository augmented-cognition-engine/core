from unittest.mock import AsyncMock, patch

import pytest

from core.engine.orchestrator.engagement_models import EngagementResult
from core.engine.orchestrator.verification_gate import VerificationGate, VerificationResult


@pytest.mark.asyncio
async def test_verification_gate_returns_clean_result():
    clean = VerificationResult(verified=True, gaps=[], verdict="clean")
    with patch(
        "core.engine.orchestrator.verification_gate.get_llm",
    ) as mock_llm:
        mock_llm.return_value.complete_structured = AsyncMock(return_value=clean)
        gate = VerificationGate()
        result = await gate.verify("Add rate limiting", "Here is the implementation...")
    assert result.verified is True
    assert result.verdict == "clean"
    assert result.gaps == []


@pytest.mark.asyncio
async def test_verification_gate_returns_gaps():
    gaps_result = VerificationResult(
        verified=False,
        gaps=["Missing Retry-After header", "No test for multi-worker failure"],
        verdict="gaps_found",
    )
    with patch(
        "core.engine.orchestrator.verification_gate.get_llm",
    ) as mock_llm:
        mock_llm.return_value.complete_structured = AsyncMock(return_value=gaps_result)
        gate = VerificationGate()
        result = await gate.verify("Add rate limiting", "Partial implementation...")
    assert result.verified is False
    assert len(result.gaps) == 2
    assert result.verdict == "gaps_found"


@pytest.mark.asyncio
async def test_verification_gate_fails_gracefully_on_llm_error():
    with patch(
        "core.engine.orchestrator.verification_gate.get_llm",
    ) as mock_llm:
        mock_llm.return_value.complete_structured = AsyncMock(side_effect=Exception("LLM down"))
        gate = VerificationGate()
        result = await gate.verify("task", "output")
    # Must not raise — returns a safe default
    assert result.verified is False  # unconfirmed, not confirmed-clean
    assert result.verdict == "skipped"


def test_engagement_result_has_verification_fields():
    """EngagementResult schema includes verification fields."""
    result = EngagementResult(
        spins=[],
        merged_output="output",
        perspectives_used=["executor"],
        verified=False,
        verification_gaps=["missing edge case"],
        verification_verdict="gaps_found",
    )
    assert result.verified is False
    assert "missing edge case" in result.verification_gaps
    assert result.verification_verdict == "gaps_found"


@pytest.mark.asyncio
async def test_execute_engagement_populates_verification_fields():
    """execute_engagement() must populate verification fields on EngagementResult."""
    from core.engine.orchestrator.engagement import execute_engagement
    from core.engine.orchestrator.engagement_models import SpinOutput

    mock_spin = SpinOutput(
        content="Implementation result",
        handoff="Summary",
        confidence=0.9,
        open_questions=[],
        perspective="executor",
        specialties_used=[],
    )

    clean_result = VerificationResult(verified=True, gaps=[], verdict="clean")

    with (
        patch(
            "core.engine.orchestrator.engagement._execute_single_spin",
            new=AsyncMock(return_value=mock_spin),
        ),
        patch(
            "core.engine.orchestrator.executor._load_snapshot",
            new=AsyncMock(return_value={"insights": [], "specialties_loaded": []}),
        ),
        patch(
            "core.engine.orchestrator.verification_gate.VerificationGate.verify",
            new=AsyncMock(return_value=clean_result),
        ),
    ):
        result = await execute_engagement(
            task_description="Add rate limiting",
            classification={
                "discipline": "architecture",
                "archetype": "executor",
                "mode": "reactive",
                "complexity": "moderate",
                "perspective": "executor",
                "specialties": [],
                "org_context": [],
                "engagement": {
                    "perspectives": ["executor"],
                    "adversarial_pair": None,
                    "rationale": "Single spin",
                },
            },
            product_id="product:test",
        )

    assert isinstance(result, EngagementResult)
    assert hasattr(result, "verified")
    assert hasattr(result, "verification_gaps")
    assert hasattr(result, "verification_verdict")
    assert result.verified is True
    assert result.verification_verdict == "clean"
    assert result.verification_gaps == []
