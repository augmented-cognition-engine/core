"""Provider-neutral contracts for destination delivery, export, and effects.

Prepared internal handoffs, delivery, administrative export, and consequential
external effects are deliberately distinct operations.  Every external
operation binds exact current authority and policy evidence.  Receipts are
historical audit material and never reusable bearer authority.
"""

from __future__ import annotations

import re
from datetime import UTC, datetime
from enum import StrEnum
from typing import Literal, Self

from pydantic import ConfigDict, Field, field_validator, model_validator

from ace.core.agent_composition import ExactArtifactReferenceV1Alpha1
from ace.core.contracts import FrozenContract, canonical_hash
from ace.core.runtime_use import (
    AuthenticatedRuntimeContextV1Alpha1,
    AuthorityUseReceiptV1Alpha1,
    CapabilityUseReceiptV1Alpha1,
)
from ace.core.state import GovernedStateHeadPreconditionV1Alpha1

DESTINATION_DEFINITION_VERSION = "ace.core.destination-definition/v1alpha1"
DESTINATION_REVISION_VERSION = "ace.core.destination-revision/v1alpha1"
DESTINATION_POLICY_COORDINATE_VERSION = "ace.core.destination-policy-coordinate/v1alpha1"
EXTERNAL_OPERATION_AUTHORITY_VERSION = "ace.core.external-operation-authority/v1alpha1"
DELIVERY_INTENT_VERSION = "ace.core.destination-delivery-intent/v1alpha1"
DELIVERY_ADMISSION_VERSION = "ace.core.destination-delivery-admission/v1alpha1"
DELIVERY_ATTEMPT_VERSION = "ace.core.destination-delivery-attempt/v1alpha1"
DESTINATION_ACKNOWLEDGMENT_VERSION = "ace.core.destination-acknowledgment/v1alpha1"
DELIVERY_RESULT_VERSION = "ace.core.destination-delivery-result/v1alpha1"
DELIVERY_LOOKUP_VERSION = "ace.core.destination-delivery-lookup/v1alpha1"
ADMINISTRATIVE_EXPORT_MANIFEST_VERSION = "ace.core.administrative-export-manifest/v1alpha1"
PORTABILITY_RECEIPT_VERSION = "ace.core.portability-receipt/v1alpha1"
EXTERNAL_EFFECT_INTENT_VERSION = "ace.core.external-effect-intent/v1alpha1"
EXTERNAL_EFFECT_ADMISSION_VERSION = "ace.core.external-effect-admission/v1alpha1"
EXTERNAL_EFFECT_ATTEMPT_VERSION = "ace.core.external-effect-attempt/v1alpha1"
EXTERNAL_EFFECT_RESULT_VERSION = "ace.core.external-effect-result/v1alpha1"
EXTERNAL_EFFECT_LOOKUP_VERSION = "ace.core.external-effect-lookup/v1alpha1"
EXTERNAL_OPERATION_CANCELLATION_VERSION = "ace.core.external-operation-cancellation/v1alpha1"

_DIGEST = re.compile(r"^sha256:[a-f0-9]{64}$")
_POLICY_KINDS = 6


class _Contract(FrozenContract):
    model_config = ConfigDict(
        extra="forbid",
        frozen=True,
        strict=True,
        revalidate_instances="always",
        validate_default=True,
        allow_inf_nan=False,
    )


def _bounded(value: str, *, name: str, maximum: int = 240) -> str:
    if not value or value != value.strip() or len(value) > maximum:
        raise ValueError(f"{name} must be non-empty, trimmed, and at most {maximum} characters")
    return value


def _aware(value: datetime, *, name: str) -> datetime:
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError(f"{name} must include a timezone")
    return value.astimezone(UTC)


def _digest(value: str, *, name: str) -> str:
    if not _DIGEST.fullmatch(value):
        raise ValueError(f"{name} must use lowercase sha256:<64-hex> syntax")
    return value


def _unique(values: tuple[str, ...], *, name: str) -> tuple[str, ...]:
    normalized = tuple(sorted(_bounded(value, name=name) for value in values))
    if len(normalized) != len(set(normalized)):
        raise ValueError(f"{name} must be unique")
    return normalized


def _identity(instance: _Contract, *, prefix: str, id_field: str, digest_field: str) -> None:
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


def exact_external_reference(value: object) -> ExactArtifactReferenceV1Alpha1:
    contract = str(getattr(value, "contract"))
    for id_field, digest_field in (
        ("destination_id", "destination_digest"),
        ("revision_id", "revision_digest"),
        ("intent_id", "intent_digest"),
        ("admission_id", "admission_digest"),
        ("attempt_id", "attempt_digest"),
        ("acknowledgment_id", "acknowledgment_digest"),
        ("result_id", "result_digest"),
        ("manifest_id", "manifest_digest"),
        ("receipt_id", "receipt_digest"),
        ("lookup_id", "lookup_digest"),
        ("cancellation_id", "cancellation_digest"),
    ):
        item_id = getattr(value, id_field, None)
        item_digest = getattr(value, digest_field, None)
        if item_id is not None and item_digest is not None:
            return ExactArtifactReferenceV1Alpha1(
                artifact_id=str(item_id), artifact_digest=str(item_digest), artifact_contract=contract
            )
    raise ValueError("value does not expose exact external-operation coordinates")


