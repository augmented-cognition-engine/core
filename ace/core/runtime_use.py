"""Actor-scoped, point-in-time Core runtime-use contracts.

These receipts prove one bounded past evaluation. They are audit evidence and
must never be accepted as reusable bearer credentials or as activation-time
authority.
"""

from __future__ import annotations

import re
from datetime import UTC, datetime
from typing import Literal, Protocol, Self

from pydantic import ConfigDict, field_validator, model_validator

from ace.core.contracts import FrozenContract, canonical_hash
from ace.core.state import GovernedStateHeadPreconditionV1Alpha1

AUTHENTICATED_RUNTIME_CONTEXT_VERSION = "ace.core.authenticated-runtime-context/v1alpha1"
CAPABILITY_ARTIFACT_IDENTITY_VERSION = "ace.core.capability-artifact-identity/v1alpha1"
CAPABILITY_USE_RECEIPT_VERSION = "ace.core.capability-use-receipt/v1alpha1"
AUTHORITY_USE_RECEIPT_VERSION = "ace.core.authority-use-receipt/v1alpha1"
CAPABILITY_STATE_KIND = "capability_state"
AUTHORITY_GRANT_STATE_KIND = "authority_grant"

_REFERENCE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:/-]{0,239}$")
_SLUG = re.compile(r"^[a-z][a-z0-9]*(?:[._-][a-z0-9]+)*$")
_CONTRACT = re.compile(r"^[a-z][a-z0-9._/-]{0,238}/v[0-9][a-z0-9.-]*$")
_VERSION = re.compile(r"^[0-9]+(?:\.[0-9]+){2}(?:[-+][A-Za-z0-9.-]+)?$")
_DIGEST = re.compile(r"^sha256:[a-f0-9]{64}$")
_RAW_HASH = re.compile(r"^[a-f0-9]{64}$")


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


def _reference(value: str, *, name: str) -> str:
    if not _REFERENCE.fullmatch(value):
        raise ValueError(f"{name} must be a bounded stable reference")
    return value


def _digest(value: str, *, name: str) -> str:
    if not _DIGEST.fullmatch(value):
        raise ValueError(f"{name} must use lowercase sha256:<64-hex> syntax")
    return value


def _derive_receipt_identity(instance: _StrictFrozenContract, *, prefix: str) -> None:
    material = instance.model_dump(mode="json", exclude={"receipt_id", "receipt_digest"})
    digest = canonical_hash(material)
    expected_id = f"{prefix}:{digest[:32]}"
    expected_digest = f"sha256:{digest}"
    supplied_id = getattr(instance, "receipt_id")
    supplied_digest = getattr(instance, "receipt_digest")
    if supplied_id is not None and supplied_id != expected_id:
        raise ValueError("receipt_id does not match exact runtime-use material")
    if supplied_digest is not None and supplied_digest != expected_digest:
        raise ValueError("receipt_digest does not match exact runtime-use material")
    object.__setattr__(instance, "receipt_id", expected_id)
    object.__setattr__(instance, "receipt_digest", expected_digest)


def capability_state_ref_for_artifact(
    artifact: CapabilityArtifactIdentityV1Alpha1,
) -> str:
    """Derive the only capability-state identity valid for one exact artifact."""

    validated = CapabilityArtifactIdentityV1Alpha1.model_validate(artifact.model_dump(mode="python"))
    digest = canonical_hash(validated.model_dump(mode="json"))
    return f"capability_state:{digest[:32]}"


class AuthenticatedRuntimeContextV1Alpha1(_StrictFrozenContract):
    """Exact authenticated actor and product context for one runtime request."""

    contract: Literal["ace.core.authenticated-runtime-context/v1alpha1"] = AUTHENTICATED_RUNTIME_CONTEXT_VERSION
    product_id: str
    actor_ref: str
    authentication_receipt_ref: str
    authentication_receipt_digest: str
    authenticated_at: datetime
    expires_at: datetime

    @field_validator("product_id", "actor_ref", "authentication_receipt_ref")
    @classmethod
    def validate_references(cls, value: str, info) -> str:
        return _reference(value, name=info.field_name)

    @field_validator("authentication_receipt_digest")
    @classmethod
    def validate_authentication_digest(cls, value: str) -> str:
        return _digest(value, name="authentication_receipt_digest")

    @field_validator("authenticated_at", "expires_at")
    @classmethod
    def normalize_times(cls, value: datetime, info) -> datetime:
        return _aware(value, name=info.field_name)

    @model_validator(mode="after")
    def validate_window(self) -> Self:
        if self.expires_at <= self.authenticated_at:
            raise ValueError("authenticated runtime context must have a positive validity window")
        return self


