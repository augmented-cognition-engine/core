"""Domain-neutral ownership contracts for one personal Intelligence product.

The export artifact is canonical portability evidence.  It deliberately does
not claim that another ACE installation can restore or execute the artifact.
Deletion is a two-phase operation: an exact product snapshot is previewed, and
the caller must return its confirmation digest before Core removes the same
immutable records and leaves a content-free proof.
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Literal, Self

from pydantic import ConfigDict, Field, field_validator, model_validator

from ace.core.agent_memory_lifecycle import DependencyKind
from ace.core.contracts import FrozenContract, canonical_hash
from ace.core.records import ImmutableRecordReferenceV1, ImmutableRecordV1
from ace.core.runtime_use import AuthenticatedRuntimeContextV1Alpha1

PERSONAL_INTELLIGENCE_EXPORT_REQUEST_VERSION = "ace.core.personal-intelligence-export-request/v1alpha1"
PERSONAL_INTELLIGENCE_EXPORT_ARTIFACT_VERSION = "ace.core.personal-intelligence-export-artifact/v1alpha1"
PERSONAL_INTELLIGENCE_DELETE_PREVIEW_REQUEST_VERSION = "ace.core.personal-intelligence-delete-preview-request/v1alpha1"
PERSONAL_INTELLIGENCE_DELETE_PREVIEW_VERSION = "ace.core.personal-intelligence-delete-preview/v1alpha1"
PERSONAL_INTELLIGENCE_DELETE_CONFIRMATION_VERSION = "ace.core.personal-intelligence-delete-confirmation/v1alpha1"
PERSONAL_INTELLIGENCE_DELETION_PROOF_VERSION = "ace.core.personal-intelligence-deletion-proof/v1alpha1"

PORTABILITY_SCOPE = "canonical-records-only; runnable restore is not provided"
BACKUP_NON_REAPPEARANCE_LIMITATION = (
    "ACE verifies removal from the configured primary immutable-record store only; "
    "pre-existing backups, exports, caches, and external copies must be expired or purged separately."
)
# Additive disclosure (Decision 9): explicitly enumerate the derivative kinds that survive if present,
# so a person can tell exactly what is NOT removed. Kept as a new, defaulted field (never by editing
# the persisted backup_limitation Literal) and excluded from the record identity digest, so archived
# previews/proofs written before this field revalidate identically.
SURVIVING_DERIVATIVE_DISCLOSURE = (
    "Derivatives held outside the primary immutable-record store are NOT reached by this deletion and "
    "survive until purged separately: external embeddings and vector material, external graph rows and "
    "edges, search indexes, caches, native database backups, prior exports, and connector- or "
    "externally-held copies."
)

DERIVED_ARTIFACT_COVERAGE_VERSION = "ace.core.personal-intelligence-derived-artifact-coverage/v1alpha1"
DERIVED_ARTIFACT_ERASURE_ENTRY_VERSION = "ace.core.personal-intelligence-derived-artifact-erasure-entry/v1alpha1"

# Delivery half of Decision 9: the workspace derivative kinds a deletion must cover or explicitly
# prove surviving. The vocabulary is the AM4 dependency closure's, not a parallel invention.
WORKSPACE_DERIVED_ARTIFACT_KINDS: tuple[str, ...] = (
    DependencyKind.EMBEDDING.value,
    DependencyKind.VECTOR_MATERIAL.value,
    DependencyKind.GRAPH_PROJECTION.value,
    DependencyKind.GRAPH_EDGE.value,
    DependencyKind.CACHE.value,
    DependencyKind.SUMMARY.value,
)

_DIGEST_PATTERN = r"^sha256:[a-f0-9]{64}$"


class _StrictFrozen(FrozenContract):
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


def _bounded(value: str, *, name: str) -> str:
    if not value or value != value.strip() or len(value) > 240:
        raise ValueError(f"{name} must be non-empty, trimmed, and at most 240 characters")
    return value


def _derive_identity(
    value: _StrictFrozen,
    *,
    prefix: str,
    id_field: str,
    digest_field: str,
    exclude: set[str] | None = None,
) -> None:
    material = value.model_dump(
        mode="json",
        exclude={id_field, digest_field, *(exclude or set())},
    )
    digest = canonical_hash(material)
    expected_id = f"{prefix}:{digest[:32]}"
    expected_digest = f"sha256:{digest}"
    if getattr(value, id_field) not in {None, expected_id}:
        raise ValueError(f"{id_field} does not match exact contract material")
    if getattr(value, digest_field) not in {None, expected_digest}:
        raise ValueError(f"{digest_field} does not match exact contract material")
    object.__setattr__(value, id_field, expected_id)
    object.__setattr__(value, digest_field, expected_digest)


class DerivedArtifactCoverageV1Alpha1(_StrictFrozen):
    """One workspace derivative kind's exact pre-deletion count and disposition.

    Carried on the delete PREVIEW so the person reviews, before confirming, what
    the deletion will remove (covered=True) and what will survive with a concrete
    per-kind reason (covered=False). The generic catch-all disclosure is not an
    acceptable reason here — that boundary belongs to SURVIVING_DERIVATIVE_DISCLOSURE.
    """

    contract: Literal["ace.core.personal-intelligence-derived-artifact-coverage/v1alpha1"] = (
        DERIVED_ARTIFACT_COVERAGE_VERSION
    )
    artifact_kind: str
    store: str
    enumerated_count: int = Field(ge=0)
    covered: bool
    surviving_reason: str | None = None

    @field_validator("artifact_kind")
    @classmethod
    def validate_kind(cls, value: str) -> str:
        if value not in WORKSPACE_DERIVED_ARTIFACT_KINDS:
            raise ValueError("artifact_kind must be one of the workspace derived-artifact kinds")
        return value

    @field_validator("store")
    @classmethod
    def validate_store(cls, value: str) -> str:
        return _bounded(value, name="store")

    @model_validator(mode="after")
    def validate_disposition(self) -> Self:
        if self.covered:
            if self.surviving_reason is not None:
                raise ValueError("a covered derivative kind carries no surviving reason")
        else:
            if self.surviving_reason is None:
                raise ValueError("a surviving derivative kind requires a concrete reason")
            _bounded(self.surviving_reason, name="surviving_reason")
            if self.surviving_reason == SURVIVING_DERIVATIVE_DISCLOSURE:
                raise ValueError("surviving_reason must be concrete per kind, not the generic disclosure")
        return self


class DerivedArtifactErasureEntryV1Alpha1(_StrictFrozen):
    """One workspace derivative kind's per-deletion erasure outcome on the proof.

    Derived deterministically from the reviewed preview coverage (see
    derive_erasure_entries) so an idempotent confirmation replay reproduces the
    byte-identical proof; the erasure step's job is to make this report true or
    fail closed before the proof is appended.
    """

    contract: Literal["ace.core.personal-intelligence-derived-artifact-erasure-entry/v1alpha1"] = (
        DERIVED_ARTIFACT_ERASURE_ENTRY_VERSION
    )
    artifact_kind: str
    store: str
    enumerated_count: int = Field(ge=0)
    removed_count: int = Field(ge=0)
    surviving_count: int = Field(ge=0)
    verified_absent: bool
    surviving_reason: str | None = None

    @field_validator("artifact_kind")
    @classmethod
    def validate_kind(cls, value: str) -> str:
        if value not in WORKSPACE_DERIVED_ARTIFACT_KINDS:
            raise ValueError("artifact_kind must be one of the workspace derived-artifact kinds")
        return value

    @field_validator("store")
    @classmethod
    def validate_store(cls, value: str) -> str:
        return _bounded(value, name="store")

    @model_validator(mode="after")
    def validate_outcome(self) -> Self:
        if self.removed_count + self.surviving_count != self.enumerated_count:
            raise ValueError("removed_count and surviving_count must partition enumerated_count exactly")
        if self.surviving_count == 0:
            if not self.verified_absent:
                raise ValueError("a fully-removed derivative kind must be probe-verified absent")
            if self.surviving_reason is not None:
                raise ValueError("a fully-removed derivative kind carries no surviving reason")
        else:
            if self.verified_absent:
                raise ValueError("a kind with survivors cannot claim verified absence")
            if self.surviving_reason is None:
                raise ValueError("surviving derivatives require a concrete reason")
            _bounded(self.surviving_reason, name="surviving_reason")
            if self.surviving_reason == SURVIVING_DERIVATIVE_DISCLOSURE:
                raise ValueError("surviving_reason must be concrete per kind, not the generic disclosure")
        return self


def derive_erasure_entries(
    coverage: tuple[DerivedArtifactCoverageV1Alpha1, ...],
) -> tuple[DerivedArtifactErasureEntryV1Alpha1, ...]:
    """The deterministic erasure report one exact preview coverage promises."""

    return tuple(
        DerivedArtifactErasureEntryV1Alpha1(
            artifact_kind=item.artifact_kind,
            store=item.store,
            enumerated_count=item.enumerated_count,
            removed_count=item.enumerated_count if item.covered else 0,
            surviving_count=0 if item.covered else item.enumerated_count,
            verified_absent=item.covered,
            surviving_reason=None if item.covered else item.surviving_reason,
        )
        for item in coverage
    )


def _unique_kinds(
    entries: tuple[DerivedArtifactCoverageV1Alpha1, ...] | tuple[DerivedArtifactErasureEntryV1Alpha1, ...],
) -> None:
    kinds = [entry.artifact_kind for entry in entries]
    if len(kinds) != len(set(kinds)):
        raise ValueError("derived-artifact entries must name each kind at most once")


def _record_set_digest(records: tuple[ImmutableRecordReferenceV1, ...]) -> str:
    material = tuple((item.storage_id, item.material_hash) for item in records)
    return f"sha256:{canonical_hash(material)}"


class PersonalIntelligenceExportRequestV1Alpha1(_StrictFrozen):
    contract: Literal["ace.core.personal-intelligence-export-request/v1alpha1"] = (
        PERSONAL_INTELLIGENCE_EXPORT_REQUEST_VERSION
    )
    authenticated_context: AuthenticatedRuntimeContextV1Alpha1
    requested_at: datetime
    request_id: str | None = None
    request_digest: str | None = Field(default=None, pattern=_DIGEST_PATTERN)

    @field_validator("requested_at")
    @classmethod
    def normalize_requested_at(cls, value: datetime) -> datetime:
        return _aware(value, name="requested_at")

    @model_validator(mode="after")
    def validate_window_and_identity(self) -> Self:
        if not (
            self.authenticated_context.authenticated_at <= self.requested_at < self.authenticated_context.expires_at
        ):
            raise ValueError("export request is outside its authenticated context window")
        _derive_identity(
            self,
            prefix="personal_intelligence_export_request",
            id_field="request_id",
            digest_field="request_digest",
        )
        return self


class PersonalIntelligenceExportArtifactV1Alpha1(_StrictFrozen):
    """Canonical product-scoped records with intentionally bounded portability claims."""

    contract: Literal["ace.core.personal-intelligence-export-artifact/v1alpha1"] = (
        PERSONAL_INTELLIGENCE_EXPORT_ARTIFACT_VERSION
    )
    request_ref: str
    product_id: str
    requested_by_ref: str
    records: tuple[ImmutableRecordV1, ...]
    record_count: int = Field(ge=0)
    record_set_digest: str = Field(pattern=_DIGEST_PATTERN)
    created_at: datetime
    portability_scope: Literal["canonical-records-only; runnable restore is not provided"] = PORTABILITY_SCOPE
    runnable_restore_supported: Literal[False] = False
    artifact_id: str | None = None
    artifact_digest: str | None = Field(default=None, pattern=_DIGEST_PATTERN)

    @field_validator("request_ref", "product_id", "requested_by_ref")
    @classmethod
    def validate_refs(cls, value: str, info) -> str:
        return _bounded(value, name=info.field_name)

    @field_validator("created_at")
    @classmethod
    def normalize_created_at(cls, value: datetime) -> datetime:
        return _aware(value, name="created_at")

    @model_validator(mode="after")
    def validate_records_and_identity(self) -> Self:
        if self.record_count != len(self.records):
            raise ValueError("record_count must match the canonical record collection")
        if any(item.product_id != self.product_id for item in self.records):
            raise ValueError("export artifact crossed its exact product scope")
        storage_ids = tuple(str(item.storage_id) for item in self.records)
        if storage_ids != tuple(sorted(storage_ids)) or len(storage_ids) != len(set(storage_ids)):
            raise ValueError("export records must be unique and sorted by storage identity")
        references = tuple(item.reference() for item in self.records)
        if self.record_set_digest != _record_set_digest(references):
            raise ValueError("record_set_digest does not bind the canonical export records")
        _derive_identity(
            self,
            prefix="personal_intelligence_export_artifact",
            id_field="artifact_id",
            digest_field="artifact_digest",
        )
        return self


class PersonalIntelligenceDeletePreviewRequestV1Alpha1(_StrictFrozen):
    contract: Literal["ace.core.personal-intelligence-delete-preview-request/v1alpha1"] = (
        PERSONAL_INTELLIGENCE_DELETE_PREVIEW_REQUEST_VERSION
    )
    authenticated_context: AuthenticatedRuntimeContextV1Alpha1
    requested_at: datetime
    expires_at: datetime
    request_id: str | None = None
    request_digest: str | None = Field(default=None, pattern=_DIGEST_PATTERN)

    @field_validator("requested_at", "expires_at")
    @classmethod
    def normalize_times(cls, value: datetime, info) -> datetime:
        return _aware(value, name=info.field_name)

    @model_validator(mode="after")
    def validate_window_and_identity(self) -> Self:
        if not (
            self.authenticated_context.authenticated_at
            <= self.requested_at
            < self.expires_at
            <= self.authenticated_context.expires_at
        ):
            raise ValueError("delete preview has an invalid authenticated validity window")
        _derive_identity(
            self,
            prefix="personal_intelligence_delete_preview_request",
            id_field="request_id",
            digest_field="request_digest",
        )
        return self


class PersonalIntelligenceDeletePreviewV1Alpha1(_StrictFrozen):
    contract: Literal["ace.core.personal-intelligence-delete-preview/v1alpha1"] = (
        PERSONAL_INTELLIGENCE_DELETE_PREVIEW_VERSION
    )
    request_ref: str
    product_id: str
    requested_by_ref: str
    records: tuple[ImmutableRecordReferenceV1, ...] = Field(min_length=1)
    record_count: int = Field(ge=1)
    record_set_digest: str = Field(pattern=_DIGEST_PATTERN)
    created_at: datetime
    expires_at: datetime
    backup_non_reappearance_proven: Literal[False] = False
    backup_limitation: Literal[
        "ACE verifies removal from the configured primary immutable-record store only; "
        "pre-existing backups, exports, caches, and external copies must be expired or purged separately."
    ] = BACKUP_NON_REAPPEARANCE_LIMITATION
    surviving_derivative_disclosure: Literal[
        "Derivatives held outside the primary immutable-record store are NOT reached by this deletion and "
        "survive until purged separately: external embeddings and vector material, external graph rows and "
        "edges, search indexes, caches, native database backups, prior exports, and connector- or "
        "externally-held copies."
    ] = SURVIVING_DERIVATIVE_DISCLOSURE
    # Decision 9 delivery half: exact per-kind pre-deletion counts and dispositions, reviewed
    # before confirming. Additive and digest-excluded so pre-change previews revalidate identically.
    derived_artifacts: tuple[DerivedArtifactCoverageV1Alpha1, ...] = ()
    preview_id: str | None = None
    preview_digest: str | None = Field(default=None, pattern=_DIGEST_PATTERN)
    confirmation_digest: str | None = Field(default=None, pattern=_DIGEST_PATTERN)

    @field_validator("request_ref", "product_id", "requested_by_ref")
    @classmethod
    def validate_refs(cls, value: str, info) -> str:
        return _bounded(value, name=info.field_name)

    @field_validator("created_at", "expires_at")
    @classmethod
    def normalize_times(cls, value: datetime, info) -> datetime:
        return _aware(value, name=info.field_name)

    @model_validator(mode="after")
    def validate_snapshot_and_identity(self) -> Self:
        if self.expires_at <= self.created_at:
            raise ValueError("delete preview must have a positive confirmation window")
        if self.record_count != len(self.records):
            raise ValueError("record_count must match the preview snapshot")
        if any(item.product_id != self.product_id for item in self.records):
            raise ValueError("delete preview crossed its exact product scope")
        storage_ids = tuple(item.storage_id for item in self.records)
        if storage_ids != tuple(sorted(storage_ids)) or len(storage_ids) != len(set(storage_ids)):
            raise ValueError("delete preview records must be unique and sorted by storage identity")
        if self.record_set_digest != _record_set_digest(self.records):
            raise ValueError("record_set_digest does not bind the exact delete preview")
        _unique_kinds(self.derived_artifacts)
        _derive_identity(
            self,
            prefix="personal_intelligence_delete_preview",
            id_field="preview_id",
            digest_field="preview_digest",
            exclude={"confirmation_digest", "surviving_derivative_disclosure", "derived_artifacts"},
        )
        confirmation_material = {
            "preview_id": self.preview_id,
            "preview_digest": self.preview_digest,
            "record_set_digest": self.record_set_digest,
            "expires_at": self.expires_at.isoformat(),
        }
        expected_confirmation = f"sha256:{canonical_hash(confirmation_material)}"
        if self.confirmation_digest not in {None, expected_confirmation}:
            raise ValueError("confirmation_digest does not bind the exact delete preview")
        object.__setattr__(self, "confirmation_digest", expected_confirmation)
        return self


class PersonalIntelligenceDeleteConfirmationV1Alpha1(_StrictFrozen):
    contract: Literal["ace.core.personal-intelligence-delete-confirmation/v1alpha1"] = (
        PERSONAL_INTELLIGENCE_DELETE_CONFIRMATION_VERSION
    )
    authenticated_context: AuthenticatedRuntimeContextV1Alpha1
    preview: PersonalIntelligenceDeletePreviewV1Alpha1
    confirmation_digest: str = Field(pattern=_DIGEST_PATTERN)
    confirmed_at: datetime
    confirmation_id: str | None = None
    confirmation_material_digest: str | None = Field(default=None, pattern=_DIGEST_PATTERN)

    @field_validator("confirmed_at")
    @classmethod
    def normalize_confirmed_at(cls, value: datetime) -> datetime:
        return _aware(value, name="confirmed_at")

    @model_validator(mode="after")
    def validate_scope_window_and_identity(self) -> Self:
        if self.confirmation_digest != self.preview.confirmation_digest:
            raise ValueError("confirmation_digest does not match the exact delete preview")
        if (
            self.authenticated_context.product_id != self.preview.product_id
            or self.authenticated_context.actor_ref != self.preview.requested_by_ref
        ):
            raise ValueError("delete confirmation crossed authenticated product or actor scope")
        if not (
            self.authenticated_context.authenticated_at <= self.confirmed_at < self.authenticated_context.expires_at
            and self.confirmed_at < self.preview.expires_at
        ):
            raise ValueError("delete confirmation is outside its authenticated preview window")
        _derive_identity(
            self,
            prefix="personal_intelligence_delete_confirmation",
            id_field="confirmation_id",
            digest_field="confirmation_material_digest",
        )
        return self


class PersonalIntelligenceDeletionProofV1Alpha1(_StrictFrozen):
    """Content-free proof of primary-store removal for one exact preview."""

    contract: Literal["ace.core.personal-intelligence-deletion-proof/v1alpha1"] = (
        PERSONAL_INTELLIGENCE_DELETION_PROOF_VERSION
    )
    product_id: str
    preview_ref: str
    confirmation_ref: str
    removed_count: int = Field(ge=1)
    removed_record_set_digest: str = Field(pattern=_DIGEST_PATTERN)
    removal_evidence_digest: str = Field(pattern=_DIGEST_PATTERN)
    completed_at: datetime
    primary_store_non_reappearance_verified: Literal[True] = True
    backup_non_reappearance_proven: Literal[False] = False
    backup_limitation: Literal[
        "ACE verifies removal from the configured primary immutable-record store only; "
        "pre-existing backups, exports, caches, and external copies must be expired or purged separately."
    ] = BACKUP_NON_REAPPEARANCE_LIMITATION
    surviving_derivative_disclosure: Literal[
        "Derivatives held outside the primary immutable-record store are NOT reached by this deletion and "
        "survive until purged separately: external embeddings and vector material, external graph rows and "
        "edges, search indexes, caches, native database backups, prior exports, and connector- or "
        "externally-held copies."
    ] = SURVIVING_DERIVATIVE_DISCLOSURE
    # Decision 9 delivery half: the per-kind erasure report this deletion made true, derived
    # deterministically from the reviewed preview coverage. Additive and digest-excluded so
    # pre-change proofs revalidate identically and idempotent replay reproduces the same proof.
    derived_artifact_erasure: tuple[DerivedArtifactErasureEntryV1Alpha1, ...] = ()
    proof_id: str | None = None
    proof_digest: str | None = Field(default=None, pattern=_DIGEST_PATTERN)

    @field_validator("product_id", "preview_ref", "confirmation_ref")
    @classmethod
    def validate_refs(cls, value: str, info) -> str:
        return _bounded(value, name=info.field_name)

    @field_validator("completed_at")
    @classmethod
    def normalize_completed_at(cls, value: datetime) -> datetime:
        return _aware(value, name="completed_at")

    @model_validator(mode="after")
    def derive_identity(self) -> Self:
        _unique_kinds(self.derived_artifact_erasure)
        _derive_identity(
            self,
            prefix="personal_intelligence_deletion_proof",
            id_field="proof_id",
            digest_field="proof_digest",
            exclude={"surviving_derivative_disclosure", "derived_artifact_erasure"},
        )
        return self


__all__ = [
    "BACKUP_NON_REAPPEARANCE_LIMITATION",
    "DERIVED_ARTIFACT_COVERAGE_VERSION",
    "DERIVED_ARTIFACT_ERASURE_ENTRY_VERSION",
    "SURVIVING_DERIVATIVE_DISCLOSURE",
    "WORKSPACE_DERIVED_ARTIFACT_KINDS",
    "DerivedArtifactCoverageV1Alpha1",
    "DerivedArtifactErasureEntryV1Alpha1",
    "derive_erasure_entries",
    "PERSONAL_INTELLIGENCE_DELETE_CONFIRMATION_VERSION",
    "PERSONAL_INTELLIGENCE_DELETE_PREVIEW_REQUEST_VERSION",
    "PERSONAL_INTELLIGENCE_DELETE_PREVIEW_VERSION",
    "PERSONAL_INTELLIGENCE_DELETION_PROOF_VERSION",
    "PERSONAL_INTELLIGENCE_EXPORT_ARTIFACT_VERSION",
    "PERSONAL_INTELLIGENCE_EXPORT_REQUEST_VERSION",
    "PORTABILITY_SCOPE",
    "PersonalIntelligenceDeleteConfirmationV1Alpha1",
    "PersonalIntelligenceDeletePreviewRequestV1Alpha1",
    "PersonalIntelligenceDeletePreviewV1Alpha1",
    "PersonalIntelligenceDeletionProofV1Alpha1",
    "PersonalIntelligenceExportArtifactV1Alpha1",
    "PersonalIntelligenceExportRequestV1Alpha1",
]
