# tests/test_api_observations.py
"""Tests for POST /observations — lightweight observation capture."""

from unittest.mock import AsyncMock, patch

import pytest
from fastapi.testclient import TestClient

from core.engine.api.main import app
from core.engine.core.auth import get_current_user


@pytest.fixture
def client():
    mock_user = {"sub": "user:test", "product": "product:test"}
    app.dependency_overrides[get_current_user] = lambda: mock_user
    yield TestClient(app)
    app.dependency_overrides.clear()


def test_create_observation_returns_201(client):
    """POST /observations creates an observation and returns 201."""
    with patch("core.engine.api.capture.pool") as mock_pool:
        mock_conn = AsyncMock()
        mock_conn.query = AsyncMock(return_value=[[{"id": "observation:abc"}]])
        mock_pool.connection.return_value.__aenter__ = AsyncMock(return_value=mock_conn)
        mock_pool.connection.return_value.__aexit__ = AsyncMock(return_value=False)

        resp = client.post(
            "/observations",
            json={
                "observation_type": "correction",
                "content": "Use rem not px",
                "domain_path": "design_systems.tokens",
                "confidence": 0.85,
            },
        )

    assert resp.status_code == 201
    data = resp.json()
    assert data["status"] == "captured"
    assert "id" in data


def test_create_observation_default_confidence(client):
    """POST /observations uses default confidence of 0.7."""
    with patch("core.engine.api.capture.pool") as mock_pool:
        mock_conn = AsyncMock()
        mock_conn.query = AsyncMock(return_value=[[{"id": "observation:def"}]])
        mock_pool.connection.return_value.__aenter__ = AsyncMock(return_value=mock_conn)
        mock_pool.connection.return_value.__aexit__ = AsyncMock(return_value=False)

        resp = client.post(
            "/observations",
            json={
                "observation_type": "pattern",
                "content": "Teams prefer async standup",
                "domain_path": "operations.process",
            },
        )

    assert resp.status_code == 201
    call_args = mock_conn.query.call_args
    # Params dict is the second positional arg to db.query(sql, params)
    params = call_args[0][1] if len(call_args[0]) > 1 else call_args[1]
    assert params["confidence"] == 0.7


def test_create_observation_validates_required_fields(client):
    """POST /observations returns 422 when required fields are missing."""
    resp = client.post(
        "/observations",
        json={
            "observation_type": "correction",
            # missing content and domain_path
        },
    )
    assert resp.status_code == 422


def _intervention_payload(request_id: str = "checkout-rollout-v1") -> dict:
    return {
        "observation_type": "intervention",
        "content": "Checkout retry rollout completed.",
        "domain_path": "reliability.checkout",
        "confidence": 0.95,
        "source_surface": "thin_mcp",
        "intervention": {
            "request_id": request_id,
            "decision_id": "decision:d1",
            "prediction_id": "decision_prediction:p1",
            "status": "completed",
            "observed_at": "2026-02-01T00:00:00Z",
            "applicability_conditions_met": True,
            "conditions": [
                {
                    "condition": "Rollout reaches 80% of traffic",
                    "met": True,
                    "evidence_refs": ["deployment:r1"],
                }
            ],
            "exposure": {"degree": 0.9, "scope": "checkout traffic", "unit": "fraction"},
            "evidence_refs": ["deployment:r1"],
        },
    }


def _indicator_payload(request_id: str = "checkout-indicator-v1") -> dict:
    return {
        "observation_type": "forecast_indicator",
        "content": "Checkout reliability reached 0.75.",
        "domain_path": "reliability.checkout",
        "source_surface": "thin_mcp",
        "indicator": {
            "request_id": request_id,
            "decision_id": "decision:d1",
            "prediction_id": "decision_prediction:p1",
            "indicator_id": "indicator:1",
            "effect": "supports",
            "observed_at": "2026-02-01T00:00:00Z",
            "value": 0.75,
            "unit": "capability_quality_score",
            "evidence_refs": ["measurement:m1"],
            "reason": "Observed in the reliability report.",
        },
    }


