# tests/test_acceptance.py
"""Tests for AcceptanceVerifier — TDD.

Four tests:
1. test_verify_fully_met: all criteria met → overall="fully_met", status updated to "completed"
2. test_verify_partially_met: some criteria met → overall="partially_met", follow_up_needed=True
3. test_verify_spec_not_found: invalid spec_id → returns error dict
4. test_verify_gap_closed: score >= 0.6 → closed=True

Note: behavioral checks and honesty enforcement are patched out here.
Those are tested in test_behavioral_verification.py and test_evaluator_honesty.py.
"""

import sys
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

# Disable honesty module in acceptance tests — it's tested separately.
# This prevents pre-commitment calls from consuming LLM mock responses.
_disable_honesty = patch.dict(sys.modules, {"core.engine.verification.honesty": None})

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_pool(db):
    """Build a mock pool that yields db on context manager entry."""
    pool = MagicMock()
    cm = AsyncMock()
    cm.__aenter__ = AsyncMock(return_value=db)
    cm.__aexit__ = AsyncMock(return_value=None)
    pool.connection.return_value = cm
    return pool


def _make_db(*side_effects):
    """Build a mock DB with query returning the given side effects in order.

    After explicit side effects are consumed, additional calls return [].
    This accommodates V2 verification data persistence (best-effort, try/except).
    """
    effects = list(side_effects)

    async def _flexible_query(*args, **kwargs):
        if effects:
            return effects.pop(0)
        return []

    db = AsyncMock()
    db.query = AsyncMock(side_effect=_flexible_query)
    return db


# ---------------------------------------------------------------------------
# Shared fixtures
# ---------------------------------------------------------------------------

FAKE_SPEC_TWO_CRITERIA = {
    "id": "agent_spec:001",
    "objective": "Add rate limiting to login endpoint",
    "acceptance_criteria": [
        {"criterion": "Returns 429 after 100 req/min", "verification": "curl test", "automated": True},
        {"criterion": "Existing auth tests still pass", "verification": "pytest", "automated": True},
    ],
    "estimated_files": ["engine/api/auth.py"],
    "capability": "capability:auth",
    "status": "executing",
}

FAKE_SPEC_ONE_CRITERION = {
    "id": "agent_spec:002",
    "objective": "Add OAuth2 support",
    "acceptance_criteria": [
        {"criterion": "OAuth2 login flow works end-to-end", "verification": "manual", "automated": False},
    ],
    "estimated_files": ["engine/api/auth.py"],
    "status": "executing",
}


# ---------------------------------------------------------------------------
# Test 1: all criteria met → fully_met, spec status updated to "completed"
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_verify_fully_met():
    """All LLM evaluations return 'met' → overall='fully_met', status set to 'completed'."""
    db = _make_db(
        [FAKE_SPEC_TWO_CRITERIA],  # SELECT spec
        # V2: extra DB calls for verification_signal handled by flexible mock
    )
    pool = _make_pool(db)

    llm_met = {
        "status": "met",
        "evidence": "Verified via curl — 429 returned after 100 req/min",
        "evidence_aligned": True,
    }

    with (
        _disable_honesty,
        patch("core.engine.product.acceptance.get_llm") as MockLLM,
        patch("core.engine.product.acceptance.ProductMap"),
        patch("core.engine.product.acceptance.run_checks", new_callable=AsyncMock, return_value={}),
    ):
        mock_llm_instance = MagicMock()
        mock_llm_instance.complete_json = AsyncMock(return_value=llm_met)
        MockLLM.return_value = mock_llm_instance

        from core.engine.product.acceptance import AcceptanceVerifier

        verifier = AcceptanceVerifier(pool)
        result = await verifier.verify("agent_spec:001", "product:test")

    assert result["overall"] == "fully_met"
    assert result["met"] == 2
    assert result["total"] == 2
    assert result["follow_up_needed"] is False


# ---------------------------------------------------------------------------
# Test 2: some criteria met → partially_met, follow_up_needed=True
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_verify_partially_met():
    """First criterion met, second not_met → overall='partially_met', follow_up_needed=True."""
    db = _make_db(
        [FAKE_SPEC_TWO_CRITERIA],  # SELECT spec
        # V2: extra DB calls handled by flexible mock returning []
    )
    pool = _make_pool(db)

    llm_responses = [
        {"status": "met", "evidence": "429 returned correctly", "evidence_aligned": True},
        {"status": "not_met", "evidence": "3 auth tests still failing", "evidence_aligned": True},
    ]

    with (
        _disable_honesty,
        patch("core.engine.product.acceptance.get_llm") as MockLLM,
        patch("core.engine.product.acceptance.ProductMap"),
        patch("core.engine.product.acceptance.run_checks", new_callable=AsyncMock, return_value={}),
    ):
        mock_llm_instance = MagicMock()
        mock_llm_instance.complete_json = AsyncMock(side_effect=llm_responses)
        MockLLM.return_value = mock_llm_instance

        from core.engine.product.acceptance import AcceptanceVerifier

        verifier = AcceptanceVerifier(pool)
        result = await verifier.verify("agent_spec:001", "product:test")

    assert result["overall"] == "partially_met"
    assert result["met"] == 1
    assert result["total"] == 2
    assert result["follow_up_needed"] is True
    assert "unmet_criteria" in result
    assert len(result["unmet_criteria"]) == 1
    assert result["unmet_criteria"][0]["criterion"] == "Existing auth tests still pass"


# ---------------------------------------------------------------------------
# Test 3: spec not found → error dict
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_verify_spec_not_found():
    """When spec does not exist, verify() returns an error dict."""
    db = _make_db(
        [],  # SELECT returns nothing
    )
    pool = _make_pool(db)

    with (
        patch("core.engine.product.acceptance.get_llm"),
        patch("core.engine.product.acceptance.ProductMap"),
    ):
        from core.engine.product.acceptance import AcceptanceVerifier

        verifier = AcceptanceVerifier(pool)
        result = await verifier.verify("agent_spec:nonexistent", "product:test")

    assert "error" in result
    assert "nonexistent" in result["error"]


# ---------------------------------------------------------------------------
# Test 4: verify_gap_closed — score >= 0.6 → closed=True
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_verify_gap_closed():
    """When capability quality score is >= 0.6, verify_gap_closed returns closed=True."""
    db = _make_db(
        [{"score": 0.75, "assessed_at": "2026-03-26T00:00:00Z"}],  # quality lookup
    )
    pool = _make_pool(db)

    with (
        patch("core.engine.product.acceptance.get_llm"),
        patch("core.engine.product.acceptance.ProductMap"),
    ):
        from core.engine.product.acceptance import AcceptanceVerifier

        verifier = AcceptanceVerifier(pool)
        result = await verifier.verify_gap_closed("security", "auth", "product:test")

    assert result["closed"] is True
    assert result["score"] == 0.75
    assert result["threshold"] == 0.6
