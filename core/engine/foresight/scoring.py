"""Typed, deterministic scoring for resolved foresight consequences.

Lower interval scores are better. Missing interval semantics, unsupported prediction types, and
ineligible resolutions abstain explicitly; legacy calibration remains a separate compatibility
diagnostic and is never relabeled as a proper score.
"""

from __future__ import annotations

import math
from statistics import NormalDist
from typing import Any

from core.engine.foresight.contracts import PREDICTION_SCORE_VERSION


def _finite(value: object) -> float | None:
    if isinstance(value, bool):
        return None
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    return number if math.isfinite(number) else None


def continuous_interval_score(*, lower: float, upper: float, coverage: float, actual: float) -> float:
    """Return the proper central interval score for one continuous observation."""
    values = (lower, upper, coverage, actual)
    if not all(math.isfinite(value) for value in values):
        raise ValueError("interval score inputs must be finite")
    if lower > upper:
        raise ValueError("lower interval bound must not exceed upper bound")
    if not 0.0 < coverage < 1.0:
        raise ValueError("interval coverage must be between zero and one")
    alpha = 1.0 - coverage
    score = upper - lower
    if actual < lower:
        score += (2.0 / alpha) * (lower - actual)
    elif actual > upper:
        score += (2.0 / alpha) * (actual - upper)
    return score


def _abstained(local_id: str, target: str | None, kind: str, reason: str) -> dict[str, Any]:
    return {
        "consequence_id": local_id,
        "target_id": target,
        "prediction_type": kind,
        "state": "unscored",
        "reason": reason,
        "method": None,
        "scores": None,
        "outside_view_score": None,
    }


def _outside_view_score(
    *,
    forecast_contract: dict[str, Any],
    target: str,
    coverage: float,
    actual: float,
) -> dict[str, Any] | None:
    baseline = forecast_contract.get("baseline")
    outside_view = baseline.get("outside_view") if isinstance(baseline, dict) else None
    if not isinstance(outside_view, dict) or outside_view.get("state") not in {"provisional", "supported"}:
        return None
    priors = outside_view.get("target_priors")
    prior = priors.get(target) if isinstance(priors, dict) else None
    if not isinstance(prior, dict):
        return None
    mean = _finite(prior.get("weighted_mean_actual_delta"))
    standard_deviation = _finite(prior.get("weighted_standard_deviation"))
    if mean is None or standard_deviation is None or standard_deviation < 0.0:
        return None
    z = NormalDist().inv_cdf((1.0 + coverage) / 2.0)
    lower = max(-1.0, mean - z * standard_deviation)
    upper = min(1.0, mean + z * standard_deviation)
    score = continuous_interval_score(lower=lower, upper=upper, coverage=coverage, actual=actual)
    return {
        "state": "scored",
        "method": "central_interval_score/v1",
        "predictive_interval_method": "normal_reference_distribution/v1",
        "evidence_maturity": outside_view.get("state"),
        "point": mean,
        "lower": lower,
        "upper": upper,
        "coverage": coverage,
        "interval_score": score,
        "absolute_error": abs(mean - actual),
        "covered": lower <= actual <= upper,
        "interval_width": upper - lower,
    }


