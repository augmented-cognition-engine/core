from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from core.engine.foresight.comparators import (
    ComparatorRequestConflict,
    ComparatorTargetNotFound,
    comparator_effects,
    evaluate_plan_alignment,
    record_comparator_observation,
)
from core.engine.foresight.contracts import (
    FORECAST_CONTRACT_VERSION,
    build_comparator_observation_contract,
    build_comparator_plan,
    build_forecast_contract,
)


def _contract(*, design: str = "matched", missing_evidence: list[str] | None = None) -> dict:
    return build_comparator_observation_contract(
        observation_id="observation:c1",
        request_id="checkout-comparator-v1",
        decision_id="decision:d1",
        prediction_id="decision_prediction:p1",
        product_id="product:alpha",
        comparator_type="holdout",
        design=design,
        observed_at="2026-02-01T00:00:00Z",
        measurements=[
            {
                "capability_id": "checkout",
                "intervention_before": 0.50,
                "intervention_after": 0.74,
                "comparator_before": 0.52,
                "comparator_after": 0.57,
                "evidence_refs": ["experiment:e1"],
            }
        ],
        evidence_refs=["experiment:e1"],
        confounders=["Holiday traffic"],
        missing_evidence=missing_evidence or [],
        reason="Matched traffic cohorts over the forecast window.",
    )


def _prediction() -> dict:
    contract = build_forecast_contract(
        {
            "horizon_days": 30,
            "applicability_conditions": ["Rollout reaches users"],
            "no_action_baseline": "Reliability remains near its current level.",
            "expected_changes": [
                {
                    "capability_id": "checkout",
                    "score_delta": 0.2,
                    "lower_bound": 0.1,
                    "upper_bound": 0.3,
                    "interval_coverage": 0.8,
                    "mechanism": "Retries reduce failures.",
                    "evidence_refs": ["decision:d1"],
                }
            ],
            "leading_indicators": ["Reliability rises"],
            "falsification_condition": "Reliability does not rise.",
            "primary_risk": "Provider errors dominate.",
        },
        decision_id="decision:d1",
        product_id="product:alpha",
        archetype="skeptic",
        discipline="reliability",
        model="test-model",
    )
    return {
        "id": "decision_prediction:p1",
        "decision": "decision:d1",
        "product": "product:alpha",
        "contract_version": FORECAST_CONTRACT_VERSION,
        "forecast_contract": contract,
        "closed": False,
        "horizon_days": 30,
        "created_at": "2026-01-01T00:00:00Z",
    }


def test_comparator_effect_is_transparent_difference_in_differences():
    contract = _contract()

    measurement = contract["measurements"][0]
    assert measurement["intervention"]["delta"] == pytest.approx(0.24)
    assert measurement["comparator"]["delta"] == pytest.approx(0.05)
    assert measurement["effect_delta"] == pytest.approx(0.19)
    assert contract["resolution_eligible"] is True
    assert comparator_effects(contract) == {"checkout": pytest.approx(0.19)}
    assert contract["comparator"]["causal_claim"] is False
    assert contract["comparator"]["attribution_strength"] == "moderate"


@pytest.mark.parametrize("design", ["unknown"])
def test_unknown_design_is_captured_but_not_resolution_eligible(design):
    contract = _contract(design=design)
    assert contract["resolution_eligible"] is False
    assert "design" in contract["non_eligibility_reasons"]
    assert comparator_effects(contract) == {}


def test_declared_randomized_design_does_not_automatically_assert_causality():
    contract = _contract(design="randomized")
    assert contract["comparator"]["attribution_strength"] == "stronger"
    assert contract["comparator"]["causal_claim"] is False
    assert "not_independently_verified" in contract["comparator"]["causal_identification"]


def test_declared_missing_evidence_prevents_resolution_use():
    contract = _contract(missing_evidence=["comparator_assignment_log"])
    assert contract["resolution_eligible"] is False
    assert "comparator_assignment_log" in contract["non_eligibility_reasons"]


