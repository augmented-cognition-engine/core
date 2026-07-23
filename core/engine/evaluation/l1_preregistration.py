"""Fail-closed preregistration and intake checks for the prospective L1 gate.

This module does not score outcomes and cannot promote L1.  It freezes the
study design before collection, then checks whether a later cohort is eligible
to enter the existing impact evaluator.  Missing or unverifiable provenance is
preserved as a blocker rather than reconstructed from prose.
"""

from __future__ import annotations

import hashlib
import json
import re
from datetime import datetime, timezone
from typing import Any

PREREGISTRATION_CONTRACT = "ace.foresight.impact-preregistration/v1"
COHORT_CONTRACT = "ace.foresight.impact-cohort/v1"
READINESS_CONTRACT = "ace.foresight.impact-readiness/v1"
REQUIRED_ARMS = ("ace_foresight", "no_foresight", "naive_base_rate", "model_only")
REQUIRED_FAILURE_CASES = (
    "null",
    "harmful",
    "missing_outcome",
    "failed_route",
    "degraded_lineage",
)
MIN_COMPLETE_CASES = 30
MIN_INDEPENDENT_CLUSTERS = 8
MAX_CASES = 256
_CREDENTIAL = re.compile(r"(?i)\b(bearer|api[_-]?key|token|password|secret)\b\s*[:=]?\s*[^\s,;]+")


def _canonical(value: object) -> bytes:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=True).encode("utf-8")


def registration_digest(registration: dict[str, Any]) -> str:
    """Return the stable digest, excluding the digest field itself."""

    payload = {key: value for key, value in registration.items() if key != "registration_hash"}
    return "sha256:" + hashlib.sha256(_canonical(payload)).hexdigest()


def _timestamp(value: object) -> datetime | None:
    if not isinstance(value, str) or not value:
        return None
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None
    return parsed if parsed.tzinfo is not None else None


def _text(value: object, limit: int = 160) -> str:
    return _CREDENTIAL.sub("[REDACTED]", " ".join(str(value or "").split()))[:limit]


def _nonempty_strings(value: object) -> bool:
    return isinstance(value, list) and bool(value) and all(isinstance(item, str) and item for item in value)


def _protocol_reasons(registration: dict[str, Any]) -> list[str]:
    reasons: list[str] = []
    if registration.get("contract_version") != PREREGISTRATION_CONTRACT:
        reasons.append("unsupported_preregistration_contract")
    if not registration.get("registration_id"):
        reasons.append("missing_registration_identity")
    registered_at = _timestamp(registration.get("registered_at"))
    if registered_at is None:
        reasons.append("invalid_registration_time")
    first_decision = _timestamp(registration.get("first_decision_not_before"))
    if first_decision is None:
        reasons.append("invalid_first_decision_time")
    elif registered_at is not None and first_decision <= registered_at:
        reasons.append("collection_not_prospective")

    recorded_hash = registration.get("registration_hash")
    if not isinstance(recorded_hash, str) or recorded_hash != registration_digest(registration):
        reasons.append("preregistration_hash_mismatch")

    arms = registration.get("arms")
    arm_ids = [item.get("id") for item in arms if isinstance(item, dict)] if isinstance(arms, list) else []
    if arm_ids != list(REQUIRED_ARMS):
        reasons.append("required_arms_not_frozen")

    assignment = registration.get("assignment") if isinstance(registration.get("assignment"), dict) else {}
    if assignment.get("design") not in {"blocked_randomized", "verified_quasi_experimental"}:
        reasons.append("unsupported_assignment_design")
    if not assignment.get("allocation_unit"):
        reasons.append("missing_allocation_unit")
    if not _nonempty_strings(assignment.get("required_evidence")):
        reasons.append("missing_assignment_evidence_requirements")

    matching = registration.get("matching") if isinstance(registration.get("matching"), dict) else {}
    if matching.get("required_dimensions") != [
        "task_hash",
        "prompt_contract_hash",
        "provider",
        "model",
        "configuration_hash",
        "decision_schema_hash",
        "toolset_hash",
    ]:
        reasons.append("matched_route_dimensions_not_frozen")

    lineage = registration.get("lineage") if isinstance(registration.get("lineage"), dict) else {}
    if lineage.get("required_receipts") != [
        "f1_resolution_id",
        "i3_intelligence_use_receipt_id",
        "decision_id",
        "outcome_id",
    ]:
        reasons.append("required_lineage_not_frozen")

    analysis = registration.get("analysis") if isinstance(registration.get("analysis"), dict) else {}
    if analysis.get("score_contract") != "continuous_absolute_error/v1":
        reasons.append("unsupported_score_contract")
    if analysis.get("minimum_complete_cases") != MIN_COMPLETE_CASES:
        reasons.append("minimum_case_count_not_frozen")
    if analysis.get("minimum_independent_clusters") != MIN_INDEPENDENT_CLUSTERS:
        reasons.append("minimum_cluster_count_not_frozen")
    if analysis.get("maximum_cases") != MAX_CASES:
        reasons.append("case_bound_not_frozen")
    if analysis.get("stopping_rule") != "analyze_once_after_fixed_cohort_closes":
        reasons.append("stopping_rule_not_frozen")
    if analysis.get("required_comparisons") != list(REQUIRED_ARMS[1:]):
        reasons.append("required_comparisons_not_frozen")
    if analysis.get("promotion_rule") != "lower_cluster_adjusted_95_bound_above_zero_for_every_comparison":
        reasons.append("promotion_rule_not_frozen")

    failure_cases = registration.get("required_failure_cases")
    if failure_cases != list(REQUIRED_FAILURE_CASES):
        reasons.append("failure_matrix_not_frozen")
    if registration.get("collection_state") != "not_started":
        reasons.append("preregistration_contains_collection_claim")
    return sorted(set(reasons))


