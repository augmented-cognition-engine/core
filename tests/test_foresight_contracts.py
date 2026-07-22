from __future__ import annotations

from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from core.engine.foresight.contracts import (
    FORECAST_CONTRACT_VERSION,
    INDICATOR_OBSERVATION_CONTRACT_VERSION,
    INDICATOR_STATE_VERSION,
    INTERVENTION_OBSERVATION_CONTRACT_VERSION,
    OUTSIDE_VIEW_BASELINE_VERSION,
    RESOLUTION_CONTRACT_VERSION,
    assess_resolution,
    build_forecast_contract,
    build_indicator_observation_contract,
    build_intervention_observation_contract,
    normalize_forecast_record,
    normalize_intervention_observation,
    normalize_resolution_record,
)

ROOT = Path(__file__).resolve().parents[1]


def _structured_forecast() -> dict:
    return {
        "horizon_days": 30,
        "applicability_conditions": ["The rollout reaches at least 80% of traffic"],
        "no_action_baseline": "Reliability remains near its current score.",
        "compared_alternatives": ["Keep the current retry policy"],
        "expected_changes": [
            {
                "capability_id": "checkout",
                "score_delta": 0.2,
                "lower_bound": 0.1,
                "upper_bound": 0.3,
                "interval_coverage": 0.8,
                "probability": 0.7,
                "order": 2,
                "lag_days": 14,
                "mechanism": "Idempotency prevents duplicate settlement attempts.",
                "assumptions": ["The payment provider behavior remains stable"],
                "dependencies": ["Idempotency keys are propagated end to end"],
                "confounders": ["A provider-side reliability change"],
                "evidence_refs": ["decision:d0"],
            }
        ],
        "primary_risk": "Retries amplify load if keys are not stable.",
        "leading_indicators": ["Duplicate settlement attempts decline"],
        "indicator_rules": [
            {
                "indicator_index": 1,
                "capability_id": "checkout",
                "dimension": "reliability",
                "operator": "gte",
                "threshold": 0.7,
                "effect_when_met": "supports",
                "effect_when_not_met": "weakens",
            }
        ],
        "falsification_condition": "Duplicate settlement attempts do not decline within 30 days.",
    }


def _prediction_record(**overrides) -> dict:
    row = {
        "id": "decision_prediction:p1",
        "decision": "decision:d1",
        "product": "product:alpha",
        "archetype": "skeptic",
        "discipline": "reliability",
        "horizon_days": 30,
        "expected_changes": [{"capability_id": "checkout", "score_delta": 0.2, "confidence": 0.7}],
        "primary_risk": "Retries amplify load.",
        "leading_indicators": ["Duplicate settlements decline"],
        "falsification_condition": "Duplicates do not decline.",
        "closed": False,
        "created_at": "2026-01-01T00:00:00+00:00",
    }
    row.update(overrides)
    return row


def _spy_pool(prediction: dict):
    calls: list[tuple[str, dict | None]] = []

    async def query(sql: str, params: dict | None = None):
        calls.append((sql, params))
        if "SELECT * FROM <record>$pred" in sql:
            return [[prediction]]
        if "SELECT calibration_score" in sql and "archetype_calibration" in sql:
            return [[]]
        if "SELECT canvas_session_id" in sql:
            return [[]]
        if "FROM capability_quality" in sql:
            return [[]]
        return [[]]

    db = AsyncMock()
    db.query = AsyncMock(side_effect=query)
    connection = AsyncMock()
    connection.__aenter__ = AsyncMock(return_value=db)
    connection.__aexit__ = AsyncMock(return_value=False)
    pool = MagicMock()
    pool.connection.return_value = connection
    return pool, calls


