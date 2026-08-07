"""Durable Intelligence resource-admission and attention receipt contracts."""

from __future__ import annotations

from datetime import UTC, datetime
from enum import StrEnum
from typing import Literal, Self, TypeAlias

from pydantic import ConfigDict, Field, field_validator, model_validator

from ace.core.contracts import FrozenContract, canonical_hash
from ace.intelligence.contracts.activation import CompiledPackRefV1
from ace.intelligence.contracts.common import (
    validate_digest,
    validate_product_id,
    validate_reference,
    validate_slug,
)
from ace.intelligence.contracts.resources import (
    ActivationRevisionReferenceV1Alpha1,
    BriefV1Alpha1,
    CaseV1Alpha1,
    EntitySnapshotV1Alpha1,
    IntelligenceResourceMode,
    ObservationV1Alpha1,
    ShiftV1Alpha1,
    SignalV1Alpha1,
)

INTELLIGENCE_RECORD_REFERENCE_VERSION = "ace.intelligence.intelligence-record-reference/v1alpha1"
PREPARED_RESOURCE_ADMISSION_VERSION = "ace.intelligence.prepared-resource-admission/v1alpha1"
PREPARED_RESOURCE_SET_ADMISSION_VERSION = "ace.intelligence.prepared-resource-set-admission/v1alpha1"
ATTENTION_DISPOSITION_RECEIPT_VERSION = "ace.intelligence.attention-disposition-receipt/v1alpha1"


class _StrictFrozenContract(FrozenContract):
    model_config = ConfigDict(
        extra="forbid",
        frozen=True,
        strict=True,
        revalidate_instances="always",
        validate_default=True,
        allow_inf_nan=False,
    )


class IntelligenceRecordKind(StrEnum):
    """Persisted record families in the bounded PREPARED ledger slice."""

    OBSERVATION = "observation"
    ENTITY_SNAPSHOT = "entity_snapshot"
    SHIFT = "shift"
    SIGNAL = "signal"
    CASE = "case"
    BRIEF = "brief"
    ATTENTION_DISPOSITION = "attention_disposition"


class AttentionDisposition(StrEnum):
    ROUTE = "route"
    SUPPRESSED = "suppressed"


class AttentionSuppressionReason(StrEnum):
    NO_ELIGIBLE_ROUTE = "no_eligible_route"


PreparedResourceV1Alpha1: TypeAlias = (
    ObservationV1Alpha1 | EntitySnapshotV1Alpha1 | ShiftV1Alpha1 | SignalV1Alpha1 | CaseV1Alpha1 | BriefV1Alpha1
)


def _aware(value: datetime, name: str) -> datetime:
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError(f"{name} must include a timezone")
    return value.astimezone(UTC)


def resource_kind(resource: PreparedResourceV1Alpha1) -> IntelligenceRecordKind:
    if isinstance(resource, ObservationV1Alpha1):
        return IntelligenceRecordKind.OBSERVATION
    if isinstance(resource, EntitySnapshotV1Alpha1):
        return IntelligenceRecordKind.ENTITY_SNAPSHOT
    if isinstance(resource, ShiftV1Alpha1):
        return IntelligenceRecordKind.SHIFT
    if isinstance(resource, SignalV1Alpha1):
        return IntelligenceRecordKind.SIGNAL
    if isinstance(resource, CaseV1Alpha1):
        return IntelligenceRecordKind.CASE
    if isinstance(resource, BriefV1Alpha1):
        return IntelligenceRecordKind.BRIEF
    raise TypeError("unsupported Intelligence resource contract")


def resource_available_at(resource: PreparedResourceV1Alpha1) -> datetime:
    if isinstance(resource, ObservationV1Alpha1):
        return resource.ingested_at
    if isinstance(resource, EntitySnapshotV1Alpha1):
        return resource.projected_at
    if isinstance(resource, (ShiftV1Alpha1, SignalV1Alpha1)):
        return resource.detected_at
    if isinstance(resource, CaseV1Alpha1):
        return resource.assembled_at
    if isinstance(resource, BriefV1Alpha1):
        return resource.generated_at
    raise TypeError("unsupported Intelligence resource contract")