def test_reconciler_projects_only_eligible_comparator_effects():
    from core.engine.foresight.reconciler import _comparator_resolution_inputs

    contract = _contract()
    row = {
        "id": "observation:c1",
        "product": "product:alpha",
        "affected_decision": "decision:d1",
        "affected_prediction": "decision_prediction:p1",
        "comparator_contract_version": contract["contract_version"],
        "comparator_contract": contract,
    }
    inputs = _comparator_resolution_inputs(row)
    assert inputs["force_actual"] == {"checkout": pytest.approx(0.19)}
    assert inputs["comparator_context"]["effect_method"] == "difference_in_differences/v1"
    assert inputs["comparator_context"]["causal_claim"] is False
    assert "observation:c1" in inputs["observation_refs"]

    row["comparator_contract"] = _contract(design="unknown")
    assert _comparator_resolution_inputs(row) == {}


def test_reconciler_preserves_plan_alignment_and_effective_attribution():
    from core.engine.foresight.reconciler import _comparator_resolution_inputs

    contract = _contract()
    contract["plan_alignment"] = {
        "state": "partially_aligned",
        "plan_id": "comparator_plan:aaaaaaaaaaaaaaaaaaaaaaaa",
        "deviations": ["duration_below_plan"],
        "effective_attribution_strength": "limited",
        "causal_claim": False,
    }
    row = {
        "id": "observation:c1",
        "product": "product:alpha",
        "affected_prediction": "decision_prediction:p1",
        "comparator_contract_version": contract["contract_version"],
        "comparator_contract": contract,
    }
    context = _comparator_resolution_inputs(row)["comparator_context"]
    assert context["plan_alignment_state"] == "partially_aligned"
    assert context["effective_attribution_strength"] == "limited"
    assert context["plan_deviations"] == ["duration_below_plan"]


def _plan() -> dict:
    return build_comparator_plan(
        {
            "comparator_type": "holdout",
            "assignment_design": "matched",
            "comparator_label": "Unexposed matched traffic",
            "feasibility": "conditional",
            "feasibility_reason": "Routing supports a stable holdout.",
            "required_conditions": ["Holdout traffic remains safe"],
            "assignment_unit": "request",
            "allocation": "Keep a stable unexposed request cohort",
            "eligibility_criteria": ["Request is eligible for either route"],
            "minimum_duration_days": 7,
            "guardrails": ["Stop if checkout failures rise"],
            "measurements": [
                {
                    "capability_id": "checkout",
                    "baseline_source": "Pre-period quality",
                    "outcome_source": "Post-period quality",
                    "cadence": "daily",
                }
            ],
        },
        consequences=[
            {
                "target": {
                    "entity_id": "checkout",
                    "metric": "capability_quality",
                    "unit": "score_delta",
                }
            }
        ],
        horizon_days=30,
        decision_id="decision:d1",
        product_id="product:alpha",
    )


def test_plan_alignment_preserves_strength_only_when_execution_matches():
    plan = _plan()
    contract = _contract()
    contract["observation_window"] = {
        "start": "2026-01-01T00:00:00Z",
        "end": "2026-01-15T00:00:00Z",
    }
    alignment = evaluate_plan_alignment(
        plan=plan,
        observation_contract=contract,
        execution={
            "plan_id": plan["plan_id"],
            "assignment_unit": "request",
            "eligibility_criteria_met": True,
            "guardrail_breaches": [],
            "deviations": [],
        },
        explicit_plan_id=plan["plan_id"],
    )
    assert alignment["state"] == "aligned"
    assert alignment["effective_attribution_strength"] == "moderate"
    assert alignment["link_method"] == "explicit_plan_id"
    assert alignment["causal_claim"] is False


