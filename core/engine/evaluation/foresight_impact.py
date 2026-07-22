"""Bounded, sample-aware evaluation of later use of resolved foresight.

This module evaluates ACE; it is not a second outcome store or an execution
surface.  The evaluator accepts already-frozen, provenance-bearing cases and
computes every score itself.  A favorable mean is never enough: a supported
benefit claim requires all declared controls, cluster-aware uncertainty that
excludes zero, complete pre-outcome lineage, and adequate attribution.
"""

from __future__ import annotations

import hashlib
import json
import math
import re
from statistics import mean, stdev
from typing import Any

CONTRACT_VERSION = "ace.foresight.impact-evaluation/v1"
REQUIRED_ARMS = ("ace_foresight", "no_foresight", "naive_base_rate", "model_only")
REQUIRED_CONTROLS = REQUIRED_ARMS[1:]
MAX_CASES = 256
MIN_CASES = 30
MIN_CLUSTERS = 8
SUPPORTED_SCORE = "continuous_absolute_error/v1"
ATTRIBUTION_SUPPORTING_STATES = frozenset({"randomized_verified", "quasi_experimental_supported"})
_CREDENTIAL = re.compile(r"(?i)\b(bearer|api[_-]?key|token|password|secret)\b\s*[:=]?\s*[^\s,;]+")


def _hash(value: object) -> str:
    payload = json.dumps(value, sort_keys=True, separators=(",", ":"), default=str)
    return "sha256:" + hashlib.sha256(payload.encode("utf-8")).hexdigest()


def _finite(value: object) -> float | None:
    if isinstance(value, bool):
        return None
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    return number if math.isfinite(number) else None


def _text(value: object, limit: int = 240) -> str:
    return _CREDENTIAL.sub("[REDACTED]", " ".join(str(value or "").split()))[:limit]


def _critical_95(degrees_of_freedom: int) -> float:
    """Conservative two-sided 95% Student-t critical value.

    The small table avoids an optional scipy dependency. Values between table
    entries use the next smaller degree of freedom, which is conservative.
    """

    table = {
        1: 12.706,
        2: 4.303,
        3: 3.182,
        4: 2.776,
        5: 2.571,
        6: 2.447,
        7: 2.365,
        8: 2.306,
        9: 2.262,
        10: 2.228,
        12: 2.179,
        15: 2.131,
        20: 2.086,
        25: 2.060,
        30: 2.042,
        40: 2.021,
        60: 2.000,
        120: 1.980,
    }
    df = max(1, int(degrees_of_freedom))
    eligible = [key for key in table if key <= df]
    return table[max(eligible)] if eligible else table[1]


def _confidence_interval(values: list[float]) -> dict[str, float | int | None]:
    count = len(values)
    if not count:
        return {"count": 0, "mean": None, "standard_error": None, "lower_95": None, "upper_95": None}
    center = mean(values)
    if count == 1:
        return {
            "count": 1,
            "mean": center,
            "standard_error": None,
            "lower_95": None,
            "upper_95": None,
        }
    standard_error = stdev(values) / math.sqrt(count)
    margin = _critical_95(count - 1) * standard_error
    return {
        "count": count,
        "mean": center,
        "standard_error": standard_error,
        "lower_95": center - margin,
        "upper_95": center + margin,
    }


def _arm(case: dict[str, Any], name: str) -> dict[str, Any] | None:
    arms = case.get("arms")
    value = arms.get(name) if isinstance(arms, dict) else None
    return value if isinstance(value, dict) else None


