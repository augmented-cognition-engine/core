"""Ground forecasts in bounded, product-scoped settled analogue reference classes.

The outside view is deliberately observational. It summarizes what happened after similar
interventions in the same product; it does not pretend those outcomes identify a no-action
counterfactual or establish causality. Forecasts retain the selected case IDs, deterministic
similarity features, sufficiency state, and limitations so the prior can be audited later.
"""

from __future__ import annotations

import datetime as dt
import logging
import math
from typing import Any

from core.engine.core.db import parse_rows
from core.engine.foresight.contracts import OUTSIDE_VIEW_BASELINE_VERSION

logger = logging.getLogger(__name__)

MAX_CANDIDATES = 200
MAX_ANALOGUES = 12
MIN_PROVISIONAL_CASES = 3
MIN_SUPPORTED_CASES = 8
MIN_SUPPORTED_EFFECTIVE_SAMPLE_SIZE = 5.0
MIN_SUPPORTED_MEAN_SIMILARITY = 0.4
MAX_SUPPORTED_90_CI_HALF_WIDTH = 0.25
SCORABLE_STATES = frozenset({"confirmed", "contradicted", "mixed"})

_LIMITATIONS = [
    "Observational settled interventions do not identify a causal effect.",
    "The reference class is isolated to this product and may be sparse.",
    "Similarity uses capability overlap, discipline, and horizon only.",
    "Unrecorded context, exposure differences, and confounding may remain.",
    "This intervention reference class is not a no-action counterfactual.",
]


def _finite(value: object) -> float | None:
    if isinstance(value, bool):
        return None
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    return number if math.isfinite(number) else None


def _finite_deltas(value: object) -> dict[str, float]:
    if not isinstance(value, dict):
        return {}
    deltas: dict[str, float] = {}
    for raw_key, raw_value in list(value.items())[:50]:
        key = str(raw_key).strip()[:240]
        number = _finite(raw_value)
        if key and number is not None:
            deltas[key] = max(-1.0, min(1.0, number))
    return deltas


def _iso(value: object) -> str | None:
    if value is None:
        return None
    if isinstance(value, dt.datetime):
        parsed = value
    else:
        text = str(value).strip()
        if not text:
            return None
        try:
            parsed = dt.datetime.fromisoformat(text.replace("Z", "+00:00"))
        except ValueError:
            return text[:120]
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=dt.timezone.utc)
    return parsed.astimezone(dt.timezone.utc).isoformat().replace("+00:00", "Z")


def _datetime(value: object) -> dt.datetime | None:
    if isinstance(value, dt.datetime):
        parsed = value
    elif value is not None:
        try:
            parsed = dt.datetime.fromisoformat(str(value).strip().replace("Z", "+00:00"))
        except ValueError:
            return None
    else:
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=dt.timezone.utc)
    return parsed.astimezone(dt.timezone.utc)


def _empty_baseline(*, product_id: str, retrieved_at: object, state: str, reason: str) -> dict[str, Any]:
    return {
        "contract_version": OUTSIDE_VIEW_BASELINE_VERSION,
        "state": state,
        "reason": reason,
        "reference_class": {
            "kind": "settled_intervention_outcomes",
            "product_id": str(product_id)[:240],
            "isolation": "same_product_only",
            "eligibility": [
                "score_eligible",
                "applicability_conditions_met",
                "settled_resolution_state",
                "overlapping_target_capability",
                "closed_before_retrieval",
            ],
        },
        "retrieved_at": _iso(retrieved_at),
        "sample": {
            "candidate_count": 0,
            "eligible_count": 0,
            "selected_count": 0,
            "target_count": 0,
            "anecdotal_target_count": 0,
            "provisional_target_count": 0,
            "supported_target_count": 0,
            "minimum_cases_for_provisional": MIN_PROVISIONAL_CASES,
            "supported_criteria": {
                "minimum_raw_cases": MIN_SUPPORTED_CASES,
                "minimum_effective_sample_size": MIN_SUPPORTED_EFFECTIVE_SAMPLE_SIZE,
                "minimum_mean_similarity": MIN_SUPPORTED_MEAN_SIMILARITY,
                "maximum_90_percent_interval_half_width": MAX_SUPPORTED_90_CI_HALF_WIDTH,
            },
        },
        "target_priors": {},
        "analogues": [],
        "no_action_counterfactual": {
            "state": "not_identified",
            "reason": "settled_intervention_cases_do_not_supply_a_no_action_comparator",
        },
        "limitations": list(_LIMITATIONS),
        "provenance": {"source_kind": "settled_prediction_outcomes", "outcome_refs": []},
    }


