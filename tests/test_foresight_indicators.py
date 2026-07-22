from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

import pytest

from core.engine.foresight.contracts import FORECAST_CONTRACT_VERSION, build_forecast_contract
from core.engine.foresight.indicators import (
    IndicatorRequestConflict,
    evaluate_indicator_rules_for_prediction,
    evaluate_rule,
    record_indicator_observation,
)


def _prediction(*, automatic: bool = True) -> dict:
    raw = {
        "horizon_days": 30,
        "applicability_conditions": ["Rollout reaches users"],
        "no_action_baseline": "Reliability remains at 0.5.",
        "expected_changes": [
            {
                "capability_id": "checkout",
                "score_delta": 0.2,
                "lower_bound": 0.1,
                "upper_bound": 0.3,
                "mechanism": "Retry changes reduce failures.",
                "evidence_refs": ["decision:d1"],
            }
        ],
        "leading_indicators": ["Checkout reliability reaches 0.7"],
        "indicator_rules": (
            [
                {
                    "indicator_index": 1,
                    "capability_id": "checkout",
                    "dimension": "reliability",
                    "operator": "gte",
                    "threshold": 0.7,
                    "effect_when_met": "supports",
                    "effect_when_not_met": "weakens",
                }
            ]
            if automatic
            else []
        ),
        "falsification_condition": "Reliability remains below 0.7.",
        "primary_risk": "Provider failures dominate.",
    }
    contract = build_forecast_contract(
        raw,
        decision_id="decision:d1",
        product_id="product:alpha",
        archetype="skeptic",
        discipline="reliability",
        model="test-model",
        current_state_baseline={"checkout": {"reliability": 0.5}},
        baseline_observed_at="2026-01-01T00:00:00Z",
        baseline_observation_refs=["capability_quality:q0"],
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


class _IndicatorDB:
    def __init__(self, prediction: dict, quality: dict | None = None):
        self.prediction = prediction
        self.quality = quality
        self.observations: list[dict] = []
        self.calls: list[tuple[str, dict | None]] = []

    async def query(self, sql: str, params: dict | None = None):
        self.calls.append((sql, params))
        if "SELECT * FROM ONLY <record>$prediction" in sql:
            return [[self.prediction]]
        if "SELECT * FROM ONLY <record>$id" in sql:
            row = next(
                (item for item in self.observations if str(item.get("id")) == str((params or {}).get("id"))),
                None,
            )
            return [[row]] if row else [[]]
        if "FROM capability_quality" in sql:
            return [[self.quality]] if self.quality else [[]]
        if "UPSERT type::record('observation', $record_key)" in sql:
            row = {
                "id": f"observation:{params['record_key']}",
                "product": params["product"],
                "affected_decision": params["decision"],
                "affected_prediction": params["prediction"],
                "content_hash": params["content_hash"],
                "indicator_contract_version": params["contract_version"],
                "indicator_contract": params["contract"],
                "observed_at": params["observed_at"],
            }
            self.observations.append(row)
            return [[row]]
        if "observation_type = 'forecast_indicator'" in sql:
            return [list(reversed(self.observations))]
        return [[]]


def _pool(db: _IndicatorDB):
    context = AsyncMock()
    context.__aenter__ = AsyncMock(return_value=db)
    context.__aexit__ = AsyncMock(return_value=False)
    pool = MagicMock()
    pool.connection.return_value = context
    return pool


@pytest.mark.parametrize(
    ("rule", "value", "baseline", "effect", "reason"),
    [
        ({"operator": "gte", "threshold": 0.7, "effect_when_met": "supports"}, 0.8, None, "supports", "rule_met"),
        (
            {"operator": "lte", "threshold": 0.4, "effect_when_met": "falsifies", "effect_when_not_met": "supports"},
            0.5,
            None,
            "supports",
            "rule_not_met",
        ),
        (
            {"operator": "delta_gte", "threshold": 0.1, "effect_when_met": "supports"},
            0.7,
            0.5,
            "supports",
            "rule_met",
        ),
        (
            {"operator": "delta_gte", "threshold": 0.1, "effect_when_met": "supports"},
            0.7,
            None,
            "inconclusive",
            "missing_baseline",
        ),
    ],
)
def test_machine_indicator_rule_evaluation_is_deterministic(rule, value, baseline, effect, reason):
    assert evaluate_rule(rule, value, baseline) == (effect, reason)


@pytest.mark.asyncio
async def test_manual_indicator_evidence_is_idempotent_and_does_not_mutate_forecast():
    prediction = _prediction()
    db = _IndicatorDB(prediction)
    pool = _pool(db)
    kwargs = {
        "product_id": "product:alpha",
        "decision_id": "decision:d1",
        "prediction_id": "decision_prediction:p1",
        "request_id": "manual-indicator-v1",
        "indicator_id": "indicator:1",
        "effect": "supports",
        "observed_at": "2026-02-01T00:00:00Z",
        "value": 0.75,
        "unit": "capability_quality_score",
        "evidence_refs": ["measurement:m1"],
        "reason": "Observed in the reliability report.",
        "content": "Checkout reliability reached 0.75.",
        "source_kind": "manual_observation",
        "source_surface": "thin_mcp",
        "actor_ref": "user:operator",
        "pool": pool,
    }

    first = await record_indicator_observation(**kwargs)
    second = await record_indicator_observation(**kwargs)

    assert first["status"] == "captured"
    assert second["status"] == "duplicate"
    assert first["id"] == second["id"]
    assert first["indicator_state"]["overall_state"] == "supports"
    upserts = [sql for sql, _ in db.calls if "UPSERT type::record('observation'" in sql]
    assert len(upserts) == 1
    prediction_updates = [sql for sql, _ in db.calls if "UPDATE <record>$prediction" in sql]
    assert prediction_updates
    assert all("forecast_contract" not in sql for sql in prediction_updates)


@pytest.mark.asyncio
async def test_indicator_request_id_conflict_never_overwrites_evidence():
    prediction = _prediction()
    db = _IndicatorDB(prediction)
    pool = _pool(db)
    common = {
        "product_id": "product:alpha",
        "decision_id": "decision:d1",
        "prediction_id": "decision_prediction:p1",
        "request_id": "manual-indicator-v1",
        "indicator_id": "indicator:1",
        "observed_at": "2026-02-01T00:00:00Z",
        "value": 0.75,
        "unit": "score",
        "evidence_refs": ["measurement:m1"],
        "reason": None,
        "content": "Observed signal.",
        "source_kind": "manual_observation",
        "source_surface": "api",
        "actor_ref": "user:operator",
        "pool": pool,
    }
    await record_indicator_observation(effect="supports", **common)
    with pytest.raises(IndicatorRequestConflict):
        await record_indicator_observation(effect="falsifies", **common)
    assert len(db.observations) == 1


@pytest.mark.asyncio
async def test_automatic_quality_rule_records_evidence_and_aggregates_state():
    prediction = _prediction()
    quality = {
        "id": "capability_quality:q1",
        "score": 0.75,
        "dimension": "reliability",
        "assessed_at": "2026-02-01T00:00:00Z",
    }
    db = _IndicatorDB(prediction, quality)
    results = await evaluate_indicator_rules_for_prediction(prediction, "product:alpha", pool=_pool(db))

    assert len(results) == 1
    indicator = results[0]["indicator"]
    assert indicator["effect"] == "supports"
    assert indicator["measurement"]["value"] == 0.75
    assert indicator["evidence_refs"] == ["capability_quality:q1"]
    assert results[0]["indicator_state"]["overall_state"] == "supports"


@pytest.mark.asyncio
async def test_prose_only_indicator_remains_explicitly_manual():
    prediction = _prediction(automatic=False)
    db = _IndicatorDB(prediction)
    results = await evaluate_indicator_rules_for_prediction(prediction, "product:alpha", pool=_pool(db))

    assert results == []
    indicator = prediction["forecast_contract"]["resolution_rule"]["indicators"][0]
    assert indicator["monitoring"] == "manual"
    assert not any("FROM capability_quality" in sql for sql, _ in db.calls)
