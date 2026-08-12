"""Provider-neutral AM4 lifecycle, retention, export, and erasure contracts.

Core owns the authoritative scope, exact lifecycle coordinate, dependency proof,
and content-free administration receipts.  Bodies remain opaque payloads of the
existing immutable-record owner and never enter lifecycle or erasure receipts.
"""

from __future__ import annotations

from datetime import UTC, datetime
from enum import StrEnum
from typing import Any, Literal, Self

from pydantic import ConfigDict, Field, field_validator, model_validator

from ace.core.agent_memory import AgentMemoryScopeV1Alpha1, LedgerCoordinateV1Alpha1, LifecycleState
from ace.core.contracts import FrozenContract, canonical_hash, stable_id

RETENTION_POLICY_VERSION = "ace.core.agent-memory-retention-policy/v1alpha1"
LIFECYCLE_REQUEST_VERSION = "ace.core.agent-memory-lifecycle-request/v1alpha1"
DEPENDENCY_ENTRY_VERSION = "ace.core.agent-memory-dependency-entry/v1alpha1"
DEPENDENCY_SNAPSHOT_VERSION = "ace.core.agent-memory-dependency-snapshot/v1alpha1"
LIFECYCLE_IMPACT_VERSION = "ace.core.agent-memory-lifecycle-impact/v1alpha1"
ERASURE_RECEIPT_VERSION = "ace.core.agent-memory-erasure-receipt/v1alpha1"
EXPORT_REQUEST_VERSION = "ace.core.agent-memory-export-request/v1alpha1"
EXPORT_ENTRY_VERSION = "ace.core.agent-memory-export-entry/v1alpha1"
EXPORT_ARTIFACT_VERSION = "ace.core.agent-memory-export-artifact/v1alpha1"
EXPORT_RECEIPT_VERSION = "ace.core.agent-memory-export-receipt/v1alpha1"
IMPORT_REQUEST_VERSION = "ace.core.agent-memory-import-request/v1alpha1"
IMPORT_RECEIPT_VERSION = "ace.core.agent-memory-import-receipt/v1alpha1"
LIFECYCLE_MUTATION_RECEIPT_VERSION = "ace.core.agent-memory-lifecycle-mutation-receipt/v1alpha1"

AM4_RECORD_SPACE = "agent_memory_lifecycle_v1alpha1"
LIFECYCLE_EVENT_RECORD_KIND = "memory_lifecycle_event"
LIFECYCLE_RECEIPT_RECORD_KIND = "memory_lifecycle_receipt"
DEPENDENCY_SNAPSHOT_RECORD_KIND = "memory_dependency_snapshot"
ERASURE_RECEIPT_RECORD_KIND = "memory_erasure_receipt"
EXPORT_RECEIPT_RECORD_KIND = "memory_export_receipt"
IMPORT_RECEIPT_RECORD_KIND = "memory_import_receipt"

_SHA256_PATTERN = r"^sha256:[a-f0-9]{64}$"
_REF_PATTERN = r"^[A-Za-z0-9][A-Za-z0-9._:/-]{0,239}$"
MAX_DEPENDENCIES = 20_000


class _StrictFrozen(FrozenContract):
    model_config = ConfigDict(
        extra="forbid",
        frozen=True,
        strict=True,
        revalidate_instances="always",
        validate_default=True,
        allow_inf_nan=False,
    )


def _aware(value: datetime, name: str) -> datetime:
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError(f"{name} must include a timezone")
    return value.astimezone(UTC)


def _refs(value: Any, name: str, *, required: bool = False) -> tuple[str, ...]:
    if not isinstance(value, (list, tuple, set, frozenset)):
        raise ValueError(f"{name} must be a collection")
    if any(not isinstance(item, str) for item in value):
        raise ValueError(f"{name} must contain stable references")
    result = tuple(sorted(set(value)))
    if required and not result:
        raise ValueError(f"{name} must not be empty")
    if len(result) > MAX_DEPENDENCIES:
        raise ValueError(f"{name} exceeds the supported bound")
    return result


