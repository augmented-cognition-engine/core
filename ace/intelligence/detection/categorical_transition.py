"""Pure interpretation of exact, activation-bound categorical-transition policy."""

from __future__ import annotations

import math
from datetime import UTC, datetime
from typing import Any

from ace.core.contracts import canonical_json
from ace.intelligence.contracts.common import validate_reference
from ace.intelligence.contracts.detection import CategoricalTransitionRuleV1
from ace.intelligence.contracts.pack import (
    AttributeDeclarationV1,
    AttributeValueType,
    EntityTypeDeclarationV1,
)
from ace.intelligence.contracts.resources import (
    CanonicalJsonValueV1Alpha1,
    EntitySnapshotV1Alpha1,
    IntelligenceResourceMode,
    LineageReferenceV1Alpha1,
    LineageRelation,
    LineageResourceKind,
    ShiftV1Alpha1,
    SignalV1Alpha1,
)
from ace.intelligence.packs.runtime import (
    PreparedActivationBinding,
    PreparedActivationBindingError,
    resolve_categorical_transition_rule,
    resolve_entity_type_declaration,
    validate_prepared_activation_binding,
)


class CategoricalTransitionDetectionError(ValueError):
    """The supplied snapshots cannot be compared under the bound rule."""


def _aware_utc(value: datetime, *, label: str) -> datetime:
    if value.tzinfo is None or value.utcoffset() is None:
        raise CategoricalTransitionDetectionError(f"{label} must include a timezone")
    return value.astimezone(UTC)


def _revalidate_snapshot(
    snapshot: EntitySnapshotV1Alpha1,
    *,
    label: str,
) -> EntitySnapshotV1Alpha1:
    try:
        return EntitySnapshotV1Alpha1.model_validate(snapshot.model_dump(mode="python"))
    except (AttributeError, TypeError, ValueError) as exc:
        raise CategoricalTransitionDetectionError(f"{label} failed exact resource revalidation") from exc


def _revalidate_shift(shift: ShiftV1Alpha1) -> ShiftV1Alpha1:
    try:
        return ShiftV1Alpha1.model_validate(shift.model_dump(mode="python"))
    except (AttributeError, TypeError, ValueError) as exc:
        raise CategoricalTransitionDetectionError("Shift failed exact resource revalidation") from exc


def _validated_binding(binding: PreparedActivationBinding) -> PreparedActivationBinding:
    try:
        return validate_prepared_activation_binding(binding)
    except PreparedActivationBindingError as exc:
        raise CategoricalTransitionDetectionError(str(exc)) from exc


def _attributes(snapshot: EntitySnapshotV1Alpha1) -> dict[str, Any]:
    attributes = snapshot.attributes.parsed_value()
    if not isinstance(attributes, dict):
        raise CategoricalTransitionDetectionError("entity snapshot attributes must be a JSON object")
    return attributes


def _validate_scalar_attribute(
    value: Any,
    *,
    declaration: AttributeDeclarationV1,
) -> None:
    value_type = declaration.value_type
    valid = False
    if value_type is AttributeValueType.STRING:
        valid = type(value) is str
    elif value_type is AttributeValueType.INTEGER:
        valid = type(value) is int
    elif value_type is AttributeValueType.NUMBER:
        valid = type(value) in {int, float} and (type(value) is int or math.isfinite(value))
    elif value_type is AttributeValueType.BOOLEAN:
        valid = type(value) is bool
    elif value_type is AttributeValueType.DATETIME:
        if type(value) is str:
            try:
                parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
                valid = parsed.tzinfo is not None and parsed.utcoffset() is not None
            except ValueError:
                valid = False
    elif value_type is AttributeValueType.ENTITY_REF:
        if type(value) is str:
            try:
                validate_reference(value, name=declaration.attribute_id)
                valid = True
            except ValueError:
                valid = False
    else:
        valid = value_type is AttributeValueType.JSON
    if not valid:
        raise CategoricalTransitionDetectionError(
            f"attribute {declaration.attribute_id} must match ontology type {value_type.value}"
        )