def test_forecast_v1_preserves_conditions_ranges_mechanism_and_provenance() -> None:
    contract = build_forecast_contract(
        _structured_forecast(),
        decision_id="decision:d1",
        product_id="product:alpha",
        archetype="skeptic",
        discipline="reliability",
        model="test-model",
        current_state_baseline={"checkout": 0.5},
        baseline_observed_at="2026-01-01T00:00:00Z",
        baseline_observation_refs=["capability_quality:q1"],
    )

    assert contract["contract_version"] == FORECAST_CONTRACT_VERSION
    assert contract["intervention"]["status"] == "authorized"
    assert contract["intervention"]["conditions"] == ["The rollout reaches at least 80% of traffic"]
    assert contract["baseline"]["no_action"].startswith("Reliability remains")
    assert contract["baseline"]["current_state"] == {"checkout": 0.5}
    assert contract["baseline"]["observation_refs"] == ["capability_quality:q1"]
    consequence = contract["consequences"][0]
    assert consequence["estimate"] == {
        "kind": "continuous",
        "point": 0.2,
        "lower": 0.1,
        "upper": 0.3,
        "interval_coverage": 0.8,
        "probability": 0.7,
    }
    assert consequence["mechanism"].startswith("Idempotency")
    assert consequence["evidence_refs"] == ["decision:d0"]
    assert contract["provenance"] == {
        "source_kind": "model_inference",
        "model": "test-model",
        "evidence_refs": ["decision:d0"],
    }
    indicator = contract["resolution_rule"]["indicators"][0]
    assert indicator["local_id"] == "indicator:1"
    assert indicator["monitoring"] == "automatic"
    assert indicator["rule"]["operator"] == "gte"
    assert contract["resolution_rule"]["indicator_monitoring"] == {
        "state": "automatic",
        "automatic_count": 1,
        "manual_count": 0,
    }


def test_forecast_freezes_outside_view_and_marks_no_action_as_unidentified() -> None:
    outside_view = {
        "contract_version": OUTSIDE_VIEW_BASELINE_VERSION,
        "state": "supported",
        "target_priors": {
            "checkout": {
                "case_count": 3,
                "weighted_mean_actual_delta": 0.15,
                "maturity": "supported",
            }
        },
        "analogues": [{"outcome_id": "prediction_outcome:o1", "similarity": 1.0}],
    }
    contract = build_forecast_contract(
        _structured_forecast(),
        decision_id="decision:d1",
        product_id="product:alpha",
        archetype="skeptic",
        discipline="reliability",
        model="test-model",
        current_state_baseline={"checkout": 0.5},
        baseline_observed_at="2026-01-01T00:00:00Z",
        baseline_observation_refs=["capability_quality:q1"],
        outside_view_baseline=outside_view,
    )

    assert contract["baseline"]["outside_view"] == outside_view
    assert contract["baseline"]["no_action_grounding"] == {
        "state": "model_inference_only",
        "empirically_identified": False,
        "reason": "no_observed_no_action_comparator",
    }
    assert contract["completeness"]["state"] == "complete"


def test_forecast_contract_redacts_credentials() -> None:
    raw = _structured_forecast()
    raw["expected_changes"][0]["mechanism"] = "Use api_key=do-not-return in the callback"
    contract = build_forecast_contract(
        raw,
        decision_id="decision:d1",
        product_id="product:alpha",
        archetype="skeptic",
        discipline="security",
        model="test-model",
    )
    assert "do-not-return" not in contract["consequences"][0]["mechanism"]
    assert "api_key=<redacted>" in contract["consequences"][0]["mechanism"]


def test_invalid_interval_coverage_is_missing_not_clamped() -> None:
    raw = _structured_forecast()
    raw["expected_changes"][0]["interval_coverage"] = 1.2
    contract = build_forecast_contract(
        raw,
        decision_id="decision:d1",
        product_id="product:alpha",
        archetype="skeptic",
        discipline="reliability",
        model="test-model",
    )

    assert contract["consequences"][0]["estimate"]["interval_coverage"] is None
    assert "consequences.0.estimate.interval_coverage" in contract["completeness"]["missing_fields"]


def test_cold_start_outside_view_is_not_a_forecast_completeness_failure() -> None:
    contract = build_forecast_contract(
        _structured_forecast(),
        decision_id="decision:d1",
        product_id="product:new",
        archetype="skeptic",
        discipline="reliability",
        model="test-model",
        current_state_baseline={"checkout": 0.5},
        baseline_observed_at="2026-01-01T00:00:00Z",
        baseline_observation_refs=["capability_quality:q1"],
        outside_view_baseline={
            "contract_version": OUTSIDE_VIEW_BASELINE_VERSION,
            "state": "cold_start",
            "reason": "no_eligible_settled_analogues",
            "analogues": [],
            "target_priors": {},
        },
    )

    assert contract["completeness"]["state"] == "complete"
    assert not any(field.startswith("baseline.outside_view") for field in contract["completeness"]["missing_fields"])


