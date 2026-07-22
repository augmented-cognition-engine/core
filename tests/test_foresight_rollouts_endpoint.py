"""Tests for /foresight/{id}/rollouts endpoint."""

from unittest.mock import AsyncMock, patch

import pytest
from httpx import ASGITransport, AsyncClient

from core.engine.api.main import app


def _make_db_conn():
    """Return a mock async context manager that yields a fake DB handle.

    The foresight endpoints do ``async with _pool.connection() as db:``
    and then call ``db.query()``. parse_rows is patched separately per
    test; the db mock just needs to be a valid async context manager.
    """
    mock_db = AsyncMock()
    mock_db.query = AsyncMock(return_value=[])

    mock_conn = AsyncMock()
    mock_conn.__aenter__ = AsyncMock(return_value=mock_db)
    mock_conn.__aexit__ = AsyncMock(return_value=False)
    return mock_conn


@pytest.mark.asyncio
async def test_get_prediction_scores_is_product_scoped_and_sample_aware():
    from core.engine.foresight.scoring import score_prediction

    score = score_prediction(
        forecast_contract={
            "consequences": [
                {
                    "local_id": "consequence:1",
                    "target": {"entity_id": "auth"},
                    "estimate": {
                        "kind": "continuous",
                        "point": 0.2,
                        "lower": 0.0,
                        "upper": 0.4,
                        "interval_coverage": 0.8,
                    },
                }
            ]
        },
        actual_deltas={"auth": 0.3},
        resolution_score_eligible=True,
        non_score_reason=None,
    )
    row = {
        "id": "prediction_outcome:o1",
        "prediction": "decision_prediction:p1",
        "decision": "decision:d1",
        "discipline": "testing",
        "prediction_score_version": score["contract_version"],
        "prediction_score": score,
        "closed_at": "2026-05-14T00:00:00Z",
    }
    conn = _make_db_conn()
    with patch("core.engine.api.foresight._pool.connection", return_value=conn):
        with patch("core.engine.api.foresight.parse_rows", return_value=[row]):
            async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
                response = await ac.get("/foresight/product:test/scores?limit=900")

    assert response.status_code == 200
    body = response.json()
    assert body["summary"]["contract_version"] == "ace.foresight.prediction-score/v1"
    assert body["summary"]["scored_consequence_count"] == 1
    assert body["summary"]["by_interval_coverage"][0]["evidence_maturity"] == "anecdotal"
    assert body["outcomes"][0]["prediction_score"]["state"] == "scored"
    query = conn.__aenter__.return_value.query.await_args.args[0]
    params = conn.__aenter__.return_value.query.await_args.args[1]
    assert "product = <record>$product" in query
    assert params == {"product": "product:test", "limit": 500}


@pytest.mark.asyncio
async def test_get_outside_view_returns_frozen_product_scoped_baseline():
    from core.engine.foresight.contracts import build_forecast_contract

    outside_view = {
        "contract_version": "ace.foresight.outside-view-baseline/v1",
        "state": "supported",
        "target_priors": {
            "auth": {
                "case_count": 3,
                "weighted_mean_actual_delta": 0.2,
                "maturity": "supported",
            }
        },
        "analogues": [{"outcome_id": "prediction_outcome:o1", "similarity": 1.0}],
    }
    contract = build_forecast_contract(
        {
            "horizon_days": 14,
            "applicability_conditions": ["rollout occurs"],
            "no_action_baseline": "No observed comparator.",
            "expected_changes": [
                {
                    "capability_id": "auth",
                    "score_delta": 0.2,
                    "lower_bound": 0.1,
                    "upper_bound": 0.3,
                    "mechanism": "More reliable callbacks.",
                    "evidence_refs": ["prediction_outcome:o1"],
                }
            ],
            "primary_risk": "Callback regressions.",
            "leading_indicators": ["Auth reliability rises"],
            "falsification_condition": "Auth reliability does not rise.",
        },
        decision_id="decision:d1",
        product_id="product:test",
        archetype="skeptic",
        discipline="testing",
        model="test-model",
        outside_view_baseline=outside_view,
    )
    row = {
        "id": "decision_prediction:p1",
        "decision": "decision:d1",
        "product": "product:test",
        "contract_version": contract["contract_version"],
        "forecast_contract": contract,
        "closed": False,
        "created_at": "2026-05-14T00:00:00Z",
    }
    conn = _make_db_conn()
    with patch("core.engine.api.foresight._pool.connection", return_value=conn):
        with patch("core.engine.api.foresight.parse_rows", return_value=[row]):
            async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
                response = await ac.get("/foresight/product:test/outside-view?limit=500")

    assert response.status_code == 200
    baseline = response.json()["baselines"][0]
    assert baseline["prediction_id"] == "decision_prediction:p1"
    assert baseline["outside_view"]["state"] == "supported"
    assert baseline["no_action_grounding"]["empirically_identified"] is False
    query_params = conn.__aenter__.return_value.query.await_args.args[1]
    assert query_params == {"product": "product:test", "limit": 100}