class DestinationLifecycle(StrEnum):
    ACTIVE = "active"
    SUSPENDED = "suspended"
    RETIRED = "retired"


class DestinationPolicyKind(StrEnum):
    CAPABILITY = "capability"
    COMPATIBILITY = "compatibility"
    ENTITLEMENT = "entitlement"
    CONSENT = "consent"
    REDACTION = "redaction"
    DATA_CLASS = "data_class"


class ExternalOperation(StrEnum):
    DELIVERY = "destination_delivery"
    ADMIN_EXPORT = "administrative_export"
    EXTERNAL_EFFECT = "external_effect"


class DeliveryState(StrEnum):
    ACKNOWLEDGED = "acknowledged"
    TIMED_OUT = "timed_out"
    REJECTED = "rejected"
    PARTIAL = "partial"
    DUPLICATE = "duplicate"
    UNKNOWN = "unknown_result"
    CANCELLED = "cancelled"


class EffectState(StrEnum):
    SUCCEEDED = "succeeded"
    REJECTED = "rejected"
    PARTIAL = "partial"
    DUPLICATE = "duplicate"
    UNKNOWN = "unknown_result"
    CANCELLED = "cancelled"


class LookupDisposition(StrEnum):
    FOUND = "found"
    NOT_FOUND = "not_found"
    INDETERMINATE = "indeterminate"


class DestinationPolicyCoordinateV1Alpha1(_Contract):
    contract: Literal["ace.core.destination-policy-coordinate/v1alpha1"] = DESTINATION_POLICY_COORDINATE_VERSION
    kind: DestinationPolicyKind
    policy_ref: str
    state_id: str
    material_digest: str

    @field_validator("policy_ref", "state_id")
    @classmethod
    def validate_refs(cls, value: str, info) -> str:
        return _bounded(value, name=info.field_name)

    @field_validator("material_digest")
    @classmethod
    def validate_digest(cls, value: str) -> str:
        return _digest(value, name="material_digest")


class DestinationDefinitionV1Alpha1(_Contract):
    """Portable destination identity without endpoint or secret material."""

    contract: Literal["ace.core.destination-definition/v1alpha1"] = DESTINATION_DEFINITION_VERSION
    product_id: str
    destination_key: str
    adapter_contract: str
    protocol_refs: tuple[str, ...] = Field(min_length=1, max_length=32)
    capability_refs: tuple[str, ...] = Field(min_length=1, max_length=64)
    recipient_binding_kind: str
    destination_id: str | None = None
    destination_digest: str | None = None

    @field_validator("product_id", "destination_key", "adapter_contract", "recipient_binding_kind")
    @classmethod
    def validate_refs(cls, value: str, info) -> str:
        return _bounded(value, name=info.field_name)

    @field_validator("protocol_refs", "capability_refs")
    @classmethod
    def normalize_refs(cls, value: tuple[str, ...], info) -> tuple[str, ...]:
        return _unique(value, name=info.field_name)

    @field_validator("destination_digest")
    @classmethod
    def validate_optional_digest(cls, value: str | None) -> str | None:
        return _digest(value, name="destination_digest") if value is not None else None

    @model_validator(mode="after")
    def derive_identity(self) -> Self:
        _identity(self, prefix="destination_definition", id_field="destination_id", digest_field="destination_digest")
        return self


class DestinationRevisionV1Alpha1(_Contract):
    contract: Literal["ace.core.destination-revision/v1alpha1"] = DESTINATION_REVISION_VERSION
    definition: ExactArtifactReferenceV1Alpha1
    sequence: int = Field(ge=1)
    prior_revision_id: str | None = None
    lifecycle: DestinationLifecycle
    policies: tuple[DestinationPolicyCoordinateV1Alpha1, ...] = Field(
        min_length=_POLICY_KINDS, max_length=_POLICY_KINDS
    )
    revised_at: datetime
    revision_id: str | None = None
    revision_digest: str | None = None

    @field_validator("prior_revision_id")
    @classmethod
    def validate_prior(cls, value: str | None) -> str | None:
        return _bounded(value, name="prior_revision_id") if value is not None else None

    @field_validator("revised_at")
    @classmethod
    def normalize_time(cls, value: datetime) -> datetime:
        return _aware(value, name="revised_at")

    @field_validator("revision_digest")
    @classmethod
    def validate_optional_digest(cls, value: str | None) -> str | None:
        return _digest(value, name="revision_digest") if value is not None else None

    @model_validator(mode="after")
    def validate_lineage_and_identity(self) -> Self:
        if self.definition.artifact_contract != DESTINATION_DEFINITION_VERSION:
            raise ValueError("destination revision requires an exact destination definition")
        if (self.sequence == 1) != (self.prior_revision_id is None):
            raise ValueError("destination revision lineage must match its sequence")
        kinds = [item.kind for item in self.policies]
        if set(kinds) != set(DestinationPolicyKind) or len(kinds) != len(set(kinds)):
            raise ValueError("destination revision requires each exact policy coordinate once")
        object.__setattr__(self, "policies", tuple(sorted(self.policies, key=lambda item: item.kind.value)))
        _identity(self, prefix="destination_revision", id_field="revision_id", digest_field="revision_digest")
        return self


