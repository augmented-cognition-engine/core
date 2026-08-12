"""Unified, domain-neutral query contracts for the ACE Intelligence resource plane.

The resource plane is a read model over authoritative Core state and rebuildable
Intelligence projections.  It does not grant authority, acquire sources, execute
effects, or become another persistence engine.
"""

from __future__ import annotations

from datetime import UTC, datetime
from enum import StrEnum
from typing import Literal, Self

from pydantic import ConfigDict, Field, StrictInt, field_validator, model_validator

from ace.core.contracts import FrozenContract, canonical_hash
from ace.core.runtime_use import AuthenticatedRuntimeContextV1Alpha1, AuthorityUseReceiptV1Alpha1
from ace.intelligence.contracts.common import (
    validate_contract,
    validate_digest,
    validate_product_id,
    validate_reference,
)
from ace.intelligence.contracts.resources import CanonicalJsonValueV1Alpha1

RESOURCE_PLANE_QUERY_VERSION = "ace.intelligence.resource-plane-query/v1alpha1"
RESOURCE_PLANE_CURSOR_VERSION = "ace.intelligence.resource-plane-cursor/v1alpha1"
RESOURCE_PLANE_REFERENCE_VERSION = "ace.intelligence.resource-plane-reference/v1alpha1"
RESOURCE_PLANE_RECORD_VERSION = "ace.intelligence.resource-plane-record/v1alpha1"
RESOURCE_PLANE_PAGE_VERSION = "ace.intelligence.resource-plane-page/v1alpha1"

MAX_RESOURCE_PLANE_KINDS = 32
MAX_RESOURCE_PLANE_SUBJECTS = 256
MAX_RESOURCE_PLANE_PROVENANCE = 256
MAX_RESOURCE_PLANE_PAGE_SIZE = 200


class _StrictFrozenContract(FrozenContract):
    model_config = ConfigDict(
        extra="forbid",
        frozen=True,
        strict=True,
        revalidate_instances="always",
        validate_default=True,
        allow_inf_nan=False,
    )


def _aware(value: datetime, *, name: str) -> datetime:
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError(f"{name} must include a timezone")
    return value.astimezone(UTC)


def _unique_references(values: tuple[str, ...], *, name: str) -> tuple[str, ...]:
    normalized = tuple(sorted(validate_reference(value, name=name) for value in values))
    if len(normalized) != len(set(normalized)):
        raise ValueError(f"{name} must be unique")
    return normalized


def _derive_identity(instance: _StrictFrozenContract, *, prefix: str, id_field: str, digest_field: str) -> None:
    material = instance.model_dump(mode="json", exclude={id_field, digest_field})
    digest = canonical_hash(material)
    expected_id = f"{prefix}:{digest[:32]}"
    expected_digest = f"sha256:{digest}"
    if getattr(instance, id_field) not in {None, expected_id}:
        raise ValueError(f"{id_field} does not match exact contract material")
    if getattr(instance, digest_field) not in {None, expected_digest}:
        raise ValueError(f"{digest_field} does not match exact contract material")
    object.__setattr__(instance, id_field, expected_id)
    object.__setattr__(instance, digest_field, expected_digest)


class IntelligenceResourceKind(StrEnum):
    """Stable domain-neutral families rendered by Atrium and machine consumers."""

    CONNECTION = "connection"
    SOURCE = "source"
    SOURCE_HEALTH = "source_health"
    ENTITY = "entity"
    OBSERVATION = "observation"
    SIGNAL = "signal"
    SHIFT = "shift"
    CASE = "case"
    BRIEF = "brief"
    MONITOR = "monitor"
    SUBSCRIPTION = "subscription"
    AGENT = "agent"
    DECISION = "decision"
    ACTION = "action"
    OUTCOME = "outcome"
    FEEDBACK = "feedback"
    EVIDENCE_LINEAGE = "evidence_lineage"
    UNCERTAINTY = "uncertainty"
    CONFLICT = "conflict"
    SEMANTIC_REVISION = "semantic_revision"
    CONTEXT_MANIFEST = "context_manifest"
    MEMORY_USE = "memory_use"


class IntelligenceResourceAvailability(StrEnum):
    AVAILABLE = "available"
    DEGRADED = "degraded"
    TOMBSTONED = "tombstoned"


class IntelligenceResourcePageState(StrEnum):
    COMPLETE = "complete"
    DEGRADED = "degraded"


