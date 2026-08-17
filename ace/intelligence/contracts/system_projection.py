"""Canonical, domain-neutral product projection for one ACE intelligence system.

The projection is a content-addressed read model over exact Pack, Builder, and
resource material.  It grants no authority, performs no source access, and does
not replace the Intelligence resource DAG.  Unsupported product values remain
explicitly unsupported rather than being inferred from counts or UI state.
"""

from __future__ import annotations

from datetime import UTC, datetime
from enum import StrEnum
from typing import Literal, Self

from pydantic import ConfigDict, Field, StrictBool, StrictInt, field_validator, model_validator

from ace.core.contracts import FrozenContract, canonical_hash, canonical_json
from ace.intelligence.contracts.activation import CompiledPackRefV1
from ace.intelligence.contracts.common import (
    validate_contract,
    validate_digest,
    validate_product_id,
    validate_reference,
    validate_slug,
)
from ace.intelligence.contracts.resources import ActivationRevisionReferenceV1Alpha1, CanonicalJsonValueV1Alpha1

INTELLIGENCE_SYSTEM_PROJECTION_VERSION = "ace.intelligence.system-projection/v1alpha1"
PROJECTION_MATERIAL_REFERENCE_VERSION = "ace.intelligence.projection-material-reference/v1alpha1"


class _ProjectionContract(FrozenContract):
    model_config = ConfigDict(
        extra="forbid",
        frozen=True,
        strict=True,
        revalidate_instances="always",
        validate_default=True,
        allow_inf_nan=False,
    )


class ProjectionMode(StrEnum):
    PROPOSED = "proposed"
    LIVE = "live"


class ProjectionSupport(StrEnum):
    MEASURED = "measured"
    DERIVED = "derived"
    OBSERVED = "observed"
    UNSUPPORTED = "unsupported"


class BlueprintElementKind(StrEnum):
    ENTITY = "entity"
    RELATIONSHIP = "relationship"
    EVENT = "event"
    SIGNAL = "signal"
    QUESTION = "question"
    UPDATE = "update"
    OUTPUT = "output"
    CONSUMER = "consumer"


class ProjectionChangeOperation(StrEnum):
    ADD = "add"
    UPDATE = "update"
    REMOVE = "remove"


class SourceBindingState(StrEnum):
    PROPOSED = "proposed"
    ACCESS_NEEDED = "access_needed"
    READY = "ready"
    UNAVAILABLE = "unavailable"


class PermissionReadinessState(StrEnum):
    NOT_EVALUATED = "not_evaluated"
    PENDING = "pending"
    READY = "ready"
    DENIED = "denied"
    UNAVAILABLE = "unavailable"


class CoverageDimension(StrEnum):
    ENTITY = "entity"
    EVENT = "event"
    SIGNAL = "signal"


class InitializationStage(StrEnum):
    BLUEPRINT_GENERATED = "blueprint_generated"
    REVIEW = "review"
    PERMISSIONS_VALIDATED = "permissions_validated"
    SOURCE_READINESS_VALIDATED = "source_readiness_validated"
    EVIDENCE_ADMITTED = "evidence_admitted"
    MODEL_INITIALIZED = "model_initialized"
    FIRST_INTELLIGENCE_VALIDATED = "first_intelligence_validated"
    MAINTENANCE_ACTIVATED = "maintenance_activated"


INITIALIZATION_STAGE_ORDER: tuple[InitializationStage, ...] = (
    InitializationStage.BLUEPRINT_GENERATED,
    InitializationStage.REVIEW,
    InitializationStage.PERMISSIONS_VALIDATED,
    InitializationStage.SOURCE_READINESS_VALIDATED,
    InitializationStage.EVIDENCE_ADMITTED,
    InitializationStage.MODEL_INITIALIZED,
    InitializationStage.FIRST_INTELLIGENCE_VALIDATED,
    InitializationStage.MAINTENANCE_ACTIVATED,
)