class ExternalOperationAuthorityV1Alpha1(_Contract):
    """One point-in-time operation-specific current-use resolution."""

    contract: Literal["ace.core.external-operation-authority/v1alpha1"] = EXTERNAL_OPERATION_AUTHORITY_VERSION
    operation: ExternalOperation
    product_id: str
    actor_ref: str
    authenticated_context: AuthenticatedRuntimeContextV1Alpha1
    use_subject: ExactArtifactReferenceV1Alpha1
    destination_revision: ExactArtifactReferenceV1Alpha1 | None
    capability_use: CapabilityUseReceiptV1Alpha1
    authority_use: AuthorityUseReceiptV1Alpha1
    current_heads: tuple[GovernedStateHeadPreconditionV1Alpha1, ...] = Field(min_length=3, max_length=32)
    evaluated_at: datetime
    receipt_id: str | None = None
    receipt_digest: str | None = None

    @field_validator("product_id", "actor_ref")
    @classmethod
    def validate_refs(cls, value: str, info) -> str:
        return _bounded(value, name=info.field_name)

    @field_validator("evaluated_at")
    @classmethod
    def normalize_time(cls, value: datetime) -> datetime:
        return _aware(value, name="evaluated_at")

    @field_validator("receipt_digest")
    @classmethod
    def validate_optional_digest(cls, value: str | None) -> str | None:
        return _digest(value, name="receipt_digest") if value is not None else None

    @field_validator("current_heads")
    @classmethod
    def normalize_heads(
        cls, value: tuple[GovernedStateHeadPreconditionV1Alpha1, ...]
    ) -> tuple[GovernedStateHeadPreconditionV1Alpha1, ...]:
        keys = [(item.state_kind, item.product_id, item.state_id) for item in value]
        if len(keys) != len(set(keys)):
            raise ValueError("current external-operation heads must be unique")
        return tuple(sorted(value, key=lambda item: (item.state_kind, item.product_id, item.state_id)))

    @model_validator(mode="after")
    def validate_scope_and_identity(self) -> Self:
        if (
            self.authenticated_context.product_id != self.product_id
            or self.authenticated_context.actor_ref != self.actor_ref
            or self.capability_use.product_id != self.product_id
            or self.authority_use.product_id != self.product_id
            or self.capability_use.operation != self.operation.value
            or self.authority_use.operation != self.operation.value
            or self.capability_use.use_subject_ref != self.use_subject.artifact_id
            or self.capability_use.use_subject_digest != self.use_subject.artifact_digest
            or self.authority_use.use_subject_ref != self.use_subject.artifact_id
            or self.authority_use.use_subject_digest != self.use_subject.artifact_digest
            or any(item.product_id != self.product_id for item in self.current_heads)
        ):
            raise ValueError("external-operation authority crossed exact operation, subject, or product scope")
        required = {
            (
                self.capability_use.state_head_precondition.state_kind,
                self.capability_use.state_head_precondition.state_id,
            ),
            (
                self.authority_use.state_head_precondition.state_kind,
                self.authority_use.state_head_precondition.state_id,
            ),
        }
        present = {(item.state_kind, item.state_id) for item in self.current_heads}
        if not required.issubset(present):
            raise ValueError("external-operation authority omits current capability or grant head")
        if not (
            self.authenticated_context.authenticated_at <= self.evaluated_at < self.authenticated_context.expires_at
        ):
            raise ValueError("external-operation authority falls outside authenticated context")
        _identity(self, prefix="external_operation_authority", id_field="receipt_id", digest_field="receipt_digest")
        return self

    @property
    def reusable_authority(self) -> Literal[False]:
        return False