class IntelligenceResourceReferenceV1Alpha1(_StrictFrozenContract):
    """Exact reference to one projected resource revision."""

    contract: Literal["ace.intelligence.resource-plane-reference/v1alpha1"] = RESOURCE_PLANE_REFERENCE_VERSION
    product_id: str
    resource_kind: IntelligenceResourceKind
    resource_id: str
    resource_digest: str
    resource_contract: str
    revision: StrictInt = Field(ge=1)
    as_of: datetime
    available_at: datetime

    @field_validator("product_id")
    @classmethod
    def validate_scope(cls, value: str) -> str:
        return validate_product_id(value)

    @field_validator("resource_id")
    @classmethod
    def validate_id(cls, value: str) -> str:
        return validate_reference(value, name="resource_id")

    @field_validator("resource_digest")
    @classmethod
    def validate_resource_digest(cls, value: str) -> str:
        return validate_digest(value)

    @field_validator("resource_contract")
    @classmethod
    def validate_resource_contract(cls, value: str) -> str:
        return validate_contract(value)

    @field_validator("as_of", "available_at")
    @classmethod
    def normalize_times(cls, value: datetime, info) -> datetime:
        return _aware(value, name=info.field_name)

    @model_validator(mode="after")
    def validate_availability(self) -> Self:
        if self.available_at < self.as_of:
            raise ValueError("resource available_at cannot precede as_of")
        return self


class IntelligenceResourceRecordV1Alpha1(_StrictFrozenContract):
    """One rebuildable public projection with exact provenance and revision lineage."""

    contract: Literal["ace.intelligence.resource-plane-record/v1alpha1"] = RESOURCE_PLANE_RECORD_VERSION
    reference: IntelligenceResourceReferenceV1Alpha1
    availability: IntelligenceResourceAvailability
    title: str = Field(min_length=1, max_length=300)
    summary: str | None = Field(default=None, min_length=1, max_length=4_000)
    subject_refs: tuple[str, ...] = Field(default_factory=tuple, max_length=MAX_RESOURCE_PLANE_SUBJECTS)
    provenance: tuple[IntelligenceResourceReferenceV1Alpha1, ...] = Field(
        default_factory=tuple,
        max_length=MAX_RESOURCE_PLANE_PROVENANCE,
    )
    supersedes: IntelligenceResourceReferenceV1Alpha1 | None = None
    payload: CanonicalJsonValueV1Alpha1 | None = None
    degraded_reason_refs: tuple[str, ...] = Field(default_factory=tuple, max_length=64)

    @field_validator("subject_refs", "degraded_reason_refs")
    @classmethod
    def normalize_refs(cls, value: tuple[str, ...], info) -> tuple[str, ...]:
        return _unique_references(value, name=info.field_name)

    @field_validator("provenance")
    @classmethod
    def normalize_provenance(
        cls,
        value: tuple[IntelligenceResourceReferenceV1Alpha1, ...],
    ) -> tuple[IntelligenceResourceReferenceV1Alpha1, ...]:
        keys = [(item.resource_kind.value, item.resource_id, item.revision, item.resource_digest) for item in value]
        if len(keys) != len(set(keys)):
            raise ValueError("provenance references must be unique")
        return tuple(sorted(value, key=lambda item: (item.resource_kind.value, item.resource_id, item.revision)))

    @model_validator(mode="after")
    def validate_projection(self) -> Self:
        for item in self.provenance:
            if item.product_id != self.reference.product_id:
                raise ValueError("resource provenance crossed product scope")
            if item.as_of > self.reference.as_of or item.available_at > self.reference.available_at:
                raise ValueError("resource provenance was not available at the projected revision")
        if self.supersedes is not None:
            if (
                self.supersedes.product_id != self.reference.product_id
                or self.supersedes.resource_kind is not self.reference.resource_kind
                or self.supersedes.resource_id != self.reference.resource_id
                or self.supersedes.revision != self.reference.revision - 1
            ):
                raise ValueError("supersedes must identify the immediately previous revision of the same resource")
        if self.availability is IntelligenceResourceAvailability.AVAILABLE and self.degraded_reason_refs:
            raise ValueError("an available resource cannot declare degraded reasons")
        if self.availability is IntelligenceResourceAvailability.DEGRADED and not self.degraded_reason_refs:
            raise ValueError("a degraded resource requires explicit reason references")
        if self.availability is IntelligenceResourceAvailability.TOMBSTONED and self.payload is not None:
            raise ValueError("a tombstoned projection cannot expose payload material")
        return self