def _case_projection(case: dict[str, Any], index: int) -> dict[str, Any]:
    case_id = _text(case.get("case_id") or f"case:{index + 1}", 160)
    cluster_id = _text(case.get("cluster_id"), 160)
    outcome = case.get("outcome") if isinstance(case.get("outcome"), dict) else {}
    actual = _finite(outcome.get("value"))
    reason_codes: list[str] = []
    if not cluster_id:
        reason_codes.append("missing_cluster_identity")
    if not str(outcome.get("outcome_id") or ""):
        reason_codes.append("missing_outcome_identity")
    if not str(outcome.get("observed_at") or ""):
        reason_codes.append("missing_outcome_time")
    if not (outcome.get("evidence_refs") or []):
        reason_codes.append("missing_outcome_provenance")
    if outcome.get("resolution_eligible") is not True:
        reason_codes.append("outcome_not_resolution_eligible")
    if actual is None:
        reason_codes.append("invalid_outcome_value")

    scores: dict[str, dict[str, Any]] = {}
    for name in REQUIRED_ARMS:
        arm = _arm(case, name)
        if arm is None:
            reason_codes.append(f"missing_{name}_arm")
            continue
        prediction = _finite(arm.get("prediction"))
        if prediction is None:
            reason_codes.append(f"invalid_{name}_prediction")
            continue
        if actual is not None:
            scores[name] = {
                "prediction": prediction,
                "absolute_error": abs(prediction - actual),
            }

    treatment = _arm(case, "ace_foresight") or {}
    source_resolutions = treatment.get("source_resolutions")
    if not isinstance(source_resolutions, list) or not source_resolutions:
        reason_codes.append("missing_resolved_foresight_lineage")
    else:
        for source in source_resolutions[:16]:
            if not isinstance(source, dict) or not source.get("resolution_id") or not source.get("resolved_at"):
                reason_codes.append("partial_resolved_foresight_lineage")
                break
            if str(source.get("resolved_at")) >= str(outcome.get("observed_at") or ""):
                reason_codes.append("post_outcome_or_ambiguous_foresight_source")
                break
    if treatment.get("material_use") is not True:
        reason_codes.append("foresight_material_use_not_established")

    matching = case.get("matching") if isinstance(case.get("matching"), dict) else {}

    return {
        "case_id": case_id,
        "cluster_id": cluster_id or None,
        "eligible": not reason_codes,
        "reason_codes": sorted(set(reason_codes)),
        "outcome": {
            "outcome_id": _text(outcome.get("outcome_id"), 200) or None,
            "value": actual,
            "observed_at": str(outcome.get("observed_at") or "")[:120] or None,
            "evidence_refs": [_text(item, 200) for item in (outcome.get("evidence_refs") or [])[:16]],
        },
        "scores": scores,
        "model_comparison": {
            "state": str(matching.get("state") or "unreported")[:80],
            "provider": _text(matching.get("provider"), 160) or None,
            "model": _text(matching.get("model"), 160) or None,
            "configuration_hash": _text(matching.get("configuration_hash"), 200) or None,
        },
    }


def _comparison(cases: list[dict[str, Any]], control: str) -> dict[str, Any]:
    eligible = [
        case
        for case in cases
        if case["eligible"]
        and "ace_foresight" in case["scores"]
        and control in case["scores"]
        and (control != "model_only" or case["model_comparison"]["state"] == "matched")
    ]
    paired = [
        case["scores"][control]["absolute_error"] - case["scores"]["ace_foresight"]["absolute_error"]
        for case in eligible
    ]
    clusters: dict[str, list[float]] = {}
    for case, delta in zip(eligible, paired, strict=True):
        clusters.setdefault(str(case["cluster_id"]), []).append(float(delta))
    cluster_means = [mean(values) for _, values in sorted(clusters.items())]
    interval = _confidence_interval(cluster_means)
    lower = interval["lower_95"]
    supported = (
        len(eligible) >= MIN_CASES and len(clusters) >= MIN_CLUSTERS and isinstance(lower, float) and lower > 0.0
    )
    if len(eligible) < MIN_CASES:
        reason = "insufficient_case_count"
    elif len(clusters) < MIN_CLUSTERS:
        reason = "insufficient_independent_clusters"
    elif lower is None:
        reason = "uncertainty_not_estimable"
    elif lower <= 0.0:
        reason = "cluster_adjusted_interval_includes_no_benefit"
    else:
        reason = None
    ace_errors = [case["scores"]["ace_foresight"]["absolute_error"] for case in eligible]
    control_errors = [case["scores"][control]["absolute_error"] for case in eligible]
    return {
        "control": control,
        "state": "benefit_supported" if supported else "benefit_not_established",
        "reason": reason,
        "direction": "positive_delta_favors_ace_foresight",
        "case_count": len(eligible),
        "cluster_count": len(clusters),
        "ace_mean_absolute_error": mean(ace_errors) if ace_errors else None,
        "control_mean_absolute_error": mean(control_errors) if control_errors else None,
        "mean_error_reduction": mean(paired) if paired else None,
        "wins": sum(delta > 0 for delta in paired),
        "ties": sum(delta == 0 for delta in paired),
        "losses": sum(delta < 0 for delta in paired),
        "cluster_adjusted_95_percent_interval": interval,
        "benefit_supported": supported,
    }