def _comparator_payload(request_id: str = "checkout-comparator-v1") -> dict:
    return {
        "observation_type": "forecast_comparator",
        "content": "Observed the checkout holdout against exposed traffic.",
        "domain_path": "reliability.checkout",
        "source_surface": "thin_mcp",
        "comparator": {
            "request_id": request_id,
            "decision_id": "decision:d1",
            "prediction_id": "decision_prediction:p1",
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
            "evidence_refs": ["experiment:e1"],
            "execution": {
                "plan_id": "comparator_plan:aaaaaaaaaaaaaaaaaaaaaaaa",
                "assignment_unit": "request",
                "eligibility_criteria_met": True,
                "guardrail_breaches": [],
                "deviations": [],
            },
        },
    }


def test_forecast_indicator_uses_existing_capture_boundary(client):
    result = {
        "status": "captured",
        "id": "observation:s1",
        "indicator": {"effect": "supports"},
        "indicator_state": {"overall_state": "supports"},
    }
    with patch(
        "core.engine.foresight.indicators.record_indicator_observation",
        AsyncMock(return_value=result),
    ) as record:
        response = client.post("/observations", json=_indicator_payload())

    assert response.status_code == 201
    assert response.json() == result
    kwargs = record.await_args.kwargs
    assert kwargs["product_id"] == "product:test"
    assert kwargs["prediction_id"] == "decision_prediction:p1"
    assert kwargs["indicator_id"] == "indicator:1"
    assert kwargs["source_surface"] == "thin_mcp"


def test_forecast_indicator_requires_structured_payload(client):
    response = client.post(
        "/observations",
        json={
            "observation_type": "forecast_indicator",
            "content": "A signal occurred.",
            "domain_path": "reliability.checkout",
        },
    )
    assert response.status_code == 422


def test_forecast_comparator_uses_existing_capture_boundary(client):
    result = {
        "status": "captured",
        "id": "observation:c1",
        "comparator": {"resolution_eligible": True},
        "comparator_state": {"status": "eligible"},
        "resolution_trigger": {"state": "awaiting_horizon"},
    }
    with patch(
        "core.engine.foresight.comparators.record_comparator_observation",
        AsyncMock(return_value=result),
    ) as record:
        response = client.post("/observations", json=_comparator_payload())

    assert response.status_code == 201
    assert response.json() == result
    kwargs = record.await_args.kwargs
    assert kwargs["product_id"] == "product:test"
    assert kwargs["prediction_id"] == "decision_prediction:p1"
    assert kwargs["comparator_type"] == "holdout"
    assert kwargs["design"] == "matched"
    assert kwargs["measurements"][0]["capability_id"] == "checkout"
    assert kwargs["execution"]["plan_id"] == "comparator_plan:aaaaaaaaaaaaaaaaaaaaaaaa"


def test_forecast_comparator_requires_structured_payload(client):
    response = client.post(
        "/observations",
        json={
            "observation_type": "forecast_comparator",
            "content": "A comparison occurred.",
            "domain_path": "reliability.checkout",
        },
    )
    assert response.status_code == 422