class IntelligenceResourceCursorV1Alpha1(_StrictFrozenContract):
    """Content-addressed pagination position; explicitly not reusable authority."""

    contract: Literal["ace.intelligence.resource-plane-cursor/v1alpha1"] = RESOURCE_PLANE_CURSOR_VERSION
    query_id: str
    after_available_at: datetime
    after_resource_kind: IntelligenceResourceKind
    after_resource_id: str
    after_revision: StrictInt = Field(ge=1)
    cursor_id: str | None = None
    cursor_digest: str | None = None

    @field_validator("query_id", "after_resource_id")
    @classmethod
    def validate_refs(cls, value: str, info) -> str:
        return validate_reference(value, name=info.field_name)

    @field_validator("after_available_at")
    @classmethod
    def normalize_after(cls, value: datetime) -> datetime:
        return _aware(value, name="after_available_at")

    @field_validator("cursor_digest")
    @classmethod
    def validate_optional_digest(cls, value: str | None) -> str | None:
        return validate_digest(value) if value is not None else None

    @model_validator(mode="after")
    def derive_identity(self) -> Self:
        _derive_identity(self, prefix="resource_cursor", id_field="cursor_id", digest_field="cursor_digest")
        return self

    @property
    def reusable_authority(self) -> Literal[False]:
        return False


class IntelligenceResourceQueryV1Alpha1(_StrictFrozenContract):
    """One authenticated, product-scoped, point-in-time resource query."""

    contract: Literal["ace.intelligence.resource-plane-query/v1alpha1"] = RESOURCE_PLANE_QUERY_VERSION
    authenticated_context: AuthenticatedRuntimeContextV1Alpha1
    product_id: str
    authority_grant_ref: str
    resource_kinds: tuple[IntelligenceResourceKind, ...] = Field(
        min_length=1,
        max_length=MAX_RESOURCE_PLANE_KINDS,
    )
    subject_refs: tuple[str, ...] = Field(default_factory=tuple, max_length=MAX_RESOURCE_PLANE_SUBJECTS)
    as_of: datetime
    available_at: datetime
    page_size: StrictInt = Field(ge=1, le=MAX_RESOURCE_PLANE_PAGE_SIZE)
    cursor: IntelligenceResourceCursorV1Alpha1 | None = None
    query_id: str | None = None
    query_digest: str | None = None

    @field_validator("product_id")
    @classmethod
    def validate_scope(cls, value: str) -> str:
        return validate_product_id(value)

    @field_validator("authority_grant_ref")
    @classmethod
    def validate_grant(cls, value: str) -> str:
        return validate_reference(value, name="authority_grant_ref")

    @field_validator("resource_kinds")
    @classmethod
    def normalize_kinds(cls, value: tuple[IntelligenceResourceKind, ...]) -> tuple[IntelligenceResourceKind, ...]:
        normalized = tuple(sorted(value, key=lambda item: item.value))
        if len(normalized) != len(set(normalized)):
            raise ValueError("resource_kinds must be unique")
        return normalized

    @field_validator("subject_refs")
    @classmethod
    def normalize_subjects(cls, value: tuple[str, ...]) -> tuple[str, ...]:
        return _unique_references(value, name="subject_refs")

    @field_validator("as_of", "available_at")
    @classmethod
    def normalize_times(cls, value: datetime, info) -> datetime:
        return _aware(value, name=info.field_name)

    @field_validator("query_digest")
    @classmethod
    def validate_optional_digest(cls, value: str | None) -> str | None:
        return validate_digest(value) if value is not None else None

    @model_validator(mode="after")
    def validate_scope_time_and_identity(self) -> Self:
        if self.authenticated_context.product_id != self.product_id:
            raise ValueError("resource query crossed authenticated product scope")
        if self.available_at < self.as_of:
            raise ValueError("query available_at cannot precede as_of")
        material = self.model_dump(
            mode="json",
            exclude={"authenticated_context", "cursor", "query_id", "query_digest"},
        )
        material["actor_ref"] = self.authenticated_context.actor_ref
        digest = canonical_hash(material)
        expected_id = f"resource_query:{digest[:32]}"
        expected_digest = f"sha256:{digest}"
        if self.query_id not in {None, expected_id} or self.query_digest not in {None, expected_digest}:
            raise ValueError("query identity does not match exact selector material")
        object.__setattr__(self, "query_id", expected_id)
        object.__setattr__(self, "query_digest", expected_digest)
        if self.cursor is not None and self.cursor.query_id != expected_id:
            raise ValueError("pagination cursor belongs to a different query")
        return self