class InitializationStageState(StrEnum):
    COMPLETE = "complete"
    IN_PROGRESS = "in_progress"
    PENDING = "pending"
    BLOCKED = "blocked"


class DerivationStepKind(StrEnum):
    OBSERVATION = "observation"
    RESOLVED_ENTITY = "resolved_entity"
    MATERIAL_EVENT = "material_event"
    SIGNAL = "signal"
    CONCLUSION = "conclusion"


DERIVATION_STEP_ORDER: tuple[DerivationStepKind, ...] = (
    DerivationStepKind.OBSERVATION,
    DerivationStepKind.RESOLVED_ENTITY,
    DerivationStepKind.MATERIAL_EVENT,
    DerivationStepKind.SIGNAL,
    DerivationStepKind.CONCLUSION,
)


class DomainHealthDimension(StrEnum):
    COVERAGE = "coverage"
    FRESHNESS = "freshness"
    CONFIDENCE = "confidence"
    CONFLICTS = "conflicts"
    RESOLUTION = "resolution"
    SOURCE_HEALTH = "source_health"
    MAINTENANCE_HEALTH = "maintenance_health"
    HISTORICAL_DEPTH = "historical_depth"


DOMAIN_HEALTH_DIMENSION_ORDER: tuple[DomainHealthDimension, ...] = (
    DomainHealthDimension.COVERAGE,
    DomainHealthDimension.FRESHNESS,
    DomainHealthDimension.CONFIDENCE,
    DomainHealthDimension.CONFLICTS,
    DomainHealthDimension.RESOLUTION,
    DomainHealthDimension.SOURCE_HEALTH,
    DomainHealthDimension.MAINTENANCE_HEALTH,
    DomainHealthDimension.HISTORICAL_DEPTH,
)


def _aware(value: datetime, *, name: str) -> datetime:
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError(f"{name} must include a timezone")
    return value.astimezone(UTC)


def _trimmed(value: str, *, name: str, maximum: int = 2_000) -> str:
    if not value or value != value.strip() or len(value) > maximum:
        raise ValueError(f"{name} must be non-empty, trimmed, and at most {maximum} characters")
    return value


def _unique_refs(
    value: tuple["ProjectionMaterialReferenceV1Alpha1", ...],
    *,
    name: str,
) -> tuple["ProjectionMaterialReferenceV1Alpha1", ...]:
    keys = [(item.reference, item.digest, item.contract) for item in value]
    if len(keys) != len(set(keys)):
        raise ValueError(f"{name} must be unique")
    return tuple(sorted(value, key=lambda item: (item.reference, item.digest, item.contract)))


def _derive_identity(
    instance: _ProjectionContract,
    *,
    prefix: str,
    id_field: str,
    digest_field: str,
) -> None:
    material = instance.model_dump(mode="json", exclude={id_field, digest_field})
    digest = canonical_hash(material)
    expected_id = f"{prefix}:{digest[:32]}"
    expected_digest = f"sha256:{digest}"
    if getattr(instance, id_field) not in {None, expected_id}:
        raise ValueError(f"{id_field} does not match exact projection material")
    if getattr(instance, digest_field) not in {None, expected_digest}:
        raise ValueError(f"{digest_field} does not match exact projection material")
    object.__setattr__(instance, id_field, expected_id)
    object.__setattr__(instance, digest_field, expected_digest)


class ProjectionMaterialReferenceV1Alpha1(_ProjectionContract):
    """Exact immutable material used as projection basis, never reusable authority."""

    contract: Literal["ace.intelligence.projection-material-reference/v1alpha1"] = PROJECTION_MATERIAL_REFERENCE_VERSION
    material_contract: str
    reference: str
    digest: str

    @field_validator("material_contract")
    @classmethod
    def _contract(cls, value: str) -> str:
        return validate_contract(value)

    @field_validator("reference")
    @classmethod
    def _reference(cls, value: str) -> str:
        return validate_reference(value, name="projection material reference")

    @field_validator("digest")
    @classmethod
    def _digest(cls, value: str) -> str:
        return validate_digest(value)

    @property
    def reusable_authority(self) -> Literal[False]:
        return False


