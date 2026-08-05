"""Pre-outcome, fail-closed audit for starting prospective L1 collection.

The audit deliberately does not import or call the impact evaluator.  It can
record that collection is executable, blocked, or invalidated, but it cannot
score target outcomes or make a beneficial-impact claim.
"""

from __future__ import annotations

import hashlib
import json
from typing import Any

from core.engine.evaluation.l1_preregistration import (
    PREREGISTRATION_CONTRACT,
    READINESS_CONTRACT,
    REQUIRED_ARMS,
    registration_digest,
)

ATTEMPT_CONTRACT = "ace.foresight.impact-collection-start/v1"
RECEIPT_CONTRACT = "ace.foresight.impact-collection-start-receipt/v1"


def _canonical(value: object) -> bytes:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=True).encode("utf-8")


def attempt_digest(attempt: dict[str, Any]) -> str:
    """Return the stable attempt digest, excluding the digest field itself."""

    payload = {key: value for key, value in attempt.items() if key != "attempt_hash"}
    return "sha256:" + hashlib.sha256(_canonical(payload)).hexdigest()


def receipt_digest(receipt: dict[str, Any]) -> str:
    """Return the stable receipt digest, excluding its tamper-evident field."""

    payload = {key: value for key, value in receipt.items() if key != "receipt_hash"}
    return "sha256:" + hashlib.sha256(_canonical(payload)).hexdigest()


def _nonempty_strings(value: object) -> bool:
    return isinstance(value, list) and bool(value) and all(isinstance(item, str) and item for item in value)


def _contains_target_outcomes(value: object) -> bool:
    if isinstance(value, dict):
        forbidden = {"outcome", "outcomes", "cases", "comparisons", "scores", "effect_estimate"}
        if forbidden.intersection(value):
            return True
        return any(_contains_target_outcomes(item) for item in value.values())
    if isinstance(value, list):
        return any(_contains_target_outcomes(item) for item in value)
    return False


def _execution_blockers(registration: dict[str, Any]) -> list[str]:
    """Name preregistered degrees of freedom that were not operationally frozen."""

    blockers: list[str] = []
    cohort = registration.get("cohort") if isinstance(registration.get("cohort"), dict) else {}
    if not cohort.get("cohort_id"):
        blockers.append("cohort_identity_not_frozen")
    if not _nonempty_strings(cohort.get("eligibility_rules")):
        blockers.append("cohort_eligibility_rules_not_frozen")
    if not _nonempty_strings(cohort.get("exclusion_rules")):
        blockers.append("cohort_exclusion_rules_not_frozen")
    if not _nonempty_strings(cohort.get("leakage_boundaries")):
        blockers.append("cohort_leakage_boundaries_not_frozen")

    assignment = registration.get("assignment") if isinstance(registration.get("assignment"), dict) else {}
    if not assignment.get("schedule_id") or not assignment.get("schedule_hash"):
        blockers.append("assignment_schedule_identity_not_frozen")
    if not assignment.get("exposure_receipt_schema"):
        blockers.append("exposure_receipt_schema_not_frozen")

    arms = registration.get("arms") if isinstance(registration.get("arms"), list) else []
    if any(not isinstance(item, dict) or not item.get("id") or not item.get("policy_contract") for item in arms):
        blockers.append("control_policy_identities_not_frozen")

    matching = registration.get("matching") if isinstance(registration.get("matching"), dict) else {}
    exact_route = matching.get("exact_route") if isinstance(matching.get("exact_route"), dict) else {}
    required_route_values = (
        "provider",
        "model",
        "configuration_hash",
        "decision_schema_hash",
        "toolset_hash",
    )
    if any(not exact_route.get(field) for field in required_route_values):
        blockers.append("exact_route_values_not_frozen")

    observation = (
        registration.get("observation_schema") if isinstance(registration.get("observation_schema"), dict) else {}
    )
    required_observation_fields = {
        "product_id",
        "task_id",
        "decision_id",
        "prediction_id",
        "outcome_id",
        "calls",
        "input_tokens",
        "output_tokens",
        "latency_ms",
        "cost",
        "retries",
        "failures",
        "degraded_states",
    }
    recorded_fields = set(observation.get("required_fields") or [])
    if not required_observation_fields.issubset(recorded_fields):
        blockers.append("observation_resource_schema_not_frozen")

    outcome = registration.get("outcome") if isinstance(registration.get("outcome"), dict) else {}
    if outcome.get("metric") in {None, "", "declared later decision-quality outcome"}:
        blockers.append("primary_outcome_metric_not_frozen")
    if not outcome.get("provenance_schema"):
        blockers.append("outcome_provenance_schema_not_frozen")

    analysis = registration.get("analysis") if isinstance(registration.get("analysis"), dict) else {}
    window = analysis.get("window") if isinstance(analysis.get("window"), dict) else {}
    if not window.get("opens_at") or not window.get("closes_at"):
        blockers.append("analysis_window_not_frozen")
    if not analysis.get("cluster_definition"):
        blockers.append("independent_cluster_definition_not_frozen")
    if analysis.get("case_structure") != "one_assigned_arm_per_non_overlapping_allocation_unit":
        blockers.append("cohort_to_analysis_mapping_not_frozen")
    if not analysis.get("attribution_verification_contract"):
        blockers.append("attribution_verification_not_frozen")
    if assignment.get("design") == "blocked_randomized" and not analysis.get("minimum_complete_cases_per_arm"):
        blockers.append("sample_threshold_per_arm_not_frozen")
    if assignment.get("design") == "blocked_randomized" and analysis.get("estimator") != (
        "cluster_level_control_minus_treatment_mean_absolute_error/v1"
    ):
        blockers.append("paired_evaluator_conflicts_with_non_overlapping_assignment")

    lineage = registration.get("lineage") if isinstance(registration.get("lineage"), dict) else {}
    if not lineage.get("control_non_exposure_receipt"):
        blockers.append("control_lineage_semantics_not_frozen")
    if not registration.get("failure_case_evidence_schema"):
        blockers.append("failure_case_evidence_schema_not_frozen")
    return sorted(set(blockers))