class IntelligenceRecordReferenceV1Alpha1(_StrictFrozenContract):
    """Exact Intelligence-owned coordinates for replay and historical reads."""

    contract: Literal["ace.intelligence.intelligence-record-reference/v1alpha1"] = INTELLIGENCE_RECORD_REFERENCE_VERSION
    product_id: str
    mode: IntelligenceResourceMode
    resource_kind: IntelligenceRecordKind
    resource_id: str
    resource_digest: str
    resource_contract: str
    as_of: datetime
    available_at: datetime

    @field_validator("product_id")
    @classmethod
    def validate_product_scope(cls, value: str) -> str:
        return validate_product_id(value)

    @field_validator("resource_id", "resource_contract")
    @classmethod
    def validate_refs(cls, value: str, info) -> str:
        return validate_reference(value, name=info.field_name)

    @field_validator("resource_digest")
    @classmethod
    def validate_resource_digest(cls, value: str) -> str:
        return validate_digest(value)

    @field_validator("as_of", "available_at")
    @classmethod
    def normalize_times(cls, value: datetime, info) -> datetime:
        return _aware(value, info.field_name)

    @model_validator(mode="after")
    def validate_exact_reference(self) -> Self:
        if self.available_at < self.as_of:
            raise ValueError("record reference availability cannot precede its as_of cutoff")
        expected_prefix = f"{self.resource_kind.value}:"
        if not self.resource_id.startswith(expected_prefix):
            raise ValueError("record kind and resource identity prefix do not match")
        expected_id = f"{self.resource_kind.value}:{self.resource_digest.removeprefix('sha256:')[:32]}"
        if self.resource_id != expected_id:
            raise ValueError("record resource_id and digest do not identify the same material")
        return self


def resource_reference(
    resource: PreparedResourceV1Alpha1,
) -> IntelligenceRecordReferenceV1Alpha1:
    if resource.resource_id is None or resource.resource_digest is None:
        raise ValueError("resource is missing its exact content identity")
    return IntelligenceRecordReferenceV1Alpha1(
        product_id=resource.product_id,
        mode=resource.mode,
        resource_kind=resource_kind(resource),
        resource_id=resource.resource_id,
        resource_digest=resource.resource_digest,
        resource_contract=resource.contract,
        as_of=resource.as_of,
        available_at=resource_available_at(resource),
    )


def deterministic_resource_order(
    resources: tuple[PreparedResourceV1Alpha1, ...],
) -> tuple[IntelligenceRecordReferenceV1Alpha1, ...]:
    """Return a stable topological order using exact in-batch lineage edges."""

    by_id = {str(resource.resource_id): resource for resource in resources}
    if len(by_id) != len(resources):
        raise ValueError("resource identities must be present and unique")
    dependencies = {
        resource_id: {lineage.resource_id for lineage in resource.lineage if lineage.resource_id in by_id}
        for resource_id, resource in by_id.items()
    }
    ordered: list[PreparedResourceV1Alpha1] = []
    remaining = set(by_id)
    while remaining:
        ready = [by_id[resource_id] for resource_id in remaining if dependencies[resource_id].isdisjoint(remaining)]
        if not ready:
            raise ValueError("resource lineage contains an in-batch cycle")
        ready.sort(
            key=lambda resource: (
                resource_available_at(resource),
                resource_kind(resource).value,
                str(resource.resource_id),
            )
        )
        for resource in ready:
            ordered.append(resource)
            remaining.remove(str(resource.resource_id))
    return tuple(resource_reference(resource) for resource in ordered)