class ProjectionSupportStatementV1Alpha1(_ProjectionContract):
    support: ProjectionSupport
    basis: tuple[ProjectionMaterialReferenceV1Alpha1, ...] = Field(default_factory=tuple, max_length=256)
    reason: str | None = Field(default=None, min_length=1, max_length=1_000)

    @field_validator("basis")
    @classmethod
    def _basis(
        cls,
        value: tuple[ProjectionMaterialReferenceV1Alpha1, ...],
    ) -> tuple[ProjectionMaterialReferenceV1Alpha1, ...]:
        return _unique_refs(value, name="projection support basis")

    @model_validator(mode="after")
    def _support_truth(self) -> Self:
        if self.support is ProjectionSupport.UNSUPPORTED:
            if self.reason is None:
                raise ValueError("unsupported projection material requires an explicit reason")
        elif not self.basis:
            raise ValueError("supported projection material requires exact basis references")
        return self


class ProjectionValueV1Alpha1(_ProjectionContract):
    support: ProjectionSupport
    value: CanonicalJsonValueV1Alpha1 | None = None
    basis: tuple[ProjectionMaterialReferenceV1Alpha1, ...] = Field(default_factory=tuple, max_length=256)
    reason: str | None = Field(default=None, min_length=1, max_length=1_000)

    @field_validator("basis")
    @classmethod
    def _basis(
        cls,
        value: tuple[ProjectionMaterialReferenceV1Alpha1, ...],
    ) -> tuple[ProjectionMaterialReferenceV1Alpha1, ...]:
        return _unique_refs(value, name="projected value basis")

    @model_validator(mode="after")
    def _value_truth(self) -> Self:
        if self.support is ProjectionSupport.UNSUPPORTED:
            if self.value is not None or self.reason is None:
                raise ValueError("an unsupported value must omit value and explain why")
        elif self.value is None or not self.basis:
            raise ValueError("a supported value requires a value and exact basis references")
        return self


class BlueprintElementProjectionV1Alpha1(_ProjectionContract):
    kind: BlueprintElementKind
    element_id: str
    element_ref: str | None = None
    label: str = Field(min_length=1, max_length=240)
    rationale: str = Field(min_length=1, max_length=2_000)
    source_material: tuple[ProjectionMaterialReferenceV1Alpha1, ...] = Field(min_length=1, max_length=64)
    confidence: ProjectionValueV1Alpha1

    @field_validator("element_id")
    @classmethod
    def _element_id(cls, value: str) -> str:
        return validate_slug(value, name="blueprint element_id")

    @field_validator("element_ref")
    @classmethod
    def _element_ref(cls, value: str | None) -> str | None:
        return validate_reference(value, name="blueprint element_ref") if value is not None else None

    @field_validator("source_material")
    @classmethod
    def _source_material(
        cls,
        value: tuple[ProjectionMaterialReferenceV1Alpha1, ...],
    ) -> tuple[ProjectionMaterialReferenceV1Alpha1, ...]:
        return _unique_refs(value, name="blueprint source material")

    @model_validator(mode="after")
    def _identity(self) -> Self:
        expected = f"blueprint_element:{self.kind.value}:{self.element_id}"
        if self.element_ref not in {None, expected}:
            raise ValueError("element_ref does not match blueprint kind and identifier")
        object.__setattr__(self, "element_ref", expected)
        return self


