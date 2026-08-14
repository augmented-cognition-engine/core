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
from ace.intelligence.contracts.resources import LineageResourceKind
from ace.intelligence.packs.activation import compile_overlay, prepare_activation_revision, prepare_domain_activation
from ace.intelligence.packs.compiler import PackCompilationError, compile_pack_document
from ace.intelligence.packs.runtime import PreparedActivationBinding, bind_prepared_activation

pytestmark = pytest.mark.unit

PRODUCT_ID = "product:categorical-transition"
AS_OF = datetime(2026, 8, 6, 12, 0, tzinfo=UTC)
DETECTOR_ID = "material_stage_transition"

# Exact identities produced by the unchanged v1alpha1 toolchain before the
# v1alpha2 detection contract existed.  These pins are the Market-compatibility
# regression: adding categorical detection must not move any v1alpha1 identity.
V1ALPHA1_PACK_ID = "pack_ir:3282854421ceb6015e60fb2bf1b160c4"
V1ALPHA1_PACK_DIGEST = "sha256:3282854421ceb6015e60fb2bf1b160c4a3485503dbac7123382677d49f6221db"
V1ALPHA1_DETECTION_MODULE_DIGEST = "sha256:9997b41d954489f057263b38da742b731c7ede09029c08fafd19d17fe09ac1c7"


def _encoded(payload: dict) -> bytes:
    return json.dumps(payload, ensure_ascii=False, separators=(",", ":")).encode()


def _categorical_rule(**overrides: Any) -> dict:
    rule = {
        "detector_id": DETECTOR_ID,
        "entity_type_id": "subject",
        "attribute_id": "stage",
        "baseline": "prior_snapshot",
        "context_attribute_ids": ["cohort"],
        "transitions": [
            {"from_value": "draft", "to_value": "active"},
            {"from_value": "active", "to_value": "retired"},
        ],
        "shift_type": "material_stage_transition",
        "signal_type": "stage_attention",
    }
    rule.update(overrides)
    return rule


def _compiled_pack(
    *,
    pack_id: str = "generic_lifecycle",
    categorical_rules: list[dict] | None = None,
    numeric_rules: list[dict] | None = None,
    stage_many: bool = False,
    extra_modules: dict[str, dict] | None = None,
    extra_dependencies: dict[str, list[str]] | None = None,
):
    ontology = {
        "contract": "ace.intelligence.ontology/v1alpha1",
        "module_id": "ontology",
        "entity_types": [
            {
                "entity_type_id": "subject",
                "attributes": [
                    {
                        "attribute_id": "stage",
                        "value_type": "string",
                        "required": True,
                        "many": stage_many,
                    },
                    {"attribute_id": "cohort", "value_type": "string", "required": True},
                    {"attribute_id": "measure", "value_type": "number"},
                ],
            }
        ],
        "relation_types": [],
    }
    detection = {
        "contract": "ace.intelligence.detection/v1alpha2",
        "module_id": "detection",
    }
    if categorical_rules is None and numeric_rules is None:
        categorical_rules = [_categorical_rule()]
    if categorical_rules is not None:
        detection["categorical_transition_rules"] = categorical_rules
    if numeric_rules is not None:
        detection["numeric_delta_rules"] = numeric_rules
    modules = {"ontology": ontology, "detection": detection}
    if extra_modules:
        modules.update(extra_modules)
    dependencies = {"ontology": [], "detection": ["ontology"]}
    if extra_dependencies:
        dependencies.update(extra_dependencies)
    resources = {f"modules/{module_id}.json": _encoded(payload) for module_id, payload in modules.items()}
    manifest = {
        "contract": "ace.intelligence.domain-pack-manifest/v1alpha1",
        "metadata": {
            "pack_id": pack_id,
            "version": "0.1.0",
            "display_name": "Generic Lifecycle",
        },
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
                "depends_on": dependencies.get(module_id, []),
            }
            for module_id, payload in modules.items()
        ],
        "capability_requirements": [],
        "authority_requests": [],
        "overlay_slots": [],
    }
    return compile_pack_document(_encoded(manifest), resources)


