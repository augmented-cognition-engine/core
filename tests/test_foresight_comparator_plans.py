from __future__ import annotations

from core.engine.foresight.contracts import (
    COMPARATOR_PLAN_VERSION,
    build_comparator_plan,
    build_forecast_contract,
    normalize_comparator_plan,
)


def _consequences() -> list[dict]:
    return [
        {
            "local_id": "consequence:1",
            "target": {
                "entity_id": "checkout",
                "metric": "capability_quality",
                "unit": "score_delta",
            },
        }
    ]


def _raw_plan(**overrides) -> dict:
    plan = {
        "comparator_type": "phased_rollout",
        "assignment_design": "randomized",
        "comparator_label": "Teams scheduled for the later rollout phase",
        "feasibility": "feasible",
        "feasibility_reason": "Deployment already supports cohorts.",
        "required_conditions": ["Operators confirm delayed exposure is safe"],
        "assignment_unit": "team",
        "allocation": "Stagger eligible teams across two rollout windows",
        "eligibility_criteria": ["Team has not received the change"],
        "minimum_duration_days": 14,
        "guardrails": ["Stop if checkout failure rate rises"],
        "measurements": [
            {
                "capability_id": "checkout",
                "baseline_source": "Capability quality before assignment",
                "outcome_source": "Capability quality at the forecast horizon",
                "cadence": "daily",
            },
            {
                "capability_id": "not-in-forecast",
                "outcome_source": "Must be dropped",
            },
        ],
    }
    plan.update(overrides)
    return plan


def test_comparator_plan_is_advisory_bounded_and_target_grounded():
    plan = build_comparator_plan(
        _raw_plan(),
        consequences=_consequences(),
        horizon_days=10,
        decision_id="decision:d1",
        product_id="product:alpha",
    )

    assert plan["contract_version"] == COMPARATOR_PLAN_VERSION
    assert plan["status"] == "proposed"
    assert plan["feasibility"]["state"] == "conditional"
    assert plan["feasibility"]["operator_confirmation_required"] is True
    assert plan["timing"]["minimum_duration_days"] == 10
    assert [item["target"]["entity_id"] for item in plan["measurements"]] == ["checkout"]
    assert plan["sample_size"]["state"] == "not_estimated"
    assert plan["evidence_status"] == "plan_only_not_observed"
    assert plan["resolution_eligible"] is False
    assert plan["plan_id"].startswith("comparator_plan:")


def test_plan_identity_is_deterministic_and_product_isolated():
    first = build_comparator_plan(
        _raw_plan(),
        consequences=_consequences(),
        horizon_days=14,
        decision_id="decision:d1",
        product_id="product:alpha",
    )
    retry = build_comparator_plan(
        _raw_plan(),
        consequences=_consequences(),
        horizon_days=14,
        decision_id="decision:d1",
        product_id="product:alpha",
    )
    other_product = build_comparator_plan(
        _raw_plan(),
        consequences=_consequences(),
        horizon_days=14,
        decision_id="decision:d1",
        product_id="product:beta",
    )
    assert first["plan_id"] == retry["plan_id"]
    assert first["plan_id"] != other_product["plan_id"]


def test_missing_plan_is_explicit_and_does_not_invent_feasibility():
    plan = build_comparator_plan(None, consequences=_consequences(), horizon_days=14)

    assert plan["status"] == "not_proposed"
    assert plan["feasibility"]["state"] == "unknown"
    assert plan["measurements"] == []
    assert plan["resolution_eligible"] is False
    assert plan["fallback"]["method"] == "pre_post_observation"


def test_unknown_or_incomplete_plan_requires_operator_review():
    plan = build_comparator_plan(
        _raw_plan(assignment_design="unknown", required_conditions=[]),
        consequences=_consequences(),
        horizon_days=14,
    )

    assert plan["status"] == "needs_operator_review"
    assert plan["completeness"]["state"] == "partial"
    assert "comparator.assignment_design" in plan["completeness"]["missing_fields"]
    assert "feasibility.required_conditions" in plan["completeness"]["missing_fields"]


def test_optional_plan_does_not_make_cold_start_forecast_incomplete():
    contract = build_forecast_contract(
        {
            "horizon_days": 14,
            "applicability_conditions": ["Rollout reaches users"],
            "no_action_baseline": "Checkout quality remains stable.",
            "expected_changes": [
                {
                    "capability_id": "checkout",
                    "score_delta": 0.2,
                    "lower_bound": 0.0,
                    "upper_bound": 0.4,
                    "interval_coverage": 0.8,
                    "mechanism": "Retry changes reduce failures.",
                    "evidence_refs": ["decision:d1"],
                }
            ],
            "leading_indicators": ["Checkout reliability rises"],
            "falsification_condition": "Reliability does not rise.",
            "primary_risk": "Provider errors dominate.",
        },
        decision_id="decision:d1",
        product_id="product:alpha",
        archetype="skeptic",
        discipline="reliability",
        model="test-model",
        current_state_baseline={"checkout": {"overall": 0.5}},
        baseline_observed_at="2026-01-01T00:00:00Z",
        baseline_observation_refs=["capability_quality:q1"],
    )

    assert contract["completeness"]["state"] == "complete"
    assert contract["evaluation"]["comparator_plan"]["status"] == "not_proposed"


def test_normalization_never_promotes_plan_to_observed_evidence():
    plan = build_comparator_plan(_raw_plan(), consequences=_consequences(), horizon_days=14)
    normalized = normalize_comparator_plan(
        {
            "comparator_plan_version": COMPARATOR_PLAN_VERSION,
            "comparator_plan": {**plan, "resolution_eligible": True, "evidence_status": "observed"},
        }
    )

    assert normalized["resolution_eligible"] is False
    assert normalized["evidence_status"] == "plan_only_not_observed"


def test_v152_migration_is_additive_and_plan_only():
    from pathlib import Path

    migration = (Path(__file__).parents[1] / "core/schema/v152_comparator_planning_v1.surql").read_text(
        encoding="utf-8"
    )
    assert "comparator_plan" in migration
    assert "decision_prediction" in migration
    assert "ON TABLE observation" not in migration
    assert "ON TABLE prediction_outcome" not in migration
    assert "DELETE" not in migration
    assert "REMOVE" not in migration
    assert "value = '152'" in migration