class GeneratedBlueprintProjectionV1Alpha1(_ProjectionContract):
    plan: ProjectionMaterialReferenceV1Alpha1
    request: ProjectionMaterialReferenceV1Alpha1
    pack: CompiledPackRefV1
    subject: str = Field(min_length=8, max_length=2_000)
    elements: tuple[BlueprintElementProjectionV1Alpha1, ...] = Field(min_length=1, max_length=1_024)
    gaps: tuple[str, ...] = Field(default_factory=tuple, max_length=128)
    blueprint_id: str | None = None
    blueprint_digest: str | None = None

    @field_validator("elements")
    @classmethod
    def _elements(
        cls,
        value: tuple[BlueprintElementProjectionV1Alpha1, ...],
    ) -> tuple[BlueprintElementProjectionV1Alpha1, ...]:
        keys = [(item.kind.value, item.element_id) for item in value]
        if len(keys) != len(set(keys)):
            raise ValueError("blueprint elements must be unique by kind and identifier")
        return tuple(sorted(value, key=lambda item: (item.kind.value, item.element_id)))

    @field_validator("gaps")
    @classmethod
    def _gaps(cls, value: tuple[str, ...]) -> tuple[str, ...]:
        normalized = tuple(sorted(_trimmed(item, name="blueprint gap", maximum=1_000) for item in value))
        if len(normalized) != len(set(normalized)):
            raise ValueError("blueprint gaps must be unique")
        return normalized

    @model_validator(mode="after")
    def _identity(self) -> Self:
        _derive_identity(
            self,
            prefix="generated_blueprint",
            id_field="blueprint_id",
            digest_field="blueprint_digest",
        )
        return self


class ReviewableProjectionChangeV1Alpha1(_ProjectionContract):
    operation: ProjectionChangeOperation
    target_ref: str
    before: CanonicalJsonValueV1Alpha1 | None = None
    after: CanonicalJsonValueV1Alpha1 | None = None
    rationale: str = Field(min_length=1, max_length=2_000)
    expected_effect: ProjectionValueV1Alpha1
    requires_review: StrictBool = True
    change_id: str | None = None
    change_digest: str | None = None

    @field_validator("target_ref", "change_id")
    @classmethod
    def _references(cls, value: str | None, info) -> str | None:
        return validate_reference(value, name=info.field_name) if value is not None else None

    @field_validator("change_digest")
    @classmethod
    def _digest(cls, value: str | None) -> str | None:
        return validate_digest(value) if value is not None else None

    @model_validator(mode="after")
    def _diff_and_identity(self) -> Self:
        if self.operation is ProjectionChangeOperation.ADD and (self.before is not None or self.after is None):
            raise ValueError("an add change requires only after material")
        if self.operation is ProjectionChangeOperation.REMOVE and (self.before is None or self.after is not None):
            raise ValueError("a remove change requires only before material")
        if self.operation is ProjectionChangeOperation.UPDATE and (self.before is None or self.after is None):
            raise ValueError("an update change requires before and after material")
        if self.operation is ProjectionChangeOperation.UPDATE and self.before == self.after:
            raise ValueError("an update change must change the projected material")
        _derive_identity(self, prefix="projection_change", id_field="change_id", digest_field="change_digest")
        return self


class SourceBindingProjectionV1Alpha1(_ProjectionContract):
    binding_id: str
    selection: ProjectionMaterialReferenceV1Alpha1
    source_group_id: str
    label: str = Field(min_length=1, max_length=240)
    evidence_role: str
    source_definition_ref: str
    source_type_ref: str
    source_uri: str = Field(min_length=3, max_length=2_048)
    mapping_id: str
    subject_binding_id: str
    entity_type_id: str
    entity_ref: str
    access_requirement_label: str = Field(min_length=1, max_length=240)
    binding_state: SourceBindingState
    permission_state: PermissionReadinessState
    readiness_state: PermissionReadinessState
    capability_requirement_ids: tuple[str, ...] = Field(default_factory=tuple, max_length=256)
    authority_request_ids: tuple[str, ...] = Field(default_factory=tuple, max_length=256)
    requirements: ProjectionSupportStatementV1Alpha1

    @field_validator("binding_id", "source_definition_ref", "source_type_ref", "entity_ref")
    @classmethod
    def _references(cls, value: str, info) -> str:
        return validate_reference(value, name=info.field_name)

    @field_validator("source_group_id", "evidence_role", "mapping_id", "subject_binding_id", "entity_type_id")
    @classmethod
    def _slugs(cls, value: str, info) -> str:
        return validate_slug(value, name=info.field_name)

    @field_validator("source_uri")
    @classmethod
    def _uri(cls, value: str) -> str:
        return _trimmed(value, name="source_uri", maximum=2_048)

    @field_validator("capability_requirement_ids", "authority_request_ids")
    @classmethod
    def _requirement_ids(cls, value: tuple[str, ...], info) -> tuple[str, ...]:
        normalized = tuple(sorted(validate_slug(item, name=info.field_name) for item in value))
        if len(normalized) != len(set(normalized)):
            raise ValueError(f"{info.field_name} must be unique")
        return normalized

    @model_validator(mode="after")
    def _binding_truth_and_identity(self) -> Self:
        if self.binding_state is SourceBindingState.READY and (
            self.permission_state is not PermissionReadinessState.READY
            or self.readiness_state is not PermissionReadinessState.READY
        ):
            raise ValueError("a ready binding requires ready permission and source readiness")
        expected = f"source_binding:{canonical_hash(self.selection.model_dump(mode='json'))[:32]}"
        if self.binding_id != expected:
            raise ValueError("binding_id does not match the exact recorded source selection")
        return self


