from __future__ import annotations

import copy
import hashlib
import json
from pathlib import Path

from core.engine.evaluation.l1_collection_start import (
    ATTEMPT_CONTRACT,
    RECEIPT_CONTRACT,
    attempt_digest,
    evaluate_l1_collection_start,
    receipt_digest,
)


def _read(path: str) -> dict:
    value = json.loads(Path(path).read_text(encoding="utf-8"))
    assert isinstance(value, dict)
    return value


def _inputs() -> tuple[dict, dict, dict]:
    return (
        _read("evaluations/fixtures/l1_preregistration_v1.json"),
        _read("evaluations/results/l1_preregistration_readiness_v1.json"),
        _read("evaluations/fixtures/l1_collection_start_v1.json"),
    )


def _source_hashes() -> dict[str, str]:
    paths = {
        "analysis_code": Path("core/engine/evaluation/foresight_impact.py"),
        "attempt": Path("evaluations/fixtures/l1_collection_start_v1.json"),
        "collection_audit_code": Path("core/engine/evaluation/l1_collection_start.py"),
        "collection_audit_script": Path("scripts/verify_l1_collection_start.py"),
        "intake_code": Path("core/engine/evaluation/l1_preregistration.py"),
        "preregistration": Path("evaluations/fixtures/l1_preregistration_v1.json"),
        "prior_readiness_receipt": Path("evaluations/results/l1_preregistration_readiness_v1.json"),
    }
    return {name: "sha256:" + hashlib.sha256(path.read_bytes()).hexdigest() for name, path in paths.items()}


def test_frozen_collection_start_is_invalidated_without_outcome_analysis() -> None:
    registration, readiness, attempt = _inputs()
    result = evaluate_l1_collection_start(registration, readiness, attempt, source_hashes=_source_hashes())

    assert attempt["contract_version"] == ATTEMPT_CONTRACT
    assert result["contract_version"] == RECEIPT_CONTRACT
    assert result["disposition"] == "invalidated"
    assert result["collection_started"] is False
    assert result["pre_outcome_guard"] == {
        "mode": "pre_outcome_dry_run",
        "target_outcomes_submitted": False,
        "impact_evaluator_invoked": False,
        "comparative_result_calculated": False,
        "comparative_result_revealed": False,
        "dry_run_passed": True,
    }
    assert result["beneficial_impact_evaluated"] is False
    assert result["beneficial_impact_supported"] is False
    assert result["receipt_hash"] == receipt_digest(result)
    assert result == _read("evaluations/results/l1_collection_start_v1.json")


def test_collection_start_names_frozen_execution_blockers() -> None:
    registration, readiness, attempt = _inputs()
    result = evaluate_l1_collection_start(registration, readiness, attempt, source_hashes=_source_hashes())

    assert set(result["blockers"]) >= {
        "no_independently_timed_cohort_submitted",
        "cohort_identity_not_frozen",
        "cohort_eligibility_rules_not_frozen",
        "cohort_exclusion_rules_not_frozen",
        "cohort_leakage_boundaries_not_frozen",
        "assignment_schedule_identity_not_frozen",
        "exposure_receipt_schema_not_frozen",
        "control_policy_identities_not_frozen",
        "exact_route_values_not_frozen",
        "observation_resource_schema_not_frozen",
        "primary_outcome_metric_not_frozen",
        "outcome_provenance_schema_not_frozen",
        "analysis_window_not_frozen",
        "independent_cluster_definition_not_frozen",
        "cohort_to_analysis_mapping_not_frozen",
        "attribution_verification_not_frozen",
        "sample_threshold_per_arm_not_frozen",
        "paired_evaluator_conflicts_with_non_overlapping_assignment",
        "control_lineage_semantics_not_frozen",
        "failure_case_evidence_schema_not_frozen",
    }


def test_dry_run_rejects_target_outcome_payload_without_inspecting_it() -> None:
    registration, readiness, attempt = _inputs()
    attempt["outcomes_submitted"] = True
    attempt["outcome"] = {"opaque": "must-not-be-read"}
    attempt["attempt_hash"] = attempt_digest(attempt)

    result = evaluate_l1_collection_start(registration, readiness, attempt, source_hashes=_source_hashes())

    assert "target_outcome_payload_present" in result["blockers"]
    assert result["pre_outcome_guard"]["target_outcomes_submitted"] is True
    assert result["pre_outcome_guard"]["impact_evaluator_invoked"] is False
    assert "opaque" not in json.dumps(result)


def test_attempt_and_registration_tampering_fail_closed() -> None:
    registration, readiness, attempt = _inputs()
    attempt["requested_disposition"] = "force_collection"
    registration["analysis"]["minimum_complete_cases"] = 1

    result = evaluate_l1_collection_start(registration, readiness, attempt, source_hashes=_source_hashes())

    assert "collection_start_attempt_hash_mismatch" in result["blockers"]
    assert "preregistration_hash_mismatch" in result["blockers"]
    assert result["disposition"] == "invalidated"


def test_collection_start_does_not_mutate_inputs() -> None:
    registration, readiness, attempt = _inputs()
    before = copy.deepcopy((registration, readiness, attempt))

    evaluate_l1_collection_start(registration, readiness, attempt, source_hashes=_source_hashes())

    assert (registration, readiness, attempt) == before