def _derive(instance: _StrictFrozen, field: str, prefix: str, *, exclude: set[str] | None = None) -> None:
    omitted = {field} | (exclude or set())
    expected = stable_id(prefix, instance.model_dump(mode="json", exclude=omitted))
    supplied = getattr(instance, field)
    if supplied is not None and supplied != expected:
        raise ValueError(f"{field} does not match exact canonical material")
    object.__setattr__(instance, field, expected)


def lifecycle_record_space(scope: AgentMemoryScopeV1Alpha1) -> str:
    """Return the existing-store namespace for one exact authenticated scope."""

    return stable_id(AM4_RECORD_SPACE, {"scope_id": scope.scope_id})


class MemoryLifecycleMeaning(StrEnum):
    SUPERSESSION = "supersession"
    EXPIRY = "expiry"
    ARCHIVAL = "archival"
    REDACTION = "redaction"
    SOFT_FORGET = "soft_forget"
    HARD_ERASURE = "hard_erasure"


class RetentionSelectorKind(StrEnum):
    CATEGORY = "category"
    SCOPE = "scope"
    SOURCE = "source"
    POLICY = "policy"


class DependencyKind(StrEnum):
    PRIMARY_RECORD = "primary_record"
    SOURCE_BODY = "source_body"
    ASSERTION = "assertion"
    RANK_CANDIDATE = "rank_candidate"
    CONTEXT_MANIFEST = "context_manifest"
    USE_LINEAGE = "use_lineage"
    GRAPH_PROJECTION = "graph_projection"
    GRAPH_EDGE = "graph_edge"
    EMBEDDING = "embedding"
    VECTOR_MATERIAL = "vector_material"
    SUMMARY = "summary"
    CACHE = "cache"
    EXTERNAL_BODY = "external_body"
    EXPORT_ARTIFACT = "export_artifact"
    OTHER_DERIVATIVE = "other_derivative"


class ExportScopeKind(StrEnum):
    PRODUCT = "product"
    SESSION = "session"
    PRINCIPAL = "principal"


class BodyAvailability(StrEnum):
    INCLUDED = "included"
    OMITTED_BY_POLICY = "omitted_by_policy"
    MISSING = "missing"
    EXTERNAL_REFERENCE = "external_reference"
    ERASED = "erased"


class ImportDisposition(StrEnum):
    IMPORTED = "imported"
    EXACT_REPLAY = "exact_replay"
    REFUSED_COLLISION = "refused_collision"
    REFUSED_MISSING_BODY = "refused_missing_body"
    REFUSED_POLICY = "refused_incompatible_policy"
    REFUSED_SCOPE = "refused_scope"
    REFUSED_STALE = "refused_stale"


class RetentionPolicyV1Alpha1(_StrictFrozen):
    contract: Literal["ace.core.agent-memory-retention-policy/v1alpha1"] = RETENTION_POLICY_VERSION
    policy_ref: str = Field(pattern=_REF_PATTERN)
    policy_version: str = Field(pattern=_REF_PATTERN)
    selector_kind: RetentionSelectorKind
    selector_refs: tuple[str, ...]
    lifecycle_meaning: MemoryLifecycleMeaning
    retain_for_seconds: int | None = Field(default=None, ge=0)
    archive_body: bool = False
    require_external_body_removal: bool = True
    policy_digest: str | None = Field(default=None, pattern=_SHA256_PATTERN)

    @field_validator("selector_refs", mode="before")
    @classmethod
    def normalize_selector_refs(cls, value: Any) -> tuple[str, ...]:
        return _refs(value, "selector_refs", required=True)

    @model_validator(mode="after")
    def validate_policy(self) -> Self:
        if self.lifecycle_meaning is MemoryLifecycleMeaning.EXPIRY and self.retain_for_seconds is None:
            raise ValueError("expiry retention policy requires retain_for_seconds")
        material = self.model_dump(mode="json", exclude={"policy_digest"})
        expected = f"sha256:{canonical_hash(material)}"
        if self.policy_digest is not None and self.policy_digest != expected:
            raise ValueError("policy_digest does not match exact policy material")
        object.__setattr__(self, "policy_digest", expected)
        return self


