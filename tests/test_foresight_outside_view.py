"""Contract and integration evidence for grounded settled-analogue outside views."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

import pytest

from core.engine.foresight.contracts import OUTSIDE_VIEW_BASELINE_VERSION
from core.engine.foresight.outside_view import (
    attach_projection_comparison,
    build_outside_view_baseline,
    compare_forecast_to_outside_view,
    load_outside_view_baseline,
)


def _candidate(
    index: int,
    *,
    product: str = "product:platform",
    capability: str = "auth",
    actual: float = 0.2,
    discipline: str = "testing",
    horizon_days: int = 14,
    score_eligible: bool = True,
    applicable: bool = True,
    state: str = "confirmed",
) -> dict:
    return {
        "id": f"prediction_outcome:o{index}",
        "prediction": f"decision_prediction:p{index}",
        "decision": f"decision:d{index}",
        "product": product,
        "discipline": discipline,
        "resolution_state": state,
        "score_eligible": score_eligible,
        "applicability_conditions_met": applicable,
        "actual_deltas": {capability: actual},
        "horizon_days": horizon_days,
        "closed_at": f"2026-01-{index:02d}T00:00:00Z",
    }


def test_three_matching_settled_cases_form_provisional_weighted_prior() -> None:
    baseline = build_outside_view_baseline(
        product_id="product:platform",
        target_capability_ids=["auth"],
        discipline="testing",
        horizon_days=14,
        candidates=[
            _candidate(1, actual=0.1),
            _candidate(2, actual=0.2),
            _candidate(3, actual=0.3),
        ],
        retrieved_at="2026-02-01T00:00:00Z",
    )

    assert baseline["contract_version"] == OUTSIDE_VIEW_BASELINE_VERSION
    assert baseline["state"] == "provisional"
    assert baseline["sample"]["selected_count"] == 3
    assert baseline["target_priors"]["auth"]["case_count"] == 3
    assert baseline["target_priors"]["auth"]["weighted_mean_actual_delta"] == pytest.approx(0.2)
    assert baseline["target_priors"]["auth"]["maturity"] == "provisional"
    assert baseline["no_action_counterfactual"]["state"] == "not_identified"
    assert "not a no-action counterfactual" in baseline["limitations"][-1]


def test_supported_requires_larger_effective_consistent_sample() -> None:
    baseline = build_outside_view_baseline(
        product_id="product:platform",
        target_capability_ids=["auth"],
        discipline="testing",
        horizon_days=14,
        candidates=[_candidate(index, actual=0.2) for index in range(1, 9)],
        retrieved_at="2026-02-01T00:00:00Z",
    )

    prior = baseline["target_priors"]["auth"]
    assert baseline["state"] == "supported"
    assert prior["maturity"] == "supported"
    assert prior["case_count"] == 8
    assert prior["effective_sample_size"] == pytest.approx(8.0)
    assert prior["uncertainty_90_percent"]["half_width"] == pytest.approx(0.0)


def test_two_case_reference_class_is_anecdotal() -> None:
    baseline = build_outside_view_baseline(
        product_id="product:platform",
        target_capability_ids=["auth"],
        discipline="testing",
        horizon_days=14,
        candidates=[_candidate(1), _candidate(2)],
        retrieved_at="2026-02-01T00:00:00Z",
    )

    assert baseline["state"] == "anecdotal"
    assert baseline["reason"] == "fewer_than_three_settled_cases_per_target"
    assert baseline["target_priors"]["auth"]["maturity"] == "anecdotal"


def test_ineligible_cross_product_and_nonoverlapping_cases_are_excluded() -> None:
    baseline = build_outside_view_baseline(
        product_id="product:platform",
        target_capability_ids=["auth"],
        discipline="testing",
        horizon_days=14,
        candidates=[
            _candidate(1, product="product:other"),
            _candidate(2, capability="billing"),
            _candidate(3, score_eligible=False),
            _candidate(4, applicable=False),
            _candidate(5, state="unresolved"),
        ],
        retrieved_at="2026-02-01T00:00:00Z",
    )

    assert baseline["state"] == "cold_start"
    assert baseline["sample"]["candidate_count"] == 5
    assert baseline["sample"]["eligible_count"] == 0
    assert baseline["analogues"] == []


def test_future_and_duplicate_prediction_outcomes_are_excluded() -> None:
    original = _candidate(1)
    duplicate = {**_candidate(2), "prediction": original["prediction"]}
    future = {**_candidate(3), "closed_at": "2027-01-01T00:00:00Z"}
    baseline = build_outside_view_baseline(
        product_id="product:platform",
        target_capability_ids=["auth"],
        discipline="testing",
        horizon_days=14,
        candidates=[original, duplicate, future],
        retrieved_at="2026-02-01T00:00:00Z",
    )

    assert baseline["sample"]["eligible_count"] == 1
    assert [case["prediction_id"] for case in baseline["analogues"]] == ["decision_prediction:p1"]


def test_ranking_is_deterministic_and_exposes_similarity_features() -> None:
    exact = _candidate(1, horizon_days=14)
    weaker = _candidate(2, discipline="security", horizon_days=30)
    baseline = build_outside_view_baseline(
        product_id="product:platform",
        target_capability_ids=["auth"],
        discipline="testing",
        horizon_days=14,
        candidates=[weaker, exact],
        retrieved_at="2026-02-01T00:00:00Z",
    )

    assert baseline["analogues"][0]["outcome_id"] == "prediction_outcome:o1"
    features = baseline["analogues"][0]["similarity_features"]
    assert features == {
        "capability_overlap": 1.0,
        "overlapping_capabilities": ["auth"],
        "discipline_match": True,
        "horizon_similarity": 1.0,
    }


def test_outside_view_comparison_scores_provisional_prior_as_diagnostic() -> None:
    baseline = build_outside_view_baseline(
        product_id="product:platform",
        target_capability_ids=["auth"],
        discipline="testing",
        horizon_days=14,
        candidates=[
            _candidate(1, actual=0.1),
            _candidate(2, actual=0.2),
            _candidate(3, actual=0.3),
        ],
        retrieved_at="2026-02-01T00:00:00Z",
    )
    comparison = compare_forecast_to_outside_view(
        forecast_contract={"baseline": {"outside_view": baseline}},
        predicted_deltas={"auth": 0.25},
        actual_deltas={"auth": 0.3},
    )

    assert comparison["state"] == "scored"
    assert comparison["proper_score"] is False
    assert comparison["evidence_maturity"] == "provisional"
    assert comparison["model_mean_absolute_error"] == pytest.approx(0.05)
    assert comparison["outside_view_mean_absolute_error"] == pytest.approx(0.1)
    assert comparison["model_advantage"] == pytest.approx(0.05)
    assert comparison["winner"] == "model_forecast"


def test_forecast_time_comparison_exposes_disagreement_without_aggregation() -> None:
    baseline = build_outside_view_baseline(
        product_id="product:platform",
        target_capability_ids=["auth"],
        discipline="testing",
        horizon_days=14,
        candidates=[
            _candidate(1, actual=0.1),
            _candidate(2, actual=0.2),
            _candidate(3, actual=0.3),
        ],
        retrieved_at="2026-02-01T00:00:00Z",
    )
    compared = attach_projection_comparison(baseline, predicted_deltas={"auth": 0.35})

    comparison = compared["projection_comparison"]
    assert comparison["state"] == "available"
    assert comparison["aggregation_applied"] is False
    assert comparison["evidence_maturity"] == "provisional"
    assert comparison["targets"][0] == {
        "capability_id": "auth",
        "model_predicted_delta": 0.35,
        "outside_view_delta": 0.2,
        "difference": 0.15,
        "absolute_difference": 0.15,
        "direction": "model_higher",
    }


def test_sparse_outside_view_comparison_abstains() -> None:
    sparse = build_outside_view_baseline(
        product_id="product:platform",
        target_capability_ids=["auth"],
        discipline="testing",
        horizon_days=14,
        candidates=[_candidate(1)],
        retrieved_at="2026-02-01T00:00:00Z",
    )
    comparison = compare_forecast_to_outside_view(
        forecast_contract={"baseline": {"outside_view": sparse}},
        predicted_deltas={"auth": 0.2},
        actual_deltas={"auth": 0.2},
    )

    assert comparison == {
        "contract_version": OUTSIDE_VIEW_BASELINE_VERSION,
        "state": "unscored",
        "reason": "outside_view_anecdotal",
        "method": "mean_absolute_delta_error/v1",
    }


def _pool_with_rows(outcomes: list[dict], predictions: list[dict]):
    db = AsyncMock()
    db.query = AsyncMock(side_effect=[[outcomes], [predictions]])
    ctx = AsyncMock()
    ctx.__aenter__ = AsyncMock(return_value=db)
    ctx.__aexit__ = AsyncMock(return_value=False)
    pool = MagicMock()
    pool.connection.return_value = ctx
    return pool, db


@pytest.mark.asyncio
async def test_loader_queries_and_preserves_product_scope() -> None:
    outcomes = [_candidate(1), _candidate(2), _candidate(3)]
    predictions = [{"id": f"decision_prediction:p{index}", "horizon_days": 14} for index in range(1, 4)]
    pool, db = _pool_with_rows(outcomes, predictions)

    baseline = await load_outside_view_baseline(
        product_id="product:platform",
        target_capability_ids=["auth"],
        discipline="testing",
        horizon_days=14,
        pool=pool,
    )

    assert baseline["state"] == "provisional"
    assert db.query.await_count == 2
    for call in db.query.await_args_list:
        assert "product = <record>$product" in call.args[0]
        assert call.args[1]["product"] == "product:platform"


@pytest.mark.asyncio
async def test_loader_failure_returns_explicit_unavailable_state() -> None:
    db = AsyncMock()
    db.query = AsyncMock(side_effect=RuntimeError("offline"))
    ctx = AsyncMock()
    ctx.__aenter__ = AsyncMock(return_value=db)
    ctx.__aexit__ = AsyncMock(return_value=False)
    pool = MagicMock()
    pool.connection.return_value = ctx

    baseline = await load_outside_view_baseline(
        product_id="product:platform",
        target_capability_ids=["auth"],
        discipline="testing",
        horizon_days=14,
        pool=pool,
    )

    assert baseline["state"] == "unavailable"
    assert baseline["reason"] == "settled_analogue_retrieval_failed"