@pytest.mark.asyncio
async def test_get_rollouts_empty_when_no_cache():
    """No cached rollout → empty scenarios list."""
    with patch("core.engine.api.foresight._pool.connection", return_value=_make_db_conn()):
        with patch("core.engine.api.foresight.parse_rows", return_value=[]):
            async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
                resp = await ac.get("/foresight/product:test/rollouts")
    assert resp.status_code == 200
    assert resp.json() == {"scenarios": []}


@pytest.mark.asyncio
async def test_get_rollouts_returns_latest_cached():
    """Latest cached rollout is returned with branches + authored_by normalized."""
    cached = {
        "id": "rollout_cache:abc",
        "candidate": "Use JWT",
        "product": "product:test",
        "branches": [
            {"path": ["x"], "terminal_score": 0.8, "top_risk": "leaks", "state_override": {}},
            {
                "path": ["y"],
                "terminal_score": 0.7,
                "top_risk": "complexity",
                "state_override": {},
                "authored_by_archetype": "skeptic",
            },
        ],
        "best_path": ["x"],
        "created_at": "2026-05-14T00:00:00Z",
    }
    with patch("core.engine.api.foresight._pool.connection", return_value=_make_db_conn()):
        with patch("core.engine.api.foresight.parse_rows", return_value=[cached]):
            async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
                resp = await ac.get("/foresight/product:test/rollouts")
    assert resp.status_code == 200
    body = resp.json()
    assert len(body["scenarios"]) == 1
    scenario = body["scenarios"][0]
    # Legacy branches without authored_by_archetype get normalized to ""
    assert scenario["branches"][0]["authored_by_archetype"] == ""
    assert scenario["branches"][1]["authored_by_archetype"] == "skeptic"


@pytest.mark.asyncio
async def test_get_interventions_returns_bounded_product_scoped_contracts():
    from core.engine.foresight.contracts import build_intervention_observation_contract

    contract = build_intervention_observation_contract(
        observation_id="observation:i1",
        request_id="checkout-rollout-v1",
        decision_id="decision:d1",
        prediction_id="decision_prediction:p1",
        product_id="product:test",
        status="completed",
        observed_at="2026-05-14T00:00:00Z",
        applicability_conditions_met=True,
        conditions=[],
        exposure={"degree": 1.0},
        evidence_refs=["deployment:r1"],
        confounders=[],
        missing_evidence=[],
        reason=None,
        source_surface="thin_mcp",
        actor_ref="user:test",
    )
    row = {
        "id": "observation:i1",
        "product": "product:test",
        "affected_decision": "decision:d1",
        "affected_prediction": "decision_prediction:p1",
        "intervention_contract_version": contract["contract_version"],
        "intervention_contract": contract,
    }
    conn = _make_db_conn()
    with patch("core.engine.api.foresight._pool.connection", return_value=conn):
        with patch("core.engine.api.foresight.parse_rows", return_value=[row]):
            async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
                response = await ac.get("/foresight/product:test/interventions?limit=500")

    assert response.status_code == 200
    intervention = response.json()["interventions"][0]
    assert intervention["contract_version"] == "ace.foresight.intervention-observation/v1"
    assert intervention["prediction_id"] == "decision_prediction:p1"
    assert intervention["status"] == "completed"
    query_params = conn.__aenter__.return_value.query.await_args.args[1]
    assert query_params == {"product": "product:test", "limit": 100}