class LifecycleRequestV1Alpha1(_StrictFrozen):
    contract: Literal["ace.core.agent-memory-lifecycle-request/v1alpha1"] = LIFECYCLE_REQUEST_VERSION
    scope: AgentMemoryScopeV1Alpha1
    target_refs: tuple[str, ...]
    meaning: MemoryLifecycleMeaning
    authority_receipt_ref: str = Field(pattern=_REF_PATTERN)
    requested_by_ref: str = Field(pattern=_REF_PATTERN)
    requested_at: datetime
    exact_prior_coordinate: LedgerCoordinateV1Alpha1
    policy_ref: str = Field(pattern=_REF_PATTERN)
    policy_version: str = Field(pattern=_REF_PATTERN)
    dry_run: bool = True
    successor_ref: str | None = Field(default=None, pattern=_REF_PATTERN)
    request_id: str | None = None

    @field_validator("target_refs", mode="before")
    @classmethod
    def normalize_target_refs(cls, value: Any) -> tuple[str, ...]:
        return _refs(value, "target_refs", required=True)

    @field_validator("requested_at")
    @classmethod
    def normalize_requested_at(cls, value: datetime) -> datetime:
        return _aware(value, "requested_at")

    @model_validator(mode="after")
    def validate_request(self) -> Self:
        if self.meaning is MemoryLifecycleMeaning.SUPERSESSION:
            if self.successor_ref is None or len(self.target_refs) != 1:
                raise ValueError("supersession requires one target and an exact successor")
        elif self.successor_ref is not None:
            raise ValueError("successor_ref is reserved for supersession")
        if self.meaning is MemoryLifecycleMeaning.HARD_ERASURE and len(self.target_refs) != 1:
            raise ValueError("hard erasure binds exactly one root and its complete derivative closure")
        _derive(self, "request_id", "agent_memory_lifecycle_request", exclude={"dry_run"})
        return self


class DependencyEntryV1Alpha1(_StrictFrozen):
    contract: Literal["ace.core.agent-memory-dependency-entry/v1alpha1"] = DEPENDENCY_ENTRY_VERSION
    dependency_ref: str = Field(pattern=_REF_PATTERN)
    kind: DependencyKind
    root_refs: tuple[str, ...]
    storage_id: str | None = Field(default=None, pattern=_REF_PATTERN)
    record_space: str | None = Field(default=None, pattern=_REF_PATTERN)
    record_kind: str | None = Field(default=None, pattern=_REF_PATTERN)
    material_digest: str = Field(pattern=_SHA256_PATTERN)
    external_body_ref: str | None = Field(default=None, pattern=_REF_PATTERN)

    @field_validator("root_refs", mode="before")
    @classmethod
    def normalize_root_refs(cls, value: Any) -> tuple[str, ...]:
        return _refs(value, "root_refs", required=True)

    @model_validator(mode="after")
    def validate_location(self) -> Self:
        stored = (self.storage_id, self.record_space, self.record_kind)
        if any(item is not None for item in stored) and any(item is None for item in stored):
            raise ValueError("stored dependency requires storage_id, record_space, and record_kind")
        if self.kind is DependencyKind.EXTERNAL_BODY and self.external_body_ref is None:
            raise ValueError("external body dependency requires its exact reference")
        return self


