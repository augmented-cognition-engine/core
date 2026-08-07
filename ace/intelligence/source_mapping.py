"""Pure PREPARED interpretation of activation-bound declarative source mappings."""

from __future__ import annotations

import math
import re
from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal, InvalidOperation
from typing import Any, Literal
from urllib.parse import urlsplit

from ace.core.contracts import canonical_hash, canonical_json
from ace.core.source import CanonicalSourceSnapshotV1Alpha1, SourceAcquisitionMode
from ace.intelligence.contracts.common import MAX_CANONICAL_VALUE_CHARS
from ace.intelligence.contracts.pack import AttributeDeclarationV1, AttributeValueType
from ace.intelligence.contracts.resources import (
    CanonicalJsonValueV1Alpha1,
    EntitySnapshotV1Alpha1,
    EvidenceAcquisitionMode,
    IntelligenceResourceMode,
    LineageReferenceV1Alpha1,
    LineageResourceKind,
    ObservationV1Alpha1,
    SourceMappingReferenceV1Alpha1,
)
from ace.intelligence.contracts.source_mapping import (
    AttributeMappingV1,
    ResolvedSubjectBindingV1Alpha1,
    SourceMappingCharacterSet,
    SourceMappingTransform,
)
from ace.intelligence.packs.runtime import (
    PreparedActivationBinding,
    PreparedActivationBindingError,
    resolve_entity_type_declaration,
    resolve_source_mapping_policy,
    validate_prepared_activation_binding,
)

_DECIMAL_TEXT = re.compile(r"^-?(?:0|[1-9][0-9]*)(?:\.[0-9]+)?$")
_MAX_DECIMAL_TEXT_CHARS = 64


class PreparedSourceMappingError(ValueError):
    """A source snapshot failed closed PREPARED mapping."""


class LiveSourceMappingError(ValueError):
    """A candidate LIVE source snapshot failed closed pure mapping."""


@dataclass(frozen=True, slots=True)
class PreparedSourceMappingResult:
    """Exactly one normalized Observation and its exact-lineage Entity Snapshot."""

    observation: ObservationV1Alpha1
    entity_snapshot: EntitySnapshotV1Alpha1
    mode: Literal[IntelligenceResourceMode.PREPARED] = IntelligenceResourceMode.PREPARED
    authority_stage: Literal["prepared_only"] = "prepared_only"

    @property
    def live_authority(self) -> Literal[False]:
        return False

    @property
    def live_acquisition(self) -> Literal[False]:
        return False


@dataclass(frozen=True, slots=True)
class LiveSourceMappingResult:
    """Candidate LIVE Observation and exact-lineage Entity Snapshot only."""

    observation: ObservationV1Alpha1
    entity_snapshot: EntitySnapshotV1Alpha1
    mode: Literal[IntelligenceResourceMode.LIVE] = IntelligenceResourceMode.LIVE
    authority_stage: Literal["mapping_only"] = "mapping_only"

    @property
    def live_authority(self) -> Literal[False]:
        return False

    @property
    def live_acquisition(self) -> Literal[True]:
        return True


def _revalidate_source_snapshot(
    source_snapshot: CanonicalSourceSnapshotV1Alpha1,
) -> CanonicalSourceSnapshotV1Alpha1:
    try:
        return CanonicalSourceSnapshotV1Alpha1.model_validate(source_snapshot.model_dump(mode="python"))
    except (AttributeError, TypeError, ValueError) as exc:
        raise PreparedSourceMappingError("source snapshot failed exact Core contract revalidation") from exc


def _revalidate_subject_binding(
    subject_binding: ResolvedSubjectBindingV1Alpha1,
) -> ResolvedSubjectBindingV1Alpha1:
    try:
        return ResolvedSubjectBindingV1Alpha1.model_validate(subject_binding.model_dump(mode="python"))
    except (AttributeError, TypeError, ValueError) as exc:
        raise PreparedSourceMappingError("resolved subject binding failed exact revalidation") from exc


def _pointer_segment(value: str) -> str:
    return value.replace("~1", "/").replace("~0", "~")


