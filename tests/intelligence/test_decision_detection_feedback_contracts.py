from __future__ import annotations

from datetime import UTC, datetime

import pytest
from pydantic import ValidationError

from ace.core import (
    AuthenticatedRuntimeContextV1Alpha1,
    DecisionActionDisposition,
    DecisionDisposition,
    DecisionIntentV1Alpha1,
    ImmutableRecordReferenceV1,
    immutable_record_storage_id,
)
from ace.intelligence.contracts import (
    DecisionOutcomesModuleV1,
    DetectionModuleV1Alpha2,
    FeedbackPolicyV1,
)

pytestmark = pytest.mark.unit


def _time(minute: int) -> datetime:
    return datetime(2026, 8, 6, 15, minute, tzinfo=UTC)


def _decision(**updates) -> DecisionIntentV1Alpha1:
    product_id = "product:generic-intelligence"
    subject = ImmutableRecordReferenceV1(
        storage_id=immutable_record_storage_id(
            product_id=product_id,
            record_space="prepared",
            record_kind="opaque_orientation",
            record_key="orientation:one",
        ),
        product_id=product_id,
        record_space="prepared",
        record_kind="opaque_orientation",
        record_key="orientation:one",
        material_hash="sha256:" + "b" * 64,
        payload_contract="example.opaque-orientation/v1",
        as_of=_time(1),
        available_at=_time(2),
        processing_order=0,
    )
    payload = {
        "product_id": product_id,
        "authenticated_context": AuthenticatedRuntimeContextV1Alpha1(
            product_id=product_id,
            actor_ref="principal:analyst",
            authentication_receipt_ref="receipt:authentication",
            authentication_receipt_digest="sha256:" + "a" * 64,
            authenticated_at=_time(0),
            expires_at=_time(59),
        ),
        "subject": subject,
        "actor_role_ref": "domain_analyst",
        "decision_type": "orientation_review",
        "disposition": DecisionDisposition.ACCEPT,
        "action_disposition": DecisionActionDisposition.NO_ACTION,
        "action_type": None,
        "rationale": "Useful orientation; no external action is authorized.",
        "decided_at": _time(3),
    }
    payload.update(updates)
    return DecisionIntentV1Alpha1(**payload)


def _feedback_policy(**updates) -> FeedbackPolicyV1:
    payload = {
        "policy_id": "orientation_usefulness",
        "persona_id": "domain_analyst",
        "routing_rule_id": "route_attention",
        "decision_type": "orientation_review",
        "eligible_decision_dispositions": ("accept",),
        "eligible_action_dispositions": ("no_action",),
        "outcome_type": "decision_usefulness",
        "measure_id": "analyst_usefulness",
        "initial_value": 0.5,
        "minimum_value": 0.0,
        "maximum_value": 1.0,
        "adjustments": (
            {"outcome_value_json": '"not_useful"', "delta": -0.1},
            {"outcome_value_json": '"useful"', "delta": 0.05},
        ),
    }
    payload.update(updates)
    return FeedbackPolicyV1(**payload)


def test_decision_acceptance_never_implies_external_action() -> None:
    decision = _decision()
    assert decision.disposition is DecisionDisposition.ACCEPT
    assert decision.action_disposition is DecisionActionDisposition.NO_ACTION
    assert decision.action_type is None
    with pytest.raises(ValidationError, match="explicit no-action"):
        _decision(action_type="publish")
    with pytest.raises(ValidationError, match="requires an explicit action type"):
        _decision(
            action_disposition=DecisionActionDisposition.AUTHORIZE_ACTION,
            action_type=None,
        )


def test_feedback_policy_is_declarative_bounded_and_canonical() -> None:
    module = DecisionOutcomesModuleV1(
        module_id="decision_outcomes",
        feedback_policies=(_feedback_policy(),),
    )
    assert module.feedback_policies[0].adjustments[1].outcome_value_json == '"useful"'
    with pytest.raises(ValidationError, match="inside policy bounds"):
        _feedback_policy(initial_value=0.8, maximum_value=0.5)
    with pytest.raises(ValidationError, match="canonical JSON"):
        _feedback_policy(adjustments=({"outcome_value_json": '{"useful": true}', "delta": 0.1},))


def test_detection_rules_are_inert_canonical_configuration() -> None:
    module = DetectionModuleV1Alpha2(
        module_id="detection",
        numeric_delta_rules=(
            {
                "detector_id": "rule_b",
                "entity_type_id": "subject",
                "attribute_id": "measure",
                "metric": "absolute_change",
                "threshold": 5,
                "shift_type": "measure_change",
                "signal_type": "measure_attention",
            },
            {
                "detector_id": "rule_a",
                "entity_type_id": "subject",
                "attribute_id": "measure",
                "metric": "percent_change",
                "threshold": 0.1,
                "shift_type": "measure_change",
                "signal_type": "measure_attention",
            },
        ),
    )
    assert [item.detector_id for item in module.numeric_delta_rules] == ["rule_a", "rule_b"]
    assert "execute" not in module.model_dump_json()


@pytest.mark.parametrize("threshold", ["0.1", True, float("nan")])
def test_detection_thresholds_fail_closed(threshold) -> None:
    with pytest.raises(ValidationError):
        DetectionModuleV1Alpha2(
            module_id="detection",
            numeric_delta_rules=(
                {
                    "detector_id": "rule",
                    "entity_type_id": "subject",
                    "attribute_id": "measure",
                    "metric": "percent_change",
                    "threshold": threshold,
                    "shift_type": "measure_change",
                    "signal_type": "measure_attention",
                },
            ),
        )