class DependencySnapshotV1Alpha1(_StrictFrozen):
    contract: Literal["ace.core.agent-memory-dependency-snapshot/v1alpha1"] = DEPENDENCY_SNAPSHOT_VERSION
    scope: AgentMemoryScopeV1Alpha1
    request_ref: str = Field(pattern=_REF_PATTERN)
    ledger_through: LedgerCoordinateV1Alpha1
    entries: tuple[DependencyEntryV1Alpha1, ...]
    complete: bool
    completeness_policy_ref: str = Field(pattern=_REF_PATTERN)
    omissions: tuple[str, ...] = ()
    created_at: datetime
    snapshot_id: str | None = None
    snapshot_digest: str | None = Field(default=None, pattern=_SHA256_PATTERN)

    @field_validator("entries", mode="before")
    @classmethod
    def preserve_entries(cls, value: Any) -> tuple[Any, ...]:
        if not isinstance(value, (list, tuple)):
            raise ValueError("entries must be an ordered collection")
        if len(value) > MAX_DEPENDENCIES:
            raise ValueError("dependency snapshot must be bounded")
        return tuple(value)

    @field_validator("omissions", mode="before")
    @classmethod
    def normalize_omissions(cls, value: Any) -> tuple[str, ...]:
        return _refs(value, "omissions")

    @field_validator("created_at")
    @classmethod
    def normalize_created_at(cls, value: datetime) -> datetime:
        return _aware(value, "created_at")

    @model_validator(mode="after")
    def validate_snapshot(self) -> Self:
        refs = [entry.dependency_ref for entry in self.entries]
        if refs != sorted(refs) or len(refs) != len(set(refs)):
            raise ValueError("dependency entries must be unique and sorted by dependency_ref")
        if self.complete and self.omissions:
            raise ValueError("a complete dependency snapshot cannot report omissions")
        if self.complete and not self.entries:
            raise ValueError("a complete dependency snapshot cannot be empty")
        if not self.complete and not self.omissions:
            raise ValueError("an incomplete dependency snapshot must explain omissions")
        _derive(self, "snapshot_id", "agent_memory_dependency_snapshot", exclude={"snapshot_digest"})
        material = self.model_dump(mode="json", exclude={"snapshot_digest"})
        expected = f"sha256:{canonical_hash(material)}"
        if self.snapshot_digest is not None and self.snapshot_digest != expected:
            raise ValueError("snapshot_digest does not match exact dependency material")
        object.__setattr__(self, "snapshot_digest", expected)
        return self


class LifecycleImpactReceiptV1Alpha1(_StrictFrozen):
    contract: Literal["ace.core.agent-memory-lifecycle-impact/v1alpha1"] = LIFECYCLE_IMPACT_VERSION
    request_ref: str = Field(pattern=_REF_PATTERN)
    scope: AgentMemoryScopeV1Alpha1
    dependency_snapshot_ref: str = Field(pattern=_REF_PATTERN)
    affected_by_kind: dict[str, int]
    current_recall_removed_refs: tuple[str, ...]
    history_preserved: bool
    external_action_refs: tuple[str, ...] = ()
    dry_run: Literal[True] = True
    receipt_id: str | None = None

    @field_validator("current_recall_removed_refs", "external_action_refs", mode="before")
    @classmethod
    def normalize_refs(cls, value: Any, info) -> tuple[str, ...]:
        return _refs(value, info.field_name)

    @model_validator(mode="after")
    def derive_receipt(self) -> Self:
        if any(not key or count < 0 for key, count in self.affected_by_kind.items()):
            raise ValueError("affected_by_kind must contain bounded non-negative counts")
        _derive(self, "receipt_id", "agent_memory_lifecycle_impact")
        return self


class LifecycleMutationReceiptV1Alpha1(_StrictFrozen):
    contract: Literal["ace.core.agent-memory-lifecycle-mutation-receipt/v1alpha1"] = LIFECYCLE_MUTATION_RECEIPT_VERSION
    request_ref: str = Field(pattern=_REF_PATTERN)
    scope: AgentMemoryScopeV1Alpha1
    meaning: MemoryLifecycleMeaning
    target_refs: tuple[str, ...]
    lifecycle_event_refs: tuple[str, ...]
    resulting_state: LifecycleState
    dependency_snapshot_ref: str = Field(pattern=_REF_PATTERN)
    authority_receipt_ref: str = Field(pattern=_REF_PATTERN)
    applied_at: datetime
    receipt_id: str | None = None

    @field_validator("target_refs", "lifecycle_event_refs", mode="before")
    @classmethod
    def normalize_refs(cls, value: Any, info) -> tuple[str, ...]:
        return _refs(value, info.field_name, required=True)

    @field_validator("applied_at")
    @classmethod
    def normalize_applied_at(cls, value: datetime) -> datetime:
        return _aware(value, "applied_at")

    @model_validator(mode="after")
    def derive_receipt(self) -> Self:
        if len(self.target_refs) != len(self.lifecycle_event_refs):
            raise ValueError("each lifecycle target requires one exact event")
        _derive(self, "receipt_id", "agent_memory_lifecycle_mutation_receipt")
        return self