class CoverageProjectionV1Alpha1(_ProjectionContract):
    dimension: CoverageDimension
    target_ref: str
    target_label: str = Field(min_length=1, max_length=240)
    source_binding_ids: tuple[str, ...] = Field(default_factory=tuple, max_length=256)
    predicted: ProjectionValueV1Alpha1
    observed: ProjectionValueV1Alpha1

    @field_validator("target_ref")
    @classmethod
    def _target_ref(cls, value: str) -> str:
        return validate_reference(value, name="coverage target_ref")

    @field_validator("source_binding_ids")
    @classmethod
    def _binding_ids(cls, value: tuple[str, ...]) -> tuple[str, ...]:
        normalized = tuple(sorted(validate_reference(item, name="source_binding_id") for item in value))
        if len(normalized) != len(set(normalized)):
            raise ValueError("source_binding_ids must be unique")
        return normalized


class InitializationStageProjectionV1Alpha1(_ProjectionContract):
    sequence: StrictInt = Field(ge=1, le=len(INITIALIZATION_STAGE_ORDER))
    stage: InitializationStage
    state: InitializationStageState
    detail: str = Field(min_length=1, max_length=1_000)
    basis: tuple[ProjectionMaterialReferenceV1Alpha1, ...] = Field(default_factory=tuple, max_length=256)

    @field_validator("basis")
    @classmethod
    def _basis(
        cls,
        value: tuple[ProjectionMaterialReferenceV1Alpha1, ...],
    ) -> tuple[ProjectionMaterialReferenceV1Alpha1, ...]:
        return _unique_refs(value, name="initialization stage basis")

    @model_validator(mode="after")
    def _stage_truth(self) -> Self:
        if self.state in {InitializationStageState.COMPLETE, InitializationStageState.IN_PROGRESS} and not self.basis:
            raise ValueError("complete or in-progress stages require exact basis material")
        return self


class DerivationStepProjectionV1Alpha1(_ProjectionContract):
    sequence: StrictInt = Field(ge=1, le=len(DERIVATION_STEP_ORDER))
    kind: DerivationStepKind
    label: str = Field(min_length=1, max_length=500)
    record: ProjectionMaterialReferenceV1Alpha1
    supporting_evidence: tuple[ProjectionMaterialReferenceV1Alpha1, ...] = Field(
        default_factory=tuple,
        max_length=256,
    )
    conflicting_evidence: tuple[ProjectionMaterialReferenceV1Alpha1, ...] = Field(
        default_factory=tuple,
        max_length=256,
    )

    @field_validator("supporting_evidence", "conflicting_evidence")
    @classmethod
    def _evidence(
        cls,
        value: tuple[ProjectionMaterialReferenceV1Alpha1, ...],
        info,
    ) -> tuple[ProjectionMaterialReferenceV1Alpha1, ...]:
        return _unique_refs(value, name=info.field_name)