def evaluate_foresight_impact(study: dict[str, Any]) -> dict[str, Any]:
    """Return a bounded L1 evaluation without inventing missing evidence."""

    score_contract = study.get("score_contract") if isinstance(study.get("score_contract"), dict) else {}
    raw_cases = study.get("cases") if isinstance(study.get("cases"), list) else []
    bounded_cases = raw_cases[:MAX_CASES]
    cases = [_case_projection(case, index) for index, case in enumerate(bounded_cases) if isinstance(case, dict)]
    comparisons = [_comparison(cases, control) for control in REQUIRED_CONTROLS]
    attribution = study.get("attribution") if isinstance(study.get("attribution"), dict) else {}
    attribution_state = str(attribution.get("state") or "unreported")
    score_supported = score_contract.get("method") == SUPPORTED_SCORE
    complete_cases = [case for case in cases if case["eligible"]]
    reasons: list[str] = []
    if not score_supported:
        reasons.append("unsupported_score_contract")
    if len(raw_cases) > MAX_CASES:
        reasons.append("case_limit_exceeded")
    if len(complete_cases) < MIN_CASES:
        reasons.append("insufficient_complete_cases")
    if any(not comparison["benefit_supported"] for comparison in comparisons):
        reasons.append("benefit_not_supported_against_every_required_control")
    if attribution_state not in ATTRIBUTION_SUPPORTING_STATES:
        reasons.append("intervention_or_confounder_attribution_not_supported")

    supported = not reasons
    invalid_reason_counts: dict[str, int] = {}
    for case in cases:
        for reason in case["reason_codes"]:
            invalid_reason_counts[reason] = invalid_reason_counts.get(reason, 0) + 1

    return {
        "contract_version": CONTRACT_VERSION,
        "evaluation_id": "impact-evaluation:"
        + _hash(
            {
                "scenario_id": study.get("scenario_id"),
                "case_ids": [case["case_id"] for case in cases],
                "score_contract": score_contract,
            }
        ).split(":", 1)[1][:32],
        "scenario_id": str(study.get("scenario_id") or "")[:160] or None,
        "state": "benefit_supported" if supported else "benefit_not_established",
        "beneficial_impact_supported": supported,
        "reason_codes": sorted(set(reasons)),
        "claim": (
            "Resolved foresight beneficially improved the declared later decision-quality outcome "
            "against every required control."
            if supported
            else "The bounded evidence does not establish that resolved foresight beneficially improved later decisions."
        ),
        "score_contract": {
            "method": score_contract.get("method"),
            "metric": score_contract.get("metric"),
            "direction": "lower_absolute_error_is_better",
            "supported": score_supported,
        },
        "sample": {
            "submitted_case_count": min(len(raw_cases), MAX_CASES),
            "complete_case_count": len(complete_cases),
            "ineligible_case_count": len(cases) - len(complete_cases),
            "minimum_case_count": MIN_CASES,
            "minimum_independent_clusters": MIN_CLUSTERS,
            "invalid_reason_counts": invalid_reason_counts,
        },
        "comparisons": comparisons,
        "attribution": {
            "state": attribution_state,
            "supported_for_benefit_claim": attribution_state in ATTRIBUTION_SUPPORTING_STATES,
            "intervention_identity": attribution.get("intervention_identity"),
            "assignment": attribution.get("assignment"),
            "confounders": [_text(item, 240) for item in (attribution.get("confounders") or [])[:32]],
            "limitations": [_text(item, 400) for item in (attribution.get("limitations") or [])[:32]],
        },
        "cases": cases,
        "required_controls": list(REQUIRED_CONTROLS),
        "limitations": [
            "Material use and a favorable average do not establish beneficial impact.",
            "Cluster-adjusted uncertainty is computed over declared independent clusters.",
            "Retrospective predictive evidence does not identify an intervention effect.",
            "Every required control must pass; favorable subset selection is not allowed.",
        ],
    }