class ErasureReceiptV1Alpha1(_StrictFrozen):
    """Tamper-evident content-free proof; erased bodies are structurally absent."""

    contract: Literal["ace.core.agent-memory-erasure-receipt/v1alpha1"] = ERASURE_RECEIPT_VERSION
    request_ref: str = Field(pattern=_REF_PATTERN)
    scope: AgentMemoryScopeV1Alpha1
    exact_prior_coordinate: LedgerCoordinateV1Alpha1
    dependency_snapshot_ref: str = Field(pattern=_REF_PATTERN)
    dependency_snapshot_digest: str = Field(pattern=_SHA256_PATTERN)
    removed_dependency_refs: tuple[str, ...]
    removal_evidence_digests: tuple[str, ...]
    authority_receipt_ref: str = Field(pattern=_REF_PATTERN)
    completed_at: datetime
    post_removal_probe_digest: str = Field(pattern=_SHA256_PATTERN)
    receipt_id: str | None = None

    @field_validator("removed_dependency_refs", "removal_evidence_digests", mode="before")
    @classmethod
    def normalize_collections(cls, value: Any, info) -> tuple[str, ...]:
        return _refs(value, info.field_name, required=True)

    @field_validator("completed_at")
    @classmethod
    def normalize_completed_at(cls, value: datetime) -> datetime:
        return _aware(value, "completed_at")

    @model_validator(mode="after")
    def validate_erasure(self) -> Self:
        if len(self.removed_dependency_refs) != len(self.removal_evidence_digests):
            raise ValueError("every removed dependency requires one content-free removal digest")
        _derive(self, "receipt_id", "agent_memory_erasure_receipt")
        return self


class ExportRequestV1Alpha1(_StrictFrozen):
    contract: Literal["ace.core.agent-memory-export-request/v1alpha1"] = EXPORT_REQUEST_VERSION
    scope: AgentMemoryScopeV1Alpha1
    export_scope: ExportScopeKind
    selector_ref: str = Field(pattern=_REF_PATTERN)
    ledger_through: LedgerCoordinateV1Alpha1
    authority_receipt_ref: str = Field(pattern=_REF_PATTERN)
    policy_ref: str = Field(pattern=_REF_PATTERN)
    policy_version: str = Field(pattern=_REF_PATTERN)
    include_bodies: bool
    requested_at: datetime
    request_id: str | None = None

    @field_validator("requested_at")
    @classmethod
    def normalize_requested_at(cls, value: datetime) -> datetime:
        return _aware(value, "requested_at")

    @model_validator(mode="after")
    def validate_selector(self) -> Self:
        expected = {
            ExportScopeKind.PRODUCT: self.scope.product_id,
            ExportScopeKind.SESSION: self.scope.session_id,
            ExportScopeKind.PRINCIPAL: self.scope.actor_id,
        }[self.export_scope]
        if expected is None or self.selector_ref != expected:
            raise ValueError("export selector must match the authenticated exact scope")
        _derive(self, "request_id", "agent_memory_export_request")
        return self


