"""Internal AC2 runtime-authority seam for governed task composition.

The public task request does not carry any of this material.  Hosts construct
authentication evidence after cryptographic verification and resolve current
governed heads immediately before planning and again immediately before a
participant is executed.  Every receipt in this module is historical evidence,
never reusable authority.
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Literal, Protocol, Self

from pydantic import ConfigDict, Field, field_validator, model_validator

from ace.core.agent_composition import (
    AuthorityCoordinateV1Alpha1,
    ExactArtifactReferenceV1Alpha1,
    StageRunManifestV1Alpha1,
)
from ace.core.contracts import FrozenContract, canonical_hash
from ace.core.reasoning import ReasoningExecutionBindingV1Alpha1
from ace.core.runtime_use import (
    AuthenticatedRuntimeContextV1Alpha1,
    AuthorityUseReceiptV1Alpha1,
    CapabilityUseReceiptV1Alpha1,
)
from ace.core.state import GovernedStateHeadPreconditionV1Alpha1

TASK_AUTHENTICATION_RECEIPT_VERSION = "ace.application.task-authentication-receipt/v1alpha1"
COMPOSITION_AUTHORITY_RESOLUTION_VERSION = "ace.application.composition-authority-resolution/v1alpha1"


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


def _bounded(value: str, name: str) -> str:
    if not value or value != value.strip() or len(value) > 240:
        raise ValueError(f"{name} must be a bounded stable reference")
    return value


def _digest(value: str, name: str) -> str:
    if len(value) != 71 or not value.startswith("sha256:"):
        raise ValueError(f"{name} must use sha256:<64-hex> syntax")
    try:
        int(value[7:], 16)
    except ValueError as exc:
        raise ValueError(f"{name} must use sha256:<64-hex> syntax") from exc
    if value != value.lower():
        raise ValueError(f"{name} must use sha256:<64-hex> syntax")
    return value


def _identity(instance: _StrictFrozen, prefix: str, id_field: str, digest_field: str) -> None:
    material = instance.model_dump(mode="json", exclude={id_field, digest_field})
    digest = canonical_hash(material)
    expected_id = f"{prefix}:{digest[:32]}"
    expected_digest = f"sha256:{digest}"
    supplied_id = getattr(instance, id_field)
    supplied_digest = getattr(instance, digest_field)
    if supplied_id is not None and supplied_id != expected_id:
        raise ValueError(f"{id_field} does not match exact material")
    if supplied_digest is not None and supplied_digest != expected_digest:
        raise ValueError(f"{digest_field} does not match exact material")
    object.__setattr__(instance, id_field, expected_id)
    object.__setattr__(instance, digest_field, expected_digest)


class TaskAuthenticationReceiptV1Alpha1(_StrictFrozen):
    """Opaque append-only proof of one successful host JWT verification."""

    contract: Literal["ace.application.task-authentication-receipt/v1alpha1"] = (
        TASK_AUTHENTICATION_RECEIPT_VERSION
    )
    product_id: str
    actor_ref: str
    verification_policy_ref: str
    authenticated_at: datetime
    expires_at: datetime
    credential_fingerprint: str | None = Field(default=None, pattern=r"^sha256:[a-f0-9]{64}$")
    receipt_id: str | None = None
    receipt_digest: str | None = None

    @field_validator("product_id", "actor_ref", "verification_policy_ref")
    @classmethod
    def validate_refs(cls, value: str, info) -> str:
        return _bounded(value, info.field_name)

    @field_validator("authenticated_at", "expires_at")
    @classmethod
    def validate_times(cls, value: datetime, info) -> datetime:
        return _aware(value, info.field_name)

    @field_validator("receipt_digest")
    @classmethod
    def validate_digest(cls, value: str | None) -> str | None:
        return _digest(value, "receipt_digest") if value is not None else None

    @model_validator(mode="after")
    def derive_identity(self) -> Self:
        if self.expires_at <= self.authenticated_at:
            raise ValueError("authentication evidence must have a positive validity window")
        _identity(self, "task_authentication_receipt", "receipt_id", "receipt_digest")
        return self

    def runtime_context(self) -> AuthenticatedRuntimeContextV1Alpha1:
        return AuthenticatedRuntimeContextV1Alpha1(
            product_id=self.product_id,
            actor_ref=self.actor_ref,
            authentication_receipt_ref=str(self.receipt_id),
            authentication_receipt_digest=str(self.receipt_digest),
            authenticated_at=self.authenticated_at,
            expires_at=self.expires_at,
        )


class CompositionAuthorityResolutionReceiptV1Alpha1(_StrictFrozen):
    """Content-addressed evidence binding AC1 coordinates to current-use receipts."""

    contract: Literal["ace.application.composition-authority-resolution/v1alpha1"] = (
        COMPOSITION_AUTHORITY_RESOLUTION_VERSION
    )
    phase: Literal["planning", "pre_execution"]
    product_id: str
    actor_ref: str
    participant_principal_ref: str
    use_subject: ExactArtifactReferenceV1Alpha1
    authentication_receipt_ref: str
    execution_binding: ExactArtifactReferenceV1Alpha1
    capability_use: ExactArtifactReferenceV1Alpha1
    authority_use: tuple[ExactArtifactReferenceV1Alpha1, ...] = Field(min_length=1, max_length=32)
    authority_coordinates: tuple[AuthorityCoordinateV1Alpha1, ...] = Field(min_length=1, max_length=32)
    current_heads: tuple[GovernedStateHeadPreconditionV1Alpha1, ...] = Field(min_length=3, max_length=64)
    evaluated_at: datetime
    receipt_id: str | None = None
    receipt_digest: str | None = None

    @field_validator("product_id", "actor_ref", "participant_principal_ref", "authentication_receipt_ref")
    @classmethod
    def validate_refs(cls, value: str, info) -> str:
        return _bounded(value, info.field_name)

    @field_validator("evaluated_at")
    @classmethod
    def validate_time(cls, value: datetime) -> datetime:
        return _aware(value, "evaluated_at")

    @field_validator("receipt_digest")
    @classmethod
    def validate_receipt_digest(cls, value: str | None) -> str | None:
        return _digest(value, "receipt_digest") if value is not None else None

    @field_validator("authority_use")
    @classmethod
    def normalize_authority_use(
        cls, value: tuple[ExactArtifactReferenceV1Alpha1, ...]
    ) -> tuple[ExactArtifactReferenceV1Alpha1, ...]:
        identities = [(item.artifact_contract, item.artifact_id, item.artifact_digest) for item in value]
        if len(identities) != len(set(identities)):
            raise ValueError("authority-use references must be unique")
        return tuple(sorted(value, key=lambda item: (item.artifact_contract, item.artifact_id)))

    @field_validator("current_heads")
    @classmethod
    def normalize_heads(
        cls, value: tuple[GovernedStateHeadPreconditionV1Alpha1, ...]
    ) -> tuple[GovernedStateHeadPreconditionV1Alpha1, ...]:
        keys = [(item.state_kind, item.product_id, item.state_id) for item in value]
        if len(keys) != len(set(keys)):
            raise ValueError("each current governed head may appear only once")
        return tuple(sorted(value, key=lambda item: (item.state_kind, item.product_id, item.state_id)))

    @model_validator(mode="after")
    def validate_scope_and_identity(self) -> Self:
        if any(item.product_id != self.product_id for item in self.authority_coordinates):
            raise ValueError("authority resolution crossed product scope")
        if any(item.principal_ref != self.participant_principal_ref for item in self.authority_coordinates):
            raise ValueError("authority resolution crossed participant principal")
        forbidden = "ace.application.domain-activation-commit-reference/v1alpha2"
        references = (self.use_subject, self.execution_binding, self.capability_use, *self.authority_use)
        if any(item.artifact_contract == forbidden for item in references):
            raise ValueError("historical activation references cannot satisfy runtime authority")
        _identity(self, "composition_authority_resolution", "receipt_id", "receipt_digest")
        return self


class ReasoningCompositionRuntimeAuthorityBundle(_StrictFrozen):
    authenticated_context: AuthenticatedRuntimeContextV1Alpha1
    execution_binding: ReasoningExecutionBindingV1Alpha1
    capability_use: CapabilityUseReceiptV1Alpha1
    authority_use: tuple[AuthorityUseReceiptV1Alpha1, ...] = Field(min_length=1, max_length=32)
    authority_coordinates: tuple[AuthorityCoordinateV1Alpha1, ...] = Field(min_length=1, max_length=32)
    current_heads: tuple[GovernedStateHeadPreconditionV1Alpha1, ...] = Field(min_length=3, max_length=64)
    resolution_receipt: CompositionAuthorityResolutionReceiptV1Alpha1

    @model_validator(mode="after")
    def validate_exact_bundle(self) -> Self:
        receipt = self.resolution_receipt
        if (
            receipt.product_id != self.authenticated_context.product_id
            or receipt.actor_ref != self.authenticated_context.actor_ref
            or receipt.authentication_receipt_ref != self.authenticated_context.authentication_receipt_ref
        ):
            raise ValueError("runtime authority bundle crossed authenticated scope")
        binding_ref = exact_reference(self.execution_binding)
        capability_ref = exact_reference(self.capability_use)
        authority_refs = tuple(exact_reference(item) for item in self.authority_use)
        if receipt.execution_binding != binding_ref or receipt.capability_use != capability_ref:
            raise ValueError("resolution receipt does not bind exact execution evidence")
        if set(receipt.authority_use) != set(authority_refs):
            raise ValueError("resolution receipt does not bind exact authority evidence")
        if receipt.authority_coordinates != self.authority_coordinates:
            raise ValueError("resolution receipt does not bind exact AC1 coordinates")
        if receipt.current_heads != self.current_heads:
            raise ValueError("resolution receipt does not bind exact current heads")
        grants = {(item.authority, item.grant_ref) for item in self.authority_use}
        if any((item.authority_class.value, item.grant_ref) not in grants for item in self.authority_coordinates):
            raise ValueError("AC1 authority coordinate lacks an exact current-use receipt")
        return self


def exact_reference(value: object) -> ExactArtifactReferenceV1Alpha1:
    contract = str(getattr(value, "contract"))
    candidates = (
        ("binding_id", "binding_digest"),
        ("receipt_id", "receipt_digest"),
        ("contract_id", "contract_digest"),
        ("composition_plan_id", "composition_plan_digest"),
        ("manifest_id", "manifest_digest"),
    )
    for id_field, digest_field in candidates:
        artifact_id = getattr(value, id_field, None)
        artifact_digest = getattr(value, digest_field, None)
        if artifact_id is not None and artifact_digest is not None:
            return ExactArtifactReferenceV1Alpha1(
                artifact_id=str(artifact_id),
                artifact_digest=str(artifact_digest),
                artifact_contract=contract,
            )
    raise ValueError("value does not expose an exact content-addressed coordinate")


def validate_bundle_for_manifest(
    manifest: StageRunManifestV1Alpha1,
    bundle: ReasoningCompositionRuntimeAuthorityBundle,
) -> None:
    if manifest.product_id != bundle.authenticated_context.product_id:
        raise ValueError("manifest crossed runtime-authority product scope")
    if manifest.execution_binding != exact_reference(bundle.execution_binding):
        raise ValueError("manifest execution binding differs from current resolution")
    if manifest.authority != bundle.authority_coordinates:
        raise ValueError("manifest authority differs from current resolution")
    subject = bundle.resolution_receipt.use_subject
    if subject != exact_reference(manifest):
        raise ValueError("pre-execution authority was not evaluated for the exact manifest")


class ReasoningCompositionRuntimeAuthorityPort(Protocol):
    """Internal two-phase authority resolver; implementations must fail closed."""

    async def resolve_planning(
        self,
        *,
        authenticated_context: AuthenticatedRuntimeContextV1Alpha1,
        use_subject: ExactArtifactReferenceV1Alpha1,
        participant_principal_ref: str,
        authority_class: str,
        operation: str,
        grant_ref: str,
        scope_ref: str,
        policy_ref: str,
        evaluated_at: datetime,
    ) -> ReasoningCompositionRuntimeAuthorityBundle: ...

    async def resolve_pre_execution(
        self,
        *,
        authenticated_context: AuthenticatedRuntimeContextV1Alpha1,
        manifest: StageRunManifestV1Alpha1,
        evaluated_at: datetime,
    ) -> ReasoningCompositionRuntimeAuthorityBundle: ...


__all__ = [
    "COMPOSITION_AUTHORITY_RESOLUTION_VERSION",
    "TASK_AUTHENTICATION_RECEIPT_VERSION",
    "CompositionAuthorityResolutionReceiptV1Alpha1",
    "ReasoningCompositionRuntimeAuthorityBundle",
    "ReasoningCompositionRuntimeAuthorityPort",
    "TaskAuthenticationReceiptV1Alpha1",
    "exact_reference",
    "validate_bundle_for_manifest",
]
