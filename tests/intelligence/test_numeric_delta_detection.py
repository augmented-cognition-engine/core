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
    SignalRoutingError,
    SignalV1Alpha1,
    detect_live_numeric_shift,
    detect_numeric_shift,
    eligible_live_signal_routes,
    eligible_signal_routes,
    route_live_shift_as_signal,
    route_shift_as_signal,
)
from ace.intelligence.contracts.resources import LineageResourceKind
from ace.intelligence.detection import NumericDeltaDetectionError
from ace.intelligence.packs.activation import compile_overlay, prepare_activation_revision, prepare_domain_activation
from ace.intelligence.packs.compiler import compile_pack_document
from ace.intelligence.packs.runtime import (
    PreparedActivationBinding,
    PreparedActivationBindingError,
    bind_prepared_activation,
)

pytestmark = pytest.mark.unit

PRODUCT_ID = "product:numeric-delta"
AS_OF = datetime(2026, 2, 15, 12, 0, tzinfo=UTC)
DETECTOR_ID = "material_measure_change"


def _compiled_pack(
    *,
    pack_id: str = "generic_measurement",
    threshold: float = 5.0,
    direction: str = "any",
    signal_type: str = "measure_attention",
    context_attribute_ids: list[str] | None = None,
    unit_many: bool = False,
):
    ontology = {
        "contract": "ace.intelligence.ontology/v1alpha1",
        "module_id": "ontology",
        "entity_types": [
            {
                "entity_type_id": "subject",
                "attributes": [
                    {"attribute_id": "measure", "value_type": "number", "required": True},
                    {
                        "attribute_id": "unit",
                        "value_type": "string",
                        "required": True,
                        "many": unit_many,
                    },
                ],
            }
        ],
        "relation_types": [],
    }
    detection = {
        "contract": "ace.intelligence.detection/v1alpha1",
        "module_id": "detection",
        "numeric_delta_rules": [
            {
                "detector_id": DETECTOR_ID,
                "entity_type_id": "subject",
                "attribute_id": "measure",
                "baseline": "prior_snapshot",
                "context_attribute_ids": context_attribute_ids or [],
                "metric": "percent_change",
                "threshold": threshold,
                "direction": direction,
                "shift_type": "material_measure_change",
                "signal_type": signal_type,
            }
        ],
    }
    resources = {
        "modules/ontology.json": json.dumps(ontology, ensure_ascii=False, separators=(",", ":")).encode(),
        "modules/detection.json": json.dumps(detection, ensure_ascii=False, separators=(",", ":")).encode(),
    }
    manifest = {
        "contract": "ace.intelligence.domain-pack-manifest/v1alpha1",
        "metadata": {
            "pack_id": pack_id,
            "version": "0.1.0",
            "display_name": "Generic Measurement",
        },
        "resources": [
            {
                "resource_id": module_id,
                "path": path,
                "digest": f"sha256:{hashlib.sha256(payload).hexdigest()}",
            }
            for module_id, path, payload in (
                ("ontology", "modules/ontology.json", resources["modules/ontology.json"]),
                ("detection", "modules/detection.json", resources["modules/detection.json"]),
            )
        ],
        "modules": [
            {
                "module_id": "ontology",
                "contract": "ace.intelligence.ontology/v1alpha1",
                "resource_id": "ontology",
                "depends_on": [],
            },
            {
                "module_id": "detection",
                "contract": "ace.intelligence.detection/v1alpha1",
                "resource_id": "detection",
                "depends_on": ["ontology"],
            },
        ],
        "capability_requirements": [],
        "authority_requests": [],
        "overlay_slots": [],
    }
    return compile_pack_document(
        json.dumps(manifest, ensure_ascii=False, separators=(",", ":")).encode(),
        resources,
    )