class ExportEntryV1Alpha1(_StrictFrozen):
    contract: Literal["ace.core.agent-memory-export-entry/v1alpha1"] = EXPORT_ENTRY_VERSION
    storage_id: str = Field(pattern=_REF_PATTERN)
    record_space: str = Field(pattern=_REF_PATTERN)
    record_kind: str = Field(pattern=_REF_PATTERN)
    record_key: str = Field(pattern=_REF_PATTERN)
    payload_contract: str = Field(pattern=_REF_PATTERN)
    canonical_identity_ref: str = Field(pattern=_REF_PATTERN)
    as_of: datetime
    available_at: datetime
    processing_order: int = Field(ge=0)
    lifecycle_state: LifecycleState
    provenance_refs: tuple[str, ...]
    source_body_availability: BodyAvailability
    artifact_digest: str = Field(pattern=_SHA256_PATTERN)
    payload: dict[str, Any] | None = None
    omission_reason: str | None = Field(default=None, pattern=_REF_PATTERN)

    @field_validator("provenance_refs", mode="before")
    @classmethod
    def normalize_provenance_refs(cls, value: Any) -> tuple[str, ...]:
        return _refs(value, "provenance_refs")

    @field_validator("as_of", "available_at")
    @classmethod
    def normalize_times(cls, value: datetime, info) -> datetime:
        return _aware(value, info.field_name)

    @model_validator(mode="after")
    def validate_availability(self) -> Self:
        if self.available_at < self.as_of:
            raise ValueError("export entry availability cannot precede its as-of time")
        if self.source_body_availability is BodyAvailability.INCLUDED:
            if self.payload is None:
                raise ValueError("included export entries require payload material")
            if self.omission_reason is not None:
                raise ValueError("included export entries cannot report an omission")
        elif self.payload is not None:
            raise ValueError("non-included export entries cannot retain payload material")
        return self


class ExportArtifactV1Alpha1(_StrictFrozen):
    contract: Literal["ace.core.agent-memory-export-artifact/v1alpha1"] = EXPORT_ARTIFACT_VERSION
    request_ref: str = Field(pattern=_REF_PATTERN)
    scope: AgentMemoryScopeV1Alpha1
    export_scope: ExportScopeKind
    selector_ref: str = Field(pattern=_REF_PATTERN)
    ledger_through: LedgerCoordinateV1Alpha1
    policy_ref: str = Field(pattern=_REF_PATTERN)
    policy_version: str = Field(pattern=_REF_PATTERN)
    entries: tuple[ExportEntryV1Alpha1, ...]
    omissions: tuple[str, ...] = ()
    created_at: datetime
    artifact_digest: str | None = Field(default=None, pattern=_SHA256_PATTERN)

    @field_validator("entries", mode="before")
    @classmethod
    def preserve_entries(cls, value: Any) -> tuple[Any, ...]:
        if not isinstance(value, (list, tuple)) or len(value) > MAX_DEPENDENCIES:
            raise ValueError("export entries must be a bounded ordered collection")
        return tuple(value)

    @field_validator("omissions", mode="before")
    @classmethod
    def normalize_omissions(cls, value: Any) -> tuple[str, ...]:
        return _refs(value, "omissions")

    @field_validator("created_at")
    @classmethod
    def normalize_created_at(cls, value: datetime) -> datetime:
        return _aware(value, "created_at")

    @model_validator(mode="after")
    def derive_digest(self) -> Self:
        ids = [entry.storage_id for entry in self.entries]
        if ids != sorted(ids) or len(ids) != len(set(ids)):
            raise ValueError("export entries must have unique sorted storage identities")
        expected = f"sha256:{canonical_hash(self.model_dump(mode='json', exclude={'artifact_digest'}))}"
        if self.artifact_digest is not None and self.artifact_digest != expected:
            raise ValueError("artifact_digest does not match canonical export")
        object.__setattr__(self, "artifact_digest", expected)
        return self


class ExportReceiptV1Alpha1(_StrictFrozen):
    contract: Literal["ace.core.agent-memory-export-receipt/v1alpha1"] = EXPORT_RECEIPT_VERSION
    request_ref: str = Field(pattern=_REF_PATTERN)
    authority_receipt_ref: str = Field(pattern=_REF_PATTERN)
    ledger_through: LedgerCoordinateV1Alpha1
    artifact_digest: str = Field(pattern=_SHA256_PATTERN)
    exported_entry_digests: tuple[str, ...]
    omission_refs: tuple[str, ...] = ()
    completed_at: datetime
    receipt_id: str | None = None

    @field_validator("exported_entry_digests", "omission_refs", mode="before")
    @classmethod
    def normalize_refs(cls, value: Any, info) -> tuple[str, ...]:
        return _refs(value, info.field_name)

    @field_validator("completed_at")
    @classmethod
    def normalize_completed_at(cls, value: datetime) -> datetime:
        return _aware(value, "completed_at")

    @model_validator(mode="after")
    def derive_receipt(self) -> Self:
        _derive(self, "receipt_id", "agent_memory_export_receipt")
        return self


