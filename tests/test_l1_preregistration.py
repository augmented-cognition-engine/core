from __future__ import annotations

import copy
import json
from pathlib import Path

from core.engine.evaluation.l1_preregistration import (
    COHORT_CONTRACT,
    PREREGISTRATION_CONTRACT,
    READINESS_CONTRACT,
    evaluate_l1_readiness,
    registration_digest,
)


def _registration() -> dict:
    value = json.loads(Path("evaluations/fixtures/l1_preregistration_v1.json").read_text(encoding="utf-8"))
    assert value["contract_version"] == PREREGISTRATION_CONTRACT
    return value


def _case(index: int) -> dict:
    return {
        "case_id": f"case:{index}",
        "allocation_unit_hash": f"sha256:unit-{index}",
        "cluster_id": f"cluster:{index % 10}",
        "decision_id": f"decision:{index}",
        "decision_at": "2026-07-25T00:00:00Z",
        "outcome": {
            "outcome_id": f"outcome:{index}",
            "observed_at": "2026-08-25T00:00:00Z",
            "evidence_refs": [f"evidence:{index}"],
        },
        "assignment": {
            "arm": ("ace_foresight", "no_foresight", "naive_base_rate", "model_only")[index % 4],
            "assignment_receipt_id": f"assignment:{index}",
            "evidence_refs": [f"assignment-evidence:{index}"],
            "exposure_receipt_id": f"exposure:{index}",
            "exposed": True,
        },
        "lineage": {
            "f1_resolution_id": f"resolution:{index}",
            "i3_intelligence_use_receipt_id": f"intelligence-use:{index}",
            "material_use": True,
        },
        "matched_route": {
            "state": "matched",
            "task_hash": "sha256:task",
            "prompt_contract_hash": "sha256:prompt",
            "provider": "provider",
            "model": "model",
            "configuration_hash": "sha256:config",
            "decision_schema_hash": "sha256:decision",
            "toolset_hash": "sha256:tools",
        },
    }


def _cohort(registration: dict, count: int = 40) -> dict:
    return {
        "contract_version": COHORT_CONTRACT,
        "registration_id": registration["registration_id"],
        "registration_hash": registration["registration_hash"],
        "cases": [_case(index) for index in range(count)],
        "failure_cases": [
            {"kind": kind, "observed": True}
            for kind in ("null", "harmful", "missing_outcome", "failed_route", "degraded_lineage")
        ],
    }


def test_frozen_registration_is_valid_but_does_not_claim_benefit() -> None:
    registration = _registration()
    result = evaluate_l1_readiness(registration)

    assert result["contract_version"] == READINESS_CONTRACT
    assert result["state"] == "collection_not_started"
    assert result["protocol_valid"] is True
    assert result["analysis_ready"] is False
    assert result["beneficial_impact_evaluated"] is False
    assert result["beneficial_impact_supported"] is False
    assert result["reason_codes"] == ["no_independently_timed_cohort_submitted"]
    recorded = json.loads(Path("evaluations/results/l1_preregistration_readiness_v1.json").read_text(encoding="utf-8"))
    assert result == recorded


def test_tampering_after_registration_fails_closed() -> None:
    registration = _registration()
    registration["analysis"]["minimum_complete_cases"] = 12
    result = evaluate_l1_readiness(registration)

    assert result["state"] == "invalid_preregistration"
    assert "minimum_case_count_not_frozen" in result["reason_codes"]
    assert "preregistration_hash_mismatch" in result["reason_codes"]


def test_future_contract_and_unfrozen_arms_fail_closed() -> None:
    registration = _registration()
    registration["contract_version"] = "ace.foresight.impact-preregistration/v2"
    registration["arms"] = registration["arms"][:-1]
    registration["registration_hash"] = registration_digest(registration)
    result = evaluate_l1_readiness(registration)

    assert result["state"] == "invalid_preregistration"
    assert "unsupported_preregistration_contract" in result["reason_codes"]
    assert "required_arms_not_frozen" in result["reason_codes"]


def test_complete_fixed_cohort_can_only_become_ready_for_frozen_analysis() -> None:
    registration = _registration()
    result = evaluate_l1_readiness(registration, _cohort(registration))

    assert result["state"] == "ready_for_frozen_analysis"
    assert result["analysis_ready"] is True
    assert result["beneficial_impact_evaluated"] is False
    assert result["beneficial_impact_supported"] is False
    assert result["reason_codes"] == []


def test_pre_registration_and_overlapping_units_are_ineligible() -> None:
    registration = _registration()
    cohort = _cohort(registration)
    cohort["cases"][0]["decision_at"] = "2026-07-23T00:00:00Z"
    cohort["cases"][1]["allocation_unit_hash"] = cohort["cases"][0]["allocation_unit_hash"]
    result = evaluate_l1_readiness(registration, cohort)

    reasons = {reason for case in result["cases"] for reason in case["reason_codes"]}
    assert result["state"] == "cohort_ineligible"
    assert "decision_predates_preregistration" in reasons
    assert "overlapping_allocation_unit" in reasons
    assert result["sample"]["duplicate_allocation_units"] == ["sha256:unit-0"]


def test_missing_assignment_exposure_lineage_and_route_are_named() -> None:
    registration = _registration()
    cohort = _cohort(registration)
    broken = cohort["cases"][0]
    broken["assignment"] = {}
    broken["lineage"] = {}
    broken["matched_route"] = {}
    result = evaluate_l1_readiness(registration, cohort)

    first = result["cases"][0]
    assert first["eligible"] is False
    assert set(first["reason_codes"]) >= {
        "invalid_assigned_arm",
        "unverified_assignment",
        "unverified_exposure",
        "missing_f1_resolution_id",
        "missing_i3_intelligence_use_receipt_id",
        "material_use_not_established",
        "matched_model_route_not_established",
        "partial_matched_route",
    }


def test_missing_failure_coverage_blocks_analysis() -> None:
    registration = _registration()
    cohort = _cohort(registration)
    cohort["failure_cases"] = []
    result = evaluate_l1_readiness(registration, cohort)

    assert result["state"] == "cohort_ineligible"
    assert "required_failure_coverage_missing" in result["reason_codes"]
    assert result["missing_required_failure_cases"] == [
        "null",
        "harmful",
        "missing_outcome",
        "failed_route",
        "degraded_lineage",
    ]


def test_input_objects_are_not_mutated() -> None:
    registration = _registration()
    cohort = _cohort(registration)
    before_registration = copy.deepcopy(registration)
    before_cohort = copy.deepcopy(cohort)

    evaluate_l1_readiness(registration, cohort)

    assert registration == before_registration
    assert cohort == before_cohort


def test_public_readiness_receipt_bounds_and_redacts_identifiers() -> None:
    registration = _registration()
    cohort = _cohort(registration)
    cohort["cases"][0]["case_id"] = "api_key=top-secret " + ("x" * 300)
    cohort["cases"][0]["cluster_id"] = "Bearer private-token"

    result = evaluate_l1_readiness(registration, cohort)

    assert result["cases"][0]["case_id"].startswith("[REDACTED]")
    assert len(result["cases"][0]["case_id"]) <= 160
    assert result["cases"][0]["cluster_id"] == "[REDACTED]"