class DestinationDeliveryIntentV1Alpha1(_Contract):
    contract: Literal["ace.core.destination-delivery-intent/v1alpha1"] = DELIVERY_INTENT_VERSION
    product_id: str
    authenticated_context: AuthenticatedRuntimeContextV1Alpha1
    prepared_handoff: ExactArtifactReferenceV1Alpha1
    destination_revision: ExactArtifactReferenceV1Alpha1
    recipient_ref: str
    payload_artifacts: tuple[ExactArtifactReferenceV1Alpha1, ...] = Field(min_length=1, max_length=256)
    payload_digest: str
    idempotency_key: str
    retry_policy_ref: str
    cancellation_ref: str
    requested_at: datetime
    expires_at: datetime
    intent_id: str | None = None
    intent_digest: str | None = None

    @field_validator("product_id", "recipient_ref", "idempotency_key", "retry_policy_ref", "cancellation_ref")
    @classmethod
    def validate_refs(cls, value: str, info) -> str:
        return _bounded(value, name=info.field_name)

    @field_validator("payload_digest", "intent_digest")
    @classmethod
    def validate_digests(cls, value: str | None, info) -> str | None:
        return _digest(value, name=info.field_name) if value is not None else None

    @field_validator("requested_at", "expires_at")
    @classmethod
    def normalize_times(cls, value: datetime, info) -> datetime:
        return _aware(value, name=info.field_name)

    @model_validator(mode="after")
    def validate_scope_and_identity(self) -> Self:
        if self.authenticated_context.product_id != self.product_id:
            raise ValueError("delivery intent crossed authenticated product scope")
        if self.prepared_handoff.artifact_contract != "ace.application.prepared-lifecycle-delivery/v1alpha1":
            raise ValueError("delivery intent requires an exact AC3 prepared handoff")
        if self.destination_revision.artifact_contract != DESTINATION_REVISION_VERSION:
            raise ValueError("delivery intent requires an exact destination revision")
        if not (self.authenticated_context.authenticated_at <= self.requested_at < self.expires_at):
            raise ValueError("delivery intent has an invalid authenticated validity window")
        if self.expires_at > self.authenticated_context.expires_at:
            raise ValueError("delivery intent cannot outlive authenticated context")
        identities = [
            (item.artifact_contract, item.artifact_id, item.artifact_digest) for item in self.payload_artifacts
        ]
        if len(identities) != len(set(identities)):
            raise ValueError("delivery payload artifacts must be unique")
        _identity(self, prefix="destination_delivery_intent", id_field="intent_id", digest_field="intent_digest")
        return self


class DestinationDeliveryAdmissionV1Alpha1(_Contract):
    contract: Literal["ace.core.destination-delivery-admission/v1alpha1"] = DELIVERY_ADMISSION_VERSION
    intent: DestinationDeliveryIntentV1Alpha1
    post_preparation_authority: ExternalOperationAuthorityV1Alpha1
    admitted_at: datetime
    admission_id: str | None = None
    admission_digest: str | None = None

    @field_validator("admitted_at")
    @classmethod
    def normalize_time(cls, value: datetime) -> datetime:
        return _aware(value, name="admitted_at")

    @field_validator("admission_digest")
    @classmethod
    def validate_optional_digest(cls, value: str | None) -> str | None:
        return _digest(value, name="admission_digest") if value is not None else None

    @model_validator(mode="after")
    def validate_authority_and_identity(self) -> Self:
        authority = self.post_preparation_authority
        if (
            authority.operation is not ExternalOperation.DELIVERY
            or authority.use_subject != exact_external_reference(self.intent)
            or authority.destination_revision != self.intent.destination_revision
            or authority.product_id != self.intent.product_id
            or self.admitted_at < authority.evaluated_at
            or self.admitted_at >= self.intent.expires_at
        ):
            raise ValueError("delivery admission lacks exact fresh delivery authority")
        _identity(
            self, prefix="destination_delivery_admission", id_field="admission_id", digest_field="admission_digest"
        )
        return self


class DestinationDeliveryAttemptV1Alpha1(_Contract):
    contract: Literal["ace.core.destination-delivery-attempt/v1alpha1"] = DELIVERY_ATTEMPT_VERSION
    admission: ExactArtifactReferenceV1Alpha1
    pre_send_authority: ExternalOperationAuthorityV1Alpha1
    attempt: int = Field(ge=1, le=64)
    idempotency_key: str
    payload_digest: str
    attempted_at: datetime
    external_send_attempted: Literal[True] = True
    external_effect_authorized: Literal[False] = False
    attempt_id: str | None = None
    attempt_digest: str | None = None

    @field_validator("idempotency_key")
    @classmethod
    def validate_ref(cls, value: str) -> str:
        return _bounded(value, name="idempotency_key")

    @field_validator("payload_digest", "attempt_digest")
    @classmethod
    def validate_digests(cls, value: str | None, info) -> str | None:
        return _digest(value, name=info.field_name) if value is not None else None

    @field_validator("attempted_at")
    @classmethod
    def normalize_time(cls, value: datetime) -> datetime:
        return _aware(value, name="attempted_at")

    @model_validator(mode="after")
    def validate_authority_and_identity(self) -> Self:
        if self.pre_send_authority.operation is not ExternalOperation.DELIVERY:
            raise ValueError("delivery attempt cannot use export or external-effect authority")
        if self.attempted_at < self.pre_send_authority.evaluated_at:
            raise ValueError("delivery attempt predates immediate pre-send revalidation")
        _identity(self, prefix="destination_delivery_attempt", id_field="attempt_id", digest_field="attempt_digest")
        return self