def evaluate_l1_collection_start(
    registration: dict[str, Any],
    readiness: dict[str, Any],
    attempt: dict[str, Any],
    *,
    source_hashes: dict[str, str],
) -> dict[str, Any]:
    """Audit collection start without accepting or inspecting target outcomes."""

    blockers: list[str] = []
    if registration.get("contract_version") != PREREGISTRATION_CONTRACT:
        blockers.append("unsupported_preregistration_contract")
    if registration.get("registration_hash") != registration_digest(registration):
        blockers.append("preregistration_hash_mismatch")
    if readiness.get("contract_version") != READINESS_CONTRACT:
        blockers.append("unsupported_readiness_contract")
    if readiness.get("registration_id") != registration.get("registration_id"):
        blockers.append("readiness_registration_identity_mismatch")
    if readiness.get("registration_hash") != registration.get("registration_hash"):
        blockers.append("readiness_registration_hash_mismatch")
    if readiness.get("state") != "collection_not_started":
        blockers.append("unexpected_prior_collection_state")
    if readiness.get("beneficial_impact_evaluated") is not False:
        blockers.append("prior_receipt_contains_outcome_evaluation")

    if attempt.get("contract_version") != ATTEMPT_CONTRACT:
        blockers.append("unsupported_collection_start_contract")
    if attempt.get("attempt_hash") != attempt_digest(attempt):
        blockers.append("collection_start_attempt_hash_mismatch")
    if attempt.get("registration_id") != registration.get("registration_id"):
        blockers.append("attempt_registration_identity_mismatch")
    if attempt.get("registration_hash") != registration.get("registration_hash"):
        blockers.append("attempt_registration_hash_mismatch")
    if attempt.get("mode") != "pre_outcome_dry_run":
        blockers.append("collection_start_not_pre_outcome")
    target_outcomes_present = attempt.get("outcomes_submitted") is not False or _contains_target_outcomes(attempt)
    if target_outcomes_present:
        blockers.append("target_outcome_payload_present")
    if attempt.get("cohort_submitted") is not True:
        blockers.append("no_independently_timed_cohort_submitted")

    execution_blockers = _execution_blockers(registration)
    blockers.extend(execution_blockers)
    blockers = sorted(set(blockers))
    invalidation_reasons = set(blockers) - {"no_independently_timed_cohort_submitted"}
    if invalidation_reasons:
        disposition = "invalidated"
    elif blockers:
        disposition = "collection_not_started"
    else:
        disposition = "collection_started"
    controls = {
        item.get("id"): item.get("policy")
        for item in registration.get("arms", [])
        if isinstance(item, dict) and item.get("id") in REQUIRED_ARMS
    }
    receipt: dict[str, Any] = {
        "contract_version": RECEIPT_CONTRACT,
        "receipt_id": "l1-collection-start:" + attempt_digest(attempt).split(":", 1)[1][:32],
        "attempt_id": attempt.get("attempt_id"),
        "attempt_hash": attempt.get("attempt_hash"),
        "attempted_at": attempt.get("attempted_at"),
        "disposition": disposition,
        "collection_started": disposition == "collection_started",
        "protocol": {
            "registration_id": registration.get("registration_id"),
            "registration_hash": registration.get("registration_hash"),
            "computed_registration_hash": registration_digest(registration),
            "prior_readiness_state": readiness.get("state"),
            "structural_protocol_valid": readiness.get("protocol_valid") is True,
            "collection_executable": not execution_blockers,
        },
        "pre_outcome_guard": {
            "mode": attempt.get("mode"),
            "target_outcomes_submitted": target_outcomes_present,
            "impact_evaluator_invoked": False,
            "comparative_result_calculated": False,
            "comparative_result_revealed": False,
            "dry_run_passed": not target_outcomes_present,
        },
        "blockers": blockers,
        "frozen_and_missing_identities": {
            "controls": controls,
            "assignment_design": (registration.get("assignment") or {}).get("design"),
            "allocation_unit": (registration.get("assignment") or {}).get("allocation_unit"),
            "required_assignment_evidence": (registration.get("assignment") or {}).get("required_evidence"),
            "required_matching_dimensions": (registration.get("matching") or {}).get("required_dimensions"),
            "required_lineage": (registration.get("lineage") or {}).get("required_receipts"),
            "score_contract": (registration.get("analysis") or {}).get("score_contract"),
            "stopping_rule": (registration.get("analysis") or {}).get("stopping_rule"),
            "cohort_id": (registration.get("cohort") or {}).get("cohort_id"),
            "analysis_window": (registration.get("analysis") or {}).get("window"),
            "cluster_definition": (registration.get("analysis") or {}).get("cluster_definition"),
            "exact_route": (registration.get("matching") or {}).get("exact_route"),
        },
        "source_hashes": dict(sorted(source_hashes.items())),
        "resource_inventory": {
            "collection_observations": 0,
            "provider_calls": 0,
            "input_tokens": 0,
            "output_tokens": 0,
            "latency_ms": 0,
            "cost": {"amount": 0, "currency": "USD", "semantics": "no_collection_calls_made"},
            "retries": 0,
            "failures": [],
            "degraded_states": ["collection_not_executable"],
        },
        "external_dependencies": [
            "An independently operated, post-registration decision cohort.",
            "Verified assignment and exposure receipts from the intervention operator.",
            "Live exact-route execution; simulated provider output is ineligible.",
            "Product-owned outcome observations with immutable provenance.",
            "Independent support for randomized or quasi-experimental attribution.",
        ],
        "beneficial_impact_evaluated": False,
        "beneficial_impact_supported": False,
        "limitations": [
            "The earlier readiness receipt proves only that the bounded v1 manifest passes its structural checker.",
            "No prospective target outcome was submitted, inspected, scored, compared, or revealed.",
            "The negative retrospective result remains authoritative and unchanged.",
            "A successor protocol must be preregistered before its outcomes exist; this frozen registration cannot be repaired in place.",
        ],
    }
    receipt["receipt_hash"] = receipt_digest(receipt)
    return receipt


__all__ = [
    "ATTEMPT_CONTRACT",
    "RECEIPT_CONTRACT",
    "attempt_digest",
    "evaluate_l1_collection_start",
    "receipt_digest",
]
