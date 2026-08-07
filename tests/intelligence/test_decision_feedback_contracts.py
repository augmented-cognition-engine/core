from __future__ import annotations

from copy import deepcopy
from datetime import UTC, datetime, timedelta

import pytest
from pydantic import ValidationError

from ace.core import (
    AuthenticatedRuntimeContextV1Alpha1,
    DecisionActionDisposition,
    DecisionDisposition,
    DecisionIntentV1Alpha1,
    ImmutableRecordReferenceV1,
    OutcomeIntentV1Alpha1,
    immutable_record_storage_id,
)
from ace.intelligence import ActivationState, DomainPackManifestV1, OrganizationOverlayV1
from ace.intelligence.packs.activation import compile_overlay, prepare_activation_revision, prepare_domain_activation
from ace.intelligence.packs.compiler import PackCompilationError, compile_pack
from ace.intelligence.packs.runtime import bind_prepared_activation, resolve_feedback_policy
from tests.intelligence.conftest import digest_bytes, encode_json

pytestmark = pytest.mark.unit


def _time(minutes: int) -> datetime:
    return datetime(2026, 8, 6, 15, minutes, tzinfo=UTC)


def _auth() -> AuthenticatedRuntimeContextV1Alpha1:
    return AuthenticatedRuntimeContextV1Alpha1(
        product_id="product:generic-intelligence",
        actor_ref="principal:analyst",
        authentication_receipt_ref="receipt:authentication",
        authentication_receipt_digest="sha256:" + "a" * 64,
        authenticated_at=_time(0),
        expires_at=_time(59),
    )


def _subject() -> ImmutableRecordReferenceV1:
    return ImmutableRecordReferenceV1(
        storage_id=immutable_record_storage_id(
            product_id="product:generic-intelligence",
            record_space="prepared",
            record_kind="opaque_orientation",
            record_key="orientation:one",
        ),
        product_id="product:generic-intelligence",
        record_space="prepared",
        record_kind="opaque_orientation",
        record_key="orientation:one",
        material_hash="sha256:" + "b" * 64,
        payload_contract="example.opaque-orientation/v1",
        as_of=_time(1),
        available_at=_time(2),
        processing_order=0,
    )