class EvidenceConclusionDerivationV1Alpha1(_ProjectionContract):
    conclusion: ProjectionMaterialReferenceV1Alpha1
    steps: tuple[DerivationStepProjectionV1Alpha1, ...] = Field(
        min_length=len(DERIVATION_STEP_ORDER),
        max_length=len(DERIVATION_STEP_ORDER),
    )
    recalculated_at: datetime
    derivation_id: str | None = None
    derivation_digest: str | None = None

    @field_validator("recalculated_at")
    @classmethod
    def _time(cls, value: datetime) -> datetime:
        return _aware(value, name="recalculated_at")

    @model_validator(mode="after")
    def _ordered_identity(self) -> Self:
        if tuple(item.sequence for item in self.steps) != tuple(range(1, len(DERIVATION_STEP_ORDER) + 1)):
            raise ValueError("derivation steps must use a contiguous sequence")
        if tuple(item.kind for item in self.steps) != DERIVATION_STEP_ORDER:
            raise ValueError("derivation steps must preserve observation-to-conclusion order")
        if self.steps[-1].record != self.conclusion:
            raise ValueError("the final derivation step must identify the exact conclusion")
        _derive_identity(
            self,
            prefix="evidence_conclusion_derivation",
            id_field="derivation_id",
            digest_field="derivation_digest",
        )
        return self


class DerivationProjectionSetV1Alpha1(_ProjectionContract):
    availability: ProjectionSupportStatementV1Alpha1
    items: tuple[EvidenceConclusionDerivationV1Alpha1, ...] = Field(default_factory=tuple, max_length=256)

    @model_validator(mode="after")
    def _availability_truth(self) -> Self:
        if self.availability.support is ProjectionSupport.UNSUPPORTED and self.items:
            raise ValueError("unsupported derivation availability cannot carry derivation items")
        if self.availability.support is not ProjectionSupport.UNSUPPORTED and not self.items:
            raise ValueError("supported derivation availability requires at least one derivation")
        return self


class DomainHealthProjectionV1Alpha1(_ProjectionContract):
    dimension: DomainHealthDimension
    value: ProjectionValueV1Alpha1


