# tests/test_conductor_rule_conditions.py
"""Tests for the rule condition evaluator."""

from core.engine.conductor.rule_conditions import evaluate_conditions


def test_eq_operator():
    ctx = {"payload": {"state": "gap_identified"}}
    conditions = [{"field": "payload.state", "op": "eq", "value": "gap_identified"}]
    assert evaluate_conditions(conditions, ctx) is True


def test_ne_operator():
    ctx = {"payload": {"state": "met"}}
    conditions = [{"field": "payload.state", "op": "ne", "value": "gap_identified"}]
    assert evaluate_conditions(conditions, ctx) is True


def test_lt_operator():
    ctx = {"payload": {"score": 0.3}}
    conditions = [{"field": "payload.score", "op": "lt", "value": 0.5}]
    assert evaluate_conditions(conditions, ctx) is True


def test_gt_operator():
    ctx = {"payload": {"score": 0.8}}
    conditions = [{"field": "payload.score", "op": "gt", "value": 0.5}]
    assert evaluate_conditions(conditions, ctx) is True


def test_in_operator():
    ctx = {"track": {"state": "met"}}
    conditions = [{"field": "track.state", "op": "in", "value": ["met", "exceeded"]}]
    assert evaluate_conditions(conditions, ctx) is True


def test_not_in_operator():
    ctx = {"track": {"state": "executing"}}
    conditions = [{"field": "track.state", "op": "not_in", "value": ["met", "exceeded"]}]
    assert evaluate_conditions(conditions, ctx) is True


def test_contains_operator():
    ctx = {"capability": {"tags": ["auth", "api"]}}
    conditions = [{"field": "capability.tags", "op": "contains", "value": "auth"}]
    assert evaluate_conditions(conditions, ctx) is True


def test_and_semantics_all_must_pass():
    ctx = {"payload": {"score": 0.3, "dimension": "security"}, "track": {"state": "gap_identified"}}
    conditions = [
        {"field": "payload.score", "op": "lt", "value": 0.5},
        {"field": "track.state", "op": "eq", "value": "gap_identified"},
    ]
    assert evaluate_conditions(conditions, ctx) is True


def test_and_semantics_one_fails():
    ctx = {"payload": {"score": 0.7}, "track": {"state": "gap_identified"}}
    conditions = [
        {"field": "payload.score", "op": "lt", "value": 0.5},
        {"field": "track.state", "op": "eq", "value": "gap_identified"},
    ]
    assert evaluate_conditions(conditions, ctx) is False


def test_interpolation_from_context():
    ctx = {"payload": {"score": 0.3}, "template": {"threshold": 0.5}}
    conditions = [{"field": "payload.score", "op": "lt", "value": "${template.threshold}"}]
    assert evaluate_conditions(conditions, ctx) is True


def test_missing_field_returns_false():
    ctx = {"payload": {}}
    conditions = [{"field": "payload.nonexistent", "op": "eq", "value": "x"}]
    assert evaluate_conditions(conditions, ctx) is False


def test_empty_conditions_returns_true():
    assert evaluate_conditions([], {}) is True


def test_matches_operator_regex():
    ctx = {"capability": {"slug": "auth_system"}}
    conditions = [{"field": "capability.slug", "op": "matches", "value": "auth.*"}]
    assert evaluate_conditions(conditions, ctx) is True