def _validate_attributes_against_entity_type(
    attributes: dict[str, Any],
    *,
    entity_type: EntityTypeDeclarationV1,
) -> None:
    declarations = {item.attribute_id: item for item in entity_type.attributes}
    unknown = set(attributes) - set(declarations)
    if unknown:
        raise CategoricalTransitionDetectionError(
            f"entity snapshot contains attributes not declared by {entity_type.entity_type_id}: {sorted(unknown)}"
        )
    missing = {
        item.attribute_id for item in entity_type.attributes if item.required and item.attribute_id not in attributes
    }
    if missing:
        raise CategoricalTransitionDetectionError(
            f"entity snapshot is missing required ontology attributes: {sorted(missing)}"
        )
    for attribute_id, value in attributes.items():
        declaration = declarations[attribute_id]
        if declaration.many:
            if type(value) is not list:
                raise CategoricalTransitionDetectionError(
                    f"attribute {attribute_id} must be an array under its ontology declaration"
                )
            for item in value:
                _validate_scalar_attribute(item, declaration=declaration)
        else:
            _validate_scalar_attribute(value, declaration=declaration)


def _attribute(attributes: dict[str, Any], rule: CategoricalTransitionRuleV1) -> str:
    if rule.attribute_id not in attributes:
        raise CategoricalTransitionDetectionError(
            f"entity snapshot does not contain watched attribute {rule.attribute_id}"
        )
    value = attributes[rule.attribute_id]
    if type(value) is not str:
        raise CategoricalTransitionDetectionError(
            f"{rule.attribute_id} must be a string categorical value without coercion"
        )
    return value


def _comparison_context(
    *,
    rule: CategoricalTransitionRuleV1,
    baseline_attributes: dict[str, Any],
    current_attributes: dict[str, Any],
) -> dict[str, Any]:
    context: dict[str, Any] = {}
    for attribute_id in rule.context_attribute_ids:
        if attribute_id not in baseline_attributes or attribute_id not in current_attributes:
            raise CategoricalTransitionDetectionError(
                f"both snapshots must contain comparison context attribute {attribute_id}"
            )
        if canonical_json(baseline_attributes[attribute_id]) != canonical_json(current_attributes[attribute_id]):
            raise CategoricalTransitionDetectionError(
                f"comparison context attribute {attribute_id} changed between snapshots"
            )
        context[attribute_id] = current_attributes[attribute_id]
    return context


def _validate_pair(
    *,
    binding: PreparedActivationBinding,
    rule: CategoricalTransitionRuleV1,
    baseline: EntitySnapshotV1Alpha1,
    current: EntitySnapshotV1Alpha1,
    detected_at: datetime,
    expected_mode: IntelligenceResourceMode,
) -> None:
    if baseline.mode is not expected_mode or current.mode is not expected_mode:
        raise CategoricalTransitionDetectionError(
            f"{expected_mode.value} detection can interpret only {expected_mode.value} snapshots"
        )
    if baseline.activation_revision != binding.reference or current.activation_revision != binding.reference:
        raise CategoricalTransitionDetectionError(
            "categorical transition snapshots must use the exact bound activation revision"
        )
    if baseline.product_id != current.product_id:
        raise CategoricalTransitionDetectionError("categorical transition snapshots must share one product scope")
    if baseline.product_id != binding.revision.spec.product_id:
        raise CategoricalTransitionDetectionError(
            "categorical transition snapshots are outside the bound product scope"
        )
    if baseline.entity_ref != current.entity_ref:
        raise CategoricalTransitionDetectionError("categorical transition snapshots must resolve to the same entity")
    if baseline.entity_type_ref != current.entity_type_ref:
        raise CategoricalTransitionDetectionError("categorical transition snapshots must share one entity type")
    if current.entity_type_ref != rule.entity_type_id:
        raise CategoricalTransitionDetectionError(
            "categorical transition rule does not target the snapshot entity type"
        )
    if baseline.as_of >= current.as_of:
        raise CategoricalTransitionDetectionError("categorical transition baseline must precede current state")
    if baseline.as_of < binding.revision.occurred_at:
        raise CategoricalTransitionDetectionError(
            "categorical transition baseline predates the prepared activation revision"
        )
    available_at = max(baseline.projected_at, current.projected_at)
    if _aware_utc(detected_at, label="detected_at") < available_at:
        raise CategoricalTransitionDetectionError(
            "categorical transition cannot be detected before both snapshots were projected"
        )


def _json_value(value: Any) -> CanonicalJsonValueV1Alpha1:
    return CanonicalJsonValueV1Alpha1(value_json=canonical_json(value))