def _case_reasons(case: dict[str, Any], first_decision: datetime) -> list[str]:
    reasons: list[str] = []
    for field in ("case_id", "allocation_unit_hash", "cluster_id", "decision_id"):
        if not case.get(field):
            reasons.append(f"missing_{field}")

    decision_at = _timestamp(case.get("decision_at"))
    if decision_at is None:
        reasons.append("invalid_decision_time")
    elif decision_at < first_decision:
        reasons.append("decision_predates_preregistration")

    outcome = case.get("outcome") if isinstance(case.get("outcome"), dict) else {}
    observed_at = _timestamp(outcome.get("observed_at"))
    if not outcome.get("outcome_id"):
        reasons.append("missing_outcome_id")
    if observed_at is None:
        reasons.append("invalid_outcome_time")
    elif decision_at is not None and observed_at <= decision_at:
        reasons.append("outcome_not_later_than_decision")
    if not _nonempty_strings(outcome.get("evidence_refs")):
        reasons.append("missing_outcome_provenance")

    assignment = case.get("assignment") if isinstance(case.get("assignment"), dict) else {}
    if assignment.get("arm") not in REQUIRED_ARMS:
        reasons.append("invalid_assigned_arm")
    if not assignment.get("assignment_receipt_id") or not _nonempty_strings(assignment.get("evidence_refs")):
        reasons.append("unverified_assignment")
    if not assignment.get("exposure_receipt_id") or assignment.get("exposed") is not True:
        reasons.append("unverified_exposure")

    lineage = case.get("lineage") if isinstance(case.get("lineage"), dict) else {}
    for field in ("f1_resolution_id", "i3_intelligence_use_receipt_id"):
        if not lineage.get(field):
            reasons.append(f"missing_{field}")
    if lineage.get("material_use") is not True:
        reasons.append("material_use_not_established")

    route = case.get("matched_route") if isinstance(case.get("matched_route"), dict) else {}
    if route.get("state") != "matched":
        reasons.append("matched_model_route_not_established")
    required_route_fields = (
        "task_hash",
        "prompt_contract_hash",
        "provider",
        "model",
        "configuration_hash",
        "decision_schema_hash",
        "toolset_hash",
    )
    if any(not route.get(field) for field in required_route_fields):
        reasons.append("partial_matched_route")
    return sorted(set(reasons))


