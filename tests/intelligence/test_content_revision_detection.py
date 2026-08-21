"""Content-revision detection: a document's watched text changed (PI13 WS5, packet §10).

The two shipped strategies cannot express this. ``numeric_delta`` needs a number
and a threshold; ``categorical_transition`` needs an enumerated ``from``/``to``
table and forbids identity. A read-only local corpus produces exactly one kind of
change -- a document's text is edited -- so Core needs a family whose whole
materiality test is "the exact value differs".
"""

from __future__ import annotations

import hashlib
import json
from datetime import UTC, datetime, timedelta
from typing import Any

import pytest
from pydantic import ValidationError

from ace.intelligence import (
    ActivationState,
    CanonicalJsonValueV1Alpha1,
    EntitySnapshotV1Alpha1,
    IntelligenceResourceMode,
    OrganizationOverlayV1,
)
from ace.intelligence.packs.activation import compile_overlay, prepare_activation_revision, prepare_domain_activation
from ace.intelligence.packs.compiler import compile_pack_document
from ace.intelligence.packs.runtime import PreparedActivationBinding, bind_prepared_activation

pytestmark = pytest.mark.unit

PRODUCT_ID = "product:content-revision"
AS_OF = datetime(2026, 8, 21, 12, 0, tzinfo=UTC)
DETECTOR_ID = "document_content_revised"
BASELINE_BODY = "The original note body, as first admitted."
CURRENT_BODY = "The note body after the owner edited it."


def _encoded(payload: dict) -> bytes:
    return json.dumps(payload, ensure_ascii=False, separators=(",", ":")).encode()


def _content_rule(**overrides: Any) -> dict:
    rule = {
        "detector_id": DETECTOR_ID,
        "entity_type_id": "document",
        "attribute_id": "body",
        "baseline": "prior_snapshot",
        "context_attribute_ids": ["document_ref"],
        "shift_type": "document_revised",
        "signal_type": "document_attention",
    }
    rule.update(overrides)
    return rule


def _compiled_pack(*, content_rules: list[dict] | None = None):
    ontology = {
        "contract": "ace.intelligence.ontology/v1alpha1",
        "module_id": "ontology",
        "entity_types": [
            {
                "entity_type_id": "document",
                "attributes": [
                    {"attribute_id": "document_ref", "value_type": "string", "required": True},
                    {"attribute_id": "body", "value_type": "string", "required": True},
                ],
            }
        ],
        "relation_types": [],
    }
    detection = {
        "contract": "ace.intelligence.detection/v1alpha3",
        "module_id": "detection",
        "content_revision_rules": [_content_rule()] if content_rules is None else content_rules,
    }
    modules = {"ontology": ontology, "detection": detection}
    resources = {f"modules/{module_id}.json": _encoded(payload) for module_id, payload in modules.items()}
    manifest = {
        "contract": "ace.intelligence.domain-pack-manifest/v1alpha1",
        "metadata": {"pack_id": "content_revision_pack", "version": "0.1.0", "display_name": "Content Revision"},
        "resources": [
            {
                "resource_id": module_id,
                "path": f"modules/{module_id}.json",
                "digest": f"sha256:{hashlib.sha256(resources[f'modules/{module_id}.json']).hexdigest()}",
            }
            for module_id in modules
        ],
        "modules": [
            {
                "module_id": module_id,
                "contract": payload["contract"],
                "resource_id": module_id,
                "depends_on": [] if module_id == "ontology" else ["ontology"],
            }
            for module_id, payload in modules.items()
        ],
        "capability_requirements": [],
        "authority_requests": [],
        "overlay_slots": [],
    }
    return compile_pack_document(_encoded(manifest), resources)


def _binding(**pack_changes: Any) -> PreparedActivationBinding:
    pack = _compiled_pack(**pack_changes)
    overlay = compile_overlay(
        pack,
        OrganizationOverlayV1(
            overlay_id="content_revision_test",
            version="0.1.0",
            pack_id=pack.metadata.pack_id,
            pack_version=pack.metadata.version,
            pack_digest=pack.pack_digest,
        ),
    )
    spec = prepare_domain_activation(
        product_id=PRODUCT_ID,
        activation_key=pack.metadata.pack_id,
        pack=pack,
        overlay=overlay,
        compilation_receipt_ref="receipt:prepared-compilation",
        conformance_receipt_refs=("receipt:prepared-conformance",),
    )
    revision = prepare_activation_revision(
        spec=spec,
        state=ActivationState.ACTIVE,
        actor_ref="principal:test-author",
        approval_receipt_ref="receipt:prepared-approval",
        occurred_at=AS_OF - timedelta(days=100),
    )
    return bind_prepared_activation(pack=pack, revision=revision)


def _snapshot(
    binding: PreparedActivationBinding,
    body: Any,
    *,
    as_of: datetime,
    document_ref: Any = "notes/vault.md",
    mode: IntelligenceResourceMode = IntelligenceResourceMode.PREPARED,
) -> EntitySnapshotV1Alpha1:
    return EntitySnapshotV1Alpha1(
        product_id=PRODUCT_ID,
        mode=mode,
        activation_revision=binding.reference,
        as_of=as_of,
        entity_ref="entity:watched-document",
        entity_type_ref="document",
        attributes=CanonicalJsonValueV1Alpha1(
            value_json=json.dumps({"document_ref": document_ref, "body": body}, separators=(",", ":"))
        ),
        projected_at=as_of,
        confidence=0.9,
    )