def _snapshot_lineage(snapshot: EntitySnapshotV1Alpha1) -> LineageReferenceV1Alpha1:
    return LineageReferenceV1Alpha1(
        resource_kind=LineageResourceKind.ENTITY_SNAPSHOT,
        relation=LineageRelation.DERIVED_FROM,
        resource_id=snapshot.resource_id,
        resource_digest=snapshot.resource_digest,
        resource_as_of=snapshot.as_of,
        resource_available_at=snapshot.projected_at,
    )


def _detect_categorical_shift(
    *,
    binding: PreparedActivationBinding,
    detector_id: str,
    baseline: EntitySnapshotV1Alpha1,
    current: EntitySnapshotV1Alpha1,
    detected_at: datetime,
    expected_mode: IntelligenceResourceMode,
) -> ShiftV1Alpha1 | None:
    """Interpret one detector from exact activation-bound Pack IR."""

    validated_binding = _validated_binding(binding)
    try:
        rule = resolve_categorical_transition_rule(validated_binding, detector_id=detector_id)
        entity_type = resolve_entity_type_declaration(
            validated_binding,
            entity_type_id=rule.entity_type_id,
        )
    except PreparedActivationBindingError as exc:
        raise CategoricalTransitionDetectionError(str(exc)) from exc
    validated_baseline = _revalidate_snapshot(baseline, label="baseline snapshot")
    validated_current = _revalidate_snapshot(current, label="current snapshot")
    _validate_pair(
        binding=validated_binding,
        rule=rule,
        baseline=validated_baseline,
        current=validated_current,
        detected_at=detected_at,
        expected_mode=expected_mode,
    )
    baseline_attributes = _attributes(validated_baseline)
    current_attributes = _attributes(validated_current)
    _validate_attributes_against_entity_type(
        baseline_attributes,
        entity_type=entity_type,
    )
    _validate_attributes_against_entity_type(
        current_attributes,
        entity_type=entity_type,
    )
    context = _comparison_context(
        rule=rule,
        baseline_attributes=baseline_attributes,
        current_attributes=current_attributes,
    )
    baseline_value = _attribute(baseline_attributes, rule)
    current_value = _attribute(current_attributes, rule)
    if not any(
        transition.from_value == baseline_value and transition.to_value == current_value
        for transition in rule.transitions
    ):
        return None

    confidence = min(validated_baseline.confidence, validated_current.confidence)
    return ShiftV1Alpha1(
        product_id=validated_current.product_id,
        mode=validated_current.mode,
        activation_revision=validated_binding.reference,
        as_of=validated_current.as_of,
        lineage=(
            _snapshot_lineage(validated_baseline),
            _snapshot_lineage(validated_current),
        ),
        shift_type_ref=rule.shift_type,
        title="Material transition detected",
        summary=(
            f"The watched categorical attribute {rule.attribute_id} changed from {baseline_value} to {current_value}."
        ),
        subject_refs=(validated_current.entity_ref,),
        baseline_as_of=validated_baseline.as_of,
        baseline=_json_value({"attribute_id": rule.attribute_id, "value": baseline_value}),
        current=_json_value({"attribute_id": rule.attribute_id, "value": current_value}),
        delta=_json_value(
            {
                "comparison_context": context,
                "detector_id": rule.detector_id,
                "from_value": baseline_value,
                "to_value": current_value,
            }
        ),
        detected_at=detected_at,
        confidence=confidence,
    )


def detect_categorical_shift(
    *,
    binding: PreparedActivationBinding,
    detector_id: str,
    baseline: EntitySnapshotV1Alpha1,
    current: EntitySnapshotV1Alpha1,
    detected_at: datetime,
) -> ShiftV1Alpha1 | None:
    """Interpret one detector over PREPARED snapshots only."""

    return _detect_categorical_shift(
        binding=binding,
        detector_id=detector_id,
        baseline=baseline,
        current=current,
        detected_at=detected_at,
        expected_mode=IntelligenceResourceMode.PREPARED,
    )