class DestinationAcknowledgmentV1Alpha1(_Contract):
    contract: Literal["ace.core.destination-acknowledgment/v1alpha1"] = DESTINATION_ACKNOWLEDGMENT_VERSION
    delivery_attempt: ExactArtifactReferenceV1Alpha1
    destination_revision: ExactArtifactReferenceV1Alpha1
    recipient_ref: str
    idempotency_key: str
    payload_digest: str
    acknowledgment_ref: str
    acknowledged_at: datetime
    truth_proven: Literal[False] = False
    benefit_proven: Literal[False] = False
    downstream_execution_proven: Literal[False] = False
    acknowledgment_id: str | None = None
    acknowledgment_digest: str | None = None

    @field_validator("recipient_ref", "idempotency_key", "acknowledgment_ref")
    @classmethod
    def validate_refs(cls, value: str, info) -> str:
        return _bounded(value, name=info.field_name)

    @field_validator("payload_digest", "acknowledgment_digest")
    @classmethod
    def validate_digests(cls, value: str | None, info) -> str | None:
        return _digest(value, name=info.field_name) if value is not None else None

    @field_validator("acknowledged_at")
    @classmethod
    def normalize_time(cls, value: datetime) -> datetime:
        return _aware(value, name="acknowledged_at")

    @model_validator(mode="after")
    def derive_identity(self) -> Self:
        _identity(
            self,
            prefix="destination_acknowledgment",
            id_field="acknowledgment_id",
            digest_field="acknowledgment_digest",
        )
        return self


class DestinationDeliveryResultV1Alpha1(_Contract):
    contract: Literal["ace.core.destination-delivery-result/v1alpha1"] = DELIVERY_RESULT_VERSION
    attempt: ExactArtifactReferenceV1Alpha1
    state: DeliveryState
    acknowledgment: DestinationAcknowledgmentV1Alpha1 | None = None
    failure_code: str | None = None
    retry_after_lookup: bool = False
    completed_at: datetime
    result_id: str | None = None
    result_digest: str | None = None

    @field_validator("failure_code")
    @classmethod
    def validate_failure(cls, value: str | None) -> str | None:
        return _bounded(value, name="failure_code", maximum=120) if value is not None else None

    @field_validator("completed_at")
    @classmethod
    def normalize_time(cls, value: datetime) -> datetime:
        return _aware(value, name="completed_at")

    @field_validator("result_digest")
    @classmethod
    def validate_optional_digest(cls, value: str | None) -> str | None:
        return _digest(value, name="result_digest") if value is not None else None

    @model_validator(mode="after")
    def validate_state_and_identity(self) -> Self:
        if self.state is DeliveryState.ACKNOWLEDGED and self.acknowledgment is None:
            raise ValueError("acknowledged delivery requires exact destination acknowledgment")
        if (
            self.state is not DeliveryState.ACKNOWLEDGED
            and self.state is not DeliveryState.DUPLICATE
            and not self.failure_code
        ):
            raise ValueError("non-acknowledged delivery requires an explicit failure code")
        if self.state is DeliveryState.UNKNOWN and not self.retry_after_lookup:
            raise ValueError("unknown delivery result requires lookup before retry")
        if self.state is not DeliveryState.UNKNOWN and self.retry_after_lookup:
            raise ValueError("retry-after-lookup applies only to unknown delivery results")
        _identity(self, prefix="destination_delivery_result", id_field="result_id", digest_field="result_digest")
        return self


class DestinationDeliveryLookupV1Alpha1(_Contract):
    contract: Literal["ace.core.destination-delivery-lookup/v1alpha1"] = DELIVERY_LOOKUP_VERSION
    attempt: ExactArtifactReferenceV1Alpha1
    idempotency_key: str
    disposition: LookupDisposition
    resolved_result: DestinationDeliveryResultV1Alpha1 | None = None
    looked_up_at: datetime
    permits_retry: bool = False
    lookup_id: str | None = None
    lookup_digest: str | None = None

    @field_validator("idempotency_key")
    @classmethod
    def validate_ref(cls, value: str) -> str:
        return _bounded(value, name="idempotency_key")

    @field_validator("looked_up_at")
    @classmethod
    def normalize_time(cls, value: datetime) -> datetime:
        return _aware(value, name="looked_up_at")

    @field_validator("lookup_digest")
    @classmethod
    def validate_optional_digest(cls, value: str | None) -> str | None:
        return _digest(value, name="lookup_digest") if value is not None else None

    @model_validator(mode="after")
    def validate_disposition_and_identity(self) -> Self:
        if (self.disposition is LookupDisposition.FOUND) != (self.resolved_result is not None):
            raise ValueError("delivery lookup result must exactly match found disposition")
        if self.permits_retry and self.disposition is not LookupDisposition.NOT_FOUND:
            raise ValueError("only a conclusive not-found delivery lookup can permit retry")
        _identity(self, prefix="destination_delivery_lookup", id_field="lookup_id", digest_field="lookup_digest")
        return self