def evaluate_l1_readiness(
    registration: dict[str, Any],
    cohort: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Verify prospective study readiness without making a benefit claim."""

    protocol_reasons = _protocol_reasons(registration)
    expected_hash = registration_digest(registration)
    submitted_hash = registration.get("registration_hash")
    reason_codes = list(protocol_reasons)
    case_receipts: list[dict[str, Any]] = []
    duplicate_units: set[str] = set()
    cases: list[dict[str, Any]] = []

    if cohort is None:
        reason_codes.append("no_independently_timed_cohort_submitted")
    else:
        if cohort.get("contract_version") != COHORT_CONTRACT:
            reason_codes.append("unsupported_cohort_contract")
        if cohort.get("registration_id") != registration.get("registration_id"):
            reason_codes.append("cohort_registration_identity_mismatch")
        if cohort.get("registration_hash") != submitted_hash:
            reason_codes.append("cohort_registration_hash_mismatch")
        raw_cases = cohort.get("cases")
        if not isinstance(raw_cases, list):
            reason_codes.append("invalid_cohort_cases")
        else:
            cases = [case for case in raw_cases[:MAX_CASES] if isinstance(case, dict)]
            if len(raw_cases) > MAX_CASES:
                reason_codes.append("case_limit_exceeded")
            first_decision = _timestamp(registration.get("first_decision_not_before"))
            if first_decision is None:
                first_decision = datetime.max.replace(tzinfo=timezone.utc)
            seen_units: set[str] = set()
            for index, case in enumerate(cases):
                case_reasons = _case_reasons(case, first_decision)
                unit = str(case.get("allocation_unit_hash") or "")
                if unit and unit in seen_units:
                    case_reasons.append("overlapping_allocation_unit")
                    duplicate_units.add(unit)
                seen_units.add(unit)
                case_receipts.append(
                    {
                        "case_id": _text(case.get("case_id") or f"case:{index + 1}"),
                        "cluster_id": _text(case.get("cluster_id")) or None,
                        "eligible": not case_reasons,
                        "reason_codes": sorted(set(case_reasons)),
                    }
                )
            integrity_reasons = {
                "decision_predates_preregistration",
                "overlapping_allocation_unit",
            }
            if any(integrity_reasons.intersection(item["reason_codes"]) for item in case_receipts):
                reason_codes.append("cohort_integrity_violation")

    eligible = [item for item in case_receipts if item["eligible"]]
    cluster_count = len({item["cluster_id"] for item in eligible if item["cluster_id"]})
    if cohort is not None:
        if len(eligible) < MIN_COMPLETE_CASES:
            reason_codes.append("insufficient_complete_cases")
        if cluster_count < MIN_INDEPENDENT_CLUSTERS:
            reason_codes.append("insufficient_independent_clusters")
        declared_failures = cohort.get("failure_cases") if isinstance(cohort.get("failure_cases"), list) else []
        declared_failure_ids = [
            item.get("kind") for item in declared_failures if isinstance(item, dict) and item.get("observed") is True
        ]
        missing_failure_cases = [item for item in REQUIRED_FAILURE_CASES if item not in declared_failure_ids]
        if missing_failure_cases:
            reason_codes.append("required_failure_coverage_missing")
    else:
        missing_failure_cases = list(REQUIRED_FAILURE_CASES)

    reason_codes = sorted(set(reason_codes))
    protocol_valid = not protocol_reasons
    analysis_ready = cohort is not None and protocol_valid and not reason_codes
    if not protocol_valid:
        state = "invalid_preregistration"
    elif cohort is None:
        state = "collection_not_started"
    elif analysis_ready:
        state = "ready_for_frozen_analysis"
    else:
        state = "cohort_ineligible"

    return {
        "contract_version": READINESS_CONTRACT,
        "registration_id": _text(registration.get("registration_id")) or None,
        "registration_hash": _text(submitted_hash, 200) or None,
        "computed_registration_hash": expected_hash,
        "state": state,
        "protocol_valid": protocol_valid,
        "analysis_ready": analysis_ready,
        "beneficial_impact_evaluated": False,
        "beneficial_impact_supported": False,
        "reason_codes": reason_codes,
        "sample": {
            "submitted_case_count": len(cases),
            "eligible_case_count": len(eligible),
            "independent_cluster_count": cluster_count,
            "duplicate_allocation_units": sorted(_text(item, 200) for item in duplicate_units),
            "minimum_complete_cases": MIN_COMPLETE_CASES,
            "minimum_independent_clusters": MIN_INDEPENDENT_CLUSTERS,
            "maximum_cases": MAX_CASES,
        },
        "missing_required_failure_cases": missing_failure_cases,
        "cases": case_receipts,
        "limitations": [
            "A valid preregistration is study-readiness evidence, not evidence of benefit.",
            "The intake checks provenance completeness; they do not independently prove that a receipt is truthful.",
            "No outcome comparison is computed until one fixed, independently timed cohort closes.",
            "Passing intake cannot establish correctness, causality, generality, or product benefit.",
        ],
    }


__all__ = [
    "COHORT_CONTRACT",
    "MAX_CASES",
    "MIN_COMPLETE_CASES",
    "MIN_INDEPENDENT_CLUSTERS",
    "PREREGISTRATION_CONTRACT",
    "READINESS_CONTRACT",
    "evaluate_l1_readiness",
    "registration_digest",
]
