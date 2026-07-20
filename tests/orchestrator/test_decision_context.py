# tests/orchestrator/test_decision_context.py
"""Tests for the L5 tier-tagged decision-history loader.

Spec: docs/superpowers/specs/2026-05-14-layer5-context-assembly-design.md §5–§7
decision:lv6stu70piemfwypde2e — Layer 5 context assembly.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest

from core.engine.core.db import parse_one
from core.engine.orchestrator import context as l5
from core.engine.orchestrator.context import (
    TieredDecision,
    TieredDecisionResult,
    _compute_relevance_score,
    _detect_contradictions,
    _merge_and_dedupe,
    _reset_circuit_breaker_state,
    load_decision_context,
)

# -----------------------------------------------------------------------------
# Helpers
# -----------------------------------------------------------------------------


_PRODUCT = "product:test_l5_loader"


@pytest.fixture(autouse=True)
def _reset_breaker():
    _reset_circuit_breaker_state()
    yield
    _reset_circuit_breaker_state()


async def _seed(
    pool,
    *,
    title: str,
    caps: list[str] | None = None,
    discipline: str | None = None,
    outcome: str = "accepted",
    confidence: float | None = None,
    created_offset_days: float = 0.0,
) -> str:
    """Create a decision row with the L5 columns populated."""
    caps_clause = "$caps" if caps is not None else "NONE"
    conf_clause = "$conf" if confidence is not None else "NONE"
    inferred_clause = "time::now()" if caps is not None else "NONE"
    discipline_clause = "$discipline" if discipline is not None else "NONE"
    created_clause = f"time::now() - {created_offset_days}d" if created_offset_days > 0 else "time::now()"

    sql = f"""CREATE decision SET
        product = <record>$product,
        title = $title,
        decision_type = 'architecture',
        rationale = $rationale,
        outcome = $outcome,
        affected_capabilities = {caps_clause},
        affected_capabilities_confidence = {conf_clause},
        affected_capabilities_inferred_at = {inferred_clause},
        discipline_hint = {discipline_clause},
        created_at = {created_clause}
    RETURN id"""

    params: dict = {
        "product": _PRODUCT,
        "title": title,
        "rationale": f"rationale for {title}",
        "outcome": outcome,
    }
    if caps is not None:
        params["caps"] = caps
    if confidence is not None:
        params["conf"] = confidence
    if discipline is not None:
        params["discipline"] = discipline

    async with pool.connection() as db:
        result = await db.query(sql, params)
    row = parse_one(result)
    return row["id"] if row else None


async def _cleanup(pool) -> None:
    async with pool.connection() as db:
        await db.query(
            "DELETE FROM decision WHERE product = <record>$product",
            {"product": _PRODUCT},
        )


# -----------------------------------------------------------------------------
# Unit tests — relevance score formula
# -----------------------------------------------------------------------------


def test_compute_relevance_score_stale_capability_beats_fresh_discipline():
    """Tier base 0.9 (capability) + tiny decay still > tier base 0.6 (discipline)
    + fresh bonus 0.1 — capability tier always wins on score, by design."""
    now = datetime.now(timezone.utc)
    cap_stale = _compute_relevance_score("capability", now - timedelta(days=30))
    disc_fresh = _compute_relevance_score("discipline", now)
    assert cap_stale > disc_fresh, f"cap_stale={cap_stale} disc_fresh={disc_fresh}"


def test_compute_relevance_score_decays_with_age():
    """Within a tier, newer decisions outrank older ones."""
    now = datetime.now(timezone.utc)
    fresh = _compute_relevance_score("capability", now)
    week_old = _compute_relevance_score("capability", now - timedelta(days=7))
    assert fresh > week_old


def test_compute_relevance_score_bounded_above_one():
    """Even with zero-age decay bonus, the score never exceeds 1.0
    (capability 0.9 + bonus capped at 0.1)."""
    now = datetime.now(timezone.utc)
    fresh_cap = _compute_relevance_score("capability", now)
    assert fresh_cap <= 1.0


# -----------------------------------------------------------------------------
# Unit tests — _merge_and_dedupe
# -----------------------------------------------------------------------------


def _td(decision_id: str, tier, created_at=None) -> TieredDecision:
    """Factory for TieredDecision in unit tests."""
    if created_at is None:
        created_at = datetime.now(timezone.utc)
    return TieredDecision(
        decision_id=decision_id,
        title="t",
        rationale="r",
        decision_type="architecture",
        discipline_hint=None,
        affected_capabilities=[],
        created_at=created_at,
        tier=tier,
        relevance_score=_compute_relevance_score(tier, created_at),
        outcome="accepted",
        status=None,
        affected_capabilities_confidence=None,
    )


def test_merge_dedupes_same_id_across_tiers_capability_wins():
    same = "decision:shared"
    items = [_td(same, "recency"), _td(same, "capability"), _td(same, "discipline")]
    merged = _merge_and_dedupe(items, limit=5)
    assert len(merged) == 1
    assert merged[0].tier == "capability"


def test_merge_caps_at_limit():
    items = [_td(f"decision:{i}", "recency") for i in range(8)]
    merged = _merge_and_dedupe(items, limit=5)
    assert len(merged) == 5


def test_merge_orders_capability_first():
    items = [
        _td("decision:r", "recency"),
        _td("decision:c", "capability"),
        _td("decision:d", "discipline"),
    ]
    merged = _merge_and_dedupe(items, limit=5)
    assert [d.tier for d in merged] == ["capability", "discipline", "recency"]


def test_merge_empty_returns_empty():
    assert _merge_and_dedupe([], limit=5) == []


# -----------------------------------------------------------------------------
# Unit tests — _detect_contradictions (TODO-17)
# -----------------------------------------------------------------------------


def _td_with_caps_outcome(decision_id: str, caps: list[str], outcome: str) -> TieredDecision:
    return TieredDecision(
        decision_id=decision_id,
        title="t",
        rationale="r",
        decision_type="architecture",
        discipline_hint=None,
        affected_capabilities=caps,
        created_at=datetime.now(timezone.utc),
        tier="capability",
        relevance_score=0.9,
        outcome=outcome,  # type: ignore[arg-type]
        status=None,
        affected_capabilities_confidence=None,
    )


def test_detect_contradictions_accepted_rejected_shared_cap():
    """v1 rule (reconciled with actual schema): accepted ⇆ rejected
    on a shared capability slug is a contradiction. Someone considered
    approach X for capability Y and rejected it; someone else accepted it."""
    a = _td_with_caps_outcome("decision:a", ["auth"], "accepted")
    b = _td_with_caps_outcome("decision:b", ["auth"], "rejected")
    out = _detect_contradictions([a, b])
    assert out == [("decision:a", "decision:b", "auth")]


def test_detect_contradictions_ignores_superseded_and_pending():
    """superseded means replaced (not contested); pending means not-yet-decided.
    Neither counts as a contradiction."""
    a = _td_with_caps_outcome("decision:a", ["auth"], "accepted")
    b = _td_with_caps_outcome("decision:b", ["auth"], "superseded")
    c = _td_with_caps_outcome("decision:c", ["auth"], "pending")
    out = _detect_contradictions([a, b, c])
    assert out == []


def test_detect_contradictions_requires_shared_capability():
    a = _td_with_caps_outcome("decision:a", ["auth"], "accepted")
    b = _td_with_caps_outcome("decision:b", ["billing"], "rejected")
    assert _detect_contradictions([a, b]) == []


# -----------------------------------------------------------------------------
# Unit tests — TieredDecisionResult / dataclass shape
# -----------------------------------------------------------------------------


def test_result_dataclass_has_required_fields():
    r = TieredDecisionResult(decisions=[], degraded_tiers=frozenset(), elapsed_ms=0.0)
    assert r.decisions == []
    assert r.degraded_tiers == frozenset()
    assert r.elapsed_ms == 0.0
    assert r.contradictions == []


# -----------------------------------------------------------------------------
# Integration tests — real DB via db_pool
# -----------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_load_disabled_short_circuits(db_pool, monkeypatch):
    """Feature flag set to 'disabled' → empty result, no DB queries even with seeded data."""
    await _seed(db_pool, title="seed1", caps=["auth"])
    try:
        from core.engine.core import config

        monkeypatch.setattr(config.settings, "layer5_context_tiers", "disabled")
        result = await load_decision_context(
            task_description="anything",
            classification={"discipline": "auth"},
            product_id=_PRODUCT,
            pool=db_pool,
        )
        assert result.decisions == []
        assert result.degraded_tiers == frozenset()
    finally:
        await _cleanup(db_pool)


@pytest.mark.asyncio
async def test_load_cold_start_returns_empty_no_degraded(db_pool):
    """Product with no decisions returns empty + degraded_tiers empty (success path)."""
    await _cleanup(db_pool)
    result = await load_decision_context(
        task_description="cold start",
        classification={"discipline": "general"},
        product_id=_PRODUCT,
        pool=db_pool,
    )
    assert result.decisions == []
    assert result.degraded_tiers == frozenset()


@pytest.mark.asyncio
async def test_load_capability_tier_surfaces_matching_decision(db_pool):
    """A decision tagged with the candidate capability surfaces in capability tier."""
    await _cleanup(db_pool)
    try:
        await _seed(db_pool, title="auth rotation policy", caps=["auth"], confidence=0.9)
        result = await load_decision_context(
            task_description="anything",
            classification={"affected_capabilities": ["auth"], "discipline": "general"},
            product_id=_PRODUCT,
            pool=db_pool,
        )
        assert len(result.decisions) >= 1
        assert any(d.tier == "capability" for d in result.decisions)
        assert result.degraded_tiers == frozenset()
    finally:
        await _cleanup(db_pool)


@pytest.mark.asyncio
async def test_load_filters_by_confidence_threshold(db_pool):
    """Inferred row below min_confidence is filtered out at the loader; row
    above is kept; NONE-confidence (human-authored) is always kept."""
    await _cleanup(db_pool)
    try:
        await _seed(db_pool, title="low-conf", caps=["auth"], confidence=0.5)
        await _seed(db_pool, title="high-conf", caps=["auth"], confidence=0.9)
        await _seed(db_pool, title="human-authored", caps=["auth"], confidence=None)
        result = await load_decision_context(
            task_description="x",
            classification={"affected_capabilities": ["auth"], "discipline": "general"},
            product_id=_PRODUCT,
            pool=db_pool,
        )
        titles = {d.title for d in result.decisions}
        assert "low-conf" not in titles  # filtered by default min_conf=0.75
        assert "high-conf" in titles
        assert "human-authored" in titles
    finally:
        await _cleanup(db_pool)


@pytest.mark.asyncio
async def test_load_returns_degraded_tier_on_tier_exception(db_pool, monkeypatch):
    """When _load_capability_tier raises, the result includes the failure in
    degraded_tiers and surfaces the other tiers' rows normally."""
    await _cleanup(db_pool)
    try:
        await _seed(
            db_pool,
            title="discipline-row",
            caps=["x"],
            discipline="testing",
            confidence=0.95,
        )

        async def boom(*args, **kwargs):
            raise RuntimeError("capability tier broken")

        monkeypatch.setattr(l5, "_load_capability_tier", boom)

        result = await load_decision_context(
            task_description="anything",
            classification={"affected_capabilities": ["x"], "discipline": "testing"},
            product_id=_PRODUCT,
            pool=db_pool,
        )
        assert "capability" in result.degraded_tiers
        # discipline tier should have surfaced the seeded row
        assert any(d.tier == "discipline" for d in result.decisions)
    finally:
        await _cleanup(db_pool)


@pytest.mark.asyncio
async def test_load_tier1_only_skips_discipline_and_recency(db_pool, monkeypatch):
    """When the kill-switch flag is 'tier1_only', only the capability tier runs."""
    await _cleanup(db_pool)
    try:
        await _seed(db_pool, title="cap row", caps=["auth"], confidence=0.9)
        await _seed(db_pool, title="discipline row", discipline="testing", caps=["x"], confidence=0.9)
        await _seed(db_pool, title="recent row", caps=["y"], confidence=0.9)

        from core.engine.core import config

        monkeypatch.setattr(config.settings, "layer5_context_tiers", "tier1_only")

        result = await load_decision_context(
            task_description="rotate auth keys",
            classification={"affected_capabilities": ["auth"], "discipline": "testing"},
            product_id=_PRODUCT,
            pool=db_pool,
        )
        assert all(d.tier == "capability" for d in result.decisions)
    finally:
        await _cleanup(db_pool)