def detect_live_categorical_shift(
    *,
    binding: PreparedActivationBinding,
    detector_id: str,
    baseline: EntitySnapshotV1Alpha1,
    current: EntitySnapshotV1Alpha1,
    detected_at: datetime,
) -> ShiftV1Alpha1 | None:
    """Interpret one detector over admitted LIVE snapshots only.

    This pure function grants no LIVE authority.  The application bridge must
    prove a current committed activation and authorize persistence separately.
    """

    return _detect_categorical_shift(
        binding=binding,
        detector_id=detector_id,
        baseline=baseline,
        current=current,
        detected_at=detected_at,
        expected_mode=IntelligenceResourceMode.LIVE,
    )


def _route_categorical_shift_as_signal(
    *,
    binding: PreparedActivationBinding,
    detector_id: str,
    shift: ShiftV1Alpha1,
    detected_at: datetime,
    expected_mode: IntelligenceResourceMode,
) -> SignalV1Alpha1:
    """Route an established Shift using its exact bound detector policy."""

    validated_binding = _validated_binding(binding)
    try:
        rule = resolve_categorical_transition_rule(validated_binding, detector_id=detector_id)
    except PreparedActivationBindingError as exc:
        raise CategoricalTransitionDetectionError(str(exc)) from exc
    validated_shift = _revalidate_shift(shift)
    if validated_shift.mode is not expected_mode:
        raise CategoricalTransitionDetectionError(
            f"{expected_mode.value} routing can interpret only {expected_mode.value} Shifts"
        )
    if validated_shift.activation_revision != validated_binding.reference:
        raise CategoricalTransitionDetectionError("the Shift does not use the exact bound activation revision")
    if validated_shift.product_id != validated_binding.revision.spec.product_id:
        raise CategoricalTransitionDetectionError("the Shift is outside the bound product scope")
    if validated_shift.as_of < validated_binding.revision.occurred_at:
        raise CategoricalTransitionDetectionError("the Shift predates the prepared activation revision")
    if validated_shift.shift_type_ref != rule.shift_type:
        raise CategoricalTransitionDetectionError("the Shift does not match the bound detector rule")
    delta = validated_shift.delta.parsed_value()
    if not isinstance(delta, dict) or delta.get("detector_id") != rule.detector_id:
        raise CategoricalTransitionDetectionError("the Shift was not established by the bound detector rule")
    if _aware_utc(detected_at, label="detected_at") < validated_shift.detected_at:
        raise CategoricalTransitionDetectionError("a routed Signal cannot predate its source Shift")
    return SignalV1Alpha1(
        product_id=validated_shift.product_id,
        mode=validated_shift.mode,
        activation_revision=validated_binding.reference,
        as_of=validated_shift.as_of,
        lineage=(
            LineageReferenceV1Alpha1(
                resource_kind=LineageResourceKind.SHIFT,
                relation=LineageRelation.DERIVED_FROM,
                resource_id=validated_shift.resource_id,
                resource_digest=validated_shift.resource_digest,
                resource_as_of=validated_shift.as_of,
                resource_available_at=validated_shift.detected_at,
            ),
        ),
        signal_type_ref=rule.signal_type,
        title="Material transition requires attention",
        summary=validated_shift.summary,
        subject_refs=validated_shift.subject_refs,
        details=_json_value(
            {
                "detector_id": rule.detector_id,
                "shift_ref": validated_shift.resource_id,
                "shift_type": rule.shift_type,
            }
        ),
        detected_at=detected_at,
        confidence=validated_shift.confidence,
    )


def route_categorical_shift_as_signal(
    *,
    binding: PreparedActivationBinding,
    detector_id: str,
    shift: ShiftV1Alpha1,
    detected_at: datetime,
) -> SignalV1Alpha1:
    """Route an established PREPARED Shift only."""

    return _route_categorical_shift_as_signal(
        binding=binding,
        detector_id=detector_id,
        shift=shift,
        detected_at=detected_at,
        expected_mode=IntelligenceResourceMode.PREPARED,
    )


def route_live_categorical_shift_as_signal(
    *,
    binding: PreparedActivationBinding,
    detector_id: str,
    shift: ShiftV1Alpha1,
    detected_at: datetime,
) -> SignalV1Alpha1:
    """Route an established LIVE Shift; grants no delivery authority."""

    return _route_categorical_shift_as_signal(
        binding=binding,
        detector_id=detector_id,
        shift=shift,
        detected_at=detected_at,
        expected_mode=IntelligenceResourceMode.LIVE,
    )