def test_forecast_measurement_uses_existing_capture_boundary(client):
    payload = {
        "observation_type": "forecast_measurement",
        "content": "Observed the intervention baseline metric.",
        "domain_path": "reliability.checkout",
        "source_surface": "thin_mcp",
        "measurement": {
            "request_id": "checkout-run-1-intervention-baseline",
            "decision_id": "decision:d1",
            "prediction_id": "decision_prediction:p1",
            "plan_id": "comparator_plan:aaaaaaaaaaaaaaaaaaaaaaaa",
            "run_id": "checkout-run-1",
            "source_type": "structured_metric",
            "capability_id": "checkout",
            "metric": "capability_quality",
            "unit": "score_delta",
            "arm": "intervention",
            "phase": "baseline",
            "value": 0.5,
            "measured_at": "2026-01-01T00:00:00Z",
            "window_start": "2026-01-01T00:00:00Z",
            "window_end": "2026-01-15T00:00:00Z",
            "comparator_type": "holdout",
            "design": "matched",
            "evidence_refs": ["metric:checkout:ib"],
            "execution": {
                "plan_id": "comparator_plan:aaaaaaaaaaaaaaaaaaaaaaaa",
                "assignment_unit": "request",
                "eligibility_criteria_met": True,
            },
        },
    }
    result = {
        "status": "captured",
        "id": "observation:m1",
        "measurement": {"resolution_eligible": False},
        "ingestion": {"status": "collecting"},
    }
    with patch(
        "core.engine.foresight.measurements.record_measurement_observation",
        AsyncMock(return_value=result),
    ) as record:
        response = client.post("/observations", json=payload)

    assert response.status_code == 201
    assert response.json() == result
    kwargs = record.await_args.kwargs
    assert kwargs["plan_id"] == "comparator_plan:aaaaaaaaaaaaaaaaaaaaaaaa"
    assert kwargs["arm"] == "intervention"
    assert kwargs["phase"] == "baseline"
    assert kwargs["source_surface"] == "thin_mcp"


def test_forecast_measurement_requires_structured_payload(client):
    response = client.post(
        "/observations",
        json={
            "observation_type": "forecast_measurement",
            "content": "A metric occurred.",
            "domain_path": "reliability.checkout",
        },
    )
    assert response.status_code == 422


def test_intervention_observation_is_product_scoped_and_triggers_resolution(client):
    with (
        patch("core.engine.api.capture.pool") as mock_pool,
        patch(
            "core.engine.foresight.reconciler.process_intervention_observation",
            AsyncMock(return_value={"state": "awaiting_horizon"}),
        ) as trigger,
    ):
        mock_conn = AsyncMock()

        async def query(sql, params=None):
            if "UPSERT type::record('observation', $record_key)" in sql:
                return [
                    [
                        {
                            "id": f"observation:{params['record_key']}",
                            "product": "product:test",
                            "affected_decision": "decision:d1",
                            "affected_prediction": "decision_prediction:p1",
                            "intervention_contract_version": params["contract_version"],
                            "intervention_contract": params["contract"],
                        }
                    ]
                ]
            if params and params.get("id") == "decision:d1":
                return [[{"id": "decision:d1", "product": "product:test"}]]
            if params and params.get("id") == "decision_prediction:p1":
                return [
                    [
                        {
                            "id": "decision_prediction:p1",
                            "decision": "decision:d1",
                            "product": "product:test",
                        }
                    ]
                ]
            return [[]]

        mock_conn.query = AsyncMock(side_effect=query)
        mock_pool.connection.return_value.__aenter__ = AsyncMock(return_value=mock_conn)
        mock_pool.connection.return_value.__aexit__ = AsyncMock(return_value=False)
        response = client.post("/observations", json=_intervention_payload())

    assert response.status_code == 201
    body = response.json()
    assert body["status"] == "captured"
    assert body["intervention"]["status"] == "completed"
    assert body["intervention"]["product_id"] == "product:test"
    assert body["resolution_trigger"]["state"] == "awaiting_horizon"
    trigger.assert_awaited_once()
    upsert_params = next(
        call.args[1]
        for call in mock_conn.query.await_args_list
        if "UPSERT type::record('observation', $record_key)" in call.args[0]
    )
    assert upsert_params["product"] == "product:test"
    assert upsert_params["prediction"] == "decision_prediction:p1"