class AdministrativeExportManifestV1Alpha1(_Contract):
    contract: Literal["ace.core.administrative-export-manifest/v1alpha1"] = ADMINISTRATIVE_EXPORT_MANIFEST_VERSION
    product_id: str
    authenticated_context: AuthenticatedRuntimeContextV1Alpha1
    included: tuple[ExactArtifactReferenceV1Alpha1, ...] = Field(default_factory=tuple, max_length=1024)
    omitted_refs: tuple[str, ...] = Field(default_factory=tuple, max_length=1024)
    redacted_refs: tuple[str, ...] = Field(default_factory=tuple, max_length=1024)
    retention_policy_ref: str
    erasure_dependency_refs: tuple[str, ...] = Field(default_factory=tuple, max_length=256)
    data_class_policy_ref: str
    checksum: str
    requested_at: datetime
    expires_at: datetime
    manifest_id: str | None = None
    manifest_digest: str | None = None

    @field_validator("product_id", "retention_policy_ref", "data_class_policy_ref")
    @classmethod
    def validate_refs(cls, value: str, info) -> str:
        return _bounded(value, name=info.field_name)

    @field_validator("omitted_refs", "redacted_refs", "erasure_dependency_refs")
    @classmethod
    def normalize_refs(cls, value: tuple[str, ...], info) -> tuple[str, ...]:
        return _unique(value, name=info.field_name)

    @field_validator("checksum", "manifest_digest")
    @classmethod
    def validate_digests(cls, value: str | None, info) -> str | None:
        return _digest(value, name=info.field_name) if value is not None else None

    @field_validator("requested_at", "expires_at")
    @classmethod
    def normalize_times(cls, value: datetime, info) -> datetime:
        return _aware(value, name=info.field_name)

    @model_validator(mode="after")
    def validate_scope_and_identity(self) -> Self:
        if self.authenticated_context.product_id != self.product_id:
            raise ValueError("administrative export crossed authenticated product scope")
        if not (self.authenticated_context.authenticated_at <= self.requested_at < self.expires_at):
            raise ValueError("administrative export has an invalid validity window")
        if self.expires_at > self.authenticated_context.expires_at:
            raise ValueError("administrative export cannot outlive authenticated context")
        included_ids = {item.artifact_id for item in self.included}
        if included_ids.intersection(self.omitted_refs) or included_ids.intersection(self.redacted_refs):
            raise ValueError("export coordinates cannot be both included and omitted or redacted")
        _identity(self, prefix="administrative_export_manifest", id_field="manifest_id", digest_field="manifest_digest")
        return self


class PortabilityReceiptV1Alpha1(_Contract):
    contract: Literal["ace.core.portability-receipt/v1alpha1"] = PORTABILITY_RECEIPT_VERSION
    manifest: ExactArtifactReferenceV1Alpha1
    authority: ExternalOperationAuthorityV1Alpha1
    artifact_checksum: str
    included_count: int = Field(ge=0)
    omitted_count: int = Field(ge=0)
    redacted_count: int = Field(ge=0)
    created_at: datetime
    delivery_authority: Literal[False] = False
    runtime_authority: Literal[False] = False
    external_send_occurred: Literal[False] = False
    receipt_id: str | None = None
    receipt_digest: str | None = None

    @field_validator("artifact_checksum", "receipt_digest")
    @classmethod
    def validate_digests(cls, value: str | None, info) -> str | None:
        return _digest(value, name=info.field_name) if value is not None else None

    @field_validator("created_at")
    @classmethod
    def normalize_time(cls, value: datetime) -> datetime:
        return _aware(value, name="created_at")

    @model_validator(mode="after")
    def validate_authority_and_identity(self) -> Self:
        if self.authority.operation is not ExternalOperation.ADMIN_EXPORT:
            raise ValueError("portability receipt requires distinct administrative-export authority")
        if self.authority.use_subject != self.manifest:
            raise ValueError("portability authority does not bind the exact export manifest")
        _identity(self, prefix="portability_receipt", id_field="receipt_id", digest_field="receipt_digest")
        return self