def _decision_intent(**updates) -> DecisionIntentV1Alpha1:
    payload = {
        "product_id": "product:generic-intelligence",
        "authenticated_context": _auth(),
        "subject": _subject(),
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


def _pack_payloads() -> dict[str, dict]:
    return {
        "ontology": {
            "contract": "ace.intelligence.ontology/v1alpha1",
            "module_id": "ontology",
            "entity_types": [
                {
                    "entity_type_id": "subject",
                    "attributes": [{"attribute_id": "measure", "value_type": "number"}],
                }
            ],
            "relation_types": [],
        },
        "detection": {
            "contract": "ace.intelligence.detection/v1alpha1",
            "module_id": "detection",
            "numeric_delta_rules": [
                {
                    "detector_id": "measure_change",
                    "entity_type_id": "subject",
                    "attribute_id": "measure",
                    "metric": "percent_change",
                    "threshold": 5.0,
                    "direction": "any",
                    "shift_type": "measure_change",
                    "signal_type": "measure_attention",
                }
            ],
        },
        "synthesis": {
            "contract": "ace.intelligence.synthesis/v1alpha2",
            "module_id": "synthesis",
            "brief_templates": [
                {
                    "template_id": "measure_brief",
                    "brief_type": "measurement_orientation",
                    "display_name": "Measurement Brief",
                    "objective": "Explain a bounded measurement change.",
                    "required_sections": [
                        "what_changed",
                        "recommendation",
                        "limitations",
                    ],
                    "recommendation_required": True,
                }
            ],
        },
        "personas": {
            "contract": "ace.intelligence.personas/v1alpha1",
            "module_id": "personas",
            "personas": [
                {
                    "persona_id": "domain_analyst",
                    "display_name": "Domain Analyst",
                    "description": "Reviews material changes.",
                }
            ],
            "signal_routing_rules": [
                {
                    "routing_rule_id": "route_measure_attention",
                    "signal_type": "measure_attention",
                    "persona_ids": ["domain_analyst"],
                    "minimum_confidence": 0.7,
                    "brief_template_id": "measure_brief",
                }
            ],
        },
        "decision_outcomes": {
            "contract": "ace.intelligence.decision-outcomes/v1alpha1",
            "module_id": "decision_outcomes",
            "feedback_policies": [
                {
                    "policy_id": "orientation_usefulness",
                    "persona_id": "domain_analyst",
                    "routing_rule_id": "route_measure_attention",
                    "decision_type": "orientation_review",
                    "eligible_decision_dispositions": ["accept"],
                    "eligible_action_dispositions": ["no_action"],
                    "outcome_type": "decision_usefulness",
                    "measure_id": "analyst_usefulness",
                    "initial_value": 0.5,
                    "minimum_value": 0.0,
                    "maximum_value": 1.0,
                    "adjustments": [
                        {"outcome_value_json": '"not_useful"', "delta": -0.1},
                        {"outcome_value_json": '"useful"', "delta": 0.05},
                    ],
                }
            ],
        },
    }


def _compile(payloads: dict[str, dict]):
    dependencies = {
        "ontology": [],
        "detection": ["ontology"],
        "synthesis": [],
        "personas": ["detection", "synthesis"],
        "decision_outcomes": ["personas"],
    }
    resources: dict[str, bytes] = {}
    manifest_resources = []
    modules = []
    for module_id, payload in payloads.items():
        path = f"modules/{module_id}.json"
        resource = encode_json(payload)
        resources[path] = resource
        manifest_resources.append(
            {
                "resource_id": f"{module_id}_resource",
                "path": path,
                "digest": digest_bytes(resource),
            }
        )
        modules.append(
            {
                "module_id": module_id,
                "contract": payload["contract"],
                "resource_id": f"{module_id}_resource",
                "depends_on": dependencies[module_id],
            }
        )
    manifest = DomainPackManifestV1(
        metadata={
            "pack_id": "generic_intelligence",
            "version": "0.1.0",
            "display_name": "Generic Intelligence",
        },
        resources=manifest_resources,
        modules=modules,
    )
    return compile_pack(manifest, resources)


def _binding(compiled):
    overlay = compile_overlay(
        compiled,
        OrganizationOverlayV1(
            overlay_id="generic_feedback",
            version="0.1.0",
            pack_id=compiled.metadata.pack_id,
            pack_version=compiled.metadata.version,
            pack_digest=compiled.pack_digest,
        ),
    )
    spec = prepare_domain_activation(
        product_id="product:generic-intelligence",
        activation_key="generic_intelligence",
        pack=compiled,
        overlay=overlay,
        compilation_receipt_ref="receipt:compilation",
        conformance_receipt_refs=("receipt:conformance",),
    )
    revision = prepare_activation_revision(
        spec=spec,
        state=ActivationState.ACTIVE,
        actor_ref="principal:pack-approver",
        approval_receipt_ref="receipt:pack-approval",
        occurred_at=_time(0),
    )
    return bind_prepared_activation(pack=compiled, revision=revision)


def test_decision_keeps_acceptance_separate_from_external_action() -> None:
    accepted_no_action = _decision_intent()
    assert accepted_no_action.disposition is DecisionDisposition.ACCEPT
    assert accepted_no_action.action_disposition is DecisionActionDisposition.NO_ACTION
    assert accepted_no_action.action_type is None

    with pytest.raises(ValidationError, match="explicit no-action"):
        _decision_intent(action_type="publish")
    with pytest.raises(ValidationError, match="requires an explicit action type"):
        _decision_intent(
            action_disposition=DecisionActionDisposition.AUTHORIZE_ACTION,
            action_type=None,
        )


def test_outcome_requires_canonical_json_and_later_decision_record() -> None:
    decision_reference = ImmutableRecordReferenceV1(
        storage_id=immutable_record_storage_id(
            product_id="product:generic-intelligence",
            record_space="prepared",
            record_kind="decision",
            record_key="decision:one",
        ),
        product_id="product:generic-intelligence",
        record_space="prepared",
        record_kind="decision",
        record_key="decision:one",
        material_hash="sha256:" + "c" * 64,
        payload_contract="ace.core.decision/v1alpha1",
        as_of=_time(3),
        available_at=_time(4),
        processing_order=0,
    )
    outcome = OutcomeIntentV1Alpha1(
        product_id="product:generic-intelligence",
        authenticated_context=_auth(),
        decision=decision_reference,
        outcome_type="decision_usefulness",
        measure_id="analyst_usefulness",
        value_json='"useful"',
        observed_at=_time(5),
        recorded_at=_time(6),
    )
    assert outcome.value_json == '"useful"'

    with pytest.raises(ValidationError, match="already use canonical JSON"):
        OutcomeIntentV1Alpha1(
            **outcome.model_dump(
                mode="python",
                exclude={"intent_id", "intent_digest", "value_json"},
            ),
            value_json='{"useful": true}',
        )
    with pytest.raises(ValidationError, match="cannot predate Decision"):
        OutcomeIntentV1Alpha1(
            **outcome.model_dump(
                mode="python",
                exclude={"intent_id", "intent_digest", "observed_at"},
            ),
            observed_at=_time(3),
        )


def test_feedback_pack_compiles_and_resolves_without_domain_nouns_in_kernel() -> None:
    compiled = _compile(_pack_payloads())
    resolved = resolve_feedback_policy(
        _binding(compiled),
        policy_id="orientation_usefulness",
    )

    assert resolved.policy.persona_id == "domain_analyst"
    assert resolved.policy.eligible_action_dispositions == (DecisionActionDisposition.NO_ACTION,)
    assert resolved.policy.adjustments[1].outcome_value_json == '"useful"'
    assert resolved.policy.adjustments[1].delta == 0.05
    assert all("execute" not in module.canonical_payload for module in compiled.modules)


def test_feedback_pack_rejects_unresolved_routing_and_imperative_fields() -> None:
    unresolved = _pack_payloads()
    unresolved["decision_outcomes"]["feedback_policies"][0]["routing_rule_id"] = "missing_route"
    with pytest.raises(PackCompilationError, match="outside its module dependencies"):
        _compile(unresolved)

    imperative = deepcopy(_pack_payloads())
    imperative["decision_outcomes"]["feedback_policies"][0]["execute"] = "python:feedback.apply"
    with pytest.raises(PackCompilationError) as exc_info:
        _compile(imperative)
    assert exc_info.value.report.diagnostics[0].code == "invalid_module"


def test_decision_identity_is_temporal_and_exact() -> None:
    first = _decision_intent()
    second = _decision_intent(decided_at=first.decided_at + timedelta(seconds=1))
    assert first.intent_id != second.intent_id
    assert first.intent_digest != second.intent_digest