def test_intervention_observation_request_id_conflict_never_overwrites(client):
    existing = {
        "id": "observation:existing",
        "product": "product:test",
        "affected_decision": "decision:d1",
        "affected_prediction": "decision_prediction:p1",
    }
    with patch("core.engine.api.capture.pool") as mock_pool:
        mock_conn = AsyncMock()
        calls = 0

        async def query(sql, params=None):
            nonlocal calls
            calls += 1
            if params and params.get("id") == "decision:d1":
                return [[{"id": "decision:d1", "product": "product:test"}]]
            if params and params.get("id") == "decision_prediction:p1":
                return [[[{"id": "decision_prediction:p1", "decision": "decision:d1", "product": "product:test"}]]][0]
            if "SELECT * FROM ONLY <record>$id" in sql:
                # A conflicting fingerprint proves retries cannot silently overwrite evidence.
                return [[{**existing, "content_hash": "different-payload"}]]
            return [[]]

        mock_conn.query = AsyncMock(side_effect=query)
        mock_pool.connection.return_value.__aenter__ = AsyncMock(return_value=mock_conn)
        mock_pool.connection.return_value.__aexit__ = AsyncMock(return_value=False)
        response = client.post("/observations", json=_intervention_payload())

    assert response.status_code == 409
    assert response.json()["detail"] == "intervention request_id conflict"
    assert not any(
        "UPSERT type::record('observation', $record_key)" in call.args[0] for call in mock_conn.query.await_args_list
    )
    assert calls == 3


def test_intervention_observation_identical_retry_returns_same_record(client):
    with (
        patch("core.engine.api.capture.pool") as mock_pool,
        patch(
            "core.engine.foresight.reconciler.process_intervention_observation",
            AsyncMock(return_value={"state": "awaiting_horizon"}),
        ) as trigger,
    ):
        mock_conn = AsyncMock()
        stored: dict | None = None

        async def query(sql, params=None):
            nonlocal stored
            if params and params.get("id") == "decision:d1":
                return [[{"id": "decision:d1", "product": "product:test"}]]
            if params and params.get("id") == "decision_prediction:p1":
                return [
                    [
                        {
                            "id": "decision_prediction:p1",
                            "decision": "decision:d1",
                            "product": "product:test",
                        }
                    ]
                ]
            if "SELECT * FROM ONLY <record>$id" in sql:
                return [[stored]] if stored else [[]]
            if "UPSERT type::record('observation', $record_key)" in sql:
                stored = {
                    "id": f"observation:{params['record_key']}",
                    "product": "product:test",
                    "affected_decision": "decision:d1",
                    "affected_prediction": "decision_prediction:p1",
                    "content_hash": params["content_hash"],
                    "intervention_contract_version": params["contract_version"],
                    "intervention_contract": params["contract"],
                }
                return [[stored]]
            return [[]]

        mock_conn.query = AsyncMock(side_effect=query)
        mock_pool.connection.return_value.__aenter__ = AsyncMock(return_value=mock_conn)
        mock_pool.connection.return_value.__aexit__ = AsyncMock(return_value=False)
        first = client.post("/observations", json=_intervention_payload())
        second = client.post("/observations", json=_intervention_payload())

    assert first.status_code == 201
    assert second.status_code == 201
    assert first.json()["id"] == second.json()["id"]
    assert second.json()["status"] == "duplicate"
    assert trigger.await_count == 1
    upserts = [
        call
        for call in mock_conn.query.await_args_list
        if "UPSERT type::record('observation', $record_key)" in call.args[0]
    ]
    assert len(upserts) == 1


def test_intervention_payload_rejects_conflicting_condition_summary(client):
    payload = _intervention_payload()
    payload["intervention"]["applicability_conditions_met"] = False
    response = client.post("/observations", json=payload)
    assert response.status_code == 422


def test_intervention_observation_cannot_link_cross_product_prediction(client):
    with patch("core.engine.api.capture.pool") as mock_pool:
        mock_conn = AsyncMock()

        async def query(_sql, params=None):
            if params and params.get("id") == "decision:d1":
                return [[{"id": "decision:d1", "product": "product:test"}]]
            if params and params.get("id") == "decision_prediction:p1":
                return [
                    [
                        {
                            "id": "decision_prediction:p1",
                            "decision": "decision:d1",
                            "product": "product:other",
                        }
                    ]
                ]
            return [[]]

        mock_conn.query = AsyncMock(side_effect=query)
        mock_pool.connection.return_value.__aenter__ = AsyncMock(return_value=mock_conn)
        mock_pool.connection.return_value.__aexit__ = AsyncMock(return_value=False)
        response = client.post("/observations", json=_intervention_payload())

    assert response.status_code == 404
    assert response.json()["detail"] == "Not found"