class CapabilityArtifactIdentityV1Alpha1(_StrictFrozenContract):
    """Exact installed implementation identity selected by a host registry."""

    contract_version: Literal["ace.core.capability-artifact-identity/v1alpha1"] = CAPABILITY_ARTIFACT_IDENTITY_VERSION
    capability: str
    contract: str
    implementation_id: str
    implementation_version: str
    artifact_digest: str

    @field_validator("capability", "implementation_id")
    @classmethod
    def validate_slugs(cls, value: str, info) -> str:
        if len(value) > 120 or not _SLUG.fullmatch(value):
            raise ValueError(f"{info.field_name} must be a bounded lowercase identifier")
        return value

    @field_validator("contract")
    @classmethod
    def validate_contract(cls, value: str) -> str:
        if len(value) > 240 or not _CONTRACT.fullmatch(value):
            raise ValueError("contract must be a bounded versioned contract reference")
        return value

    @field_validator("implementation_version")
    @classmethod
    def validate_version(cls, value: str) -> str:
        if len(value) > 120 or not _VERSION.fullmatch(value):
            raise ValueError("implementation_version must be an exact semantic version")
        return value

    @field_validator("artifact_digest")
    @classmethod
    def validate_artifact_digest(cls, value: str) -> str:
        return _digest(value, name="artifact_digest")


class CapabilityUseReceiptV1Alpha1(_StrictFrozenContract):
    """Proof of one past actor-scoped capability evaluation and selection."""

    contract: Literal["ace.core.capability-use-receipt/v1alpha1"] = CAPABILITY_USE_RECEIPT_VERSION
    product_id: str
    actor_ref: str
    authenticated_context: AuthenticatedRuntimeContextV1Alpha1
    use_subject_ref: str
    use_subject_digest: str
    operation: str
    artifact: CapabilityArtifactIdentityV1Alpha1
    capability_state_ref: str
    configuration_ref: str
    evaluated_at: datetime
    resolved_at: datetime
    state_head_precondition: GovernedStateHeadPreconditionV1Alpha1
    receipt_id: str | None = None
    receipt_digest: str | None = None

    @field_validator(
        "product_id",
        "actor_ref",
        "use_subject_ref",
        "capability_state_ref",
        "configuration_ref",
    )
    @classmethod
    def validate_references(cls, value: str, info) -> str:
        return _reference(value, name=info.field_name)

    @field_validator("operation")
    @classmethod
    def validate_operation(cls, value: str) -> str:
        if len(value) > 120 or not _SLUG.fullmatch(value):
            raise ValueError("operation must be a bounded lowercase identifier")
        return value

    @field_validator("use_subject_digest", "receipt_digest")
    @classmethod
    def validate_digests(cls, value: str | None, info) -> str | None:
        return _digest(value, name=info.field_name) if value is not None else None

    @field_validator("receipt_id")
    @classmethod
    def validate_receipt_id(cls, value: str | None) -> str | None:
        return _reference(value, name="receipt_id") if value is not None else None

    @field_validator("evaluated_at", "resolved_at")
    @classmethod
    def normalize_times(cls, value: datetime, info) -> datetime:
        return _aware(value, name=info.field_name)

    @model_validator(mode="after")
    def validate_scope_time_and_identity(self) -> Self:
        if (
            self.authenticated_context.product_id != self.product_id
            or self.authenticated_context.actor_ref != self.actor_ref
        ):
            raise ValueError("authenticated context crossed capability-use actor or product scope")
        if (
            self.state_head_precondition.product_id != self.product_id
            or self.state_head_precondition.state_kind != CAPABILITY_STATE_KIND
            or self.capability_state_ref != capability_state_ref_for_artifact(self.artifact)
            or self.state_head_precondition.state_id != self.capability_state_ref
        ):
            raise ValueError("capability use requires the exact artifact-derived capability-state head")
        if self.resolved_at > self.evaluated_at:
            raise ValueError("capability resolution cannot follow its evaluation time")
        if not (
            self.authenticated_context.authenticated_at
            <= self.resolved_at
            <= self.evaluated_at
            < self.authenticated_context.expires_at
        ):
            raise ValueError("capability use must resolve and evaluate inside the authenticated window")
        _derive_receipt_identity(self, prefix="capability_use_receipt")
        return self

    @property
    def reusable_authority(self) -> Literal[False]:
        return False