class IntelligenceSystemProjectionV1Alpha1(_ProjectionContract):
    """Truthful product projection shared by onboarding and later live consumers."""

    contract: Literal["ace.intelligence.system-projection/v1alpha1"] = INTELLIGENCE_SYSTEM_PROJECTION_VERSION
    product_id: str
    mode: ProjectionMode
    plan: ProjectionMaterialReferenceV1Alpha1
    request: ProjectionMaterialReferenceV1Alpha1
    pack: CompiledPackRefV1
    blueprint: GeneratedBlueprintProjectionV1Alpha1
    changes: tuple[ReviewableProjectionChangeV1Alpha1, ...] = Field(default_factory=tuple, max_length=1_024)
    source_bindings: tuple[SourceBindingProjectionV1Alpha1, ...] = Field(default_factory=tuple, max_length=256)
    unassigned_capability_requirement_ids: tuple[str, ...] = Field(default_factory=tuple, max_length=256)
    unassigned_authority_request_ids: tuple[str, ...] = Field(default_factory=tuple, max_length=256)
    coverage: tuple[CoverageProjectionV1Alpha1, ...] = Field(default_factory=tuple, max_length=768)
    initialization: tuple[InitializationStageProjectionV1Alpha1, ...] = Field(
        min_length=len(INITIALIZATION_STAGE_ORDER),
        max_length=len(INITIALIZATION_STAGE_ORDER),
    )
    derivations: DerivationProjectionSetV1Alpha1
    domain_health: tuple[DomainHealthProjectionV1Alpha1, ...] = Field(
        min_length=len(DOMAIN_HEALTH_DIMENSION_ORDER),
        max_length=len(DOMAIN_HEALTH_DIMENSION_ORDER),
    )
    activation_revision: ActivationRevisionReferenceV1Alpha1 | None = None
    generated_at: datetime
    gaps: tuple[str, ...] = Field(default_factory=tuple, max_length=256)
    projection_id: str | None = None
    projection_digest: str | None = None

    @field_validator("product_id")
    @classmethod
    def _product(cls, value: str) -> str:
        return validate_product_id(value)

    @field_validator("generated_at")
    @classmethod
    def _time(cls, value: datetime) -> datetime:
        return _aware(value, name="generated_at")

    @field_validator("changes")
    @classmethod
    def _changes(
        cls,
        value: tuple[ReviewableProjectionChangeV1Alpha1, ...],
    ) -> tuple[ReviewableProjectionChangeV1Alpha1, ...]:
        ids = [item.change_id for item in value]
        if len(ids) != len(set(ids)):
            raise ValueError("reviewable changes must use unique identities")
        targets = [item.target_ref for item in value]
        if len(targets) != len(set(targets)):
            raise ValueError("reviewable changes must name each target at most once")
        return tuple(sorted(value, key=lambda item: str(item.change_id)))

    @field_validator("source_bindings")
    @classmethod
    def _source_bindings(
        cls,
        value: tuple[SourceBindingProjectionV1Alpha1, ...],
    ) -> tuple[SourceBindingProjectionV1Alpha1, ...]:
        ids = [item.binding_id for item in value]
        if len(ids) != len(set(ids)):
            raise ValueError("source bindings must use unique identities")
        return tuple(sorted(value, key=lambda item: item.binding_id))

    @field_validator("unassigned_capability_requirement_ids", "unassigned_authority_request_ids")
    @classmethod
    def _unassigned_ids(cls, value: tuple[str, ...], info) -> tuple[str, ...]:
        normalized = tuple(sorted(validate_slug(item, name=info.field_name) for item in value))
        if len(normalized) != len(set(normalized)):
            raise ValueError(f"{info.field_name} must be unique")
        return normalized

    @field_validator("coverage")
    @classmethod
    def _coverage(
        cls,
        value: tuple[CoverageProjectionV1Alpha1, ...],
    ) -> tuple[CoverageProjectionV1Alpha1, ...]:
        keys = [(item.dimension.value, item.target_ref) for item in value]
        if len(keys) != len(set(keys)):
            raise ValueError("coverage rows must be unique by dimension and target")
        return tuple(sorted(value, key=lambda item: (item.dimension.value, item.target_ref)))

    @field_validator("gaps")
    @classmethod
    def _gaps(cls, value: tuple[str, ...]) -> tuple[str, ...]:
        normalized = tuple(sorted(_trimmed(item, name="projection gap", maximum=1_000) for item in value))
        if len(normalized) != len(set(normalized)):
            raise ValueError("projection gaps must be unique")
        return normalized

    @model_validator(mode="after")
    def _cross_contract_truth_and_identity(self) -> Self:
        if (
            self.blueprint.plan != self.plan
            or self.blueprint.request != self.request
            or self.blueprint.pack != self.pack
        ):
            raise ValueError("blueprint crossed the exact projection plan, request, or Pack")
        elements = {str(item.element_ref): item for item in self.blueprint.elements}
        for change in self.changes:
            if change.operation is ProjectionChangeOperation.REMOVE:
                if change.target_ref in elements:
                    raise ValueError("a removed change target cannot remain in the generated blueprint")
                continue
            element = elements.get(change.target_ref)
            if element is None:
                raise ValueError("added or updated change targets must exist in the generated blueprint")
            expected_after = CanonicalJsonValueV1Alpha1(value_json=canonical_json(element.model_dump(mode="json")))
            if change.after != expected_after:
                raise ValueError("change after material must equal the exact generated blueprint element")
        binding_ids = {item.binding_id for item in self.source_bindings}
        if any(not set(item.source_binding_ids).issubset(binding_ids) for item in self.coverage):
            raise ValueError("coverage rows crossed exact source bindings")
        expected_kind = {
            CoverageDimension.ENTITY: BlueprintElementKind.ENTITY,
            CoverageDimension.EVENT: BlueprintElementKind.EVENT,
            CoverageDimension.SIGNAL: BlueprintElementKind.SIGNAL,
        }
        if any(
            item.target_ref not in elements or elements[item.target_ref].kind is not expected_kind[item.dimension]
            for item in self.coverage
        ):
            raise ValueError("coverage targets must match blueprint entity, event, or signal elements")
        expected_coverage = {
            (dimension.value, element_ref)
            for element_ref, element in elements.items()
            for kind, dimension in (
                (BlueprintElementKind.ENTITY, CoverageDimension.ENTITY),
                (BlueprintElementKind.EVENT, CoverageDimension.EVENT),
                (BlueprintElementKind.SIGNAL, CoverageDimension.SIGNAL),
            )
            if element.kind is kind
        }
        actual_coverage = {(item.dimension.value, item.target_ref) for item in self.coverage}
        if actual_coverage != expected_coverage:
            raise ValueError("coverage must include every blueprint entity, event, and signal exactly once")
        if tuple(item.sequence for item in self.initialization) != tuple(range(1, len(INITIALIZATION_STAGE_ORDER) + 1)):
            raise ValueError("initialization stages must use a contiguous sequence")
        if tuple(item.stage for item in self.initialization) != INITIALIZATION_STAGE_ORDER:
            raise ValueError("initialization stages must preserve the canonical Builder order")
        unfinished_seen = False
        in_progress_count = 0
        for item in self.initialization:
            if item.state is InitializationStageState.COMPLETE:
                if unfinished_seen:
                    raise ValueError("complete initialization stages must form a contiguous prefix")
            else:
                unfinished_seen = True
            if item.state is InitializationStageState.IN_PROGRESS:
                in_progress_count += 1
        if in_progress_count > 1:
            raise ValueError("at most one initialization stage may be in progress")
        if tuple(item.dimension for item in self.domain_health) != DOMAIN_HEALTH_DIMENSION_ORDER:
            raise ValueError("Domain Health must include all eight dimensions in canonical order")
        if self.mode is ProjectionMode.LIVE:
            if self.activation_revision is None:
                raise ValueError("a live projection requires its exact bound activation revision")
            if self.activation_revision.product_id != self.product_id:
                raise ValueError("activation revision crossed the exact projection product")
        elif self.activation_revision is not None:
            raise ValueError("only a live projection may carry a bound activation revision")
        _derive_identity(
            self,
            prefix="intelligence_system_projection",
            id_field="projection_id",
            digest_field="projection_digest",
        )
        return self

    @property
    def reusable_authority(self) -> Literal[False]:
        return False