def _resolve_pointer(payload: Any, pointer: str) -> Any:
    if pointer == "":
        return payload
    current = payload
    for raw_segment in pointer.split("/")[1:]:
        segment = _pointer_segment(raw_segment)
        if isinstance(current, dict):
            if segment not in current:
                raise PreparedSourceMappingError(f"source_pointer {pointer!r} did not resolve")
            current = current[segment]
            continue
        if isinstance(current, list):
            if segment == "-" or not segment.isascii() or not segment.isdigit():
                raise PreparedSourceMappingError(f"source_pointer {pointer!r} contains an invalid array index")
            if len(segment) > 1 and segment.startswith("0"):
                raise PreparedSourceMappingError(f"source_pointer {pointer!r} contains a non-canonical array index")
            index = int(segment)
            if index >= len(current):
                raise PreparedSourceMappingError(f"source_pointer {pointer!r} did not resolve")
            current = current[index]
            continue
        raise PreparedSourceMappingError(f"source_pointer {pointer!r} traversed a scalar value")
    return current


def _validate_string_constraints(value: Any, mapping: AttributeMappingV1) -> str:
    if not isinstance(value, str):
        raise PreparedSourceMappingError(
            f"attribute {mapping.attribute_id!r} requires a string before its declared constraints"
        )
    if mapping.min_length is not None and len(value) < mapping.min_length:
        raise PreparedSourceMappingError(f"attribute {mapping.attribute_id!r} is shorter than min_length")
    if mapping.max_length is not None and len(value) > mapping.max_length:
        raise PreparedSourceMappingError(f"attribute {mapping.attribute_id!r} is longer than max_length")
    if mapping.character_set is SourceMappingCharacterSet.ASCII_UPPER and any(
        character < "A" or character > "Z" for character in value
    ):
        raise PreparedSourceMappingError(f"attribute {mapping.attribute_id!r} violates character_set=ascii_upper")
    return value


def _has_string_constraints(mapping: AttributeMappingV1) -> bool:
    return any(value is not None for value in (mapping.min_length, mapping.max_length, mapping.character_set))


def _decimal_text_to_number(value: Any, mapping: AttributeMappingV1) -> float:
    text = _validate_string_constraints(value, mapping)
    if len(text) > _MAX_DECIMAL_TEXT_CHARS or not _DECIMAL_TEXT.fullmatch(text):
        raise PreparedSourceMappingError(f"attribute {mapping.attribute_id!r} is not bounded decimal text")
    try:
        decimal_value = Decimal(text)
        result = float(decimal_value)
    except (InvalidOperation, OverflowError, ValueError) as exc:
        raise PreparedSourceMappingError(
            f"attribute {mapping.attribute_id!r} is not representable as a number"
        ) from exc
    if not decimal_value.is_finite() or not math.isfinite(result):
        raise PreparedSourceMappingError(f"attribute {mapping.attribute_id!r} must produce a finite number")
    if Decimal(str(result)) != decimal_value:
        raise PreparedSourceMappingError(
            f"attribute {mapping.attribute_id!r} is not faithfully representable as a JSON number"
        )
    return 0.0 if result == 0.0 else result


def _validate_datetime_text(value: str, *, attribute_id: str) -> None:
    try:
        parsed = datetime.fromisoformat(value)
    except ValueError as exc:
        raise PreparedSourceMappingError(f"attribute {attribute_id!r} must be an ISO 8601 datetime") from exc
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise PreparedSourceMappingError(f"attribute {attribute_id!r} datetime must include a timezone")


def _validate_reference_text(value: str, *, attribute_id: str) -> None:
    if len(value) > 240 or not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9._:/-]{0,239}", value):
        raise PreparedSourceMappingError(f"attribute {attribute_id!r} must be a bounded stable entity reference")