def score_prediction(
    *,
    forecast_contract: dict[str, Any] | None,
    actual_deltas: dict[str, float],
    resolution_score_eligible: bool,
    non_score_reason: str | None,
) -> dict[str, Any]:
    """Score every supported consequence in an immutable forecast projection."""
    base = {
        "contract_version": PREDICTION_SCORE_VERSION,
        "state": "unscored",
        "reason": non_score_reason,
        "proper_score_available": False,
        "consequence_scores": [],
        "summary": {
            "consequence_count": 0,
            "scored_count": 0,
            "abstained_count": 0,
            "mean_interval_score": None,
            "mean_absolute_error": None,
            "coverage_rate": None,
            "mean_interval_width": None,
        },
        "comparison": {
            "state": "unscored",
            "reason": "no_comparable_outside_view_scores",
        },
    }
    if not resolution_score_eligible:
        base["reason"] = non_score_reason or "resolution_not_score_eligible"
        return base
    contract = forecast_contract if isinstance(forecast_contract, dict) else {}
    consequences = contract.get("consequences")
    if not isinstance(consequences, list) or not consequences:
        base["reason"] = "forecast_has_no_typed_consequences"
        return base

    results: list[dict[str, Any]] = []
    for index, consequence in enumerate(consequences[:25]):
        if not isinstance(consequence, dict):
            results.append(_abstained(f"consequence:{index + 1}", None, "unknown", "malformed_consequence"))
            continue
        local_id = str(consequence.get("local_id") or f"consequence:{index + 1}")[:120]
        target_spec = consequence.get("target")
        target = str(target_spec.get("entity_id", ""))[:240] if isinstance(target_spec, dict) else ""
        estimate = consequence.get("estimate")
        kind = str(estimate.get("kind", "unknown")) if isinstance(estimate, dict) else "unknown"
        if kind != "continuous":
            results.append(_abstained(local_id, target or None, kind, "unsupported_prediction_type"))
            continue
        actual = _finite(actual_deltas.get(target))
        if actual is None:
            results.append(_abstained(local_id, target or None, kind, "missing_actual_value"))
            continue
        lower = _finite(estimate.get("lower"))
        upper = _finite(estimate.get("upper"))
        coverage = _finite(estimate.get("interval_coverage"))
        point = _finite(estimate.get("point"))
        if lower is None or upper is None:
            results.append(_abstained(local_id, target or None, kind, "missing_interval_bounds"))
            continue
        if coverage is None:
            results.append(_abstained(local_id, target or None, kind, "missing_interval_coverage"))
            continue
        try:
            interval_score = continuous_interval_score(
                lower=lower,
                upper=upper,
                coverage=coverage,
                actual=actual,
            )
        except ValueError as exc:
            results.append(_abstained(local_id, target or None, kind, str(exc).replace(" ", "_")))
            continue
        outside_score = _outside_view_score(
            forecast_contract=contract,
            target=target,
            coverage=coverage,
            actual=actual,
        )
        results.append(
            {
                "consequence_id": local_id,
                "target_id": target,
                "prediction_type": kind,
                "state": "scored",
                "reason": None,
                "method": "central_interval_score/v1",
                "actual": actual,
                "scores": {
                    "interval_coverage": coverage,
                    "interval_score": interval_score,
                    "absolute_error": abs(point - actual) if point is not None else None,
                    "covered": lower <= actual <= upper,
                    "interval_width": upper - lower,
                    "direction": "lower_is_better",
                },
                "outside_view_score": outside_score,
            }
        )

    scored = [item for item in results if item["state"] == "scored"]
    abstained = [item for item in results if item["state"] != "scored"]
    interval_scores = [float(item["scores"]["interval_score"]) for item in scored]
    absolute_errors = [
        float(item["scores"]["absolute_error"]) for item in scored if item["scores"]["absolute_error"] is not None
    ]
    outside_pairs = [item for item in scored if isinstance(item.get("outside_view_score"), dict)]
    if outside_pairs:
        model_mean = sum(float(item["scores"]["interval_score"]) for item in outside_pairs) / len(outside_pairs)
        outside_mean = sum(float(item["outside_view_score"]["interval_score"]) for item in outside_pairs) / len(
            outside_pairs
        )
        comparison = {
            "state": "scored",
            "reason": None,
            "method": "central_interval_score/v1",
            "target_count": len(outside_pairs),
            "model_mean_interval_score": model_mean,
            "outside_view_mean_interval_score": outside_mean,
            "winner": "tie"
            if abs(model_mean - outside_mean) <= 1e-12
            else ("model_forecast" if model_mean < outside_mean else "outside_view"),
            "direction": "lower_is_better",
        }
    else:
        comparison = base["comparison"]
    base.update(
        {
            "state": "scored" if scored and not abstained else ("partial" if scored else "unscored"),
            "reason": None if scored else "no_supported_consequences_scored",
            "proper_score_available": bool(scored),
            "consequence_scores": results,
            "summary": {
                "consequence_count": len(results),
                "scored_count": len(scored),
                "abstained_count": len(abstained),
                "mean_interval_score": sum(interval_scores) / len(interval_scores) if interval_scores else None,
                "mean_absolute_error": sum(absolute_errors) / len(absolute_errors) if absolute_errors else None,
                "coverage_rate": sum(bool(item["scores"]["covered"]) for item in scored) / len(scored)
                if scored
                else None,
                "mean_interval_width": sum(float(item["scores"]["interval_width"]) for item in scored) / len(scored)
                if scored
                else None,
            },
            "comparison": comparison,
        }
    )
    return base


def summarize_prediction_scores(rows: list[dict[str, Any]]) -> dict[str, Any]:
    """Build a product-scoped, sample-aware summary without pooling unlike coverages."""
    groups: dict[str, list[dict[str, Any]]] = {}
    prediction_count = 0
    abstained_count = 0
    for row in rows[:500]:
        score = row.get("prediction_score")
        if not isinstance(score, dict):
            resolution = row.get("resolution_contract")
            scoring = resolution.get("scoring") if isinstance(resolution, dict) else None
            score = scoring.get("prediction_score") if isinstance(scoring, dict) else None
        if not isinstance(score, dict):
            continue
        prediction_count += 1
        for item in score.get("consequence_scores") or []:
            if not isinstance(item, dict) or item.get("state") != "scored":
                abstained_count += 1
                continue
            scores = item.get("scores") or {}
            coverage = _finite(scores.get("interval_coverage"))
            if coverage is None:
                abstained_count += 1
                continue
            groups.setdefault(f"{coverage:.6f}", []).append(scores)

    by_coverage = []
    total_scored = 0
    for key in sorted(groups, key=float):
        items = groups[key]
        total_scored += len(items)
        count = len(items)
        maturity = (
            "cold_start" if count == 0 else "anecdotal" if count < 3 else "provisional" if count < 8 else "supported"
        )
        absolute_errors = [float(item["absolute_error"]) for item in items if item.get("absolute_error") is not None]
        by_coverage.append(
            {
                "interval_coverage": float(key),
                "sample_count": count,
                "evidence_maturity": maturity,
                "mean_interval_score": sum(float(item["interval_score"]) for item in items) / count,
                "coverage_rate": sum(bool(item["covered"]) for item in items) / count,
                "mean_interval_width": sum(float(item["interval_width"]) for item in items) / count,
                "mean_absolute_error": sum(absolute_errors) / len(absolute_errors) if absolute_errors else None,
                "direction": "lower_interval_score_is_better",
            }
        )
    return {
        "contract_version": PREDICTION_SCORE_VERSION,
        "prediction_count": prediction_count,
        "scored_consequence_count": total_scored,
        "abstained_consequence_count": abstained_count,
        "by_interval_coverage": by_coverage,
        "limitations": [
            "Different interval coverages are not pooled into one score.",
            "Small samples remain maturity labels, not statistical-sufficiency claims.",
            "Calibration reliability curves require more resolved forecasts.",
        ],
    }