class ExternalEffectIntentV1Alpha1(_Contract):
    contract: Literal["ace.core.external-effect-intent/v1alpha1"] = EXTERNAL_EFFECT_INTENT_VERSION
    product_id: str
    authenticated_context: AuthenticatedRuntimeContextV1Alpha1
    destination_revision: ExactArtifactReferenceV1Alpha1
    recipient_ref: str
    effect_type: str
    parameters_digest: str
    idempotency_key: str
    retry_policy_ref: str
    cancellation_ref: str
    requested_at: datetime
    expires_at: datetime
    intent_id: str | None = None
    intent_digest: str | None = None

    @field_validator(
        "product_id", "recipient_ref", "effect_type", "idempotency_key", "retry_policy_ref", "cancellation_ref"
    )
    @classmethod
    def validate_refs(cls, value: str, info) -> str:
        return _bounded(value, name=info.field_name)

    @field_validator("parameters_digest", "intent_digest")
    @classmethod
    def validate_digests(cls, value: str | None, info) -> str | None:
        return _digest(value, name=info.field_name) if value is not None else None

    @field_validator("requested_at", "expires_at")
    @classmethod
    def normalize_times(cls, value: datetime, info) -> datetime:
        return _aware(value, name=info.field_name)

    @model_validator(mode="after")
    def validate_scope_and_identity(self) -> Self:
        if self.authenticated_context.product_id != self.product_id:
            raise ValueError("external effect crossed authenticated product scope")
        if self.destination_revision.artifact_contract != DESTINATION_REVISION_VERSION:
            raise ValueError("external effect requires an exact destination revision")
        if not (self.authenticated_context.authenticated_at <= self.requested_at < self.expires_at):
            raise ValueError("external effect has an invalid validity window")
        if self.expires_at > self.authenticated_context.expires_at:
            raise ValueError("external effect cannot outlive authenticated context")
        _identity(self, prefix="external_effect_intent", id_field="intent_id", digest_field="intent_digest")
        return self


class ExternalEffectAdmissionV1Alpha1(_Contract):
    contract: Literal["ace.core.external-effect-admission/v1alpha1"] = EXTERNAL_EFFECT_ADMISSION_VERSION
    intent: ExternalEffectIntentV1Alpha1
    post_preparation_authority: ExternalOperationAuthorityV1Alpha1
    admitted_at: datetime
    admission_id: str | None = None
    admission_digest: str | None = None

    @field_validator("admitted_at")
    @classmethod
    def normalize_time(cls, value: datetime) -> datetime:
        return _aware(value, name="admitted_at")

    @field_validator("admission_digest")
    @classmethod
    def validate_optional_digest(cls, value: str | None) -> str | None:
        return _digest(value, name="admission_digest") if value is not None else None

    @model_validator(mode="after")
    def validate_authority_and_identity(self) -> Self:
        authority = self.post_preparation_authority
        if (
            authority.operation is not ExternalOperation.EXTERNAL_EFFECT
            or authority.use_subject != exact_external_reference(self.intent)
            or authority.destination_revision != self.intent.destination_revision
            or authority.product_id != self.intent.product_id
            or self.admitted_at < authority.evaluated_at
            or self.admitted_at >= self.intent.expires_at
        ):
            raise ValueError("effect admission lacks exact fresh external-effect authority")
        _identity(self, prefix="external_effect_admission", id_field="admission_id", digest_field="admission_digest")
        return self


class ExternalEffectAttemptV1Alpha1(_Contract):
    contract: Literal["ace.core.external-effect-attempt/v1alpha1"] = EXTERNAL_EFFECT_ATTEMPT_VERSION
    admission: ExactArtifactReferenceV1Alpha1
    pre_effect_authority: ExternalOperationAuthorityV1Alpha1
    attempt: int = Field(ge=1, le=64)
    idempotency_key: str
    parameters_digest: str
    attempted_at: datetime
    consequential_effect_attempted: Literal[True] = True
    attempt_id: str | None = None
    attempt_digest: str | None = None

    @field_validator("idempotency_key")
    @classmethod
    def validate_ref(cls, value: str) -> str:
        return _bounded(value, name="idempotency_key")

    @field_validator("parameters_digest", "attempt_digest")
    @classmethod
    def validate_digests(cls, value: str | None, info) -> str | None:
        return _digest(value, name=info.field_name) if value is not None else None

    @field_validator("attempted_at")
    @classmethod
    def normalize_time(cls, value: datetime) -> datetime:
        return _aware(value, name="attempted_at")

    @model_validator(mode="after")
    def validate_authority_and_identity(self) -> Self:
        if self.pre_effect_authority.operation is not ExternalOperation.EXTERNAL_EFFECT:
            raise ValueError("effect attempt cannot use delivery or export authority")
        if self.attempted_at < self.pre_effect_authority.evaluated_at:
            raise ValueError("effect attempt predates immediate pre-effect revalidation")
        _identity(self, prefix="external_effect_attempt", id_field="attempt_id", digest_field="attempt_digest")
        return self


