# tests/test_evaluator_honesty.py
"""Tests for Verification V2 — evaluator honesty.

Tests:
1. Pre-commitment protocol: returns preliminary verdict without evidence
2. Honesty enforcer: test failures block "met", code failures flag but allow
3. Sentinel engine: detects flips and overrides from judgment history
"""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from core.engine.verification.models import BehavioralEvidence

# ---------------------------------------------------------------------------
# Pre-commitment protocol
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_pre_commitment_returns_preliminary():
    """Pre-commitment protocol returns a structured preliminary verdict."""
    mock_llm = MagicMock()
    mock_llm.complete_json = AsyncMock(
        return_value={
            "preliminary": "likely_not_met",
            "evidence_needed": "Need to see test results",
        }
    )

    from core.engine.verification.honesty import PreCommitmentProtocol

    protocol = PreCommitmentProtocol(mock_llm)
    result = await protocol.pre_commit("Tests pass", "Add rate limiting")

    assert result.preliminary == "likely_not_met"
    assert result.evidence_needed == "Need to see test results"
    mock_llm.complete_json.assert_called_once()


@pytest.mark.asyncio
async def test_pre_commitment_defaults_on_invalid():
    """Pre-commitment defaults to 'uncertain' on invalid LLM response."""
    mock_llm = MagicMock()
    mock_llm.complete_json = AsyncMock(return_value={"preliminary": "invalid_value"})

    from core.engine.verification.honesty import PreCommitmentProtocol

    protocol = PreCommitmentProtocol(mock_llm)
    result = await protocol.pre_commit("Tests pass", "Add rate limiting")

    assert result.preliminary == "uncertain"


@pytest.mark.asyncio
async def test_pre_commitment_handles_error():
    """Pre-commitment returns uncertain on LLM failure."""
    mock_llm = MagicMock()
    mock_llm.complete_json = AsyncMock(side_effect=RuntimeError("LLM down"))

    from core.engine.verification.honesty import PreCommitmentProtocol

    protocol = PreCommitmentProtocol(mock_llm)
    result = await protocol.pre_commit("Tests pass", "Add rate limiting")

    assert result.preliminary == "uncertain"
    assert result.evidence_needed == ""


# ---------------------------------------------------------------------------
# Honesty enforcer
# ---------------------------------------------------------------------------


def test_enforcer_blocks_met_on_test_failure():
    """Test execution failures are a hard gate — cannot mark 'met'."""
    from core.engine.verification.honesty import HonestyEnforcer

    enforcer = HonestyEnforcer()
    evidence = [
        BehavioralEvidence(
            check_type="test_execution",
            status="failed",
            details={"tests_passed": 3, "tests_failed": 2},
        ),
    ]

    result = enforcer.enforce("met", evidence)
    assert result.status == "not_met"
    assert result.enforced is True
    assert "2 test(s) failed" in result.reason


def test_enforcer_allows_not_met_on_test_failure():
    """Enforcer doesn't interfere when verdict already matches evidence."""
    from core.engine.verification.honesty import HonestyEnforcer

    enforcer = HonestyEnforcer()
    evidence = [
        BehavioralEvidence(check_type="test_execution", status="failed", details={"tests_failed": 1}),
    ]

    result = enforcer.enforce("not_met", evidence)
    assert result.status == "not_met"
    assert result.enforced is False


def test_enforcer_flags_met_on_code_missing():
    """Code inspection failures flag but don't block."""
    from core.engine.verification.honesty import HonestyEnforcer

    enforcer = HonestyEnforcer()
    evidence = [
        BehavioralEvidence(
            check_type="code_inspection",
            status="failed",
            details={"functions_missing": ["engine/foo.py:bar"]},
        ),
    ]

    result = enforcer.enforce("met", evidence)
    assert result.status == "met"  # allowed
    assert result.flagged is True
    assert "engine/foo.py:bar" in result.reason


def test_enforcer_passes_clean_verdict():
    """All evidence passing means no enforcement."""
    from core.engine.verification.honesty import HonestyEnforcer

    enforcer = HonestyEnforcer()
    evidence = [
        BehavioralEvidence(check_type="test_execution", status="passed", details={}),
        BehavioralEvidence(check_type="code_inspection", status="passed", details={}),
    ]

    result = enforcer.enforce("met", evidence)
    assert result.status == "met"
    assert result.enforced is False
    assert result.flagged is False