def _validate_scalar(value: Any, target: AttributeDeclarationV1) -> None:
    if target.value_type is AttributeValueType.STRING:
        valid = isinstance(value, str)
    elif target.value_type is AttributeValueType.INTEGER:
        valid = type(value) is int
    elif target.value_type is AttributeValueType.NUMBER:
        valid = (
            isinstance(value, (int, float))
            and not isinstance(value, bool)
            and (not isinstance(value, float) or math.isfinite(value))
        )
    elif target.value_type is AttributeValueType.BOOLEAN:
        valid = type(value) is bool
    elif target.value_type is AttributeValueType.DATETIME:
        valid = isinstance(value, str)
        if valid:
            _validate_datetime_text(value, attribute_id=target.attribute_id)
    elif target.value_type is AttributeValueType.ENTITY_REF:
        valid = isinstance(value, str)
        if valid:
            _validate_reference_text(value, attribute_id=target.attribute_id)
    else:
        valid = True
    if not valid:
        raise PreparedSourceMappingError(
            f"attribute {target.attribute_id!r} does not match ontology type {target.value_type.value}"
        )


def _validate_target_value(value: Any, target: AttributeDeclarationV1) -> None:
    if target.many:
        if not isinstance(value, list):
            raise PreparedSourceMappingError(f"attribute {target.attribute_id!r} requires an array for many=true")
        for item in value:
            _validate_scalar(item, target)
        return
    _validate_scalar(value, target)


def _mapped_value(
    payload: Any,
    mapping: AttributeMappingV1,
    target: AttributeDeclarationV1,
) -> Any:
    selected = _resolve_pointer(payload, mapping.source_pointer)
    if mapping.transform is SourceMappingTransform.DECIMAL_TEXT_TO_NUMBER:
        value = _decimal_text_to_number(selected, mapping)
    else:
        value = selected
        if _has_string_constraints(mapping):
            if target.many:
                if not isinstance(value, list):
                    raise PreparedSourceMappingError(
                        f"attribute {mapping.attribute_id!r} requires an array for many=true"
                    )
                value = [_validate_string_constraints(item, mapping) for item in value]
            else:
                value = _validate_string_constraints(value, mapping)
    _validate_target_value(value, target)
    return value


def _map_attributes_with_budget(
    payload: Any,
    mappings: tuple[AttributeMappingV1, ...],
    attributes: dict[str, AttributeDeclarationV1],
) -> CanonicalJsonValueV1Alpha1:
    """Build exact canonical object text without evaluating mappings beyond its public bound."""

    fragments: list[str] = []
    output_chars = 2  # Opening and closing object braces.
    for item in mappings:
        value = _mapped_value(payload, item, attributes[item.attribute_id])
        fragment = f"{canonical_json(item.attribute_id)}:{canonical_json(value)}"
        next_output_chars = output_chars + len(fragment) + (1 if fragments else 0)
        if next_output_chars > MAX_CANONICAL_VALUE_CHARS:
            raise PreparedSourceMappingError("mapped attribute canonical output exceeds the bounded resource size")
        fragments.append(fragment)
        output_chars = next_output_chars
    return CanonicalJsonValueV1Alpha1(value_json=f"{{{','.join(fragments)}}}")


def _assert_activation_declarations(binding: PreparedActivationBinding, mapping) -> None:
    capability_requirements = {item.requirement_id: item for item in binding.pack.capability_requirements}
    capability_bindings = {item.requirement_id: item for item in binding.revision.spec.capability_bindings}
    requirement = capability_requirements.get(mapping.capability_requirement_id)
    capability_binding = capability_bindings.get(mapping.capability_requirement_id)
    if (
        requirement is None
        or capability_binding is None
        or capability_binding.capability != requirement.capability
        or capability_binding.contract != requirement.contract
    ):
        raise PreparedSourceMappingError(
            "prepared activation does not structurally bind the mapping's declared capability"
        )

    authority_requests = {item.request_id: item for item in binding.pack.authority_requests}
    authority_bindings = {item.request_id: item for item in binding.revision.spec.authority_bindings}
    request = authority_requests.get(mapping.authority_request_id)
    authority_binding = authority_bindings.get(mapping.authority_request_id)
    if request is None or authority_binding is None or authority_binding.authority != request.authority:
        raise PreparedSourceMappingError(
            "prepared activation does not structurally bind the mapping's declared authority request"
        )