class ExternalEffectResultV1Alpha1(_Contract):
    contract: Literal["ace.core.external-effect-result/v1alpha1"] = EXTERNAL_EFFECT_RESULT_VERSION
    attempt: ExactArtifactReferenceV1Alpha1
    state: EffectState
    result_digest_value: str | None = None
    failure_code: str | None = None
    retry_after_lookup: bool = False
    completed_at: datetime
    result_id: str | None = None
    result_digest: str | None = None

    @field_validator("result_digest_value", "result_digest")
    @classmethod
    def validate_digests(cls, value: str | None, info) -> str | None:
        return _digest(value, name=info.field_name) if value is not None else None

    @field_validator("failure_code")
    @classmethod
    def validate_failure(cls, value: str | None) -> str | None:
        return _bounded(value, name="failure_code", maximum=120) if value is not None else None

    @field_validator("completed_at")
    @classmethod
    def normalize_time(cls, value: datetime) -> datetime:
        return _aware(value, name="completed_at")

    @model_validator(mode="after")
    def validate_state_and_identity(self) -> Self:
        if self.state is EffectState.SUCCEEDED and self.result_digest_value is None:
            raise ValueError("successful effect requires exact result digest")
        if (
            self.state in {EffectState.REJECTED, EffectState.PARTIAL, EffectState.CANCELLED, EffectState.UNKNOWN}
            and not self.failure_code
        ):
            raise ValueError("non-success external effect requires explicit failure code")
        if self.state is EffectState.UNKNOWN and not self.retry_after_lookup:
            raise ValueError("unknown effect result forbids blind retry and requires lookup")
        if self.state is not EffectState.UNKNOWN and self.retry_after_lookup:
            raise ValueError("retry-after-lookup applies only to unknown effect results")
        _identity(self, prefix="external_effect_result", id_field="result_id", digest_field="result_digest")
        return self


class ExternalEffectLookupV1Alpha1(_Contract):
    contract: Literal["ace.core.external-effect-lookup/v1alpha1"] = EXTERNAL_EFFECT_LOOKUP_VERSION
    attempt: ExactArtifactReferenceV1Alpha1
    idempotency_key: str
    disposition: LookupDisposition
    resolved_result: ExternalEffectResultV1Alpha1 | None = None
    looked_up_at: datetime
    permits_retry: bool = False
    lookup_id: str | None = None
    lookup_digest: str | None = None

    @field_validator("idempotency_key")
    @classmethod
    def validate_ref(cls, value: str) -> str:
        return _bounded(value, name="idempotency_key")

    @field_validator("looked_up_at")
    @classmethod
    def normalize_time(cls, value: datetime) -> datetime:
        return _aware(value, name="looked_up_at")

    @field_validator("lookup_digest")
    @classmethod
    def validate_optional_digest(cls, value: str | None) -> str | None:
        return _digest(value, name="lookup_digest") if value is not None else None

    @model_validator(mode="after")
    def validate_disposition_and_identity(self) -> Self:
        if (self.disposition is LookupDisposition.FOUND) != (self.resolved_result is not None):
            raise ValueError("effect lookup result must exactly match found disposition")
        if self.permits_retry and self.disposition is not LookupDisposition.NOT_FOUND:
            raise ValueError("only a conclusive not-found lookup can permit retry")
        _identity(self, prefix="external_effect_lookup", id_field="lookup_id", digest_field="lookup_digest")
        return self


class ExternalOperationCancellationV1Alpha1(_Contract):
    contract: Literal["ace.core.external-operation-cancellation/v1alpha1"] = EXTERNAL_OPERATION_CANCELLATION_VERSION
    operation: ExternalOperation
    subject: ExactArtifactReferenceV1Alpha1
    cancellation_ref: str
    actor_ref: str
    cancelled_at: datetime
    cancellation_id: str | None = None
    cancellation_digest: str | None = None

    @field_validator("cancellation_ref", "actor_ref")
    @classmethod
    def validate_refs(cls, value: str, info) -> str:
        return _bounded(value, name=info.field_name)

    @field_validator("cancelled_at")
    @classmethod
    def normalize_time(cls, value: datetime) -> datetime:
        return _aware(value, name="cancelled_at")

    @field_validator("cancellation_digest")
    @classmethod
    def validate_optional_digest(cls, value: str | None) -> str | None:
        return _digest(value, name="cancellation_digest") if value is not None else None

    @model_validator(mode="after")
    def derive_identity(self) -> Self:
        _identity(
            self,
            prefix="external_operation_cancellation",
            id_field="cancellation_id",
            digest_field="cancellation_digest",
        )
        return self


__all__ = [
    "AdministrativeExportManifestV1Alpha1",
    "DeliveryState",
    "DestinationAcknowledgmentV1Alpha1",
    "DestinationDefinitionV1Alpha1",
    "DestinationDeliveryAdmissionV1Alpha1",
    "DestinationDeliveryAttemptV1Alpha1",
    "DestinationDeliveryIntentV1Alpha1",
    "DestinationDeliveryLookupV1Alpha1",
    "DestinationDeliveryResultV1Alpha1",
    "DestinationLifecycle",
    "DestinationPolicyCoordinateV1Alpha1",
    "DestinationPolicyKind",
    "DestinationRevisionV1Alpha1",
    "EffectState",
    "ExternalEffectAdmissionV1Alpha1",
    "ExternalEffectAttemptV1Alpha1",
    "ExternalEffectIntentV1Alpha1",
    "ExternalEffectLookupV1Alpha1",
    "ExternalEffectResultV1Alpha1",
    "ExternalOperation",
    "ExternalOperationAuthorityV1Alpha1",
    "ExternalOperationCancellationV1Alpha1",
    "LookupDisposition",
    "PortabilityReceiptV1Alpha1",
    "exact_external_reference",
]