def test_unverified_execution_is_partial_and_downgrades_attribution():
    alignment = evaluate_plan_alignment(
        plan=_plan(),
        observation_contract=_contract(),
        execution={},
        explicit_plan_id=None,
    )
    assert alignment["state"] == "partially_aligned"
    assert alignment["effective_attribution_strength"] == "limited"
    assert alignment["link_method"] == "prediction_plan_auto_link"


def test_core_design_deviation_is_not_aligned():
    plan = _plan()
    contract = _contract(design="observational")
    alignment = evaluate_plan_alignment(
        plan=plan,
        observation_contract=contract,
        execution={"assignment_unit": "request", "eligibility_criteria_met": True},
        explicit_plan_id=None,
    )
    assert alignment["state"] == "not_aligned"
    assert alignment["effective_attribution_strength"] == "limited"
    assert any("assignment_design" in item for item in alignment["deviations"])


class _ComparatorDB:
    def __init__(self, prediction: dict | None = None):
        self.prediction = prediction or _prediction()
        self.observations: list[dict] = []
        self.calls: list[tuple[str, dict | None]] = []

    async def query(self, sql: str, params: dict | None = None):
        self.calls.append((sql, params))
        if "SELECT * FROM ONLY <record>$prediction" in sql:
            return [[self.prediction]]
        if "SELECT * FROM ONLY <record>$id" in sql:
            row = next(
                (item for item in self.observations if item["id"] == (params or {}).get("id")),
                None,
            )
            return [[row]] if row else [[]]
        if "UPSERT type::record('observation', $record_key)" in sql:
            row = {
                "id": f"observation:{params['record_key']}",
                "product": params["product"],
                "affected_decision": params["decision"],
                "affected_prediction": params["prediction"],
                "content_hash": params["content_hash"],
                "comparator_contract_version": params["contract_version"],
                "comparator_contract": params["contract"],
                "observed_at": params["observed_at"],
            }
            self.observations.append(row)
            return [[row]]
        if "observation_type = 'forecast_comparator'" in sql:
            return [list(reversed(self.observations))]
        return [[]]


def _pool(db: _ComparatorDB):
    context = AsyncMock()
    context.__aenter__ = AsyncMock(return_value=db)
    context.__aexit__ = AsyncMock(return_value=False)
    pool = MagicMock()
    pool.connection.return_value = context
    return pool


def _record_kwargs(pool) -> dict:
    return {
        "product_id": "product:alpha",
        "decision_id": "decision:d1",
        "prediction_id": "decision_prediction:p1",
        "request_id": "checkout-comparator-v1",
        "comparator_type": "holdout",
        "design": "matched",
        "observed_at": "2026-02-01T00:00:00Z",
        "measurements": [
            {
                "capability_id": "checkout",
                "intervention_before": 0.5,
                "intervention_after": 0.74,
                "comparator_before": 0.52,
                "comparator_after": 0.57,
                "evidence_refs": ["experiment:e1"],
            }
        ],
        "comparator_label": "Unexposed matched traffic",
        "window_start": "2026-01-01T00:00:00Z",
        "window_end": "2026-02-01T00:00:00Z",
        "evidence_refs": ["experiment:e1"],
        "confounders": [],
        "missing_evidence": [],
        "reason": "Matched cohorts.",
        "content": "Observed holdout comparison.",
        "source_surface": "thin_mcp",
        "actor_ref": "user:operator",
        "pool": pool,
    }


@pytest.mark.asyncio
async def test_comparator_capture_is_idempotent_and_does_not_mutate_forecast():
    db = _ComparatorDB()
    pool = _pool(db)
    with patch(
        "core.engine.foresight.reconciler.process_comparator_observation",
        AsyncMock(return_value={"state": "awaiting_horizon"}),
    ):
        first = await record_comparator_observation(**_record_kwargs(pool))
        second = await record_comparator_observation(**_record_kwargs(pool))

    assert first["status"] == "captured"
    assert second["status"] == "duplicate"
    assert first["comparator"]["resolution_eligible"] is True
    assert first["comparator_state"]["status"] == "eligible"
    assert len([sql for sql, _ in db.calls if "UPSERT type::record('observation'" in sql]) == 1
    updates = [sql for sql, _ in db.calls if "UPDATE <record>$prediction" in sql]
    assert updates and all("forecast_contract" not in sql for sql in updates)