__all__ = [
    "BlueprintElementKind",
    "CoverageDimension",
    "CoverageProjectionV1Alpha1",
    "DERIVATION_STEP_ORDER",
    "DOMAIN_HEALTH_DIMENSION_ORDER",
    "DerivationProjectionSetV1Alpha1",
    "DerivationStepKind",
    "DerivationStepProjectionV1Alpha1",
    "DomainHealthDimension",
    "DomainHealthProjectionV1Alpha1",
    "EvidenceConclusionDerivationV1Alpha1",
    "GeneratedBlueprintProjectionV1Alpha1",
    "INITIALIZATION_STAGE_ORDER",
    "INTELLIGENCE_SYSTEM_PROJECTION_VERSION",
    "InitializationStage",
    "InitializationStageProjectionV1Alpha1",
    "InitializationStageState",
    "IntelligenceSystemProjectionV1Alpha1",
    "PROJECTION_MATERIAL_REFERENCE_VERSION",
    "PermissionReadinessState",
    "ProjectionChangeOperation",
    "ProjectionMaterialReferenceV1Alpha1",
    "ProjectionMode",
    "ProjectionSupport",
    "ProjectionSupportStatementV1Alpha1",
    "ProjectionValueV1Alpha1",
    "ReviewableProjectionChangeV1Alpha1",
    "SourceBindingProjectionV1Alpha1",
    "SourceBindingState",
]