def test_enforcer_no_evidence():
    """No evidence means no enforcement."""
    from core.engine.verification.honesty import HonestyEnforcer

    enforcer = HonestyEnforcer()
    result = enforcer.enforce("met", [])
    assert result.status == "met"
    assert result.enforced is False


# ---------------------------------------------------------------------------
# Sentinel engine
# ---------------------------------------------------------------------------


def _make_db_mock(*side_effects):
    """Flexible DB mock for sentinel engine tests."""
    effects = list(side_effects)

    async def _query(*args, **kwargs):
        if effects:
            return effects.pop(0)
        return []

    db = AsyncMock()
    db.query = AsyncMock(side_effect=_query)
    return db


@pytest.mark.asyncio
async def test_engine_no_judgments():
    """Engine returns zeros when no recent judgments."""
    mock_db = _make_db_mock([])  # empty judgments

    with patch("core.engine.sentinel.engines.evaluator_honesty.pool") as mock_pool:
        cm = AsyncMock()
        cm.__aenter__ = AsyncMock(return_value=mock_db)
        cm.__aexit__ = AsyncMock(return_value=None)
        mock_pool.connection.return_value = cm

        from core.engine.sentinel.engines.evaluator_honesty import run_evaluator_honesty

        result = await run_evaluator_honesty("product:test")

    assert result["judgments_analyzed"] == 0
    assert result["flips_detected"] == 0


@pytest.mark.asyncio
async def test_engine_detects_flips():
    """Engine detects flips from likely_not_met to met."""
    judgments = [
        {
            "spec_id": "agent_spec:001",
            "criterion_index": 0,
            "pre_commitment": "likely_not_met",
            "final_verdict": "met",
            "flipped": True,
            "evidence_aligned": False,
            "overridden": False,
        },
        {
            "spec_id": "agent_spec:001",
            "criterion_index": 1,
            "pre_commitment": "likely_not_met",
            "final_verdict": "met",
            "flipped": True,
            "evidence_aligned": False,
            "overridden": False,
        },
        {
            "spec_id": "agent_spec:002",
            "criterion_index": 0,
            "pre_commitment": "likely_not_met",
            "final_verdict": "met",
            "flipped": True,
            "evidence_aligned": True,
            "overridden": False,
        },
        # Non-flipped judgment
        {
            "spec_id": "agent_spec:002",
            "criterion_index": 1,
            "pre_commitment": "likely_met",
            "final_verdict": "met",
            "flipped": False,
            "evidence_aligned": True,
            "overridden": False,
        },
    ]

    mock_db = _make_db_mock(judgments)

    mock_llm = MagicMock()
    mock_llm.complete_json = AsyncMock(
        return_value={
            "severity": "medium",
            "pattern": "Evaluator flips on criteria about test execution",
            "correction": "Require explicit test evidence before flipping",
            "confidence": 0.7,
        }
    )

    with (
        patch("core.engine.sentinel.engines.evaluator_honesty.pool") as mock_pool,
        patch("core.engine.sentinel.engines.evaluator_honesty.get_llm", return_value=mock_llm),
        patch(
            "core.engine.sentinel.engines.evaluator_honesty.write_engine_insight",
            new_callable=AsyncMock,
            return_value="insight:001",
        ),
    ):
        cm = AsyncMock()
        cm.__aenter__ = AsyncMock(return_value=mock_db)
        cm.__aexit__ = AsyncMock(return_value=None)
        mock_pool.connection.return_value = cm

        from core.engine.sentinel.engines.evaluator_honesty import run_evaluator_honesty

        result = await run_evaluator_honesty("product:test")

    assert result["judgments_analyzed"] == 4
    assert result["flips_detected"] == 3
    assert result["corrections_written"] == 1


@pytest.mark.asyncio
async def test_engine_detects_overrides():
    """Engine counts overrides where honesty enforcer intervened."""
    judgments = [
        {
            "spec_id": "agent_spec:001",
            "criterion_index": 0,
            "pre_commitment": "uncertain",
            "final_verdict": "not_met",
            "flipped": False,
            "evidence_aligned": False,
            "overridden": True,
        },
    ]

    mock_db = _make_db_mock(judgments)

    with patch("core.engine.sentinel.engines.evaluator_honesty.pool") as mock_pool:
        cm = AsyncMock()
        cm.__aenter__ = AsyncMock(return_value=mock_db)
        cm.__aexit__ = AsyncMock(return_value=None)
        mock_pool.connection.return_value = cm

        from core.engine.sentinel.engines.evaluator_honesty import run_evaluator_honesty

        result = await run_evaluator_honesty("product:test")

    assert result["overrides_detected"] == 1