class AttentionDispositionReceiptV1Alpha1(_StrictFrozenContract):
    """Durable mode-bound route-or-suppression evaluation; never delivery."""

    contract: Literal["ace.intelligence.attention-disposition-receipt/v1alpha1"] = ATTENTION_DISPOSITION_RECEIPT_VERSION
    receipt_kind: Literal["attention_disposition"] = "attention_disposition"
    delivery_authority: Literal[False] = False
    product_id: str
    mode: IntelligenceResourceMode = IntelligenceResourceMode.PREPARED
    activation_revision: ActivationRevisionReferenceV1Alpha1
    pack: CompiledPackRefV1
    signal: IntelligenceRecordReferenceV1Alpha1
    source_lineage: tuple[IntelligenceRecordReferenceV1Alpha1, ...] = Field(default_factory=tuple, max_length=256)
    disposition: AttentionDisposition
    routing_rule_id: str | None = None
    suppression_reason: AttentionSuppressionReason | None = None
    persona_ids: tuple[str, ...] = Field(default_factory=tuple, max_length=256)
    brief_template_id: str | None = None
    evaluated_at: datetime
    receipt_id: str | None = None
    receipt_digest: str | None = None

    @field_validator("product_id")
    @classmethod
    def validate_product_scope(cls, value: str) -> str:
        return validate_product_id(value)

    @field_validator("routing_rule_id", "brief_template_id")
    @classmethod
    def validate_optional_slugs(cls, value: str | None, info) -> str | None:
        return validate_slug(value, name=info.field_name) if value is not None else None

    @field_validator("persona_ids")
    @classmethod
    def normalize_personas(cls, value: tuple[str, ...]) -> tuple[str, ...]:
        validated = tuple(validate_slug(item, name="persona_id") for item in value)
        if len(validated) != len(set(validated)):
            raise ValueError("attention personas must be unique")
        return tuple(sorted(validated))

    @field_validator("source_lineage")
    @classmethod
    def normalize_source_lineage(
        cls, value: tuple[IntelligenceRecordReferenceV1Alpha1, ...]
    ) -> tuple[IntelligenceRecordReferenceV1Alpha1, ...]:
        ids = [item.resource_id for item in value]
        if len(ids) != len(set(ids)):
            raise ValueError("attention source lineage must use unique exact records")
        return tuple(sorted(value, key=lambda item: (item.resource_kind.value, item.resource_id)))

    @field_validator("evaluated_at")
    @classmethod
    def normalize_evaluated_at(cls, value: datetime) -> datetime:
        return _aware(value, "evaluated_at")

    @model_validator(mode="after")
    def validate_disposition_and_identity(self) -> Self:
        if self.activation_revision.product_id != self.product_id:
            raise ValueError("attention activation crossed the receipt product scope")
        if (
            self.signal.product_id != self.product_id
            or self.signal.mode is not self.mode
            or self.signal.resource_kind is not IntelligenceRecordKind.SIGNAL
        ):
            raise ValueError("attention receipt must bind one exact same-mode Signal")
        if any(item.product_id != self.product_id or item.mode is not self.mode for item in self.source_lineage):
            raise ValueError("attention source lineage crossed product or mode scope")
        if any(item.available_at > self.evaluated_at for item in (self.signal, *self.source_lineage)):
            raise ValueError("attention cannot evaluate unavailable source records")
        if self.disposition is AttentionDisposition.ROUTE:
            if self.routing_rule_id is None or self.suppression_reason is not None or not self.persona_ids:
                raise ValueError("a route requires one routing rule, personas, and no suppression reason")
        elif (
            self.routing_rule_id is not None
            or self.suppression_reason is None
            or self.persona_ids
            or self.brief_template_id is not None
        ):
            raise ValueError("suppression requires only an explicit suppression reason")

        material = self.model_dump(mode="json", exclude={"receipt_id", "receipt_digest"})
        digest = canonical_hash(material)
        expected_id = f"attention_disposition:{digest[:32]}"
        expected_digest = f"sha256:{digest}"
        if self.receipt_id is not None and self.receipt_id != expected_id:
            raise ValueError("attention receipt identity does not match exact evaluation material")
        if self.receipt_digest is not None and self.receipt_digest != expected_digest:
            raise ValueError("attention receipt digest does not match exact evaluation material")
        object.__setattr__(self, "receipt_id", expected_id)
        object.__setattr__(self, "receipt_digest", expected_digest)
        return self

    def record_reference(self) -> IntelligenceRecordReferenceV1Alpha1:
        return IntelligenceRecordReferenceV1Alpha1(
            product_id=self.product_id,
            mode=self.mode,
            resource_kind=IntelligenceRecordKind.ATTENTION_DISPOSITION,
            resource_id=str(self.receipt_id),
            resource_digest=str(self.receipt_digest),
            resource_contract=self.contract,
            as_of=self.signal.as_of,
            available_at=self.evaluated_at,
        )