def test_intervention_observation_v1_preserves_conditions_exposure_and_provenance() -> None:
    contract = build_intervention_observation_contract(
        observation_id="observation:i1",
        request_id="deploy-checkout-v1",
        decision_id="decision:d1",
        prediction_id="decision_prediction:p1",
        product_id="product:alpha",
        status="partial",
        observed_at="2026-02-01T00:00:00Z",
        applicability_conditions_met=True,
        conditions=[
            {
                "condition": "The rollout reaches at least 80% of traffic",
                "met": True,
                "evidence_refs": ["deployment:r1"],
            }
        ],
        exposure={"degree": 0.8, "scope": "checkout traffic", "unit": "traffic_fraction"},
        evidence_refs=["deployment:r1"],
        confounders=["provider maintenance"],
        missing_evidence=[],
        reason="Rollout telemetry confirms exposure.",
        source_surface="thin_mcp",
        actor_ref="user:operator",
    )

    assert contract["contract_version"] == INTERVENTION_OBSERVATION_CONTRACT_VERSION
    assert contract["status"] == "partial"
    assert contract["exposure"]["degree"] == 0.8
    assert contract["applicability"]["conditions"][0]["met"] is True
    assert contract["evidence_refs"] == ["deployment:r1"]
    assert contract["provenance"]["source_surface"] == "thin_mcp"
    assert contract["completeness"]["state"] == "complete"


def test_intervention_observation_redacts_and_degrades_malformed_contracts() -> None:
    built = build_intervention_observation_contract(
        observation_id="observation:i1",
        request_id="deploy-v1",
        decision_id="decision:d1",
        prediction_id="decision_prediction:p1",
        product_id="product:alpha",
        status="completed",
        observed_at="2026-02-01T00:00:00Z",
        applicability_conditions_met=True,
        conditions=[],
        exposure=None,
        evidence_refs=["token=do-not-return"],
        confounders=[],
        missing_evidence=[],
        reason="api_key=do-not-return",
        source_surface="api",
        actor_ref="user:operator",
    )
    assert "do-not-return" not in str(built)

    normalized = normalize_intervention_observation(
        {
            "id": "observation:i1",
            "product": "product:alpha",
            "intervention_contract_version": INTERVENTION_OBSERVATION_CONTRACT_VERSION,
            "intervention_contract": {
                "contract_version": INTERVENTION_OBSERVATION_CONTRACT_VERSION,
                "status": "invented",
                "applicability": [],
                "exposure": "all",
            },
        }
    )
    assert normalized["status"] == "unknown"
    assert normalized["compatibility"]["state"] == "degraded"
    assert normalized["compatibility"]["reason"] == "malformed_intervention_contract"


def test_indicator_observation_v1_is_bounded_redacted_evidence() -> None:
    contract = build_indicator_observation_contract(
        observation_id="observation:s1",
        request_id="quality:q1",
        decision_id="decision:d1",
        prediction_id="decision_prediction:p1",
        product_id="product:alpha",
        indicator_id="indicator:1",
        indicator_description="Checkout reliability reaches 0.7",
        effect="supports",
        observed_at="2026-02-01T00:00:00Z",
        value=0.75,
        unit="capability_quality_score",
        baseline_value=0.5,
        rule={"operator": "gte", "threshold": 0.7},
        evidence_refs=["capability_quality:q1"],
        reason="token=do-not-return",
        source_kind="automatic_quality_rule",
        source_surface="sentinel",
        actor_ref="ace:indicator_evaluator",
    )

    assert contract["contract_version"] == INDICATOR_OBSERVATION_CONTRACT_VERSION
    assert contract["measurement"] == {
        "value": 0.75,
        "unit": "capability_quality_score",
        "baseline_value": 0.5,
        "delta": 0.25,
    }
    assert contract["effect"] == "supports"
    assert "do-not-return" not in str(contract)
    assert INDICATOR_STATE_VERSION == "ace.foresight.indicator-state/v1"