class IntelligenceResourcePageV1Alpha1(_StrictFrozenContract):
    """Authorized page returned from the unified resource plane."""

    contract: Literal["ace.intelligence.resource-plane-page/v1alpha1"] = RESOURCE_PLANE_PAGE_VERSION
    query_id: str
    query_digest: str
    product_id: str
    actor_ref: str
    as_of: datetime
    available_at: datetime
    evaluated_at: datetime
    state: IntelligenceResourcePageState
    items: tuple[IntelligenceResourceRecordV1Alpha1, ...] = Field(max_length=MAX_RESOURCE_PLANE_PAGE_SIZE)
    next_cursor: IntelligenceResourceCursorV1Alpha1 | None = None
    degraded_reason_refs: tuple[str, ...] = Field(default_factory=tuple, max_length=64)
    authority_use: AuthorityUseReceiptV1Alpha1
    page_id: str | None = None
    page_digest: str | None = None

    @field_validator("query_id", "actor_ref")
    @classmethod
    def validate_refs(cls, value: str, info) -> str:
        return validate_reference(value, name=info.field_name)

    @field_validator("query_digest", "page_digest")
    @classmethod
    def validate_digests(cls, value: str | None) -> str | None:
        return validate_digest(value) if value is not None else None

    @field_validator("product_id")
    @classmethod
    def validate_scope(cls, value: str) -> str:
        return validate_product_id(value)

    @field_validator("as_of", "available_at", "evaluated_at")
    @classmethod
    def normalize_times(cls, value: datetime, info) -> datetime:
        return _aware(value, name=info.field_name)

    @field_validator("degraded_reason_refs")
    @classmethod
    def normalize_reasons(cls, value: tuple[str, ...]) -> tuple[str, ...]:
        return _unique_references(value, name="degraded_reason_refs")

    @model_validator(mode="after")
    def validate_page(self) -> Self:
        if self.available_at < self.as_of or self.evaluated_at < self.available_at:
            raise ValueError("page time cutoffs must be monotonic")
        if self.state is IntelligenceResourcePageState.COMPLETE and self.degraded_reason_refs:
            raise ValueError("a complete page cannot declare degraded reasons")
        if self.state is IntelligenceResourcePageState.DEGRADED and not self.degraded_reason_refs:
            raise ValueError("a degraded page requires explicit reason references")
        if any(item.reference.product_id != self.product_id for item in self.items):
            raise ValueError("page items crossed product scope")
        if any(
            item.reference.as_of > self.as_of or item.reference.available_at > self.available_at for item in self.items
        ):
            raise ValueError("page contains resources outside its temporal cutoff")
        ordering = [
            (
                item.reference.available_at,
                item.reference.resource_kind.value,
                item.reference.resource_id,
                item.reference.revision,
            )
            for item in self.items
        ]
        if ordering != sorted(ordering):
            raise ValueError("page items must use stable ascending resource order")
        if self.next_cursor is not None and self.next_cursor.query_id != self.query_id:
            raise ValueError("next cursor belongs to a different query")
        authority = self.authority_use
        if (
            authority.product_id != self.product_id
            or authority.actor_ref != self.actor_ref
            or authority.use_subject_ref != self.query_id
            or authority.use_subject_digest != self.query_digest
            or authority.operation != "query_intelligence_resources"
            or authority.authority != "observe_read"
            or authority.evaluated_at != self.evaluated_at
        ):
            raise ValueError("page does not preserve the exact resource-query authority evaluation")
        _derive_identity(self, prefix="resource_page", id_field="page_id", digest_field="page_digest")
        return self

    @property
    def reusable_authority(self) -> Literal[False]:
        return False


__all__ = [
    "MAX_RESOURCE_PLANE_PAGE_SIZE",
    "RESOURCE_PLANE_CURSOR_VERSION",
    "RESOURCE_PLANE_PAGE_VERSION",
    "RESOURCE_PLANE_QUERY_VERSION",
    "RESOURCE_PLANE_RECORD_VERSION",
    "RESOURCE_PLANE_REFERENCE_VERSION",
    "IntelligenceResourceAvailability",
    "IntelligenceResourceCursorV1Alpha1",
    "IntelligenceResourceKind",
    "IntelligenceResourcePageState",
    "IntelligenceResourcePageV1Alpha1",
    "IntelligenceResourceQueryV1Alpha1",
    "IntelligenceResourceRecordV1Alpha1",
    "IntelligenceResourceReferenceV1Alpha1",
]
