# tests/test_conductor_rule_engine.py
"""Tests for the rule engine: loading, caching, first-match evaluation."""

import time
from unittest.mock import AsyncMock, MagicMock

import pytest

from core.engine.conductor.rule_engine import RuleEngine


def _make_pool(db):
    pool = MagicMock()
    cm = AsyncMock()
    cm.__aenter__ = AsyncMock(return_value=db)
    cm.__aexit__ = AsyncMock(return_value=None)
    pool.connection.return_value = cm
    return pool


def _make_db(rules):
    db = AsyncMock()
    db.query = AsyncMock(return_value=rules)
    return db


def _rule(name, trigger, conditions=None, actions=None, priority=100, org=None, enabled=True):
    return {
        "id": f"conductor_rule:{name}",
        "name": name,
        "trigger_event": trigger,
        "conditions": conditions or [],
        "actions": actions or [],
        "priority": priority,
        "product": org,
        "enabled": enabled,
        "cooldown_seconds": 0,
        "source": "system",
    }


@pytest.mark.asyncio
async def test_load_rules():
    rules = [_rule("r1", "quality.score_changed"), _rule("r2", "spec.created")]
    engine = RuleEngine(_make_pool(_make_db(rules)))
    await engine.load_rules("product:test")
    assert len(engine._rules) == 2


def test_evaluate_returns_matching_rules():
    engine = RuleEngine.__new__(RuleEngine)
    engine._rules = [
        _rule("r1", "quality.score_changed", conditions=[{"field": "payload.score", "op": "lt", "value": 0.5}]),
        _rule("r2", "spec.created"),
    ]
    engine._last_fired = {}
    ctx = {"payload": {"score": 0.3}}
    matched = engine.evaluate("quality.score_changed", ctx)
    assert len(matched) == 1
    assert matched[0]["name"] == "r1"


def test_first_match_by_priority():
    engine = RuleEngine.__new__(RuleEngine)
    engine._rules = [
        _rule("r_low", "test.event", priority=200),
        _rule("r_high", "test.event", priority=50),
    ]
    engine._last_fired = {}
    matched = engine.evaluate("test.event", {})
    assert matched[0]["name"] == "r_high"


def test_org_rule_shadows_universal():
    engine = RuleEngine.__new__(RuleEngine)
    engine._rules = [
        _rule("shared_name", "test.event", org=None, priority=100),
        _rule("shared_name", "test.event", org="org:custom", priority=100),
    ]
    engine._last_fired = {}
    matched = engine.evaluate("test.event", {}, product_id="org:custom")
    assert len(matched) == 1
    assert matched[0]["product"] == "org:custom"


def test_no_match_returns_empty():
    engine = RuleEngine.__new__(RuleEngine)
    engine._rules = [_rule("r1", "other.event")]
    engine._last_fired = {}
    assert engine.evaluate("test.event", {}) == []


def test_cooldown_blocks_refiring():
    engine = RuleEngine.__new__(RuleEngine)
    r = _rule("r1", "test.event")
    r["cooldown_seconds"] = 60
    engine._rules = [r]
    engine._last_fired = {"r1": time.monotonic()}
    assert engine.check_cooldown(r) is True


def test_cooldown_expired_allows_firing():
    engine = RuleEngine.__new__(RuleEngine)
    r = _rule("r1", "test.event")
    r["cooldown_seconds"] = 1
    engine._rules = [r]
    engine._last_fired = {"r1": time.monotonic() - 10}
    assert engine.check_cooldown(r) is False