def test_legacy_forecast_is_readable_but_partial_and_degraded() -> None:
    contract = normalize_forecast_record(_prediction_record())

    assert contract["contract_version"] == FORECAST_CONTRACT_VERSION
    assert contract["forecast_id"] == "decision_prediction:p1"
    assert contract["compatibility"] == {
        "state": "degraded",
        "reason": "legacy_missing_forecast_contract",
        "stored_contract_version": None,
    }
    assert contract["completeness"]["state"] == "partial"
    assert "contract_version" in contract["completeness"]["missing_fields"]
    assert contract["intervention"]["status"] == "unknown"


def test_unknown_forecast_version_is_not_reinterpreted() -> None:
    row = _prediction_record(
        contract_version="ace.foresight.forecast/v99",
        forecast_contract={
            "contract_version": "ace.foresight.forecast/v99",
            "intervention": {"status": "completed"},
            "secret": "token=do-not-return",
        },
    )
    contract = normalize_forecast_record(row)

    assert contract["compatibility"]["reason"] == "unsupported_forecast_contract_version"
    assert contract["compatibility"]["stored_contract_version"] == "ace.foresight.forecast/v99"
    assert contract["intervention"]["status"] == "unknown"
    assert "secret" not in contract


def test_malformed_current_forecast_degrades_without_raising() -> None:
    row = _prediction_record(
        contract_version=FORECAST_CONTRACT_VERSION,
        forecast_contract={
            "contract_version": FORECAST_CONTRACT_VERSION,
            "intervention": "not-an-object",
            "baseline": [],
            "consequences": ["not-a-consequence"],
            "resolution_rule": "not-an-object",
        },
    )
    contract = normalize_forecast_record(row)

    assert contract["compatibility"]["state"] == "degraded"
    assert contract["compatibility"]["reason"] == "malformed_forecast_contract"
    assert contract["completeness"]["state"] == "partial"


@pytest.mark.parametrize(
    ("intervention_status", "conditions_met", "actual", "scores", "missing", "state", "reason"),
    [
        ("cancelled", True, {"checkout": 0.2}, [1.0], [], "invalid", "intervention_cancelled"),
        ("completed", False, {"checkout": 0.2}, [1.0], [], "invalid", "applicability_conditions_failed"),
        ("completed", True, {}, [], [], "unresolved", "missing_observation"),
        ("completed", True, {"checkout": 0.2}, [1.0], ["source"], "unresolved", "missing_resolution_evidence"),
        ("authorized", True, {"checkout": 0.2}, [1.0], [], "unresolved", "intervention_not_observed"),
        ("completed", True, {"checkout": 0.2}, [0.9], [], "confirmed", None),
    ],
)
def test_resolution_assessment_never_scores_absence_or_inapplicability(
    intervention_status, conditions_met, actual, scores, missing, state, reason
) -> None:
    assessment = assess_resolution(
        requested_state=None,
        intervention_status=intervention_status,
        applicability_conditions_met=conditions_met,
        actual_deltas=actual,
        calibration_scores=scores,
        missing_evidence=missing,
    )
    assert assessment.state == state
    assert assessment.non_score_reason == reason
    assert assessment.score_eligible is (reason is None)


def test_non_finite_forecast_numbers_become_missing_not_confident_values() -> None:
    raw = _structured_forecast()
    raw["expected_changes"][0]["probability"] = float("nan")
    raw["expected_changes"][0]["lower_bound"] = float("inf")
    contract = build_forecast_contract(
        raw,
        decision_id="decision:d1",
        product_id="product:alpha",
        archetype="skeptic",
        discipline="reliability",
        model="test-model",
    )
    estimate = contract["consequences"][0]["estimate"]
    assert estimate["probability"] is None
    assert estimate["lower"] is None


def test_legacy_resolution_is_explicitly_partial() -> None:
    contract = normalize_resolution_record(
        {
            "id": "prediction_outcome:o1",
            "prediction": "decision_prediction:p1",
            "decision": "decision:d1",
            "product": "product:alpha",
            "calibration_score": 0.8,
            "predicted_deltas": {"checkout": 0.2},
            "actual_deltas": {"checkout": 0.1},
        }
    )
    assert contract["contract_version"] == RESOLUTION_CONTRACT_VERSION
    assert contract["compatibility"]["reason"] == "legacy_missing_resolution_contract"
    assert contract["completeness"]["state"] == "partial"


