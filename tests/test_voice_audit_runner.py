"""Tests for voice audit runner — orchestration + scoring + pool=None contract."""

from __future__ import annotations

import pytest


@pytest.mark.asyncio
async def test_run_audit_pool_none_returns_summary():
    """CI mode: pool=None, persist=False — should return summary without crashing."""
    from core.engine.voice.audit_runner import run_audit

    summary = await run_audit(pool=None, product_id="product:platform", trigger="ci", persist=False)
    assert "surface_scores" in summary
    assert "overall_score" in summary
    assert "violations" in summary
    # Static fixture surfaces should have non-zero total_samples
    static = [name for name, info in summary["surface_scores"].items() if info.get("enforce_at_write")]
    assert len(static) >= 2


@pytest.mark.asyncio
async def test_run_audit_clean_codebase_score_1_0():
    """All current templates pass voice rules → overall_score 1.0 in CI mode."""
    from core.engine.voice.audit_runner import run_audit

    summary = await run_audit(pool=None, product_id="product:platform", trigger="ci", persist=False)
    # Static surfaces must score 1.0 (the things CI actually gates on)
    for name, info in summary["surface_scores"].items():
        if info.get("enforce_at_write"):
            assert info["score"] == 1.0, f"{name} score {info['score']} not 1.0; violations: {summary['violations']}"


@pytest.mark.asyncio
@pytest.mark.e2e
async def test_run_audit_persists_row():
    from core.engine.core.db import parse_rows, pool
    from core.engine.voice.audit_runner import run_audit

    await pool.init()
    async with pool.connection() as db:
        await db.query("DELETE voice_audit_run WHERE product = product:test_run")

    try:
        summary = await run_audit(pool, product_id="product:test_run", trigger="manual", persist=True)
        assert "overall_score" in summary

        async with pool.connection() as db:
            rows = parse_rows(
                await db.query(
                    "SELECT overall_score, trigger, ran_at FROM voice_audit_run "
                    "WHERE product = product:test_run ORDER BY ran_at DESC LIMIT 1"
                )
            )
        assert len(rows) == 1
        assert rows[0]["trigger"] == "manual"
    finally:
        async with pool.connection() as db:
            await db.query("DELETE voice_audit_run WHERE product = product:test_run")


@pytest.mark.asyncio
async def test_run_audit_injects_violation():
    """Inject a violation by swapping the journey REGISTRY entry — overall_score drops below 1.0."""
    from dataclasses import replace

    from core.engine.voice import surfaces as surfaces_mod
    from core.engine.voice.audit_runner import run_audit

    # VoiceSurface is @dataclass(frozen=True) per spec, so we can't reassign sample_provider
    # in place. Use dataclasses.replace() to build a new surface with the violating provider
    # and swap it into the list slot. This also avoids the closure-capture problem of patching
    # _fixture_samples (the existing provider may already hold a direct reference).
    async def violating(_pid: str) -> list[str]:
        return ["Welcome! Get started"]  # contains 2 forbidden strings

    idx = next(i for i, s in enumerate(surfaces_mod.REGISTRY) if s.name == "journey_templates")
    original = surfaces_mod.REGISTRY[idx]
    surfaces_mod.REGISTRY[idx] = replace(original, sample_provider=violating)

    try:
        summary = await run_audit(pool=None, product_id="product:platform", trigger="ci", persist=False)
        assert summary["overall_score"] < 1.0
        assert any("Welcome!" in v.get("text_excerpt", "") for v in summary["violations"])
    finally:
        surfaces_mod.REGISTRY[idx] = original