def _detect(binding, baseline, current, *, detected_at: datetime = AS_OF):
    from ace.intelligence import detect_content_revision_shift

    return detect_content_revision_shift(
        binding=binding,
        detector_id=DETECTOR_ID,
        baseline=baseline,
        current=current,
        detected_at=detected_at,
    )


def _digest(value: str) -> str:
    return "sha256:" + hashlib.sha256(value.encode()).hexdigest()


# --- declarative contract ---------------------------------------------------


def test_rule_carries_no_threshold_or_transition_table() -> None:
    from ace.intelligence.contracts.detection import ContentRevisionRuleV1

    rule = ContentRevisionRuleV1.model_validate(_content_rule())
    assert rule.detector_id == DETECTOR_ID
    assert rule.baseline == "prior_snapshot"
    assert not hasattr(rule, "threshold")
    assert not hasattr(rule, "transitions")

    with pytest.raises(ValidationError):
        ContentRevisionRuleV1.model_validate({**_content_rule(), "threshold": 1})
    with pytest.raises(ValidationError):
        ContentRevisionRuleV1.model_validate({**_content_rule(), "context_attribute_ids": ["body"]})


# --- detection --------------------------------------------------------------


def test_an_edited_document_body_produces_a_shift_bound_to_digests_not_text() -> None:
    binding = _binding()
    shift = _detect(
        binding,
        _snapshot(binding, BASELINE_BODY, as_of=AS_OF - timedelta(days=1)),
        _snapshot(binding, CURRENT_BODY, as_of=AS_OF),
    )

    assert shift is not None
    assert shift.shift_type_ref == "document_revised"
    assert shift.subject_refs == ("entity:watched-document",)
    baseline_payload = shift.baseline.parsed_value()
    current_payload = shift.current.parsed_value()
    assert baseline_payload["value_digest"] == _digest(BASELINE_BODY)
    assert current_payload["value_digest"] == _digest(CURRENT_BODY)
    assert current_payload["characters"] == len(CURRENT_BODY)
    # The document text is citable through its Observation; a bounded Shift
    # payload must not copy it.
    for payload in (baseline_payload, current_payload, shift.delta.parsed_value()):
        assert BASELINE_BODY not in json.dumps(payload)
        assert CURRENT_BODY not in json.dumps(payload)
    delta = shift.delta.parsed_value()
    assert delta["detector_id"] == DETECTOR_ID
    assert delta["comparison_context"] == {"document_ref": "notes/vault.md"}


def test_an_unchanged_body_is_not_a_revision() -> None:
    binding = _binding()
    assert (
        _detect(
            binding,
            _snapshot(binding, BASELINE_BODY, as_of=AS_OF - timedelta(days=1)),
            _snapshot(binding, BASELINE_BODY, as_of=AS_OF),
        )
        is None
    )


def test_whitespace_only_and_case_changes_are_real_revisions() -> None:
    """Equality is the whole test: the strategy never guesses that an edit is
    cosmetic on the author's behalf."""

    binding = _binding()
    for edited in (BASELINE_BODY + " ", BASELINE_BODY.upper()):
        shift = _detect(
            binding,
            _snapshot(binding, BASELINE_BODY, as_of=AS_OF - timedelta(days=1)),
            _snapshot(binding, edited, as_of=AS_OF),
        )
        assert shift is not None


def test_non_string_body_and_changed_context_fail_closed() -> None:
    from ace.intelligence.detection import ContentRevisionDetectionError

    binding = _binding()
    with pytest.raises(ContentRevisionDetectionError):
        _detect(
            binding,
            _snapshot(binding, 12, as_of=AS_OF - timedelta(days=1)),
            _snapshot(binding, CURRENT_BODY, as_of=AS_OF),
        )
    with pytest.raises(ContentRevisionDetectionError):
        _detect(
            binding,
            _snapshot(binding, BASELINE_BODY, as_of=AS_OF - timedelta(days=1), document_ref="notes/a.md"),
            _snapshot(binding, CURRENT_BODY, as_of=AS_OF, document_ref="notes/b.md"),
        )


def test_routing_produces_a_signal_for_a_real_revision() -> None:
    from ace.intelligence import route_content_revision_shift_as_signal

    binding = _binding()
    shift = _detect(
        binding,
        _snapshot(binding, BASELINE_BODY, as_of=AS_OF - timedelta(days=1)),
        _snapshot(binding, CURRENT_BODY, as_of=AS_OF),
    )
    signal = route_content_revision_shift_as_signal(
        binding=binding,
        detector_id=DETECTOR_ID,
        shift=shift,
        detected_at=AS_OF,
    )
    assert signal is not None
    assert signal.signal_type_ref == "document_attention"
    assert signal.subject_refs == shift.subject_refs


def test_the_detector_resolves_through_the_generic_bound_pack_lookup() -> None:
    from ace.intelligence.packs.runtime import resolve_detector_rule

    rule = resolve_detector_rule(_binding(), detector_id=DETECTOR_ID)
    assert rule.detector_id == DETECTOR_ID
    assert rule.attribute_id == "body"