class PreparedResourceAdmissionV1Alpha1(_StrictFrozenContract):
    """One exact PREPARED derivation to validate and append atomically."""

    contract: Literal["ace.intelligence.prepared-resource-admission/v1alpha1"] = PREPARED_RESOURCE_ADMISSION_VERSION
    derivation_key: str
    product_id: str
    mode: Literal[IntelligenceResourceMode.PREPARED] = IntelligenceResourceMode.PREPARED
    activation_revision: ActivationRevisionReferenceV1Alpha1
    pack: CompiledPackRefV1
    observations: tuple[ObservationV1Alpha1, ...] = Field(min_length=1, max_length=256)
    entity_snapshots: tuple[EntitySnapshotV1Alpha1, ...] = Field(min_length=1, max_length=256)
    shift: ShiftV1Alpha1
    signal: SignalV1Alpha1
    brief: BriefV1Alpha1 | None = None
    processing_order: tuple[IntelligenceRecordReferenceV1Alpha1, ...] = Field(min_length=4, max_length=515)
    attention_evaluated_at: datetime
    batch_id: str | None = None
    batch_digest: str | None = None

    @field_validator("derivation_key")
    @classmethod
    def validate_derivation_key(cls, value: str) -> str:
        return validate_reference(value, name="derivation_key")

    @field_validator("product_id")
    @classmethod
    def validate_product_scope(cls, value: str) -> str:
        return validate_product_id(value)

    @field_validator("attention_evaluated_at")
    @classmethod
    def normalize_evaluated_at(cls, value: datetime) -> datetime:
        return _aware(value, "attention_evaluated_at")

    def resources(self) -> tuple[PreparedResourceV1Alpha1, ...]:
        optional_brief: tuple[PreparedResourceV1Alpha1, ...] = (self.brief,) if self.brief is not None else ()
        return (*self.observations, *self.entity_snapshots, self.shift, self.signal, *optional_brief)

    @model_validator(mode="after")
    def validate_exact_batch(self) -> Self:
        if self.activation_revision.product_id != self.product_id:
            raise ValueError("batch activation crossed the product scope")
        resources = self.resources()
        if any(resource.product_id != self.product_id for resource in resources):
            raise ValueError("every resource must use the batch product scope")
        if any(resource.mode is not IntelligenceResourceMode.PREPARED for resource in resources):
            raise ValueError("durable prepared admission rejects LIVE resources")
        if any(resource.activation_revision != self.activation_revision for resource in resources):
            raise ValueError("every resource must use the exact batch activation revision")
        if any(resource_available_at(resource) > self.attention_evaluated_at for resource in resources):
            raise ValueError("admission and attention evaluation cannot predate resource availability")
        expected_order = deterministic_resource_order(resources)
        if self.processing_order != expected_order:
            raise ValueError("processing_order must equal the deterministic exact DAG order")

        material = self.model_dump(mode="json", exclude={"batch_id", "batch_digest"})
        digest = canonical_hash(material)
        expected_id = f"resource_admission:{canonical_hash([self.product_id, self.derivation_key])[:32]}"
        expected_digest = f"sha256:{digest}"
        if self.batch_id is not None and self.batch_id != expected_id:
            raise ValueError("batch_id does not match the stable derivation scope")
        if self.batch_digest is not None and self.batch_digest != expected_digest:
            raise ValueError("batch_digest does not match the exact admission material")
        object.__setattr__(self, "batch_id", expected_id)
        object.__setattr__(self, "batch_digest", expected_digest)
        return self