def _binding(**pack_changes) -> PreparedActivationBinding:
    pack = _compiled_pack(**pack_changes)
    overlay = compile_overlay(
        pack,
        OrganizationOverlayV1(
            overlay_id="numeric_delta_test",
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
    value: int | float,
    *,
    as_of: datetime,
    unit: Any = "points",
    attributes_override: dict[str, Any] | None = None,
    projected_at: datetime | None = None,
    mode: IntelligenceResourceMode = IntelligenceResourceMode.PREPARED,
) -> EntitySnapshotV1Alpha1:
    return EntitySnapshotV1Alpha1(
        product_id=PRODUCT_ID,
        mode=mode,
        activation_revision=binding.reference,
        as_of=as_of,
        entity_ref="entity:watched-subject",
        entity_type_ref="subject",
        attributes=CanonicalJsonValueV1Alpha1(
            value_json=json.dumps(
                attributes_override if attributes_override is not None else {"measure": value, "unit": unit},
                separators=(",", ":"),
            )
        ),
        projected_at=projected_at or as_of,
        confidence=0.9,
    )


def _detect(
    binding: PreparedActivationBinding,
    baseline: EntitySnapshotV1Alpha1,
    current: EntitySnapshotV1Alpha1,
    *,
    detected_at: datetime = AS_OF,
):
    return detect_numeric_shift(
        binding=binding,
        detector_id=DETECTOR_ID,
        baseline=baseline,
        current=current,
        detected_at=detected_at,
    )


def test_material_delta_creates_shift_and_optional_signal() -> None:
    binding = _binding()
    baseline = _snapshot(binding, 1200.0, as_of=AS_OF - timedelta(days=31))
    current = _snapshot(binding, 1080.0, as_of=AS_OF)

    shift = _detect(binding, baseline, current)

    assert shift is not None
    assert shift.delta.parsed_value() == {
        "absolute_change": -120.0,
        "comparison_context": {},
        "detector_id": DETECTOR_ID,
        "direction": "decrease",
        "metric": "percent_change",
        "metric_value": -10.0,
        "threshold": 5.0,
    }
    assert {item.resource_kind for item in shift.lineage} == {LineageResourceKind.ENTITY_SNAPSHOT}

    signal = route_shift_as_signal(
        binding=binding,
        detector_id=DETECTOR_ID,
        shift=shift,
        detected_at=AS_OF,
    )
    assert signal.signal_type_ref == "measure_attention"
    assert signal.lineage[0].resource_kind is LineageResourceKind.SHIFT
    assert signal.lineage[0].resource_id == shift.resource_id


def test_nonmaterial_delta_does_not_require_a_shift_or_signal() -> None:
    binding = _binding()
    assert (
        _detect(
            binding,
            _snapshot(binding, 100.0, as_of=AS_OF - timedelta(days=1)),
            _snapshot(binding, 97.0, as_of=AS_OF),
        )
        is None
    )


@pytest.mark.parametrize(
    ("direction", "expected"),
    [("increase", False), ("decrease", True)],
)
def test_direction_policy_is_resolved_from_the_bound_pack(direction: str, expected: bool) -> None:
    binding = _binding(direction=direction)
    result = _detect(
        binding,
        _snapshot(binding, 100.0, as_of=AS_OF - timedelta(days=1)),
        _snapshot(binding, 90.0, as_of=AS_OF),
    )
    assert (result is not None) is expected


def test_invalid_snapshot_pairs_and_zero_baselines_fail_closed() -> None:
    binding = _binding()
    current = _snapshot(binding, 1.0, as_of=AS_OF)
    with pytest.raises(NumericDeltaDetectionError, match="baseline must precede"):
        _detect(binding, current, current)

    with pytest.raises(NumericDeltaDetectionError, match="zero baseline"):
        _detect(
            binding,
            _snapshot(binding, 0.0, as_of=AS_OF - timedelta(days=1)),
            current,
        )


def test_cross_pack_policy_cannot_relabel_or_route_a_shift() -> None:
    original = _binding(pack_id="original_policy")
    foreign = _binding(pack_id="foreign_policy", signal_type="relabelled_attention")
    shift = _detect(
        original,
        _snapshot(original, 100.0, as_of=AS_OF - timedelta(days=1)),
        _snapshot(original, 90.0, as_of=AS_OF),
    )
    assert shift is not None

    with pytest.raises(NumericDeltaDetectionError, match="exact bound activation"):
        route_shift_as_signal(
            binding=foreign,
            detector_id=DETECTOR_ID,
            shift=shift,
            detected_at=AS_OF,
        )


def test_copied_stale_resource_identity_is_revalidated() -> None:
    binding = _binding()
    baseline = _snapshot(binding, 100.0, as_of=AS_OF - timedelta(days=1))
    current = _snapshot(binding, 110.0, as_of=AS_OF)
    tampered = current.model_copy(
        update={"attributes": CanonicalJsonValueV1Alpha1(value_json='{"measure":200.0,"unit":"points"}')}
    )

    with pytest.raises(NumericDeltaDetectionError, match="revalidation"):
        _detect(binding, baseline, tampered)


def test_unsafe_huge_integer_fails_with_typed_detection_error() -> None:
    binding = _binding()
    with pytest.raises(NumericDeltaDetectionError, match="exact supported numeric range"):
        _detect(
            binding,
            _snapshot(binding, 1, as_of=AS_OF - timedelta(days=1)),
            _snapshot(binding, 10**400, as_of=AS_OF),
        )


def test_detection_and_signal_timestamps_follow_input_availability() -> None:
    binding = _binding()
    baseline = _snapshot(binding, 100.0, as_of=AS_OF - timedelta(days=1))
    current = _snapshot(
        binding,
        90.0,
        as_of=AS_OF,
        projected_at=AS_OF + timedelta(minutes=1),
    )
    with pytest.raises(NumericDeltaDetectionError, match="before both snapshots were projected"):
        _detect(binding, baseline, current, detected_at=AS_OF)

    available_shift = _detect(
        binding,
        baseline,
        current,
        detected_at=AS_OF + timedelta(minutes=1),
    )
    assert available_shift is not None
    with pytest.raises(NumericDeltaDetectionError, match="cannot predate"):
        route_shift_as_signal(
            binding=binding,
            detector_id=DETECTOR_ID,
            shift=available_shift,
            detected_at=AS_OF,
        )


def test_comparison_context_prevents_cross_unit_delta() -> None:
    binding = _binding(context_attribute_ids=["unit"])
    with pytest.raises(NumericDeltaDetectionError, match="context attribute unit changed"):
        _detect(
            binding,
            _snapshot(binding, 1200.0, unit="USD", as_of=AS_OF - timedelta(days=1)),
            _snapshot(binding, 1080.0, unit="EUR", as_of=AS_OF),
        )


def test_bound_ontology_types_required_fields_and_cardinality_are_enforced() -> None:
    binding = _binding(context_attribute_ids=["unit"])
    with pytest.raises(NumericDeltaDetectionError, match="ontology type string"):
        _detect(
            binding,
            _snapshot(binding, 100.0, unit=1, as_of=AS_OF - timedelta(days=1)),
            _snapshot(binding, 90.0, unit=True, as_of=AS_OF),
        )

    with pytest.raises(NumericDeltaDetectionError, match="missing required ontology"):
        _detect(
            binding,
            _snapshot(
                binding,
                100.0,
                as_of=AS_OF - timedelta(days=1),
                attributes_override={"measure": 100.0},
            ),
            _snapshot(binding, 90.0, as_of=AS_OF),
        )

    with pytest.raises(NumericDeltaDetectionError, match="attributes not declared"):
        _detect(
            binding,
            _snapshot(
                binding,
                100.0,
                as_of=AS_OF - timedelta(days=1),
                attributes_override={
                    "measure": 100.0,
                    "unit": "points",
                    "undeclared": "not in the bound ontology",
                },
            ),
            _snapshot(binding, 90.0, as_of=AS_OF),
        )

    many_binding = _binding(context_attribute_ids=["unit"], unit_many=True)
    assert (
        _detect(
            many_binding,
            _snapshot(
                many_binding,
                100.0,
                unit=["points"],
                as_of=AS_OF - timedelta(days=1),
            ),
            _snapshot(many_binding, 90.0, unit=["points"], as_of=AS_OF),
        )
        is not None
    )
    with pytest.raises(NumericDeltaDetectionError, match="must be an array"):
        _detect(
            many_binding,
            _snapshot(
                many_binding,
                100.0,
                unit="points",
                as_of=AS_OF - timedelta(days=1),
            ),
            _snapshot(many_binding, 90.0, unit=["points"], as_of=AS_OF),
        )


def test_integer_delta_rejects_an_inexact_result_even_when_inputs_are_exact() -> None:
    binding = _binding()
    with pytest.raises(NumericDeltaDetectionError, match="absolute change exceeds"):
        _detect(
            binding,
            _snapshot(binding, -(2**53 - 2), as_of=AS_OF - timedelta(days=1)),
            _snapshot(binding, 2**53 - 1, as_of=AS_OF),
        )


def test_retired_or_tampered_prepared_bindings_fail_closed() -> None:
    active = _binding()
    retired_revision = prepare_activation_revision(
        spec=active.revision.spec,
        state=ActivationState.RETIRED,
        actor_ref="principal:test-author",
        approval_receipt_ref="receipt:prepared-retirement",
        occurred_at=AS_OF + timedelta(days=1),
        prior_revision=active.revision,
    )
    with pytest.raises(PreparedActivationBindingError, match="active revision"):
        bind_prepared_activation(pack=active.pack, revision=retired_revision)

    tampered_pack = active.pack.model_copy(update={"compiled_pack_id": "pack_ir:" + "f" * 32})
    with pytest.raises(PreparedActivationBindingError, match="revalidation"):
        bind_prepared_activation(pack=tampered_pack, revision=active.revision)


def test_prepared_binding_rejects_a_foreign_pack_revision_pair() -> None:
    active = _binding(pack_id="binding_owner")
    foreign_pack = _compiled_pack(pack_id="foreign_pack")

    with pytest.raises(PreparedActivationBindingError, match="exact supplied compiled pack"):
        bind_prepared_activation(pack=foreign_pack, revision=active.revision)


def test_prepared_binding_reference_cannot_be_forged() -> None:
    active = _binding(pack_id="binding_reference_owner")
    foreign = _binding(pack_id="foreign_binding_reference")
    forged = PreparedActivationBinding(
        pack=active.pack,
        revision=active.revision,
        reference=foreign.reference,
    )

    with pytest.raises(NumericDeltaDetectionError, match="binding reference does not match"):
        _detect(
            forged,
            _snapshot(active, 100.0, as_of=AS_OF - timedelta(days=1)),
            _snapshot(active, 90.0, as_of=AS_OF),
        )


def test_prepared_binding_rejects_live_snapshot_shift_and_signal() -> None:
    binding = _binding()
    with pytest.raises(NumericDeltaDetectionError, match="only prepared snapshots"):
        _detect(
            binding,
            _snapshot(
                binding,
                100.0,
                as_of=AS_OF - timedelta(days=1),
                mode=IntelligenceResourceMode.LIVE,
            ),
            _snapshot(
                binding,
                90.0,
                as_of=AS_OF,
                mode=IntelligenceResourceMode.LIVE,
            ),
        )

    prepared_shift = _detect(
        binding,
        _snapshot(binding, 100.0, as_of=AS_OF - timedelta(days=1)),
        _snapshot(binding, 90.0, as_of=AS_OF),
    )
    assert prepared_shift is not None
    live_shift_payload = prepared_shift.model_dump(
        mode="python",
        exclude={"resource_id", "resource_digest"},
    )
    live_shift_payload["mode"] = IntelligenceResourceMode.LIVE
    live_shift = prepared_shift.__class__.model_validate(live_shift_payload)
    with pytest.raises(NumericDeltaDetectionError, match="only prepared Shifts"):
        route_shift_as_signal(
            binding=binding,
            detector_id=DETECTOR_ID,
            shift=live_shift,
            detected_at=AS_OF,
        )

    live_signal = SignalV1Alpha1(
        product_id=PRODUCT_ID,
        mode=IntelligenceResourceMode.LIVE,
        activation_revision=binding.reference,
        as_of=AS_OF,
        signal_type_ref="measure_attention",
        title="Live mode is not prepared authority",
        summary="A prepared binding must reject this otherwise valid Signal.",
        details=CanonicalJsonValueV1Alpha1(value_json="{}"),
        detected_at=AS_OF,
        confidence=0.9,
    )
    with pytest.raises(SignalRoutingError, match="only prepared Signals"):
        eligible_signal_routes(binding=binding, signal=live_signal)


def test_explicit_live_entry_points_accept_only_live_resources() -> None:
    binding = _binding()
    live_baseline = _snapshot(
        binding,
        100.0,
        as_of=AS_OF - timedelta(days=1),
        mode=IntelligenceResourceMode.LIVE,
    )
    live_current = _snapshot(
        binding,
        90.0,
        as_of=AS_OF,
        mode=IntelligenceResourceMode.LIVE,
    )
    shift = detect_live_numeric_shift(
        binding=binding,
        detector_id=DETECTOR_ID,
        baseline=live_baseline,
        current=live_current,
        detected_at=AS_OF,
    )
    assert shift is not None and shift.mode is IntelligenceResourceMode.LIVE
    signal = route_live_shift_as_signal(
        binding=binding,
        detector_id=DETECTOR_ID,
        shift=shift,
        detected_at=AS_OF,
    )
    assert signal.mode is IntelligenceResourceMode.LIVE
    assert eligible_live_signal_routes(binding=binding, signal=signal) == ()

    with pytest.raises(NumericDeltaDetectionError, match="only live snapshots"):
        detect_live_numeric_shift(
            binding=binding,
            detector_id=DETECTOR_ID,
            baseline=_snapshot(binding, 100.0, as_of=AS_OF - timedelta(days=1)),
            current=_snapshot(binding, 90.0, as_of=AS_OF),
            detected_at=AS_OF,
        )


def test_numeric_delta_threshold_rejects_unsafe_integer_range() -> None:
    from ace.intelligence.contracts.detection import NumericDeltaRuleV1

    with pytest.raises(ValidationError, match="exact IEEE-754 range"):
        NumericDeltaRuleV1(
            detector_id=DETECTOR_ID,
            entity_type_id="subject",
            attribute_id="measure",
            metric="percent_change",
            threshold=10**100,
            shift_type="material_measure_change",
            signal_type="measure_attention",
        )