def _interpret_source_mapping(
    *,
    binding: PreparedActivationBinding,
    mapping_id: str,
    source_snapshot: CanonicalSourceSnapshotV1Alpha1,
    subject_binding: ResolvedSubjectBindingV1Alpha1,
    mode: IntelligenceResourceMode,
) -> PreparedSourceMappingResult | LiveSourceMappingResult:
    """Interpret inert Pack IR against one immutable snapshot without effects or authority decisions."""

    try:
        validated_binding = validate_prepared_activation_binding(binding)
        resolved_mapping = resolve_source_mapping_policy(
            validated_binding,
            mapping_id=mapping_id,
        )
        mapping = resolved_mapping.rule
        entity_type = resolve_entity_type_declaration(
            validated_binding,
            entity_type_id=mapping.entity_type_id,
        )
    except (AttributeError, TypeError, ValueError, PreparedActivationBindingError) as exc:
        raise PreparedSourceMappingError("compiled Pack IR and activation binding failed exact resolution") from exc

    snapshot = _revalidate_source_snapshot(source_snapshot)
    subject = _revalidate_subject_binding(subject_binding)
    if mode is IntelligenceResourceMode.PREPARED:
        if snapshot.acquisition_mode is SourceAcquisitionMode.LIVE:
            raise PreparedSourceMappingError("PREPARED source mapping rejects every LIVE source snapshot")
    elif snapshot.acquisition_mode is not SourceAcquisitionMode.LIVE:
        raise LiveSourceMappingError("LIVE source mapping requires one LIVE source snapshot")
    if snapshot.source_definition_ref != mapping.source_definition_ref:
        raise PreparedSourceMappingError("source snapshot definition does not match the exact selected mapping")
    if snapshot.source_type_ref != mapping.source_type_ref:
        raise PreparedSourceMappingError("source snapshot type does not match the selected mapping")
    if urlsplit(snapshot.source_uri).scheme not in mapping.allowed_uri_schemes:
        raise PreparedSourceMappingError("source snapshot URI scheme is not allowed by the selected mapping")

    product_id = validated_binding.revision.spec.product_id
    if subject.product_id != product_id:
        raise PreparedSourceMappingError("resolved subject binding crossed the exact product scope")
    if subject.activation_revision != validated_binding.reference:
        raise PreparedSourceMappingError("resolved subject binding does not name the exact activation revision")
    if subject.mode is not mode:
        if mode is IntelligenceResourceMode.PREPARED:
            raise PreparedSourceMappingError("PREPARED source mapping rejects every LIVE subject binding")
        raise LiveSourceMappingError("LIVE source mapping requires one LIVE subject binding")
    if subject.subject_binding_id != mapping.subject_binding_id:
        raise PreparedSourceMappingError("resolved subject binding ID does not match the selected mapping")
    if subject.entity_type_id != mapping.entity_type_id:
        raise PreparedSourceMappingError("resolved subject entity type does not match the selected mapping")
    _assert_activation_declarations(validated_binding, mapping)

    attributes = {item.attribute_id: item for item in entity_type.attributes}
    payload = snapshot.captured_payload()
    canonical_attributes = _map_attributes_with_budget(
        payload,
        mapping.attribute_mappings,
        attributes,
    )
    acquisition_mode = EvidenceAcquisitionMode(snapshot.acquisition_mode.value)
    if snapshot.source_snapshot_ref is None or snapshot.source_snapshot_digest is None:
        raise PreparedSourceMappingError("source snapshot is missing its derived exact identity")
    if validated_binding.pack.compiled_pack_id is None or validated_binding.pack.pack_digest is None:
        raise PreparedSourceMappingError("compiled Pack IR is missing its derived exact identity")
    source_mapping_reference = SourceMappingReferenceV1Alpha1(
        activation_revision=validated_binding.reference,
        compiled_pack_id=validated_binding.pack.compiled_pack_id,
        pack_digest=validated_binding.pack.pack_digest,
        module_id=resolved_mapping.module_id,
        module_digest=resolved_mapping.module_digest,
        mapping_id=mapping.mapping_id,
        mapping_digest=f"sha256:{canonical_hash(mapping)}",
    )
    observation = ObservationV1Alpha1(
        product_id=product_id,
        mode=mode,
        activation_revision=validated_binding.reference,
        as_of=snapshot.ingested_at,
        source_ref=snapshot.source_snapshot_ref,
        source_digest=snapshot.source_snapshot_digest,
        acquisition_mode=acquisition_mode,
        acquisition_receipt_ref=snapshot.acquisition_receipt_ref,
        acquisition_receipt_digest=snapshot.acquisition_receipt_digest,
        source_published_at=snapshot.source_published_at,
        event_effective_at=snapshot.event_effective_at,
        observed_at=snapshot.observed_at,
        ingested_at=snapshot.ingested_at,
        subject_refs=(subject.entity_ref,),
        payload=canonical_attributes,
        confidence=mapping.static_confidence,
        source_mapping=source_mapping_reference,
    )
    if observation.resource_id is None or observation.resource_digest is None:
        raise PreparedSourceMappingError("Observation is missing its derived exact identity")
    entity_snapshot = EntitySnapshotV1Alpha1(
        product_id=product_id,
        mode=mode,
        activation_revision=validated_binding.reference,
        as_of=snapshot.ingested_at,
        lineage=(
            LineageReferenceV1Alpha1(
                resource_kind=LineageResourceKind.OBSERVATION,
                resource_id=observation.resource_id,
                resource_digest=observation.resource_digest,
                resource_as_of=observation.as_of,
                resource_available_at=observation.ingested_at,
            ),
        ),
        entity_ref=subject.entity_ref,
        entity_type_ref=subject.entity_type_id,
        attributes=canonical_attributes,
        projected_at=snapshot.ingested_at,
        confidence=mapping.static_confidence,
    )
    result_type = PreparedSourceMappingResult if mode is IntelligenceResourceMode.PREPARED else LiveSourceMappingResult
    return result_type(observation=observation, entity_snapshot=entity_snapshot)


