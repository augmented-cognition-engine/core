"""Tests for engine/orchestrator/budgets.py — TALE token budget + BATS call budget."""

import pytest


@pytest.mark.unit
def test_token_budget_simple_reactive():
    from core.engine.orchestrator.budgets import estimate_token_budget

    assert estimate_token_budget({"complexity": "simple", "mode": "reactive"}) == 512


@pytest.mark.unit
def test_token_budget_simple_deliberative():
    from core.engine.orchestrator.budgets import estimate_token_budget

    assert estimate_token_budget({"complexity": "simple", "mode": "deliberative"}) == 1024


@pytest.mark.unit
def test_token_budget_moderate_any_mode():
    from core.engine.orchestrator.budgets import estimate_token_budget

    assert estimate_token_budget({"complexity": "moderate", "mode": "reactive"}) == 2048
    assert estimate_token_budget({"complexity": "moderate", "mode": "deliberative"}) == 2048


@pytest.mark.unit
def test_token_budget_complex_reactive_vs_deliberative():
    from core.engine.orchestrator.budgets import estimate_token_budget

    assert estimate_token_budget({"complexity": "complex", "mode": "reactive"}) == 4096
    assert estimate_token_budget({"complexity": "complex", "mode": "deliberative"}) == 6144


@pytest.mark.unit
def test_token_budget_defaults_to_moderate_when_unknown():
    from core.engine.orchestrator.budgets import estimate_token_budget

    assert estimate_token_budget({}) == 2048
    assert estimate_token_budget({"complexity": "unknown", "mode": "unknown"}) == 2048


@pytest.mark.unit
def test_call_budget_monotonic_in_complexity():
    from core.engine.orchestrator.budgets import estimate_call_budget

    simple = estimate_call_budget({"complexity": "simple"})
    moderate = estimate_call_budget({"complexity": "moderate"})
    complex_ = estimate_call_budget({"complexity": "complex"})
    assert simple < moderate < complex_
    assert simple == 4
    assert moderate == 8
    assert complex_ == 16


@pytest.mark.unit
def test_call_budget_defaults_to_moderate():
    from core.engine.orchestrator.budgets import estimate_call_budget

    assert estimate_call_budget({}) == 8