class AuthorityUseReceiptV1Alpha1(_StrictFrozenContract):
    """Proof of one past actor-scoped authority-grant evaluation."""

    contract: Literal["ace.core.authority-use-receipt/v1alpha1"] = AUTHORITY_USE_RECEIPT_VERSION
    product_id: str
    actor_ref: str
    authenticated_context: AuthenticatedRuntimeContextV1Alpha1
    use_subject_ref: str
    use_subject_digest: str
    operation: str
    authority: str
    grant_ref: str
    grant_hash: str
    evaluated_at: datetime
    expires_at: datetime | None = None
    state_head_precondition: GovernedStateHeadPreconditionV1Alpha1
    receipt_id: str | None = None
    receipt_digest: str | None = None

    @field_validator("product_id", "actor_ref", "use_subject_ref", "grant_ref")
    @classmethod
    def validate_references(cls, value: str, info) -> str:
        return _reference(value, name=info.field_name)

    @field_validator("authority")
    @classmethod
    def validate_authority(cls, value: str) -> str:
        if len(value) > 120 or not _SLUG.fullmatch(value):
            raise ValueError("authority must be a bounded lowercase identifier")
        return value

    @field_validator("operation")
    @classmethod
    def validate_operation(cls, value: str) -> str:
        if len(value) > 120 or not _SLUG.fullmatch(value):
            raise ValueError("operation must be a bounded lowercase identifier")
        return value

    @field_validator("use_subject_digest", "receipt_digest")
    @classmethod
    def validate_digests(cls, value: str | None, info) -> str | None:
        return _digest(value, name=info.field_name) if value is not None else None

    @field_validator("grant_hash")
    @classmethod
    def validate_grant_hash(cls, value: str) -> str:
        if not _RAW_HASH.fullmatch(value):
            raise ValueError("grant_hash must be a lowercase 64-hex content hash")
        return value

    @field_validator("receipt_id")
    @classmethod
    def validate_receipt_id(cls, value: str | None) -> str | None:
        return _reference(value, name="receipt_id") if value is not None else None

    @field_validator("evaluated_at", "expires_at")
    @classmethod
    def normalize_times(cls, value: datetime | None, info) -> datetime | None:
        return _aware(value, name=info.field_name) if value is not None else None

    @model_validator(mode="after")
    def validate_scope_time_and_identity(self) -> Self:
        if (
            self.authenticated_context.product_id != self.product_id
            or self.authenticated_context.actor_ref != self.actor_ref
        ):
            raise ValueError("authenticated context crossed authority-use actor or product scope")
        if (
            self.state_head_precondition.product_id != self.product_id
            or self.state_head_precondition.state_kind != AUTHORITY_GRANT_STATE_KIND
            or self.state_head_precondition.state_id != self.grant_ref
        ):
            raise ValueError("authority use requires the exact named authority-grant head")
        if not (
            self.authenticated_context.authenticated_at <= self.evaluated_at < self.authenticated_context.expires_at
        ):
            raise ValueError("authority use must be evaluated inside the authenticated window")
        if self.expires_at is not None and self.expires_at <= self.evaluated_at:
            raise ValueError("authority grant must remain valid after its evaluation time")
        _derive_receipt_identity(self, prefix="authority_use_receipt")
        return self

    @property
    def reusable_authority(self) -> Literal[False]:
        return False


class RuntimeUseResolver(Protocol):
    """Port to current actor-scoped capability and authority sources of truth."""

    async def resolve_capability_use(
        self,
        *,
        context: AuthenticatedRuntimeContextV1Alpha1,
        use_subject_ref: str,
        use_subject_digest: str,
        operation: str,
        artifact: CapabilityArtifactIdentityV1Alpha1,
        capability_state_ref: str,
        configuration_ref: str,
        evaluated_at: datetime,
    ) -> CapabilityUseReceiptV1Alpha1: ...

    async def resolve_authority_use(
        self,
        *,
        context: AuthenticatedRuntimeContextV1Alpha1,
        use_subject_ref: str,
        use_subject_digest: str,
        operation: str,
        authority: str,
        grant_ref: str,
        evaluated_at: datetime,
    ) -> AuthorityUseReceiptV1Alpha1: ...


CoreRuntimeUseResolver = RuntimeUseResolver


__all__ = [
    "AUTHENTICATED_RUNTIME_CONTEXT_VERSION",
    "AUTHORITY_GRANT_STATE_KIND",
    "AUTHORITY_USE_RECEIPT_VERSION",
    "CAPABILITY_ARTIFACT_IDENTITY_VERSION",
    "CAPABILITY_STATE_KIND",
    "CAPABILITY_USE_RECEIPT_VERSION",
    "AuthenticatedRuntimeContextV1Alpha1",
    "AuthorityUseReceiptV1Alpha1",
    "CapabilityArtifactIdentityV1Alpha1",
    "CapabilityUseReceiptV1Alpha1",
    "CoreRuntimeUseResolver",
    "RuntimeUseResolver",
    "capability_state_ref_for_artifact",
]