@pytest.mark.asyncio
async def test_comparator_request_conflict_never_overwrites_evidence():
    db = _ComparatorDB()
    pool = _pool(db)
    kwargs = _record_kwargs(pool)
    with patch(
        "core.engine.foresight.reconciler.process_comparator_observation",
        AsyncMock(return_value={"state": "awaiting_horizon"}),
    ):
        await record_comparator_observation(**kwargs)
        kwargs["measurements"][0]["intervention_after"] = 0.9
        with pytest.raises(ComparatorRequestConflict):
            await record_comparator_observation(**kwargs)
    assert len(db.observations) == 1


def _prediction_with_plan() -> tuple[dict, dict]:
    prediction = _prediction()
    plan = _plan()
    prediction["comparator_plan_version"] = plan["contract_version"]
    prediction["comparator_plan"] = plan
    prediction["comparator_plan_status"] = plan["status"]
    prediction["forecast_contract"]["evaluation"] = {"comparator_plan": plan}
    return prediction, plan


@pytest.mark.asyncio
async def test_capture_links_plan_and_persists_alignment_provenance():
    prediction, plan = _prediction_with_plan()
    db = _ComparatorDB(prediction)
    kwargs = _record_kwargs(_pool(db))
    kwargs["execution"] = {
        "plan_id": plan["plan_id"],
        "assignment_unit": "request",
        "eligibility_criteria_met": True,
        "guardrail_breaches": [],
        "deviations": [],
    }
    with patch(
        "core.engine.foresight.reconciler.process_comparator_observation",
        AsyncMock(return_value={"state": "awaiting_horizon"}),
    ):
        result = await record_comparator_observation(**kwargs)

    comparator = result["comparator"]
    assert comparator["plan_alignment"]["state"] == "aligned"
    assert comparator["plan_alignment"]["plan_id"] == plan["plan_id"]
    assert comparator["comparator"]["effective_attribution_strength"] == "moderate"
    upsert_params = next(params for sql, params in db.calls if "UPSERT type::record('observation'" in sql)
    assert upsert_params["plan_id"] == plan["plan_id"]
    assert upsert_params["alignment_state"] == "aligned"


@pytest.mark.asyncio
async def test_capture_rejects_plan_identity_from_another_prediction():
    prediction, _ = _prediction_with_plan()
    db = _ComparatorDB(prediction)
    kwargs = _record_kwargs(_pool(db))
    kwargs["execution"] = {"plan_id": "comparator_plan:aaaaaaaaaaaaaaaaaaaaaaaa"}

    with pytest.raises(ComparatorTargetNotFound):
        await record_comparator_observation(**kwargs)


def test_v151_migration_is_additive_and_preserves_frozen_forecasts():
    from pathlib import Path

    migration = (Path(__file__).parents[1] / "core/schema/v151_observed_comparator_v1.surql").read_text(
        encoding="utf-8"
    )
    assert "comparator_contract" in migration
    assert "comparator_context" in migration
    assert "forecast_contract" not in migration
    assert "DELETE" not in migration
    assert "REMOVE" not in migration
    assert "value = '151'" in migration


def test_v153_plan_linkage_migration_is_additive_and_observation_scoped():
    from pathlib import Path

    migration = (Path(__file__).parents[1] / "core/schema/v153_comparator_plan_linkage_v1.surql").read_text(
        encoding="utf-8"
    )
    assert "comparator_plan_id" in migration
    assert "comparator_alignment_state" in migration
    assert "ON TABLE observation" in migration
    assert "forecast_contract" not in migration
    assert "DELETE" not in migration
    assert "REMOVE" not in migration
    assert "value = '153'" in migration