def _binding(*, activated_at: datetime | None = None, **pack_changes: Any) -> PreparedActivationBinding:
    pack = _compiled_pack(**pack_changes)
    overlay = compile_overlay(
        pack,
        OrganizationOverlayV1(
            overlay_id="categorical_transition_test",
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
        occurred_at=activated_at or AS_OF - timedelta(days=100),
    )
    return bind_prepared_activation(pack=pack, revision=revision)


def _snapshot(
    binding: PreparedActivationBinding,
    stage: Any,
    *,
    as_of: datetime,
    cohort: Any = "primary",
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
                attributes_override if attributes_override is not None else {"stage": stage, "cohort": cohort},
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
    from ace.intelligence import detect_categorical_shift

    return detect_categorical_shift(
        binding=binding,
        detector_id=DETECTOR_ID,
        baseline=baseline,
        current=current,
        detected_at=detected_at,
    )


# --- declarative contract ---------------------------------------------------


def test_categorical_rule_rejects_identity_and_duplicate_transitions() -> None:
    from ace.intelligence.contracts.detection import CategoricalTransitionRuleV1

    with pytest.raises(ValidationError, match="cannot map a value onto itself"):
        CategoricalTransitionRuleV1.model_validate(
            _categorical_rule(transitions=[{"from_value": "draft", "to_value": "draft"}])
        )
    with pytest.raises(ValidationError, match="must use unique"):
        CategoricalTransitionRuleV1.model_validate(
            _categorical_rule(
                transitions=[
                    {"from_value": "draft", "to_value": "active"},
                    {"from_value": "draft", "to_value": "active"},
                ]
            )
        )
    with pytest.raises(ValidationError):
        CategoricalTransitionRuleV1.model_validate(_categorical_rule(transitions=[]))


def test_categorical_rule_orders_transitions_canonically() -> None:
    from ace.intelligence.contracts.detection import CategoricalTransitionRuleV1

    first = CategoricalTransitionRuleV1.model_validate(_categorical_rule())
    second = CategoricalTransitionRuleV1.model_validate(
        _categorical_rule(
            transitions=[
                {"from_value": "active", "to_value": "retired"},
                {"from_value": "draft", "to_value": "active"},
            ]
        )
    )
    assert first == second


def test_detection_module_v1alpha2_requires_at_least_one_rule() -> None:
    from ace.intelligence.contracts.detection import DetectionModuleV1Alpha2

    with pytest.raises(ValidationError, match="at least one detector rule"):
        DetectionModuleV1Alpha2.model_validate(
            {
                "contract": "ace.intelligence.detection/v1alpha2",
                "module_id": "detection",
                "numeric_delta_rules": [],
                "categorical_transition_rules": [],
            }
        )


def test_detection_module_v1alpha2_rejects_detector_reuse_across_families() -> None:
    from ace.intelligence.contracts.detection import DetectionModuleV1Alpha2

    with pytest.raises(ValidationError, match="detector IDs must be unique"):
        DetectionModuleV1Alpha2.model_validate(
            {
                "contract": "ace.intelligence.detection/v1alpha2",
                "module_id": "detection",
                "numeric_delta_rules": [
                    {
                        "detector_id": DETECTOR_ID,
                        "entity_type_id": "subject",
                        "attribute_id": "measure",
                        "metric": "percent_change",
                        "threshold": 5.0,
                        "shift_type": "material_measure_change",
                        "signal_type": "measure_attention",
                    }
                ],
                "categorical_transition_rules": [_categorical_rule()],
            }
        )


# --- compiler ---------------------------------------------------------------


def test_v1alpha2_module_compiles_and_preserves_v1alpha1_identities() -> None:
    pack = _compiled_pack()
    module = next(item for item in pack.modules if item.module_id == "detection")
    assert module.contract == "ace.intelligence.detection/v1alpha2"

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
                        "many": False,
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
                "detector_id": "material_measure_change",
                "entity_type_id": "subject",
                "attribute_id": "measure",
                "baseline": "prior_snapshot",
                "context_attribute_ids": [],
                "metric": "percent_change",
                "threshold": 5.0,
                "direction": "any",
                "shift_type": "material_measure_change",
                "signal_type": "measure_attention",
            }
        ],
    }
    resources = {
        "modules/ontology.json": _encoded(ontology),
        "modules/detection.json": _encoded(detection),
    }
    manifest = {
        "contract": "ace.intelligence.domain-pack-manifest/v1alpha1",
        "metadata": {
            "pack_id": "generic_measurement",
            "version": "0.1.0",
            "display_name": "Generic Measurement",
        },
        "resources": [
            {
                "resource_id": module_id,
                "path": path,
                "digest": f"sha256:{hashlib.sha256(resources[path]).hexdigest()}",
            }
            for module_id, path in (
                ("ontology", "modules/ontology.json"),
                ("detection", "modules/detection.json"),
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
    historical = compile_pack_document(_encoded(manifest), resources)
    assert historical.compiled_pack_id == V1ALPHA1_PACK_ID
    assert historical.pack_digest == V1ALPHA1_PACK_DIGEST
    historical_module = next(item for item in historical.modules if item.module_id == "detection")
    assert historical_module.module_digest == V1ALPHA1_DETECTION_MODULE_DIGEST


def test_categorical_rule_declaration_order_is_not_identity_bearing() -> None:
    reordered = _categorical_rule(
        transitions=[
            {"from_value": "active", "to_value": "retired"},
            {"from_value": "draft", "to_value": "active"},
        ]
    )
    first = _compiled_pack()
    second = _compiled_pack(categorical_rules=[reordered])
    assert first.pack_digest == second.pack_digest


def test_categorical_detector_must_watch_a_single_valued_string_attribute() -> None:
    with pytest.raises(PackCompilationError, match="requires a string attribute"):
        _compiled_pack(categorical_rules=[_categorical_rule(attribute_id="measure")])
    with pytest.raises(PackCompilationError, match="references unknown attribute"):
        _compiled_pack(categorical_rules=[_categorical_rule(attribute_id="missing")])
    with pytest.raises(PackCompilationError, match="single-valued"):
        _compiled_pack(stage_many=True)
    with pytest.raises(PackCompilationError, match="unknown comparison context"):
        _compiled_pack(categorical_rules=[_categorical_rule(context_attribute_ids=["missing"])])
    with pytest.raises(PackCompilationError, match="watched attribute"):
        _compiled_pack(categorical_rules=[_categorical_rule(context_attribute_ids=["stage"])])


def test_detector_ids_are_unique_across_contract_versions_and_families() -> None:
    legacy_detection = {
        "contract": "ace.intelligence.detection/v1alpha1",
        "module_id": "legacy_detection",
        "numeric_delta_rules": [
            {
                "detector_id": DETECTOR_ID,
                "entity_type_id": "subject",
                "attribute_id": "measure",
                "metric": "percent_change",
                "threshold": 5.0,
                "shift_type": "material_measure_change",
                "signal_type": "measure_attention",
            }
        ],
    }
    with pytest.raises(PackCompilationError, match="declared by multiple modules"):
        _compiled_pack(
            extra_modules={"legacy_detection": legacy_detection},
            extra_dependencies={"legacy_detection": ["ontology"]},
        )


def test_persona_routing_sees_categorical_signal_types() -> None:
    personas = {
        "contract": "ace.intelligence.personas/v1alpha1",
        "module_id": "personas",
        "personas": [
            {
                "persona_id": "reviewer",
                "display_name": "Reviewer",
                "description": "Reviews material generic transitions.",
            }
        ],
        "signal_routing_rules": [
            {
                "routing_rule_id": "review_material_transition",
                "signal_type": "stage_attention",
                "persona_ids": ["reviewer"],
                "minimum_confidence": 0.5,
            }
        ],
    }
    pack = _compiled_pack(
        extra_modules={"personas": personas},
        extra_dependencies={"personas": ["detection"]},
    )
    assert any(item.module_id == "personas" for item in pack.modules)


# --- runtime resolution -----------------------------------------------------


def test_detector_rules_resolve_exactly_once_by_family() -> None:
    from ace.intelligence.contracts.detection import (
        CategoricalTransitionRuleV1,
        NumericDeltaRuleV1,
    )
    from ace.intelligence.packs.runtime import (
        PreparedActivationBindingError,
        resolve_categorical_transition_rule,
        resolve_detector_rule,
        resolve_numeric_delta_rule,
    )

    numeric_rule = {
        "detector_id": "material_measure_change",
        "entity_type_id": "subject",
        "attribute_id": "measure",
        "metric": "percent_change",
        "threshold": 5.0,
        "shift_type": "material_measure_change",
        "signal_type": "measure_attention",
    }
    binding = _binding(
        categorical_rules=[_categorical_rule()],
        numeric_rules=[numeric_rule],
    )

    categorical = resolve_categorical_transition_rule(binding, detector_id=DETECTOR_ID)
    assert isinstance(categorical, CategoricalTransitionRuleV1)
    numeric = resolve_numeric_delta_rule(binding, detector_id="material_measure_change")
    assert isinstance(numeric, NumericDeltaRuleV1)

    assert isinstance(
        resolve_detector_rule(binding, detector_id=DETECTOR_ID),
        CategoricalTransitionRuleV1,
    )
    assert isinstance(
        resolve_detector_rule(binding, detector_id="material_measure_change"),
        NumericDeltaRuleV1,
    )
    with pytest.raises(PreparedActivationBindingError, match="exactly once"):
        resolve_detector_rule(binding, detector_id="missing_detector")
    with pytest.raises(PreparedActivationBindingError, match="exactly once"):
        resolve_categorical_transition_rule(binding, detector_id="material_measure_change")


# --- prepared detection behavior --------------------------------------------


def test_configured_transition_creates_shift_and_routes_signal() -> None:
    from ace.intelligence import route_categorical_shift_as_signal

    binding = _binding()
    baseline = _snapshot(binding, "draft", as_of=AS_OF - timedelta(days=1))
    current = _snapshot(binding, "active", as_of=AS_OF)

    shift = _detect(binding, baseline, current)

    assert shift is not None
    assert shift.baseline.parsed_value() == {"attribute_id": "stage", "value": "draft"}
    assert shift.current.parsed_value() == {"attribute_id": "stage", "value": "active"}
    assert shift.delta.parsed_value() == {
        "comparison_context": {"cohort": "primary"},
        "detector_id": DETECTOR_ID,
        "from_value": "draft",
        "to_value": "active",
    }
    assert shift.shift_type_ref == "material_stage_transition"
    assert {item.resource_kind for item in shift.lineage} == {LineageResourceKind.ENTITY_SNAPSHOT}

    signal = route_categorical_shift_as_signal(
        binding=binding,
        detector_id=DETECTOR_ID,
        shift=shift,
        detected_at=AS_OF,
    )
    assert signal.signal_type_ref == "stage_attention"
    assert signal.lineage[0].resource_kind is LineageResourceKind.SHIFT
    assert signal.lineage[0].resource_id == shift.resource_id


def test_unconfigured_or_unchanged_transitions_are_not_material() -> None:
    binding = _binding()
    assert (
        _detect(
            binding,
            _snapshot(binding, "active", as_of=AS_OF - timedelta(days=1)),
            _snapshot(binding, "draft", as_of=AS_OF),
        )
        is None
    )
    assert (
        _detect(
            binding,
            _snapshot(binding, "draft", as_of=AS_OF - timedelta(days=1)),
            _snapshot(binding, "draft", as_of=AS_OF),
        )
        is None
    )
    assert (
        _detect(
            binding,
            _snapshot(binding, "draft", as_of=AS_OF - timedelta(days=1)),
            _snapshot(binding, "archived_elsewhere", as_of=AS_OF),
        )
        is None
    )


def test_non_string_values_fail_closed_without_coercion() -> None:
    from ace.intelligence.detection import CategoricalTransitionDetectionError

    binding = _binding()
    with pytest.raises(CategoricalTransitionDetectionError, match="ontology type string"):
        _detect(
            binding,
            _snapshot(binding, True, as_of=AS_OF - timedelta(days=1)),
            _snapshot(binding, "active", as_of=AS_OF),
        )
    with pytest.raises(CategoricalTransitionDetectionError, match="missing required ontology"):
        _detect(
            binding,
            _snapshot(
                binding,
                "draft",
                as_of=AS_OF - timedelta(days=1),
                attributes_override={"cohort": "primary"},
            ),
            _snapshot(binding, "active", as_of=AS_OF),
        )


def test_comparison_context_prevents_cross_cohort_transitions() -> None:
    from ace.intelligence.detection import CategoricalTransitionDetectionError

    binding = _binding()
    with pytest.raises(CategoricalTransitionDetectionError, match="context attribute cohort changed"):
        _detect(
            binding,
            _snapshot(binding, "draft", cohort="alpha", as_of=AS_OF - timedelta(days=1)),
            _snapshot(binding, "active", cohort="beta", as_of=AS_OF),
        )


def test_snapshot_pair_time_and_scope_discipline_is_enforced() -> None:
    from ace.intelligence.detection import CategoricalTransitionDetectionError

    binding = _binding()
    current = _snapshot(binding, "active", as_of=AS_OF)
    with pytest.raises(CategoricalTransitionDetectionError, match="baseline must precede"):
        _detect(binding, current, current)

    late_projection = _snapshot(
        binding,
        "active",
        as_of=AS_OF,
        projected_at=AS_OF + timedelta(minutes=1),
    )
    with pytest.raises(CategoricalTransitionDetectionError, match="before both snapshots were projected"):
        _detect(
            binding,
            _snapshot(binding, "draft", as_of=AS_OF - timedelta(days=1)),
            late_projection,
            detected_at=AS_OF,
        )


def test_historical_categorical_state_requires_post_activation_processing() -> None:
    from ace.intelligence import route_categorical_shift_as_signal
    from ace.intelligence.detection import CategoricalTransitionDetectionError

    activated_at = AS_OF - timedelta(hours=1)
    binding = _binding(activated_at=activated_at)
    baseline = _snapshot(
        binding,
        "draft",
        as_of=AS_OF - timedelta(days=10),
        projected_at=AS_OF,
    )
    current = _snapshot(
        binding,
        "active",
        as_of=AS_OF - timedelta(days=5),
        projected_at=AS_OF,
    )

    shift = _detect(binding, baseline, current, detected_at=AS_OF)
    assert shift is not None
    assert shift.as_of < activated_at < shift.detected_at
    signal = route_categorical_shift_as_signal(
        binding=binding,
        detector_id=DETECTOR_ID,
        shift=shift,
        detected_at=AS_OF,
    )
    assert signal.as_of < activated_at <= signal.detected_at

    preactivation_current = _snapshot(
        binding,
        "active",
        as_of=AS_OF - timedelta(days=5),
        projected_at=activated_at - timedelta(seconds=1),
    )
    with pytest.raises(CategoricalTransitionDetectionError, match="projection predates"):
        _detect(binding, baseline, preactivation_current, detected_at=AS_OF)

    shift_material = shift.model_dump(mode="python", exclude={"resource_id", "resource_digest"})
    shift_material["detected_at"] = activated_at - timedelta(seconds=1)
    shift_material["lineage"] = ()
    preactivation_shift = shift.__class__.model_validate(shift_material)
    with pytest.raises(CategoricalTransitionDetectionError, match="detection predates"):
        route_categorical_shift_as_signal(
            binding=binding,
            detector_id=DETECTOR_ID,
            shift=preactivation_shift,
            detected_at=activated_at,
        )


def test_cross_pack_policy_cannot_relabel_or_route_a_shift() -> None:
    from ace.intelligence import route_categorical_shift_as_signal
    from ace.intelligence.detection import CategoricalTransitionDetectionError

    original = _binding(pack_id="original_policy")
    foreign = _binding(
        pack_id="foreign_policy",
        categorical_rules=[_categorical_rule(signal_type="relabelled_attention")],
    )
    shift = _detect(
        original,
        _snapshot(original, "draft", as_of=AS_OF - timedelta(days=1)),
        _snapshot(original, "active", as_of=AS_OF),
    )
    assert shift is not None
    with pytest.raises(CategoricalTransitionDetectionError, match="exact bound activation"):
        route_categorical_shift_as_signal(
            binding=foreign,
            detector_id=DETECTOR_ID,
            shift=shift,
            detected_at=AS_OF,
        )


def test_forged_binding_reference_fails_closed() -> None:
    from ace.intelligence.detection import CategoricalTransitionDetectionError

    active = _binding(pack_id="binding_reference_owner")
    foreign = _binding(pack_id="foreign_binding_reference")
    forged = PreparedActivationBinding(
        pack=active.pack,
        revision=active.revision,
        reference=foreign.reference,
    )
    with pytest.raises(CategoricalTransitionDetectionError, match="binding reference does not match"):
        _detect(
            forged,
            _snapshot(active, "draft", as_of=AS_OF - timedelta(days=1)),
            _snapshot(active, "active", as_of=AS_OF),
        )


# --- mode discipline --------------------------------------------------------


def test_prepared_entry_points_reject_live_resources() -> None:
    from ace.intelligence import route_categorical_shift_as_signal
    from ace.intelligence.detection import CategoricalTransitionDetectionError

    binding = _binding()
    with pytest.raises(CategoricalTransitionDetectionError, match="only prepared snapshots"):
        _detect(
            binding,
            _snapshot(
                binding,
                "draft",
                as_of=AS_OF - timedelta(days=1),
                mode=IntelligenceResourceMode.LIVE,
            ),
            _snapshot(binding, "active", as_of=AS_OF, mode=IntelligenceResourceMode.LIVE),
        )

    prepared_shift = _detect(
        binding,
        _snapshot(binding, "draft", as_of=AS_OF - timedelta(days=1)),
        _snapshot(binding, "active", as_of=AS_OF),
    )
    assert prepared_shift is not None
    live_shift_payload = prepared_shift.model_dump(
        mode="python",
        exclude={"resource_id", "resource_digest"},
    )
    live_shift_payload["mode"] = IntelligenceResourceMode.LIVE
    live_shift = prepared_shift.__class__.model_validate(live_shift_payload)
    with pytest.raises(CategoricalTransitionDetectionError, match="only prepared Shifts"):
        route_categorical_shift_as_signal(
            binding=binding,
            detector_id=DETECTOR_ID,
            shift=live_shift,
            detected_at=AS_OF,
        )


def test_live_entry_points_accept_only_live_resources() -> None:
    from ace.intelligence import (
        detect_live_categorical_shift,
        eligible_live_signal_routes,
        route_live_categorical_shift_as_signal,
    )
    from ace.intelligence.detection import CategoricalTransitionDetectionError

    binding = _binding()
    shift = detect_live_categorical_shift(
        binding=binding,
        detector_id=DETECTOR_ID,
        baseline=_snapshot(
            binding,
            "draft",
            as_of=AS_OF - timedelta(days=1),
            mode=IntelligenceResourceMode.LIVE,
        ),
        current=_snapshot(binding, "active", as_of=AS_OF, mode=IntelligenceResourceMode.LIVE),
        detected_at=AS_OF,
    )
    assert shift is not None and shift.mode is IntelligenceResourceMode.LIVE
    signal = route_live_categorical_shift_as_signal(
        binding=binding,
        detector_id=DETECTOR_ID,
        shift=shift,
        detected_at=AS_OF,
    )
    assert signal.mode is IntelligenceResourceMode.LIVE
    assert eligible_live_signal_routes(binding=binding, signal=signal) == ()

    with pytest.raises(CategoricalTransitionDetectionError, match="only live snapshots"):
        detect_live_categorical_shift(
            binding=binding,
            detector_id=DETECTOR_ID,
            baseline=_snapshot(binding, "draft", as_of=AS_OF - timedelta(days=1)),
            current=_snapshot(binding, "active", as_of=AS_OF),
            detected_at=AS_OF,
        )


# --- exact replay -----------------------------------------------------------


def test_detection_and_routing_replay_to_identical_identities() -> None:
    from ace.intelligence import route_categorical_shift_as_signal

    binding = _binding()
    baseline = _snapshot(binding, "draft", as_of=AS_OF - timedelta(days=1))
    current = _snapshot(binding, "active", as_of=AS_OF)

    first = _detect(binding, baseline, current)
    second = _detect(binding, baseline, current)
    assert first is not None and second is not None
    assert first.resource_id == second.resource_id
    assert first.resource_digest == second.resource_digest

    first_signal = route_categorical_shift_as_signal(
        binding=binding, detector_id=DETECTOR_ID, shift=first, detected_at=AS_OF
    )
    second_signal = route_categorical_shift_as_signal(
        binding=binding, detector_id=DETECTOR_ID, shift=second, detected_at=AS_OF
    )
    assert first_signal.resource_id == second_signal.resource_id
    assert first_signal.resource_digest == second_signal.resource_digest