class PreparedResourceSetAdmissionV1Alpha1(_StrictFrozenContract):
    """One exact PREPARED resource DAG admitted without forcing attention.

    This additive contract preserves the independence of Observation, Entity
    Snapshot, Shift, Signal, and Brief resources. Routing remains a separate
    operation: callers that need a durable attention disposition continue to
    use ``PreparedResourceAdmissionV1Alpha1``.
    """

    contract: Literal["ace.intelligence.prepared-resource-set-admission/v1alpha1"] = (
        PREPARED_RESOURCE_SET_ADMISSION_VERSION
    )
    admission_key: str
    product_id: str
    mode: Literal[IntelligenceResourceMode.PREPARED] = IntelligenceResourceMode.PREPARED
    activation_revision: ActivationRevisionReferenceV1Alpha1
    pack: CompiledPackRefV1
    resources: tuple[PreparedResourceV1Alpha1, ...] = Field(min_length=1, max_length=515)
    processing_order: tuple[IntelligenceRecordReferenceV1Alpha1, ...] = Field(min_length=1, max_length=515)
    admitted_at: datetime
    admission_id: str | None = None
    admission_digest: str | None = None

    @field_validator("admission_key")
    @classmethod
    def validate_admission_key(cls, value: str) -> str:
        return validate_reference(value, name="admission_key")

    @field_validator("product_id")
    @classmethod
    def validate_product_scope(cls, value: str) -> str:
        return validate_product_id(value)

    @field_validator("admitted_at")
    @classmethod
    def normalize_admitted_at(cls, value: datetime) -> datetime:
        return _aware(value, "admitted_at")

    @model_validator(mode="after")
    def validate_exact_resource_set(self) -> Self:
        if self.activation_revision.product_id != self.product_id:
            raise ValueError("resource-set activation crossed the product scope")
        if any(resource.product_id != self.product_id for resource in self.resources):
            raise ValueError("every resource must use the resource-set product scope")
        if any(resource.mode is not IntelligenceResourceMode.PREPARED for resource in self.resources):
            raise ValueError("durable prepared resource-set admission rejects LIVE resources")
        if any(resource.activation_revision != self.activation_revision for resource in self.resources):
            raise ValueError("every resource must use the exact resource-set activation revision")
        if any(resource_available_at(resource) > self.admitted_at for resource in self.resources):
            raise ValueError("resource-set admission cannot predate resource availability")
        expected_order = deterministic_resource_order(self.resources)
        if self.processing_order != expected_order:
            raise ValueError("processing_order must equal the deterministic exact DAG order")

        material = self.model_dump(mode="json", exclude={"admission_id", "admission_digest"})
        digest = canonical_hash(material)
        expected_id = f"resource_set_admission:{canonical_hash([self.product_id, self.admission_key])[:32]}"
        expected_digest = f"sha256:{digest}"
        if self.admission_id is not None and self.admission_id != expected_id:
            raise ValueError("admission_id does not match the stable resource-set scope")
        if self.admission_digest is not None and self.admission_digest != expected_digest:
            raise ValueError("admission_digest does not match the exact resource-set material")
        object.__setattr__(self, "admission_id", expected_id)
        object.__setattr__(self, "admission_digest", expected_digest)
        return self


__all__ = [
    "ATTENTION_DISPOSITION_RECEIPT_VERSION",
    "INTELLIGENCE_RECORD_REFERENCE_VERSION",
    "PREPARED_RESOURCE_ADMISSION_VERSION",
    "PREPARED_RESOURCE_SET_ADMISSION_VERSION",
    "AttentionDisposition",
    "AttentionDispositionReceiptV1Alpha1",
    "AttentionSuppressionReason",
    "IntelligenceRecordKind",
    "IntelligenceRecordReferenceV1Alpha1",
    "PreparedResourceAdmissionV1Alpha1",
    "PreparedResourceSetAdmissionV1Alpha1",
    "PreparedResourceV1Alpha1",
    "deterministic_resource_order",
    "resource_available_at",
    "resource_kind",
    "resource_reference",
]