@pytest.mark.asyncio
async def test_get_indicators_returns_bounded_product_scoped_evidence():
    from core.engine.foresight.contracts import build_indicator_observation_contract

    contract = build_indicator_observation_contract(
        observation_id="observation:s1",
        request_id="checkout-indicator-v1",
        decision_id="decision:d1",
        prediction_id="decision_prediction:p1",
        product_id="product:test",
        indicator_id="indicator:1",
        indicator_description="Checkout reliability reaches 0.7",
        effect="supports",
        observed_at="2026-05-14T00:00:00Z",
        value=0.75,
        unit="capability_quality_score",
        evidence_refs=["capability_quality:q1"],
        source_kind="automatic_quality_rule",
        source_surface="sentinel",
        actor_ref="ace:indicator_evaluator",
    )
    row = {
        "id": "observation:s1",
        "product": "product:test",
        "affected_decision": "decision:d1",
        "affected_prediction": "decision_prediction:p1",
        "indicator_contract_version": contract["contract_version"],
        "indicator_contract": contract,
    }
    conn = _make_db_conn()
    with patch("core.engine.api.foresight._pool.connection", return_value=conn):
        with patch("core.engine.api.foresight.parse_rows", return_value=[row]):
            async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
                response = await ac.get("/foresight/product:test/indicators?limit=500")

    assert response.status_code == 200
    indicator = response.json()["indicators"][0]
    assert indicator["contract_version"] == "ace.foresight.indicator-observation/v1"
    assert indicator["effect"] == "supports"
    query_params = conn.__aenter__.return_value.query.await_args.args[1]
    assert query_params == {"product": "product:test", "limit": 200}


@pytest.mark.asyncio
async def test_get_comparators_returns_bounded_product_scoped_evidence():
    from core.engine.foresight.contracts import build_comparator_observation_contract

    contract = build_comparator_observation_contract(
        observation_id="observation:c1",
        request_id="checkout-comparator-v1",
        decision_id="decision:d1",
        prediction_id="decision_prediction:p1",
        product_id="product:test",
        comparator_type="holdout",
        design="matched",
        observed_at="2026-05-14T00:00:00Z",
        measurements=[
            {
                "capability_id": "checkout",
                "intervention_before": 0.5,
                "intervention_after": 0.7,
                "comparator_before": 0.5,
                "comparator_after": 0.55,
                "evidence_refs": ["experiment:e1"],
            }
        ],
        evidence_refs=["experiment:e1"],
    )
    row = {
        "id": "observation:c1",
        "product": "product:test",
        "affected_decision": "decision:d1",
        "affected_prediction": "decision_prediction:p1",
        "comparator_contract_version": contract["contract_version"],
        "comparator_contract": contract,
    }
    conn = _make_db_conn()
    with patch("core.engine.api.foresight._pool.connection", return_value=conn):
        with patch("core.engine.api.foresight.parse_rows", return_value=[row]):
            async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
                response = await ac.get("/foresight/product:test/comparators?limit=500")

    assert response.status_code == 200
    comparator = response.json()["comparators"][0]
    assert comparator["contract_version"] == "ace.foresight.comparator-observation/v1"
    assert comparator["resolution_eligible"] is True
    assert comparator["measurements"][0]["effect_delta"] == pytest.approx(0.15)
    query_params = conn.__aenter__.return_value.query.await_args.args[1]
    assert query_params == {"product": "product:test", "limit": 100}