def unavailable_outside_view(*, product_id: str, reason: str, retrieved_at: object | None = None) -> dict[str, Any]:
    """Return an explicit unavailable projection instead of fabricating a prior."""
    return _empty_baseline(
        product_id=product_id,
        retrieved_at=retrieved_at or dt.datetime.now(dt.timezone.utc),
        state="unavailable",
        reason=reason,
    )


def _similarity(
    *,
    targets: set[str],
    case_targets: set[str],
    discipline: str,
    case_discipline: str,
    horizon_days: int,
    case_horizon_days: int | None,
) -> tuple[float, dict[str, Any]]:
    union = targets | case_targets
    overlap = targets & case_targets
    capability_overlap = len(overlap) / len(union) if union else 0.0
    discipline_match = 1.0 if discipline and discipline == case_discipline else 0.0
    if case_horizon_days is None:
        horizon_similarity = 0.0
    else:
        horizon_similarity = 1.0 - min(
            abs(horizon_days - case_horizon_days) / max(horizon_days, case_horizon_days, 1),
            1.0,
        )
    score = 0.70 * capability_overlap + 0.20 * discipline_match + 0.10 * horizon_similarity
    return round(score, 6), {
        "capability_overlap": round(capability_overlap, 6),
        "overlapping_capabilities": sorted(overlap),
        "discipline_match": bool(discipline_match),
        "horizon_similarity": round(horizon_similarity, 6),
    }


def build_outside_view_baseline(
    *,
    product_id: str,
    target_capability_ids: list[str],
    discipline: str,
    horizon_days: int,
    candidates: list[dict[str, Any]],
    retrieved_at: object,
    exclude_prediction_id: str | None = None,
) -> dict[str, Any]:
    """Build a deterministic empirical prior from eligible settled outcomes."""
    targets = {str(item).strip()[:240] for item in target_capability_ids if str(item).strip()}
    baseline = _empty_baseline(
        product_id=product_id,
        retrieved_at=retrieved_at,
        state="cold_start",
        reason="no_eligible_settled_analogues",
    )
    baseline["sample"]["candidate_count"] = min(len(candidates), MAX_CANDIDATES)
    baseline["sample"]["target_count"] = len(targets)
    if not targets:
        baseline["reason"] = "no_target_capabilities"
        return baseline

    ranked: list[dict[str, Any]] = []
    retrieval_time = _datetime(retrieved_at)
    seen_predictions: set[str] = set()
    for row in candidates[:MAX_CANDIDATES]:
        if not isinstance(row, dict):
            continue
        prediction_id = str(row.get("prediction", ""))[:240]
        if exclude_prediction_id and prediction_id == exclude_prediction_id:
            continue
        if not prediction_id or prediction_id in seen_predictions:
            continue
        row_product = str(row.get("product", product_id))
        if row_product and row_product != product_id:
            continue
        if row.get("score_eligible") is not True or row.get("applicability_conditions_met") is not True:
            continue
        if row.get("resolution_state") not in SCORABLE_STATES:
            continue
        closed_at = _datetime(row.get("closed_at"))
        if closed_at is None or (retrieval_time is not None and closed_at > retrieval_time):
            continue
        actual_deltas = _finite_deltas(row.get("actual_deltas"))
        if not actual_deltas or not targets.intersection(actual_deltas):
            continue
        case_horizon_number = _finite(row.get("horizon_days"))
        case_horizon = int(case_horizon_number) if case_horizon_number is not None else None
        similarity, features = _similarity(
            targets=targets,
            case_targets=set(actual_deltas),
            discipline=str(discipline),
            case_discipline=str(row.get("discipline", "")),
            horizon_days=max(1, int(horizon_days)),
            case_horizon_days=case_horizon,
        )
        if similarity <= 0.0:
            continue
        seen_predictions.add(prediction_id)
        ranked.append(
            {
                "outcome_id": str(row.get("id", ""))[:240],
                "prediction_id": prediction_id,
                "decision_id": str(row.get("decision", ""))[:240],
                "closed_at": _iso(closed_at),
                "resolution_state": row.get("resolution_state"),
                "discipline": str(row.get("discipline", ""))[:160],
                "horizon_days": case_horizon,
                "similarity": similarity,
                "similarity_features": features,
                "actual_deltas": actual_deltas,
            }
        )

    baseline["sample"]["eligible_count"] = len(ranked)
    ranked.sort(key=lambda case: (str(case.get("closed_at") or ""), str(case.get("outcome_id") or "")), reverse=True)
    ranked.sort(key=lambda case: float(case["similarity"]), reverse=True)
    selected = ranked[:MAX_ANALOGUES]
    baseline["analogues"] = selected
    baseline["sample"]["selected_count"] = len(selected)
    baseline["provenance"]["outcome_refs"] = [case["outcome_id"] for case in selected if case["outcome_id"]]
    if not selected:
        return baseline

    priors: dict[str, dict[str, Any]] = {}
    maturity_counts = {"anecdotal": 0, "provisional": 0, "supported": 0}
    for target in sorted(targets):
        observations = [
            (float(case["actual_deltas"][target]), float(case["similarity"]))
            for case in selected
            if target in case["actual_deltas"] and float(case["similarity"]) > 0.0
        ]
        if not observations:
            continue
        weight_sum = sum(weight for _, weight in observations)
        values = [value for value, _ in observations]
        weighted_mean = sum(value * weight for value, weight in observations) / weight_sum
        effective_n = weight_sum**2 / sum(weight**2 for _, weight in observations)
        case_count = len(observations)
        mean_similarity = weight_sum / case_count
        weighted_variance = sum(weight * (value - weighted_mean) ** 2 for value, weight in observations) / weight_sum
        standard_error = math.sqrt(weighted_variance / max(effective_n, 1.0))
        interval_half_width = 1.645 * standard_error
        if (
            case_count >= MIN_SUPPORTED_CASES
            and effective_n >= MIN_SUPPORTED_EFFECTIVE_SAMPLE_SIZE
            and mean_similarity >= MIN_SUPPORTED_MEAN_SIMILARITY
            and interval_half_width <= MAX_SUPPORTED_90_CI_HALF_WIDTH
        ):
            maturity = "supported"
        elif case_count >= MIN_PROVISIONAL_CASES:
            maturity = "provisional"
        else:
            maturity = "anecdotal"
        maturity_counts[maturity] += 1
        priors[target] = {
            "case_count": case_count,
            "effective_sample_size": round(effective_n, 6),
            "mean_similarity": round(mean_similarity, 6),
            "weighted_mean_actual_delta": round(weighted_mean, 6),
            "observed_range": {"lower": min(values), "upper": max(values)},
            "weighted_standard_deviation": round(math.sqrt(weighted_variance), 6),
            "standard_error": round(standard_error, 6),
            "uncertainty_90_percent": {
                "lower": round(max(-1.0, weighted_mean - interval_half_width), 6),
                "upper": round(min(1.0, weighted_mean + interval_half_width), 6),
                "half_width": round(interval_half_width, 6),
            },
            "maturity": maturity,
        }

    baseline["target_priors"] = priors
    for maturity, count in maturity_counts.items():
        baseline["sample"][f"{maturity}_target_count"] = count
    if maturity_counts["supported"] == len(targets):
        baseline["state"] = "supported"
        baseline["reason"] = None
    elif maturity_counts["supported"] or maturity_counts["provisional"]:
        baseline["state"] = "provisional"
        baseline["reason"] = "local_reference_is_descriptive_not_decision_grade"
    else:
        baseline["state"] = "anecdotal"
        baseline["reason"] = "fewer_than_three_settled_cases_per_target"
    return baseline


