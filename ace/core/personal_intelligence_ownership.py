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
        _derive_identity(
            self,
            prefix="personal_intelligence_delete_preview",
            id_field="preview_id",
            digest_field="preview_digest",
            exclude={"confirmation_digest"},
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
        _derive_identity(
            self,
            prefix="personal_intelligence_deletion_proof",
            id_field="proof_id",
            digest_field="proof_digest",
        )
        return self


__all__ = [
    "BACKUP_NON_REAPPEARANCE_LIMITATION",
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
