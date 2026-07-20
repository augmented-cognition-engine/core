# tests/test_conductor_bootstrap.py
"""Tests for conductor bootstrap — seeding tracks and default rules."""

from unittest.mock import AsyncMock, MagicMock

import pytest

from core.engine.conductor.bootstrap import DEFAULT_RULES, seed_default_rules, seed_lifecycle_tracks


def _make_pool(db):
    pool = MagicMock()
    cm = AsyncMock()
    cm.__aenter__ = AsyncMock(return_value=db)
    cm.__aexit__ = AsyncMock(return_value=None)
    pool.connection.return_value = cm
    return pool


@pytest.mark.asyncio
async def test_seed_creates_tracks_for_existing_quality():
    quality_rows = [
        {"capability": "capability:auth", "dimension": "security", "score": 0.3},
        {"capability": "capability:auth", "dimension": "testing", "score": 0.7},
    ]
    db = AsyncMock()
    db.query = AsyncMock(return_value=quality_rows)
    pool = _make_pool(db)

    await seed_lifecycle_tracks(pool, "product:test")
    # Should have called query multiple times (load quality + create tracks)
    assert db.query.call_count >= 2


@pytest.mark.asyncio
async def test_seed_default_rules():
    db = AsyncMock()
    db.query = AsyncMock(return_value=[])  # No existing rules
    pool = _make_pool(db)

    await seed_default_rules(pool, "product:test")
    # Should have cleaned legacy productless rules, queried, and created rules.
    assert db.query.call_count >= 2
    create_calls = [call for call in db.query.await_args_list if "CREATE conductor_rule" in call.args[0]]
    assert len(create_calls) == len(DEFAULT_RULES)
    assert all("product = <record>$product" in call.args[0] for call in create_calls)
    assert all(call.args[1]["product"] == "product:test" for call in create_calls)


def test_default_rules_exist():
    assert len(DEFAULT_RULES) >= 10
    names = [r["name"] for r in DEFAULT_RULES]
    assert "score_drop_opens_gap" in names
    assert "auto_spec_low_risk" in names
    assert "spec_risk_assessment" in names
    assert "gate_cleared_execute" in names
    assert "human_approves_gate" in names
    assert "execution_complete_verify" in names
    assert "verification_passed" in names
    assert "verification_failed_rework" in names
    assert "max_attempts_escalate" in names
    assert "stall_escalate" in names
    assert "all_gaps_closed_innovate" in names


def test_default_rules_all_have_required_fields():
    for rule in DEFAULT_RULES:
        assert "name" in rule
        assert "trigger_event" in rule
        assert "conditions" in rule
        assert "actions" in rule
        assert "priority" in rule
        assert "description" in rule