@pytest.mark.asyncio
async def test_cancelled_intervention_writes_invalid_unscored_resolution() -> None:
    from core.engine.foresight.reconciler import close_prediction

    pool, calls = _spy_pool(_prediction_record())
    with patch("core.engine.foresight.reconciler.pool", pool):
        summary = await close_prediction(
            "decision_prediction:p1",
            force_actual={"checkout": 0.2},
            intervention_status="cancelled",
            applicability_conditions_met=True,
            observation_refs=["event:cancelled"],
        )

    assert summary["resolution_state"] == "invalid"
    assert summary["score_eligible"] is False
    assert summary["calibration_score"] is None
    assert summary["non_score_reason"] == "intervention_cancelled"
    assert not any("SELECT calibration_score" in sql for sql, _ in calls)
    outcome_params = next(params for sql, params in calls if "CREATE prediction_outcome" in sql)
    assert outcome_params["resolution_state"] == "invalid"
    assert outcome_params["calibration_score"] is None
    update_sql = next(sql for sql, _ in calls if "UPDATE <record>$prediction" in sql)
    assert "forecast_contract" not in update_sql


@pytest.mark.asyncio
async def test_missing_observation_is_unresolved_not_neutral_calibration() -> None:
    from core.engine.foresight.reconciler import close_prediction

    pool, calls = _spy_pool(_prediction_record())
    with patch("core.engine.foresight.reconciler.pool", pool):
        summary = await close_prediction(
            "decision_prediction:p1",
            intervention_status="completed",
            applicability_conditions_met=True,
        )

    assert summary["resolution_state"] == "unresolved"
    assert summary["score_eligible"] is False
    assert summary["calibration_score"] is None
    assert summary["non_score_reason"] == "missing_resolution_evidence"
    assert not any("UPSERT type::record('archetype_calibration'" in sql for sql, _ in calls)


@pytest.mark.asyncio
async def test_scored_calibration_is_product_scoped() -> None:
    from core.engine.foresight.reconciler import close_prediction

    pool, calls = _spy_pool(_prediction_record())
    with patch("core.engine.foresight.reconciler.pool", pool):
        summary = await close_prediction(
            "decision_prediction:p1",
            force_actual={"checkout": 0.2},
            observation_refs=["measurement:checkout:2026-02-01"],
        )

    assert summary["score_eligible"] is True
    calibration_calls = [(sql, params) for sql, params in calls if "archetype_calibration" in sql]
    assert len(calibration_calls) == 2
    for sql, params in calibration_calls:
        assert "product" in sql
        assert params["product"] == "product:alpha"


@pytest.mark.asyncio
async def test_resolution_provenance_includes_indicator_evidence_without_using_it_as_outcome() -> None:
    from core.engine.foresight.reconciler import close_prediction

    prediction = _prediction_record(indicator_evidence_state={"observation_refs": ["observation:indicator1"]})
    pool, calls = _spy_pool(prediction)
    with patch("core.engine.foresight.reconciler.pool", pool):
        await close_prediction(
            "decision_prediction:p1",
            force_actual={"checkout": 0.2},
            observation_refs=["measurement:checkout"],
        )

    outcome_params = next(params for sql, params in calls if "CREATE prediction_outcome" in sql)
    assert outcome_params["observation_refs"] == [
        "measurement:checkout",
        "observation:indicator1",
    ]
    assert outcome_params["actual_deltas"] == {"checkout": 0.2}