@pytest.mark.asyncio
async def test_get_comparator_plans_returns_frozen_plan_only_contracts():
    from core.engine.foresight.contracts import build_comparator_plan

    plan = build_comparator_plan(
        {
            "comparator_type": "holdout",
            "assignment_design": "matched",
            "feasibility": "conditional",
            "required_conditions": ["A comparable unexposed cohort exists"],
            "assignment_unit": "request",
            "measurements": [{"capability_id": "checkout", "cadence": "daily"}],
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
    )
    row = {
        "id": "decision_prediction:p1",
        "decision": "decision:d1",
        "product": "product:test",
        "horizon_days": 14,
        "comparator_plan_version": plan["contract_version"],
        "comparator_plan": plan,
        "comparator_plan_status": plan["status"],
        "created_at": "2026-05-14T00:00:00Z",
    }
    conn = _make_db_conn()
    with patch("core.engine.api.foresight._pool.connection", return_value=conn):
        with patch("core.engine.api.foresight.parse_rows", return_value=[row]):
            async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
                response = await ac.get("/foresight/product:test/comparator-plans?limit=500")

    assert response.status_code == 200
    projected = response.json()["plans"][0]
    assert projected["prediction_id"] == "decision_prediction:p1"
    assert projected["plan"]["contract_version"] == "ace.foresight.comparator-plan/v1"
    assert projected["plan"]["resolution_eligible"] is False
    query_params = conn.__aenter__.return_value.query.await_args.args[1]
    assert query_params == {"product": "product:test", "limit": 100}


@pytest.mark.asyncio
async def test_get_measurements_returns_raw_non_resolution_samples():
    from core.engine.foresight.measurements import build_measurement_observation_contract

    contract = build_measurement_observation_contract(
        observation_id="observation:m1",
        request_id="checkout-run-1-ib",
        decision_id="decision:d1",
        prediction_id="decision_prediction:p1",
        product_id="product:test",
        plan_id="comparator_plan:aaaaaaaaaaaaaaaaaaaaaaaa",
        run_id="checkout-run-1",
        source_type="structured_metric",
        capability_id="checkout",
        metric="capability_quality",
        unit="score_delta",
        arm="intervention",
        phase="baseline",
        value=0.5,
        measured_at="2026-01-01T00:00:00Z",
        window_start="2026-01-01T00:00:00Z",
        window_end="2026-01-15T00:00:00Z",
        comparator_type="holdout",
        design="matched",
        evidence_refs=["metric:checkout:ib"],
        execution={"plan_id": "comparator_plan:aaaaaaaaaaaaaaaaaaaaaaaa"},
        confounders=[],
        source_surface="thin_mcp",
        actor_ref="user:test",
    )
    row = {
        "id": "observation:m1",
        "measurement_contract_version": contract["contract_version"],
        "measurement_contract": contract,
        "measurement_ingestion_status": "collecting",
    }
    conn = _make_db_conn()
    with patch("core.engine.api.foresight._pool.connection", return_value=conn):
        with patch("core.engine.api.foresight.parse_rows", return_value=[row]):
            async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
                response = await ac.get("/foresight/product:test/measurements?limit=900")

    assert response.status_code == 200
    item = response.json()["measurements"][0]
    assert item["sample"]["resolution_eligible"] is False
    assert item["ingestion_status"] == "collecting"
    query = conn.__aenter__.return_value.query.await_args.args[0]
    params = conn.__aenter__.return_value.query.await_args.args[1]
    assert "product = <record>$product" in query
    assert params == {"product": "product:test", "limit": 500}


@pytest.mark.asyncio
async def test_get_measurement_ingestions_returns_bounded_prediction_receipts():
    row = {
        "id": "decision_prediction:p1",
        "decision": "decision:d1",
        "measurement_ingestion_version": "ace.foresight.measurement-ingestion/v1",
        "measurement_ingestion_status": "ingested",
        "measurement_ingestion_updated_at": "2026-01-15T00:00:00Z",
        "measurement_ingestion_state": {
            "contract_version": "ace.foresight.measurement-ingestion/v1",
            "run_id": "checkout-run-1",
            "status": "ingested",
        },
    }
    conn = _make_db_conn()
    with patch("core.engine.api.foresight._pool.connection", return_value=conn):
        with patch("core.engine.api.foresight.parse_rows", return_value=[row]):
            async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
                response = await ac.get("/foresight/product:test/measurement-ingestions?limit=900")

    assert response.status_code == 200
    item = response.json()["ingestions"][0]
    assert item["prediction_id"] == "decision_prediction:p1"
    assert item["status"] == "ingested"
    params = conn.__aenter__.return_value.query.await_args.args[1]
    assert params == {"product": "product:test", "limit": 100}


@pytest.mark.asyncio
async def test_generate_rollout_requires_candidate():
    """POST without candidate_decision → 400."""
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        resp = await ac.post("/foresight/product:test/rollouts/generate", json={})
    assert resp.status_code == 400


@pytest.mark.asyncio
async def test_generate_rollout_calls_planner():
    """POST with candidate triggers plan_rollout."""
    fake_result_dict = {
        "candidate": "x",
        "product_id": "product:test",
        "branches": [],
        "best_path": ["x"],
        "created_at": "2026-05-14",
    }

    class _Stub:
        candidate = "x"
        product_id = "product:test"
        branches: list = []
        best_path = ["x"]
        created_at = "2026-05-14"

    with patch("core.engine.foresight.planner.plan_rollout", new=AsyncMock(return_value=_Stub())):
        with patch("core.engine.api.foresight.asdict", return_value=fake_result_dict):
            async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
                resp = await ac.post(
                    "/foresight/product:test/rollouts/generate",
                    json={"candidate_decision": "Use JWT for auth"},
                )
    assert resp.status_code == 200
    assert resp.json()["candidate"] == "x"


@pytest.mark.asyncio
async def test_get_calibration_empty():
    """No outcomes → empty list."""
    with patch("core.engine.api.foresight._pool.connection", return_value=_make_db_conn()):
        with patch("core.engine.api.foresight.parse_rows", return_value=[]):
            async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
                resp = await ac.get("/foresight/product:test/calibration")
    assert resp.status_code == 200
    assert resp.json() == {"outcomes": []}


@pytest.mark.asyncio
async def test_get_calibration_returns_outcomes_with_decision_title():
    """Closed outcomes surface enriched with the underlying decision title.

    Without the title the card reads as a context-free archetype + score;
    the title is what makes "Skeptic's call on Adopt JWT played out at 98%"
    legible.
    """
    outcome_rows = [
        {
            "id": "prediction_outcome:po1",
            "prediction": "decision_prediction:p1",
            "decision": "decision:d1",
            "archetype": "pm",
            "discipline": "product",
            "calibration_score": 0.82,
            "predicted_deltas": {"capability:onboard": 0.3},
            "actual_deltas": {"capability:onboard": 0.27},
            "closed_at": "2026-05-14T00:00:00Z",
        }
    ]
    decision_rows = [{"id": "decision:d1", "title": "Adopt JWT for partner API auth"}]

    # parse_rows is called twice in get_calibration: once for outcomes,
    # then once for the decision-title batched lookup.
    with patch("core.engine.api.foresight._pool.connection", return_value=_make_db_conn()):
        with patch("core.engine.api.foresight.parse_rows", side_effect=[outcome_rows, decision_rows]):
            async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
                resp = await ac.get("/foresight/product:test/calibration")
    assert resp.status_code == 200
    body = resp.json()
    assert len(body["outcomes"]) == 1
    o = body["outcomes"][0]
    assert o["archetype"] == "pm"
    assert o["calibration_score"] == 0.82
    assert o["predicted_deltas"] == {"capability:onboard": 0.3}
    # The headline regression: decision_title is threaded through.
    assert o["decision_title"] == "Adopt JWT for partner API auth"


@pytest.mark.asyncio
async def test_get_calibration_preserves_unscored_resolution_without_fabricating_zero():
    outcome_rows = [
        {
            "id": "prediction_outcome:unresolved",
            "prediction": "decision_prediction:p1",
            "decision": "decision:d1",
            "archetype": "pm",
            "discipline": "product",
            "contract_version": "ace.foresight.resolution/v1",
            "resolution_state": "unresolved",
            "score_eligible": False,
            "non_score_reason": "missing_observation",
            "calibration_score": None,
            "predicted_deltas": {"capability:onboard": 0.3},
            "actual_deltas": {},
            "closed_at": "2026-05-14T00:00:00Z",
        }
    ]
    decision_rows = [{"id": "decision:d1", "title": "Adopt JWT"}]

    with patch("core.engine.api.foresight._pool.connection", return_value=_make_db_conn()):
        with patch("core.engine.api.foresight.parse_rows", side_effect=[outcome_rows, decision_rows]):
            async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
                resp = await ac.get("/foresight/product:test/calibration")

    assert resp.status_code == 200
    outcome = resp.json()["outcomes"][0]
    assert outcome["calibration_score"] is None
    assert outcome["resolution_state"] == "unresolved"
    assert outcome["score_eligible"] is False
    assert outcome["non_score_reason"] == "missing_observation"


@pytest.mark.asyncio
async def test_get_calibration_filters_orphan_outcomes():
    """Outcomes whose decision no longer exists must not appear.

    Test cycles and manual cleanups leave orphan prediction_outcome rows;
    rendering them as context-free archetype+score cards is worse than
    omitting them. The filter is the user-facing fix.
    """
    outcome_rows = [
        {
            "id": "prediction_outcome:po_live",
            "decision": "decision:live",
            "archetype": "pm",
            "discipline": "product",
            "calibration_score": 0.82,
            "predicted_deltas": {},
            "actual_deltas": {},
            "closed_at": "2026-05-14T00:00:00Z",
        },
        {
            "id": "prediction_outcome:po_orphan",
            "decision": "decision:deleted",  # decision row no longer exists
            "archetype": "skeptic",
            "discipline": "security",
            "calibration_score": 0.5,
            "predicted_deltas": {},
            "actual_deltas": {},
            "closed_at": "2026-05-14T00:00:00Z",
        },
    ]
    # Only the live decision resolves to a title; the orphan's decision
    # is absent from the batched lookup result.
    decision_rows = [{"id": "decision:live", "title": "Adopt JWT for partner API auth"}]

    with patch("core.engine.api.foresight._pool.connection", return_value=_make_db_conn()):
        with patch("core.engine.api.foresight.parse_rows", side_effect=[outcome_rows, decision_rows]):
            async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
                resp = await ac.get("/foresight/product:test/calibration")
    assert resp.status_code == 200
    body = resp.json()
    assert len(body["outcomes"]) == 1
    assert body["outcomes"][0]["id"] == "prediction_outcome:po_live"
    # The orphan does NOT appear.
    assert all(o["id"] != "prediction_outcome:po_orphan" for o in body["outcomes"])