class ImportRequestV1Alpha1(_StrictFrozen):
    contract: Literal["ace.core.agent-memory-import-request/v1alpha1"] = IMPORT_REQUEST_VERSION
    scope: AgentMemoryScopeV1Alpha1
    artifact_digest: str = Field(pattern=_SHA256_PATTERN)
    authority_receipt_ref: str = Field(pattern=_REF_PATTERN)
    accepted_policy_refs: tuple[str, ...]
    required_policy_version: str = Field(pattern=_REF_PATTERN)
    idempotency_ref: str = Field(pattern=_REF_PATTERN)
    requested_at: datetime
    request_id: str | None = None

    @field_validator("accepted_policy_refs", mode="before")
    @classmethod
    def normalize_policy_refs(cls, value: Any) -> tuple[str, ...]:
        return _refs(value, "accepted_policy_refs", required=True)

    @field_validator("requested_at")
    @classmethod
    def normalize_requested_at(cls, value: datetime) -> datetime:
        return _aware(value, "requested_at")

    @model_validator(mode="after")
    def derive_request(self) -> Self:
        _derive(self, "request_id", "agent_memory_import_request")
        return self


class ImportReceiptV1Alpha1(_StrictFrozen):
    contract: Literal["ace.core.agent-memory-import-receipt/v1alpha1"] = IMPORT_RECEIPT_VERSION
    request_ref: str = Field(pattern=_REF_PATTERN)
    artifact_digest: str = Field(pattern=_SHA256_PATTERN)
    disposition: ImportDisposition
    imported_storage_refs: tuple[str, ...] = ()
    collision_refs: tuple[str, ...] = ()
    missing_body_refs: tuple[str, ...] = ()
    policy_ref: str = Field(pattern=_REF_PATTERN)
    policy_version: str = Field(pattern=_REF_PATTERN)
    completed_at: datetime
    receipt_id: str | None = None

    @field_validator("imported_storage_refs", "collision_refs", "missing_body_refs", mode="before")
    @classmethod
    def normalize_refs(cls, value: Any, info) -> tuple[str, ...]:
        return _refs(value, info.field_name)

    @field_validator("completed_at")
    @classmethod
    def normalize_completed_at(cls, value: datetime) -> datetime:
        return _aware(value, "completed_at")

    @model_validator(mode="after")
    def validate_disposition(self) -> Self:
        failure_fields = self.collision_refs or self.missing_body_refs
        if self.disposition in {ImportDisposition.IMPORTED, ImportDisposition.EXACT_REPLAY} and failure_fields:
            raise ValueError("successful import cannot report collisions or missing bodies")
        if self.disposition is ImportDisposition.REFUSED_COLLISION and not self.collision_refs:
            raise ValueError("collision refusal requires exact collision references")
        if self.disposition is ImportDisposition.REFUSED_MISSING_BODY and not self.missing_body_refs:
            raise ValueError("missing-body refusal requires exact references")
        _derive(self, "receipt_id", "agent_memory_import_receipt")
        return self


__all__ = [
    "AM4_RECORD_SPACE",
    "BodyAvailability",
    "DependencyEntryV1Alpha1",
    "DependencyKind",
    "DependencySnapshotV1Alpha1",
    "ErasureReceiptV1Alpha1",
    "ExportArtifactV1Alpha1",
    "ExportEntryV1Alpha1",
    "ExportReceiptV1Alpha1",
    "ExportRequestV1Alpha1",
    "ExportScopeKind",
    "ImportDisposition",
    "ImportReceiptV1Alpha1",
    "ImportRequestV1Alpha1",
    "LifecycleImpactReceiptV1Alpha1",
    "LifecycleMutationReceiptV1Alpha1",
    "LifecycleRequestV1Alpha1",
    "MemoryLifecycleMeaning",
    "RetentionPolicyV1Alpha1",
    "RetentionSelectorKind",
    "lifecycle_record_space",
]