@pytest.mark.asyncio
async def test_resolution_persists_frozen_outside_view_comparison() -> None:
    from core.engine.foresight.reconciler import close_prediction

    outside_view = {
        "contract_version": OUTSIDE_VIEW_BASELINE_VERSION,
        "state": "supported",
        "target_priors": {
            "checkout": {
                "case_count": 3,
                "weighted_mean_actual_delta": 0.1,
                "maturity": "supported",
            }
        },
    }
    forecast = build_forecast_contract(
        _structured_forecast(),
        decision_id="decision:d1",
        product_id="product:alpha",
        archetype="skeptic",
        discipline="reliability",
        model="test-model",
        outside_view_baseline=outside_view,
    )
    prediction = _prediction_record(
        contract_version=FORECAST_CONTRACT_VERSION,
        forecast_contract=forecast,
    )
    pool, calls = _spy_pool(prediction)
    with patch("core.engine.foresight.reconciler.pool", pool):
        summary = await close_prediction(
            "decision_prediction:p1",
            force_actual={"checkout": 0.2},
            observation_refs=["measurement:checkout"],
        )

    assert summary["outside_view_comparison"]["state"] == "scored"
    assert summary["outside_view_comparison"]["winner"] == "model_forecast"
    assert summary["prediction_score"]["contract_version"] == "ace.foresight.prediction-score/v1"
    assert summary["prediction_score"]["state"] == "scored"
    assert summary["prediction_score"]["proper_score_available"] is True
    outcome_params = next(params for sql, params in calls if "CREATE prediction_outcome" in sql)
    assert outcome_params["outside_view_comparison"] == summary["outside_view_comparison"]
    assert (
        outcome_params["resolution_contract"]["scoring"]["outside_view_comparison"]
        == summary["outside_view_comparison"]
    )
    assert outcome_params["prediction_score_version"] == "ace.foresight.prediction-score/v1"
    assert outcome_params["prediction_score"] == summary["prediction_score"]
    assert outcome_params["resolution_contract"]["scoring"]["prediction_score"] == summary["prediction_score"]


def test_v146_migration_is_additive_and_product_scoped() -> None:
    migration = (ROOT / "core/schema/v146_foresight_contract_v1.surql").read_text(encoding="utf-8")

    assert "forecast_contract" in migration
    assert "resolution_contract" in migration
    assert "score_eligible" in migration
    assert "product ON TABLE archetype_calibration" in migration
    assert "ac_product_archetype_discipline" in migration
    assert "DELETE" not in migration
    assert "REMOVE" not in migration
    assert "UPDATE decision_prediction" not in migration
    assert "UPDATE prediction_outcome" not in migration
    assert "value = '146'" in migration


def test_v147_intervention_migration_is_additive_and_product_scoped() -> None:
    migration = (ROOT / "core/schema/v147_intervention_observation_v1.surql").read_text(encoding="utf-8")

    assert "affected_prediction" in migration
    assert "intervention_contract" in migration
    assert "intervention_idempotency_key" in migration
    assert "product, affected_prediction, observed_at" in migration
    assert "DELETE" not in migration
    assert "REMOVE" not in migration
    assert "UPDATE observation" not in migration
    assert "value = '147'" in migration


def test_v148_indicator_migration_preserves_immutable_forecast_contract() -> None:
    migration = (ROOT / "core/schema/v148_active_forecast_indicators.surql").read_text(encoding="utf-8")

    assert "indicator_contract" in migration
    assert "indicator_evidence_state" in migration
    assert "affected_prediction, indicator_local_id, observed_at" in migration
    assert "forecast_contract" not in migration
    assert "DELETE" not in migration
    assert "REMOVE" not in migration
    assert "value = '148'" in migration


def test_v149_outside_view_migration_is_additive_and_does_not_backfill_history() -> None:
    migration = (ROOT / "core/schema/v149_outside_view_baseline_v1.surql").read_text(encoding="utf-8")

    assert "outside_view_baseline" in migration
    assert "outside_view_comparison" in migration
    assert "po_product_score_eligible_closed" in migration
    assert "DELETE" not in migration
    assert "REMOVE" not in migration
    assert "UPDATE decision_prediction SET" not in migration
    assert "UPDATE prediction_outcome SET" not in migration
    assert "value = '149'" in migration


def test_v150_prediction_score_migration_is_additive_and_does_not_reinterpret_history() -> None:
    migration = (ROOT / "core/schema/v150_prediction_score_v1.surql").read_text(encoding="utf-8")

    assert "prediction_score_version" in migration
    assert "prediction_score" in migration
    assert "po_product_prediction_score_closed" in migration
    assert "DELETE" not in migration
    assert "REMOVE" not in migration
    assert "UPDATE prediction_outcome SET" not in migration
    assert "value = '150'" in migration