async def load_outside_view_baseline(
    *,
    product_id: str,
    target_capability_ids: list[str],
    discipline: str,
    horizon_days: int,
    pool,
    exclude_prediction_id: str | None = None,
) -> dict[str, Any]:
    """Load product-scoped candidates and return a non-blocking outside-view projection."""
    retrieved_at = dt.datetime.now(dt.timezone.utc)
    try:
        async with pool.connection() as db:
            outcomes = parse_rows(
                await db.query(
                    """SELECT id, prediction, decision, product, discipline,
                              resolution_state, score_eligible,
                              applicability_conditions_met, actual_deltas, closed_at
                       FROM prediction_outcome
                       WHERE product = <record>$product
                       ORDER BY closed_at DESC LIMIT $limit""",
                    {"product": product_id, "limit": MAX_CANDIDATES},
                )
            )
            predictions = parse_rows(
                await db.query(
                    """SELECT id, horizon_days FROM decision_prediction
                       WHERE product = <record>$product AND closed = true
                       ORDER BY created_at DESC LIMIT $limit""",
                    {"product": product_id, "limit": MAX_CANDIDATES},
                )
            )
        horizons = {str(row.get("id", "")): row.get("horizon_days") for row in predictions}
        candidates = [{**row, "horizon_days": horizons.get(str(row.get("prediction", "")))} for row in outcomes]
        return build_outside_view_baseline(
            product_id=product_id,
            target_capability_ids=target_capability_ids,
            discipline=discipline,
            horizon_days=horizon_days,
            candidates=candidates,
            retrieved_at=retrieved_at,
            exclude_prediction_id=exclude_prediction_id,
        )
    except Exception:
        logger.warning("Outside-view retrieval failed for %s", product_id, exc_info=True)
        return unavailable_outside_view(
            product_id=product_id,
            reason="settled_analogue_retrieval_failed",
            retrieved_at=retrieved_at,
        )


