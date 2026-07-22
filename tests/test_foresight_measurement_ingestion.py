from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from core.engine.foresight.contracts import build_comparator_plan
from core.engine.foresight.measurements import (
    MeasurementRequestConflict,
    MeasurementTargetNotFound,
    assemble_measurement_ingestion,
    build_measurement_observation_contract,
    record_measurement_observation,
)


def _plan() -> dict:
    return build_comparator_plan(
        {
            "comparator_type": "holdout",
            "assignment_design": "matched",
            "comparator_label": "Unexposed requests",
            "feasibility": "conditional",
            "feasibility_reason": "An operator can preserve a stable cohort.",
            "required_conditions": ["Operator confirms cohort eligibility"],
            "assignment_unit": "request",
            "allocation": "Preserve a stable unexposed cohort",
            "eligibility_criteria": ["Requests are independently assignable"],
            "minimum_duration_days": 7,
            "guardrails": ["Stop if error rate increases"],
            "measurements": [
                {
                    "capability_id": "checkout",
                    "metric": "capability_quality",
                    "unit": "score_delta",
                    "baseline_source": "Structured metric export",
                    "outcome_source": "Structured metric export",
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
        horizon_days=14,
        decision_id="decision:d1",
        product_id="product:alpha",
    )


def _prediction() -> tuple[dict, dict]:
    plan = _plan()
    return (
        {
            "id": "decision_prediction:p1",
            "decision": "decision:d1",
            "product": "product:alpha",
            "closed": False,
            "horizon_days": 14,
            "comparator_plan_version": plan["contract_version"],
            "comparator_plan": plan,
        },
        plan,
    )


def _sample(plan: dict, arm: str, phase: str, value: float, request_id: str) -> dict:
    measured_at = "2026-01-01T00:00:00Z" if phase == "baseline" else "2026-01-15T00:00:00Z"
    contract = build_measurement_observation_contract(
        observation_id=f"observation:{request_id}",
        request_id=request_id,
        decision_id="decision:d1",
        prediction_id="decision_prediction:p1",
        product_id="product:alpha",
        plan_id=plan["plan_id"],
        run_id="checkout-run-1",
        source_type="structured_metric",
        capability_id="checkout",
        metric="capability_quality",
        unit="score_delta",
        arm=arm,
        phase=phase,
        value=value,
        measured_at=measured_at,
        window_start="2026-01-01T00:00:00Z",
        window_end="2026-01-15T00:00:00Z",
        comparator_type="holdout",
        design="matched",
        evidence_refs=[f"metric:{request_id}"],
        execution={
            "plan_id": plan["plan_id"],
            "assignment_unit": "request",
            "eligibility_criteria_met": True,
            "guardrail_breaches": [],
            "deviations": [],
        },
        confounders=[],
        source_surface="thin_mcp",
        actor_ref="user:operator",
    )
    return {
        "id": f"observation:{request_id}",
        "measurement_contract_version": contract["contract_version"],
        "measurement_contract": contract,
    }


def _complete_rows(plan: dict) -> list[dict]:
    return [
        _sample(plan, "intervention", "baseline", 0.50, "ib"),
        _sample(plan, "intervention", "outcome", 0.74, "io"),
        _sample(plan, "comparator", "baseline", 0.52, "cb"),
        _sample(plan, "comparator", "outcome", 0.57, "co"),
    ]


def test_partial_measurement_run_stays_collecting_and_is_not_resolution_evidence():
    _, plan = _prediction()
    receipt = assemble_measurement_ingestion(
        prediction_id="decision_prediction:p1",
        plan=plan,
        run_id="checkout-run-1",
        rows=_complete_rows(plan)[:2],
    )

    assert receipt["status"] == "collecting"
    assert receipt["sample_count"] == 2
    assert len(receipt["missing_slots"]) == 2
    assert "comparator_arguments" not in receipt
    assert receipt["authority"] == {
        "assigns_cohorts": False,
        "changes_rollout": False,
        "runs_experiment": False,
    }


def test_complete_measurement_matrix_assembles_transparent_comparator_values():
    _, plan = _prediction()
    receipt = assemble_measurement_ingestion(
        prediction_id="decision_prediction:p1",
        plan=plan,
        run_id="checkout-run-1",
        rows=_complete_rows(plan),
    )

    assert receipt["status"] == "ready"
    args = receipt["comparator_arguments"]
    assert args["request_id"].startswith("measurement_ingestion:")
    assert args["comparator_type"] == "holdout"
    assert args["design"] == "matched"
    assert args["execution"]["plan_id"] == plan["plan_id"]
    assert args["measurements"] == [
        {
            "capability_id": "checkout",
            "metric": "capability_quality",
            "unit": "score_delta",
            "intervention_before": 0.5,
            "intervention_after": 0.74,
            "comparator_before": 0.52,
            "comparator_after": 0.57,
            "evidence_refs": ["metric:cb", "metric:co", "metric:ib", "metric:io"],
        }
    ]


def test_duplicate_slot_and_inconsistent_metadata_fail_closed():
    _, plan = _prediction()
    rows = _complete_rows(plan)
    duplicate = _sample(plan, "comparator", "outcome", 0.60, "co-duplicate")
    duplicate["measurement_contract"]["observed_comparator"]["design"] = "randomized"
    receipt = assemble_measurement_ingestion(
        prediction_id="decision_prediction:p1",
        plan=plan,
        run_id="checkout-run-1",
        rows=rows + [duplicate],
    )

    assert receipt["status"] == "conflicted"
    assert any(item.startswith("duplicate_slot:") for item in receipt["conflicts"])
    assert "comparator_arguments" not in receipt


def test_unplanned_design_and_generic_quality_history_cannot_be_promoted():
    _, plan = _prediction()
    rows = _complete_rows(plan)
    for row in rows:
        row["measurement_contract"]["observed_comparator"]["design"] = "randomized"
    receipt = assemble_measurement_ingestion(
        prediction_id="decision_prediction:p1",
        plan=plan,
        run_id="checkout-run-1",
        rows=rows,
    )
    assert receipt["status"] == "conflicted"
    assert "observed_design_does_not_match_plan" in receipt["conflicts"]

    generic = _complete_rows(plan)
    for row in generic:
        row["measurement_contract"]["source"]["type"] = "capability_quality"
    receipt = assemble_measurement_ingestion(
        prediction_id="decision_prediction:p1",
        plan=plan,
        run_id="checkout-run-1",
        rows=generic,
    )
    assert receipt["status"] == "conflicted"
    assert "unsupported_measurement_source" in receipt["conflicts"]


class _MeasurementDB:
    def __init__(self, prediction: dict):
        self.prediction = prediction
        self.rows: list[dict] = []
        self.calls: list[tuple[str, dict | None]] = []

    async def query(self, sql: str, params: dict | None = None):
        self.calls.append((sql, params))
        params = params or {}
        if "SELECT * FROM ONLY <record>$prediction" in sql:
            return [[self.prediction]]
        if "SELECT * FROM ONLY <record>$id" in sql:
            row = next((item for item in self.rows if item["id"] == params.get("id")), None)
            return [[row]] if row else [[]]
        if "UPSERT type::record('observation', $record_key)" in sql:
            row = {
                "id": f"observation:{params['record_key']}",
                "product": params["product"],
                "affected_decision": params["decision"],
                "affected_prediction": params["prediction"],
                "content_hash": params["content_hash"],
                "measurement_contract_version": params["contract_version"],
                "measurement_contract": params["contract"],
                "measurement_plan_id": params["plan_id"],
                "measurement_run_id": params["run_id"],
                "measurement_slot": params["slot"],
                "measured_at": params["measured_at"],
            }
            self.rows.append(row)
            return [[row]]
        if "observation_type = 'forecast_measurement'" in sql and sql.lstrip().startswith("SELECT"):
            return [list(self.rows)]
        return [[]]


def _pool(db: _MeasurementDB):
    context = AsyncMock()
    context.__aenter__ = AsyncMock(return_value=db)
    context.__aexit__ = AsyncMock(return_value=False)
    pool = MagicMock()
    pool.connection.return_value = context
    return pool


def _record_kwargs(pool, plan: dict, arm: str, phase: str, value: float) -> dict:
    return {
        "product_id": "product:alpha",
        "decision_id": "decision:d1",
        "prediction_id": "decision_prediction:p1",
        "request_id": f"sample-{arm}-{phase}",
        "plan_id": plan["plan_id"],
        "run_id": "checkout-run-1",
        "source_type": "structured_metric",
        "capability_id": "checkout",
        "metric": "capability_quality",
        "unit": "score_delta",
        "arm": arm,
        "phase": phase,
        "value": value,
        "measured_at": "2026-01-01T00:00:00Z" if phase == "baseline" else "2026-01-15T00:00:00Z",
        "window_start": "2026-01-01T00:00:00Z",
        "window_end": "2026-01-15T00:00:00Z",
        "comparator_type": "holdout",
        "design": "matched",
        "evidence_refs": [f"metric:{arm}:{phase}"],
        "execution": {
            "plan_id": plan["plan_id"],
            "assignment_unit": "request",
            "eligibility_criteria_met": True,
        },
        "confounders": [],
        "content": f"Observed {arm} {phase} metric.",
        "source_surface": "thin_mcp",
        "actor_ref": "user:operator",
        "pool": pool,
    }


@pytest.mark.asyncio
async def test_fourth_sample_automatically_emits_plan_linked_comparator():
    prediction, plan = _prediction()
    db = _MeasurementDB(prediction)
    pool = _pool(db)
    comparator_result = {
        "status": "captured",
        "id": "observation:derived-comparator",
        "comparator": {"resolution_eligible": True},
        "resolution_trigger": {"state": "awaiting_horizon"},
    }
    samples = [
        ("intervention", "baseline", 0.50),
        ("intervention", "outcome", 0.74),
        ("comparator", "baseline", 0.52),
        ("comparator", "outcome", 0.57),
    ]
    with patch(
        "core.engine.foresight.comparators.record_comparator_observation",
        AsyncMock(return_value=comparator_result),
    ) as record:
        results = [
            await record_measurement_observation(**_record_kwargs(pool, plan, arm, phase, value))
            for arm, phase, value in samples
        ]

    assert [item["ingestion"]["status"] for item in results] == [
        "collecting",
        "collecting",
        "collecting",
        "ingested",
    ]
    assert record.await_count == 1
    kwargs = record.await_args.kwargs
    assert kwargs["execution"]["plan_id"] == plan["plan_id"]
    assert kwargs["measurements"][0]["intervention_after"] == 0.74
    assert results[-1]["ingestion"]["comparator_observation_id"] == "observation:derived-comparator"


@pytest.mark.asyncio
async def test_measurement_capture_is_idempotent_and_conflicting_retry_is_rejected():
    prediction, plan = _prediction()
    db = _MeasurementDB(prediction)
    pool = _pool(db)
    kwargs = _record_kwargs(pool, plan, "intervention", "baseline", 0.50)
    first = await record_measurement_observation(**kwargs)
    second = await record_measurement_observation(**kwargs)
    assert first["status"] == "captured"
    assert second["status"] == "duplicate"
    assert len(db.rows) == 1

    kwargs["value"] = 0.60
    with pytest.raises(MeasurementRequestConflict):
        await record_measurement_observation(**kwargs)


@pytest.mark.asyncio
async def test_identical_measurement_retry_survives_prediction_close():
    prediction, plan = _prediction()
    db = _MeasurementDB(prediction)
    pool = _pool(db)
    kwargs = _record_kwargs(pool, plan, "intervention", "baseline", 0.50)
    first = await record_measurement_observation(**kwargs)
    prediction["closed"] = True
    prediction["measurement_ingestion_state"] = {
        "contract_version": "ace.foresight.measurement-ingestion/v1",
        "prediction_id": prediction["id"],
        "plan_id": plan["plan_id"],
        "run_id": "checkout-run-1",
        "status": "ingested",
        "comparator_observation_id": "observation:derived",
    }

    second = await record_measurement_observation(**kwargs)

    assert first["status"] == "captured"
    assert second["status"] == "duplicate"
    assert second["ingestion"]["status"] == "ingested"
    assert second["ingestion"]["comparator_observation_id"] == "observation:derived"


@pytest.mark.asyncio
async def test_measurement_rejects_foreign_plan_and_unplanned_metric():
    prediction, plan = _prediction()
    pool = _pool(_MeasurementDB(prediction))
    kwargs = _record_kwargs(pool, plan, "intervention", "baseline", 0.50)
    kwargs["plan_id"] = "comparator_plan:aaaaaaaaaaaaaaaaaaaaaaaa"
    with pytest.raises(MeasurementTargetNotFound):
        await record_measurement_observation(**kwargs)

    kwargs = _record_kwargs(pool, plan, "intervention", "baseline", 0.50)
    kwargs["execution"]["plan_id"] = "comparator_plan:aaaaaaaaaaaaaaaaaaaaaaaa"
    with pytest.raises(MeasurementTargetNotFound):
        await record_measurement_observation(**kwargs)

    kwargs = _record_kwargs(pool, plan, "intervention", "baseline", 0.50)
    kwargs["metric"] = "conversion_rate"
    with pytest.raises(MeasurementTargetNotFound):
        await record_measurement_observation(**kwargs)


def test_v154_migration_is_additive_and_raw_samples_are_not_declared_resolution_evidence():
    from pathlib import Path

    migration = (Path(__file__).parents[1] / "core/schema/v154_measurement_ingestion_v1.surql").read_text(
        encoding="utf-8"
    )
    assert "measurement_contract" in migration
    assert "measurement_ingestion_state" in migration
    assert "ON TABLE observation" in migration
    assert "ON TABLE decision_prediction" in migration
    assert "comparator_resolution_eligible" not in migration
    assert "forecast_contract" not in migration
    assert "DELETE" not in migration
    assert "REMOVE" not in migration
    assert "value = '154'" in migration
