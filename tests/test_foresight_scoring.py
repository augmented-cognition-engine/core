"""Deterministic mathematical and abstention evidence for Prediction Score v1."""

from __future__ import annotations

import pytest

from core.engine.foresight.contracts import PREDICTION_SCORE_VERSION
from core.engine.foresight.scoring import (
    continuous_interval_score,
    score_prediction,
    summarize_prediction_scores,
)


def _forecast(*, coverage: float | None = 0.8, kind: str = "continuous", outside: dict | None = None):
    estimate = {
        "kind": kind,
        "point": 0.2,
        "lower": 0.0,
        "upper": 0.4,
        "interval_coverage": coverage,
    }
    return {
        "baseline": {"outside_view": outside},
        "consequences": [
            {
                "local_id": "consequence:1",
                "target": {"entity_id": "auth", "metric": "capability_quality", "unit": "score_delta"},
                "estimate": estimate,
            }
        ],
    }


def test_central_interval_score_rewards_narrow_covered_interval() -> None:
    assert continuous_interval_score(lower=0.0, upper=0.4, coverage=0.8, actual=0.3) == pytest.approx(0.4)


def test_central_interval_score_penalizes_misses_by_declared_coverage() -> None:
    # Width 0.4 plus 10 * miss distance 0.2 for an 80% central interval.
    assert continuous_interval_score(lower=0.0, upper=0.4, coverage=0.8, actual=0.6) == pytest.approx(2.4)


@pytest.mark.parametrize(
    ("kwargs", "message"),
    [
        ({"lower": 0.5, "upper": 0.4, "coverage": 0.8, "actual": 0.4}, "lower interval"),
        ({"lower": 0.0, "upper": 0.4, "coverage": 1.0, "actual": 0.4}, "coverage"),
        ({"lower": 0.0, "upper": 0.4, "coverage": 0.8, "actual": float("nan")}, "finite"),
    ],
)
def test_interval_score_rejects_invalid_semantics(kwargs, message) -> None:
    with pytest.raises(ValueError, match=message):
        continuous_interval_score(**kwargs)


def test_continuous_forecast_produces_proper_score_and_diagnostics() -> None:
    score = score_prediction(
        forecast_contract=_forecast(),
        actual_deltas={"auth": 0.3},
        resolution_score_eligible=True,
        non_score_reason=None,
    )

    assert score["contract_version"] == PREDICTION_SCORE_VERSION
    assert score["state"] == "scored"
    assert score["proper_score_available"] is True
    item = score["consequence_scores"][0]
    assert item["method"] == "central_interval_score/v1"
    assert item["scores"] == {
        "interval_coverage": 0.8,
        "interval_score": pytest.approx(0.4),
        "absolute_error": pytest.approx(0.1),
        "covered": True,
        "interval_width": pytest.approx(0.4),
        "direction": "lower_is_better",
    }


def test_missing_interval_coverage_abstains_without_reinterpreting_confidence() -> None:
    score = score_prediction(
        forecast_contract=_forecast(coverage=None),
        actual_deltas={"auth": 0.3},
        resolution_score_eligible=True,
        non_score_reason=None,
    )

    assert score["state"] == "unscored"
    assert score["proper_score_available"] is False
    assert score["consequence_scores"][0]["reason"] == "missing_interval_coverage"


def test_unsupported_prediction_type_abstains_explicitly() -> None:
    score = score_prediction(
        forecast_contract=_forecast(kind="binary"),
        actual_deltas={"auth": 1.0},
        resolution_score_eligible=True,
        non_score_reason=None,
    )
    assert score["consequence_scores"][0]["reason"] == "unsupported_prediction_type"


def test_ineligible_resolution_never_receives_prediction_score() -> None:
    score = score_prediction(
        forecast_contract=_forecast(),
        actual_deltas={"auth": 0.3},
        resolution_score_eligible=False,
        non_score_reason="intervention_cancelled",
    )
    assert score["state"] == "unscored"
    assert score["reason"] == "intervention_cancelled"
    assert score["consequence_scores"] == []


def test_model_and_outside_view_use_same_interval_score_and_coverage() -> None:
    outside = {
        "state": "supported",
        "target_priors": {
            "auth": {
                "weighted_mean_actual_delta": 0.3,
                "weighted_standard_deviation": 0.05,
            }
        },
    }
    score = score_prediction(
        forecast_contract=_forecast(outside=outside),
        actual_deltas={"auth": 0.3},
        resolution_score_eligible=True,
        non_score_reason=None,
    )

    outside_score = score["consequence_scores"][0]["outside_view_score"]
    assert outside_score["coverage"] == 0.8
    assert outside_score["method"] == "central_interval_score/v1"
    assert score["comparison"]["state"] == "scored"
    assert score["comparison"]["winner"] == "outside_view"


def test_summary_never_pools_different_interval_coverages() -> None:
    score_80 = score_prediction(
        forecast_contract=_forecast(coverage=0.8),
        actual_deltas={"auth": 0.3},
        resolution_score_eligible=True,
        non_score_reason=None,
    )
    score_90 = score_prediction(
        forecast_contract=_forecast(coverage=0.9),
        actual_deltas={"auth": 0.3},
        resolution_score_eligible=True,
        non_score_reason=None,
    )
    summary = summarize_prediction_scores([{"prediction_score": score_80}, {"prediction_score": score_90}])

    assert summary["prediction_count"] == 2
    assert summary["scored_consequence_count"] == 2
    assert [group["interval_coverage"] for group in summary["by_interval_coverage"]] == [0.8, 0.9]
    assert all(group["evidence_maturity"] == "anecdotal" for group in summary["by_interval_coverage"])