def attach_projection_comparison(baseline: dict[str, Any], *, predicted_deltas: dict[str, float]) -> dict[str, Any]:
    """Expose model/outside-view disagreement without blending the independent views."""
    comparison: dict[str, Any] = {
        "state": "unavailable",
        "reason": f"outside_view_{baseline.get('state', 'unknown')}",
        "aggregation_applied": False,
        "targets": [],
    }
    if baseline.get("state") not in {"provisional", "supported"}:
        return {**baseline, "projection_comparison": comparison}
    priors = baseline.get("target_priors")
    if not isinstance(priors, dict):
        return {**baseline, "projection_comparison": comparison}
    targets: list[dict[str, Any]] = []
    for target in sorted(set(predicted_deltas) & set(priors)):
        prior = priors.get(target)
        predicted = _finite(predicted_deltas.get(target))
        outside_delta = _finite(prior.get("weighted_mean_actual_delta")) if isinstance(prior, dict) else None
        if predicted is None or outside_delta is None:
            continue
        difference = predicted - outside_delta
        targets.append(
            {
                "capability_id": target,
                "model_predicted_delta": predicted,
                "outside_view_delta": outside_delta,
                "difference": round(difference, 6),
                "absolute_difference": round(abs(difference), 6),
                "direction": "aligned"
                if abs(difference) <= 1e-9
                else ("model_higher" if difference > 0 else "model_lower"),
            }
        )
    if targets:
        comparison = {
            "state": "available",
            "reason": None,
            "aggregation_applied": False,
            "evidence_maturity": baseline.get("state"),
            "target_count": len(targets),
            "targets": targets,
        }
    else:
        comparison["reason"] = "no_comparable_forecast_targets"
    return {**baseline, "projection_comparison": comparison}


def compare_forecast_to_outside_view(
    *,
    forecast_contract: dict[str, Any] | None,
    predicted_deltas: dict[str, float],
    actual_deltas: dict[str, float],
) -> dict[str, Any]:
    """Compare model and frozen outside-view errors without claiming a proper score."""
    baseline = (forecast_contract or {}).get("baseline")
    outside_view = baseline.get("outside_view") if isinstance(baseline, dict) else None
    if not isinstance(outside_view, dict):
        return {
            "contract_version": OUTSIDE_VIEW_BASELINE_VERSION,
            "state": "unscored",
            "reason": "forecast_has_no_frozen_outside_view",
            "method": "mean_absolute_delta_error/v1",
        }
    if outside_view.get("state") not in {"provisional", "supported"}:
        return {
            "contract_version": OUTSIDE_VIEW_BASELINE_VERSION,
            "state": "unscored",
            "reason": f"outside_view_{outside_view.get('state', 'unknown')}",
            "method": "mean_absolute_delta_error/v1",
        }
    priors = outside_view.get("target_priors")
    if not isinstance(priors, dict):
        priors = {}
    comparisons: list[dict[str, Any]] = []
    for target in sorted(set(predicted_deltas) & set(actual_deltas) & set(priors)):
        prior = priors.get(target)
        outside_delta = _finite(prior.get("weighted_mean_actual_delta")) if isinstance(prior, dict) else None
        predicted = _finite(predicted_deltas.get(target))
        actual = _finite(actual_deltas.get(target))
        if outside_delta is None or predicted is None or actual is None:
            continue
        comparisons.append(
            {
                "capability_id": target,
                "predicted_delta": predicted,
                "outside_view_delta": outside_delta,
                "actual_delta": actual,
                "model_absolute_error": abs(predicted - actual),
                "outside_view_absolute_error": abs(outside_delta - actual),
            }
        )
    if not comparisons:
        return {
            "contract_version": OUTSIDE_VIEW_BASELINE_VERSION,
            "state": "unscored",
            "reason": "no_comparable_resolved_targets",
            "method": "mean_absolute_delta_error/v1",
        }
    model_error = sum(item["model_absolute_error"] for item in comparisons) / len(comparisons)
    outside_error = sum(item["outside_view_absolute_error"] for item in comparisons) / len(comparisons)
    advantage = outside_error - model_error
    if abs(advantage) <= 1e-9:
        winner = "tie"
    elif advantage > 0:
        winner = "model_forecast"
    else:
        winner = "outside_view"
    return {
        "contract_version": OUTSIDE_VIEW_BASELINE_VERSION,
        "state": "scored",
        "reason": None,
        "method": "mean_absolute_delta_error/v1",
        "proper_score": False,
        "evidence_maturity": outside_view.get("state"),
        "target_count": len(comparisons),
        "model_mean_absolute_error": round(model_error, 6),
        "outside_view_mean_absolute_error": round(outside_error, 6),
        "model_advantage": round(advantage, 6),
        "winner": winner,
        "targets": comparisons,
        "limitations": [
            "This diagnostic uses the existing bounded numeric delta representation.",
            "It is not a prediction-type-specific proper scoring rule.",
        ],
    }
