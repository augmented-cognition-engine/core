"""Frozen K1-K3 readiness target and result reconciliation checks."""

from __future__ import annotations

import hashlib
from pathlib import Path

import pytest

from evaluations.state_engine_readiness import (
    compile_readiness_result,
    load_readiness_config,
    readiness_config_hash,
    validate_readiness_result,
)

ROOT = Path(__file__).parents[1]
CONFIG = ROOT / "evaluations/fixtures/state_engine_k1_k3_readiness_v1.json"


def test_k1_k3_readiness_target_was_frozen_before_measurement():
    config = load_readiness_config()

    assert readiness_config_hash() == "0818b3b8acfd86051bd13ff1e6111748d42a78a617133bd13e75d40a7e55df00"
    assert hashlib.sha256(CONFIG.read_bytes()).hexdigest() == readiness_config_hash()
    assert config["fixture_status"] == "frozen_before_measurement"
    assert config["k2"]["repetitions"] == config["k3"]["repetitions"] == 5
    assert config["k2"]["thresholds"]["cases_evaluated"] == 40
    assert config["k3"]["thresholds"]["journeys_evaluated"] == 5
    assert config["provider_budget"]["max_model_calls"] == 0
    assert config["provider_budget"]["max_estimated_cost_usd"] == 0.0


def test_k2_target_repeats_exact_frozen_tp5_case_set():
    config = load_readiness_config()
    expected = {
        "causal_claim_requires_human_gate",
        "foreign_product_evidence_isolated",
        "mechanism_supported_transition",
        "mechanism_with_contrary_evidence",
        "price_reaction_not_causal_fact",
        "sequence_without_causal_promotion",
        "unknown_event_time_remains_unknown",
        "world_state_changes_over_time",
    }

    assert set(config["k2"]["domains"].values()) == expected
    assert config["k2"]["thresholds"]["abstentions_min"] == 35
    assert config["k2"]["thresholds"]["unsupported_assertion_acceptances_max"] == 0


def _gate(decision: str) -> dict:
    return {"status": "passed" if decision == "ready" else "failed", "decision": decision}


def test_readiness_result_requires_three_independent_ready_decisions():
    config = load_readiness_config()
    result = compile_readiness_result(
        config=config,
        k1=_gate("ready"),
        k2=_gate("ready"),
        k3=_gate("ready"),
        commands=["frozen-command"],
    )
    validate_readiness_result(result)
    assert result["decisions"] == {"K1": "ready", "K2": "ready", "K3": "ready"}
    assert result["r7_unblocked"] is result["passed"] is True

    blocked = compile_readiness_result(
        config=config,
        k1=_gate("ready"),
        k2=_gate("candidate"),
        k3=_gate("ready"),
        commands=["frozen-command"],
    )
    validate_readiness_result(blocked)
    assert blocked["r7_unblocked"] is blocked["passed"] is False


def test_readiness_result_rejects_decision_or_hash_rewriting():
    config = load_readiness_config()
    result = compile_readiness_result(
        config=config,
        k1=_gate("ready"),
        k2=_gate("ready"),
        k3=_gate("candidate"),
        commands=["frozen-command"],
    )
    with pytest.raises(ValueError, match="decisions do not reconcile"):
        validate_readiness_result({**result, "decisions": {"K1": "ready", "K2": "ready", "K3": "ready"}})
    with pytest.raises(ValueError, match="outcome hash"):
        validate_readiness_result({**result, "limitations": []})