def interpret_prepared_source_mapping(
    *,
    binding: PreparedActivationBinding,
    mapping_id: str,
    source_snapshot: CanonicalSourceSnapshotV1Alpha1,
    subject_binding: ResolvedSubjectBindingV1Alpha1,
) -> PreparedSourceMappingResult:
    """Normalize every validation failure onto the public PREPARED error surface."""

    try:
        result = _interpret_source_mapping(
            binding=binding,
            mapping_id=mapping_id,
            source_snapshot=source_snapshot,
            subject_binding=subject_binding,
            mode=IntelligenceResourceMode.PREPARED,
        )
        if not isinstance(result, PreparedSourceMappingResult):
            raise PreparedSourceMappingError("PREPARED source mapping produced the wrong mode")
        return result
    except PreparedSourceMappingError:
        raise
    except (AttributeError, IndexError, KeyError, OverflowError, TypeError, ValueError) as exc:
        raise PreparedSourceMappingError("PREPARED source mapping validation failed closed") from exc


def interpret_live_source_mapping(
    *,
    binding: PreparedActivationBinding,
    mapping_id: str,
    source_snapshot: CanonicalSourceSnapshotV1Alpha1,
    subject_binding: ResolvedSubjectBindingV1Alpha1,
) -> LiveSourceMappingResult:
    """Purely map a LIVE capture; authorization and persistence remain external."""

    try:
        result = _interpret_source_mapping(
            binding=binding,
            mapping_id=mapping_id,
            source_snapshot=source_snapshot,
            subject_binding=subject_binding,
            mode=IntelligenceResourceMode.LIVE,
        )
        if not isinstance(result, LiveSourceMappingResult):
            raise LiveSourceMappingError("LIVE source mapping produced the wrong mode")
        return result
    except LiveSourceMappingError:
        raise
    except (AttributeError, IndexError, KeyError, OverflowError, TypeError, ValueError) as exc:
        raise LiveSourceMappingError("LIVE source mapping validation failed closed") from exc


__all__ = [
    "PreparedSourceMappingError",
    "PreparedSourceMappingResult",
    "LiveSourceMappingError",
    "LiveSourceMappingResult",
    "interpret_live_source_mapping",
    "interpret_prepared_source_mapping",
]
