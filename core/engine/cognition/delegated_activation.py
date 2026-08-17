"""Delegated headless governed-cognition review and activation contracts.

Human/local-owner review stays the interactive default and keeps its exact v1
contracts.  This sibling module adds the *only* non-human path: an
authenticated, registered, product-scoped ``PrincipalKind.SERVICE`` principal
acting under two pre-existing governed grants.

Nothing here issues, mints, widens, renews, or transfers authority, and nothing
here performs I/O. A raw MODEL/SYSTEM identity is never an accountable
authority holder. Until a durable canonical model-run record exists, non-null
model-participant metadata is parsed only so the service can reject it; no
approval or activation receipt claims model participation.
"""

from __future__ import annotations

import re
from datetime import UTC, datetime
from enum import StrEnum
from typing import Any, Literal, Self

from pydantic import ConfigDict, Field, field_validator, model_validator

from ace.core.agent_composition import (
    AgentPrincipalV1Alpha1,
    AuthorityClass,
    PrincipalKind,
)
from ace.core.contracts import FrozenContract, canonical_hash
from ace.core.delegated_cognition import (
    ACTIVATION_AUTHORITY_CLASS,
    ACTIVATION_OPERATION,
    REVIEW_AUTHORITY_CLASS,
    REVIEW_OPERATION,
)
from ace.core.runtime_use import CapabilityArtifactIdentityV1Alpha1

DELEGATED_ACTIVATION_REQUEST_VERSION = "ace.cognition.delegated-activation-request/v1alpha1"
DELEGATED_MODEL_PARTICIPANT_VERSION = "ace.cognition.delegated-model-participant/v1alpha1"
DELEGATED_PRINCIPAL_BINDING_VERSION = "ace.cognition.delegated-principal-binding/v1alpha1"
DELEGATED_APPROVAL_RECEIPT_VERSION = "ace.cognition.delegated-approval-receipt/v1alpha1"
DELEGATED_ACTIVATION_RECEIPT_VERSION = "ace.cognition.delegated-activation-receipt/v1alpha1"

DELEGATED_ACTIVATION_POLICY = "ace.cognition.delegated-activation-policy/v1alpha1"

CONSEQUENCE_CLASS = "internal_cognition_selection_no_external_effect"

DELEGATED_RECORD_SPACE = "governed_cognition_delegation"

_REFERENCE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:/-]{0,239}$")
_DIGEST = re.compile(r"^sha256:[a-f0-9]{64}$")
_RAW_HASH = re.compile(r"^[a-f0-9]{64}$")


class DelegatedDenyCode(StrEnum):
    """Exact fail-closed reasons; every one leaves zero cognition writes."""

    HUMAN_REVIEW_REQUIRED = "human_review_required"
    PRODUCT_SCOPE_REQUIRED = "product_scope_required"
    REQUEST_MISMATCH = "delegated_request_mismatch"
    PRINCIPAL_UNAVAILABLE = "delegated_principal_unavailable"
    PRINCIPAL_NOT_SERVICE = "delegated_principal_not_service"
    PRINCIPAL_INACTIVE = "delegated_principal_inactive"
    GRANT_UNAVAILABLE = "delegated_grant_unavailable"
    GRANT_MISMATCH = "delegated_grant_mismatch"
    GRANT_SELF_ISSUED = "delegated_grant_self_issued"
    CAPABILITY_UNAVAILABLE = "delegated_capability_unavailable"
    SCOPE_MISMATCH = "delegated_scope_mismatch"
    CONSEQUENCE_FORBIDDEN = "delegated_consequence_forbidden"
    SELF_REVIEW_FORBIDDEN = "delegated_self_review_forbidden"
    PARTICIPANT_FORGED = "delegated_participant_forged"
    APPROVAL_UNAVAILABLE = "delegated_approval_unavailable"
    PROPOSAL_MISMATCH = "delegated_proposal_mismatch"
    HEAD_PRECONDITION_FAILED = "delegated_head_precondition_failed"
    REPLAY_CONFLICT = "delegated_replay_conflict"


class DelegatedCognitionAuthorityError(RuntimeError):
    """Delegated governed cognition failed closed before any durable effect."""

    def __init__(self, code: DelegatedDenyCode, detail: str = "") -> None:
        self.code = code
        super().__init__(f"{code.value}:{detail}" if detail else code.value)


def _deny(code: DelegatedDenyCode, detail: str = "") -> DelegatedCognitionAuthorityError:
    return DelegatedCognitionAuthorityError(code, detail)


class _Strict(FrozenContract):
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


def _derive(instance: _Strict, *, prefix: str, id_field: str, digest_field: str) -> None:
    material = instance.model_dump(mode="json", exclude={id_field, digest_field})
    digest = canonical_hash(material)
    expected_id = f"{prefix}:{digest[:32]}"
    expected_digest = f"sha256:{digest}"
    supplied_id = getattr(instance, id_field)
    supplied_digest = getattr(instance, digest_field)
    if supplied_id is not None and supplied_id != expected_id:
        raise ValueError(f"{id_field} does not match exact delegated material")
    if supplied_digest is not None and supplied_digest != expected_digest:
        raise ValueError(f"{digest_field} does not match exact delegated material")
    object.__setattr__(instance, id_field, expected_id)
    object.__setattr__(instance, digest_field, expected_digest)


class DelegatedModelParticipantV1Alpha1(_Strict):
    """Legacy-shaped metadata that is never accepted as durable attribution."""

    contract: Literal["ace.cognition.delegated-model-participant/v1alpha1"] = DELEGATED_MODEL_PARTICIPANT_VERSION
    participant_principal_ref: str
    participant_principal_digest: str
    definition_revision_ref: str
    definition_revision_digest: str
    role_binding_ref: str
    role_binding_digest: str
    run_ref: str
    grants_authority: Literal[False] = False

    @field_validator(
        "participant_principal_ref",
        "definition_revision_ref",
        "role_binding_ref",
        "run_ref",
    )
    @classmethod
    def validate_references(cls, value: str, info) -> str:
        return _reference(value, name=info.field_name)

    @field_validator(
        "participant_principal_digest",
        "definition_revision_digest",
        "role_binding_digest",
    )
    @classmethod
    def validate_digests(cls, value: str, info) -> str:
        return _digest(value, name=info.field_name)


class DelegatedServicePrincipalBindingV1Alpha1(_Strict):
    """Exact registration and lifecycle coordinates for the SERVICE holder."""

    contract: Literal["ace.cognition.delegated-principal-binding/v1alpha1"] = DELEGATED_PRINCIPAL_BINDING_VERSION
    principal_ref: str
    principal_digest: str
    registration_ref: str
    registration_digest: str
    lifecycle_state_id: str

    @field_validator("principal_ref", "registration_ref", "lifecycle_state_id")
    @classmethod
    def validate_references(cls, value: str, info) -> str:
        return _reference(value, name=info.field_name)

    @field_validator("principal_digest", "registration_digest")
    @classmethod
    def validate_digests(cls, value: str, info) -> str:
        return _digest(value, name=info.field_name)

    @model_validator(mode="after")
    def validate_registration_binding(self) -> Self:
        if self.registration_ref != self.principal_ref or self.registration_digest != self.principal_digest:
            raise ValueError("registration coordinates must be the exact frozen principal snapshot")
        return self

    @classmethod
    def from_principal(cls, principal: AgentPrincipalV1Alpha1, *, lifecycle_state_id: str) -> Self:
        validated = AgentPrincipalV1Alpha1.model_validate(principal.model_dump(mode="python"))
        return cls(
            principal_ref=str(validated.principal_id),
            principal_digest=str(validated.principal_digest),
            registration_ref=str(validated.principal_id),
            registration_digest=str(validated.principal_digest),
            lifecycle_state_id=lifecycle_state_id,
        )


def delegated_scope_ref(
    *,
    product_id: str,
    capture_ref: str,
    capture_digest: str,
    proposal_id: str,
    proposal_hash: str,
    target_cognition_id: str,
    derived_revision_id: str,
    derived_material_digest: str,
    capability_artifact_ref: str,
    capability_artifact_digest: str,
    capability_state_ref: str,
    capability_state_digest: str,
    capability_head_ref: str,
    capability_head_digest: str,
    configuration_ref: str,
    configuration_digest: str,
    policy_ref: str,
    service_principal_ref: str,
) -> str:
    """Return the one content-derived scope identity shared by both grants."""

    digest = canonical_hash(
        {
            "capability_artifact_digest": _digest(capability_artifact_digest, name="capability_artifact_digest"),
            "capability_artifact_ref": _reference(capability_artifact_ref, name="capability_artifact_ref"),
            "capability_head_digest": _digest(capability_head_digest, name="capability_head_digest"),
            "capability_head_ref": _reference(capability_head_ref, name="capability_head_ref"),
            "capability_state_digest": _digest(capability_state_digest, name="capability_state_digest"),
            "capability_state_ref": _reference(capability_state_ref, name="capability_state_ref"),
            "capture_digest": _digest(capture_digest, name="capture_digest"),
            "capture_ref": _reference(capture_ref, name="capture_ref"),
            "configuration_digest": _digest(configuration_digest, name="configuration_digest"),
            "configuration_ref": _reference(configuration_ref, name="configuration_ref"),
            "consequence_class": CONSEQUENCE_CLASS,
            "derived_material_digest": _digest(derived_material_digest, name="derived_material_digest"),
            "derived_revision_id": _reference(derived_revision_id, name="derived_revision_id"),
            "policy_ref": _reference(policy_ref, name="policy_ref"),
            "product_id": _reference(product_id, name="product_id"),
            "proposal_hash": proposal_hash,
            "proposal_id": _reference(proposal_id, name="proposal_id"),
            "service_principal_ref": _reference(service_principal_ref, name="service_principal_ref"),
            "target_cognition_id": _reference(target_cognition_id, name="target_cognition_id"),
        }
    )
    return f"delegated_cognition_scope:{digest[:32]}"


class DelegatedCognitionActivationRequestV1Alpha1(_Strict):
    """The immutable envelope every delegated review and activation binds.

    Extra fields are forbidden and both identities derive from the exact
    material, so any alteration produces a different request that no stored
    approval, grant, or receipt can satisfy.
    """

    contract: Literal["ace.cognition.delegated-activation-request/v1alpha1"] = DELEGATED_ACTIVATION_REQUEST_VERSION
    product_id: str
    capture_ref: str
    capture_digest: str
    proposal_id: str
    proposal_hash: str
    target_cognition_id: str
    base_revision_id: str | None = None
    expected_head_generation: int = Field(ge=0)
    derived_revision_id: str
    derived_material_digest: str
    requested_disposition: Literal["approve"] = "approve"
    capability_artifact: CapabilityArtifactIdentityV1Alpha1
    capability_artifact_ref: str
    capability_artifact_digest: str
    capability_state_ref: str
    capability_state_digest: str
    capability_head_ref: str
    capability_head_digest: str
    configuration_ref: str
    configuration_digest: str
    policy_ref: str
    consequence_class: Literal["internal_cognition_selection_no_external_effect"] = CONSEQUENCE_CLASS
    service_principal: DelegatedServicePrincipalBindingV1Alpha1
    review_grant_ref: str
    activation_grant_ref: str
    scope_ref: str
    authenticated_actor_ref: str
    authentication_receipt_ref: str
    authentication_receipt_digest: str
    authenticated_at: datetime
    authentication_expires_at: datetime
    replay_key: str
    model_participant: DelegatedModelParticipantV1Alpha1 | None = None
    request_id: str | None = None
    request_digest: str | None = None

    @field_validator(
        "product_id",
        "capture_ref",
        "proposal_id",
        "target_cognition_id",
        "base_revision_id",
        "derived_revision_id",
        "capability_state_ref",
        "capability_artifact_ref",
        "capability_head_ref",
        "configuration_ref",
        "policy_ref",
        "review_grant_ref",
        "activation_grant_ref",
        "scope_ref",
        "authenticated_actor_ref",
        "authentication_receipt_ref",
        "replay_key",
        "request_id",
    )
    @classmethod
    def validate_references(cls, value: str | None, info) -> str | None:
        return _reference(value, name=info.field_name) if value is not None else None

    @field_validator(
        "capture_digest",
        "capability_artifact_digest",
        "capability_state_digest",
        "capability_head_digest",
        "configuration_digest",
        "derived_material_digest",
        "authentication_receipt_digest",
        "request_digest",
    )
    @classmethod
    def validate_digests(cls, value: str | None, info) -> str | None:
        return _digest(value, name=info.field_name) if value is not None else None

    @field_validator("proposal_hash")
    @classmethod
    def validate_proposal_hash(cls, value: str) -> str:
        if not _RAW_HASH.fullmatch(value):
            raise ValueError("proposal_hash must be a lowercase 64-hex content hash")
        return value

    @field_validator("authenticated_at", "authentication_expires_at")
    @classmethod
    def validate_times(cls, value: datetime, info) -> datetime:
        return _aware(value, name=info.field_name)

    @model_validator(mode="after")
    def validate_binding_and_identity(self) -> Self:
        if self.authentication_expires_at <= self.authenticated_at:
            raise ValueError("delegated request requires a positive authenticated window")
        if not self.product_id.startswith("product:"):
            raise ValueError("delegated request requires an explicit product scope")
        if self.review_grant_ref == self.activation_grant_ref:
            raise ValueError("delegated review and activation require two distinct grants")
        if self.capability_state_ref != _capability_state_ref(self.capability_artifact):
            raise ValueError("capability_state_ref must be the exact artifact-derived state identity")
        if self.capability_artifact_ref != _capability_artifact_ref(self.capability_artifact):
            raise ValueError("capability_artifact_ref must identify the exact capability artifact")
        if self.capability_artifact_digest != self.capability_artifact.artifact_digest:
            raise ValueError("capability_artifact_digest must equal the exact artifact digest")
        expected_configuration_digest = f"sha256:{canonical_hash({'configuration_ref': self.configuration_ref})}"
        if self.configuration_digest != expected_configuration_digest:
            raise ValueError("configuration_digest must bind the exact configuration reference")
        if self.model_participant is not None and (
            self.model_participant.participant_principal_ref == self.service_principal.principal_ref
        ):
            raise ValueError("model participant and reviewing service principal must be distinct")
        if self.authenticated_actor_ref == self.service_principal.principal_ref:
            raise ValueError("authenticated actor and delegated principal are separate coordinates")
        expected_scope = delegated_scope_ref(
            product_id=self.product_id,
            capture_ref=self.capture_ref,
            capture_digest=self.capture_digest,
            proposal_id=self.proposal_id,
            proposal_hash=self.proposal_hash,
            target_cognition_id=self.target_cognition_id,
            derived_revision_id=self.derived_revision_id,
            derived_material_digest=self.derived_material_digest,
            capability_artifact_ref=self.capability_artifact_ref,
            capability_artifact_digest=self.capability_artifact_digest,
            capability_state_ref=self.capability_state_ref,
            capability_state_digest=self.capability_state_digest,
            capability_head_ref=self.capability_head_ref,
            capability_head_digest=self.capability_head_digest,
            configuration_ref=self.configuration_ref,
            configuration_digest=self.configuration_digest,
            policy_ref=self.policy_ref,
            service_principal_ref=self.service_principal.principal_ref,
        )
        if self.scope_ref != expected_scope:
            raise ValueError("scope_ref must be the content-derived delegated request scope")
        _derive(
            self,
            prefix="delegated_cognition_request",
            id_field="request_id",
            digest_field="request_digest",
        )
        return self

    def grant_ref_for(self, operation: str) -> str:
        if operation == REVIEW_OPERATION:
            return self.review_grant_ref
        if operation == ACTIVATION_OPERATION:
            return self.activation_grant_ref
        raise _deny(DelegatedDenyCode.CONSEQUENCE_FORBIDDEN, operation)


def _capability_state_ref(artifact: CapabilityArtifactIdentityV1Alpha1) -> str:
    from ace.core.runtime_use import capability_state_ref_for_artifact

    return capability_state_ref_for_artifact(artifact)


def _capability_artifact_ref(artifact: CapabilityArtifactIdentityV1Alpha1) -> str:
    return f"capability_artifact:{canonical_hash(artifact.model_dump(mode='json'))[:32]}"


class DelegatedGrantEvidenceV1Alpha1(_Strict):
    """Exact point-of-use evidence for one resolved delegated grant."""

    contract: Literal["ace.cognition.delegated-grant-evidence/v1alpha1"] = (
        "ace.cognition.delegated-grant-evidence/v1alpha1"
    )
    grant_ref: str
    grant_hash: str
    authority_class: AuthorityClass
    operation: str
    scope_ref: str
    policy_ref: str
    delegator_ref: str
    commit_receipt_id: str
    head_sequence: int = Field(ge=1)
    head_revision_id: str
    authority_use_receipt_ref: str
    authority_use_receipt_digest: str
    expires_at: datetime | None = None

    @field_validator(
        "grant_ref",
        "scope_ref",
        "policy_ref",
        "delegator_ref",
        "commit_receipt_id",
        "head_revision_id",
        "authority_use_receipt_ref",
    )
    @classmethod
    def validate_references(cls, value: str, info) -> str:
        return _reference(value, name=info.field_name)

    @field_validator("grant_hash")
    @classmethod
    def validate_grant_hash(cls, value: str) -> str:
        if not _RAW_HASH.fullmatch(value):
            raise ValueError("grant_hash must be a lowercase 64-hex content hash")
        return value

    @field_validator("authority_use_receipt_digest")
    @classmethod
    def validate_digest(cls, value: str) -> str:
        return _digest(value, name="authority_use_receipt_digest")

    @field_validator("expires_at")
    @classmethod
    def validate_expiry(cls, value: datetime | None) -> datetime | None:
        return _aware(value, name="expires_at") if value is not None else None


class DelegatedCognitionApprovalReceiptV1Alpha1(_Strict):
    """Stage-one evidence: authority resolved, nothing activated."""

    contract: Literal["ace.cognition.delegated-approval-receipt/v1alpha1"] = DELEGATED_APPROVAL_RECEIPT_VERSION
    stage: Literal["approval"] = "approval"
    product_id: str
    request_ref: str
    request_digest: str
    policy_version: Literal["ace.cognition.delegated-activation-policy/v1alpha1"] = DELEGATED_ACTIVATION_POLICY
    policy_decision: Literal["approved"] = "approved"
    consequence_class: Literal["internal_cognition_selection_no_external_effect"] = CONSEQUENCE_CLASS
    authenticated_actor_ref: str
    authentication_receipt_ref: str
    service_principal: DelegatedServicePrincipalBindingV1Alpha1
    principal_lifecycle_head_sequence: int = Field(ge=1)
    principal_lifecycle_head_revision_id: str
    review_grant: DelegatedGrantEvidenceV1Alpha1
    activation_grant: DelegatedGrantEvidenceV1Alpha1
    capability_state_ref: str
    capability_use_receipt_ref: str
    capability_use_receipt_digest: str
    capability_head_sequence: int = Field(ge=1)
    capability_head_revision_id: str
    proposal_id: str
    proposal_hash: str
    derived_revision_id: str
    derived_material_digest: str
    expected_head_generation: int = Field(ge=0)
    replay_key: str
    resolved_at: datetime
    receipt_id: str | None = None
    receipt_digest: str | None = None

    @field_validator(
        "product_id",
        "request_ref",
        "authenticated_actor_ref",
        "authentication_receipt_ref",
        "principal_lifecycle_head_revision_id",
        "capability_state_ref",
        "capability_use_receipt_ref",
        "capability_head_revision_id",
        "proposal_id",
        "derived_revision_id",
        "replay_key",
        "receipt_id",
    )
    @classmethod
    def validate_references(cls, value: str | None, info) -> str | None:
        return _reference(value, name=info.field_name) if value is not None else None

    @field_validator(
        "request_digest",
        "capability_use_receipt_digest",
        "derived_material_digest",
        "receipt_digest",
    )
    @classmethod
    def validate_digests(cls, value: str | None, info) -> str | None:
        return _digest(value, name=info.field_name) if value is not None else None

    @field_validator("proposal_hash")
    @classmethod
    def validate_proposal_hash(cls, value: str) -> str:
        if not _RAW_HASH.fullmatch(value):
            raise ValueError("proposal_hash must be a lowercase 64-hex content hash")
        return value

    @field_validator("resolved_at")
    @classmethod
    def validate_time(cls, value: datetime) -> datetime:
        return _aware(value, name="resolved_at")

    @model_validator(mode="after")
    def validate_shape_and_identity(self) -> Self:
        _validate_grant_pair(self.review_grant, self.activation_grant)
        _derive(self, prefix="delegated_cognition_approval", id_field="receipt_id", digest_field="receipt_digest")
        return self

    @property
    def reusable_authority(self) -> Literal[False]:
        """Historical delegated evidence is never bearer authority."""

        return False


class DelegatedCognitionActivationReceiptV1Alpha1(_Strict):
    """Stage-two receipt written in the same commit as the cognition head."""

    contract: Literal["ace.cognition.delegated-activation-receipt/v1alpha1"] = DELEGATED_ACTIVATION_RECEIPT_VERSION
    stage: Literal["activation"] = "activation"
    product_id: str
    request_ref: str
    request_digest: str
    approval_receipt_ref: str
    approval_receipt_digest: str
    policy_version: Literal["ace.cognition.delegated-activation-policy/v1alpha1"] = DELEGATED_ACTIVATION_POLICY
    policy_decision: Literal["activated"] = "activated"
    consequence_class: Literal["internal_cognition_selection_no_external_effect"] = CONSEQUENCE_CLASS
    authenticated_actor_ref: str
    authentication_receipt_ref: str
    service_principal: DelegatedServicePrincipalBindingV1Alpha1
    principal_lifecycle_head_sequence: int = Field(ge=1)
    principal_lifecycle_head_revision_id: str
    review_grant: DelegatedGrantEvidenceV1Alpha1
    activation_grant: DelegatedGrantEvidenceV1Alpha1
    capability_state_ref: str
    capability_use_receipt_ref: str
    capability_use_receipt_digest: str
    capability_head_sequence: int = Field(ge=1)
    capability_head_revision_id: str
    capture_ref: str
    capture_digest: str
    proposal_id: str
    proposal_hash: str
    base_revision_id: str | None = None
    result_revision_id: str
    result_material_digest: str
    cognition_review_receipt_id: str
    result_head_id: str
    prior_head_generation: int = Field(ge=0)
    result_head_generation: int = Field(ge=1)
    activation_event_id: str
    replay_key: str
    activated_at: datetime
    receipt_id: str | None = None
    receipt_digest: str | None = None

    @field_validator(
        "product_id",
        "request_ref",
        "approval_receipt_ref",
        "authenticated_actor_ref",
        "authentication_receipt_ref",
        "principal_lifecycle_head_revision_id",
        "capability_state_ref",
        "capability_use_receipt_ref",
        "capability_head_revision_id",
        "capture_ref",
        "proposal_id",
        "base_revision_id",
        "result_revision_id",
        "cognition_review_receipt_id",
        "result_head_id",
        "activation_event_id",
        "replay_key",
        "receipt_id",
    )
    @classmethod
    def validate_references(cls, value: str | None, info) -> str | None:
        return _reference(value, name=info.field_name) if value is not None else None

    @field_validator(
        "request_digest",
        "approval_receipt_digest",
        "capability_use_receipt_digest",
        "capture_digest",
        "result_material_digest",
        "receipt_digest",
    )
    @classmethod
    def validate_digests(cls, value: str | None, info) -> str | None:
        return _digest(value, name=info.field_name) if value is not None else None

    @field_validator("proposal_hash")
    @classmethod
    def validate_proposal_hash(cls, value: str) -> str:
        if not _RAW_HASH.fullmatch(value):
            raise ValueError("proposal_hash must be a lowercase 64-hex content hash")
        return value

    @field_validator("activated_at")
    @classmethod
    def validate_time(cls, value: datetime) -> datetime:
        return _aware(value, name="activated_at")

    @model_validator(mode="after")
    def validate_shape_and_identity(self) -> Self:
        _validate_grant_pair(self.review_grant, self.activation_grant)
        if self.result_head_generation != self.prior_head_generation + 1:
            raise ValueError("delegated activation advances the cognition head by exactly one generation")
        _derive(self, prefix="delegated_cognition_activation", id_field="receipt_id", digest_field="receipt_digest")
        return self

    @property
    def reusable_authority(self) -> Literal[False]:
        """Historical delegated evidence is never bearer authority."""

        return False


def _validate_grant_pair(
    review_grant: DelegatedGrantEvidenceV1Alpha1,
    activation_grant: DelegatedGrantEvidenceV1Alpha1,
) -> None:
    if review_grant.authority_class is not REVIEW_AUTHORITY_CLASS or review_grant.operation != REVIEW_OPERATION:
        raise ValueError("delegated review evidence must bind the exact review authority and operation")
    if (
        activation_grant.authority_class is not ACTIVATION_AUTHORITY_CLASS
        or activation_grant.operation != ACTIVATION_OPERATION
    ):
        raise ValueError("delegated activation evidence must bind the exact activation authority and operation")
    if review_grant.grant_ref == activation_grant.grant_ref:
        raise ValueError("delegated evidence requires two distinct grants")
    if review_grant.scope_ref != activation_grant.scope_ref or review_grant.policy_ref != activation_grant.policy_ref:
        raise ValueError("both delegated grants must share one exact scope and policy")


DELEGATED_REVIEW_RATIONALE = (
    "Delegated headless activation resolved against pre-existing, exact, "
    "product-scoped grants held by a registered SERVICE principal."
)


def delegated_review_request_id(
    *,
    proposal_id: str,
    proposal_hash: str,
    service_principal_ref: str,
    expected_head_generation: int,
    replay_key: str,
) -> str:
    """Return the deterministic human-v1 review-request identity for one delegation."""

    digest = canonical_hash(
        {
            "expected_head_generation": expected_head_generation,
            "proposal_hash": proposal_hash,
            "proposal_id": proposal_id,
            "replay_key": replay_key,
            "service_principal_ref": service_principal_ref,
        }
    )
    return f"delegated-review-request:{digest[:32]}"


def derive_delegated_cognition_material(
    proposal: Any,
    *,
    service_principal_ref: str,
    expected_head_generation: int,
    replay_key: str,
    reviewed_at: datetime,
) -> tuple[Any, Any, Any]:
    """Return the exact ``(review receipt, revision, head)`` a delegation would write.

    The existing content-addressed human v1 contracts are reused unchanged; only
    the actor class differs, so downstream readers, discovery, and lifecycle keep
    working against one cognition vocabulary.  The result is a pure function of
    the proposal, the SERVICE principal, the expected generation, and the replay
    key, which is what lets the caller derive the request envelope up front and
    the service recompute and compare it at both stages.
    """

    from core.engine.cognition.contracts import CognitionHeadV1, CognitionRevisionV1, CognitionSourceV1
    from core.engine.cognition.governance import (
        ActorClass,
        CognitionReviewReceiptV1,
        ReviewActorV1,
        ReviewDisposition,
    )

    review_request_id = delegated_review_request_id(
        proposal_id=str(proposal.proposal_id),
        proposal_hash=str(proposal.proposal_hash),
        service_principal_ref=service_principal_ref,
        expected_head_generation=expected_head_generation,
        replay_key=replay_key,
    )
    receipt = CognitionReviewReceiptV1(
        review_request_id=review_request_id,
        proposal_id=str(proposal.proposal_id),
        proposal_hash=str(proposal.proposal_hash),
        # A delegated holder is never coerced into HUMAN and carries no token
        # authority string: the two governed grants are the whole authority.
        actor=ReviewActorV1(actor_id=service_principal_ref, actor_class=ActorClass.SERVICE, authorities=()),
        disposition=ReviewDisposition.APPROVE,
        rationale=DELEGATED_REVIEW_RATIONALE,
        expected_head_generation=expected_head_generation,
        reviewed_at=reviewed_at,
    )
    revision = CognitionRevisionV1(
        identity=proposal.target_identity,
        body_schema_version=proposal.body_schema_version,
        body=proposal.draft_body,
        dependencies=proposal.dependencies,
        sources=tuple(
            CognitionSourceV1(
                source_kind=item.source_kind,
                locator=item.source_id,
                content_hash=item.content_hash,
            )
            for item in proposal.sources
        ),
        approval_receipt_id=str(receipt.receipt_id),
    )
    head = CognitionHeadV1(
        cognition_id=str(proposal.target_identity.cognition_id),
        scope=proposal.scope,
        active_revision_id=str(revision.revision_id),
        generation=expected_head_generation + 1,
        authority_receipt_id=str(receipt.receipt_id),
    )
    receipt = receipt.model_copy(
        update={
            "result_revision_id": str(revision.revision_id),
            "result_head_id": str(head.head_id),
        }
    )
    return receipt, revision, head


def delegated_activation_event_id(*, head_id: str, generation: int, review_receipt_id: str) -> str:
    """Reuse the existing activation-event identity shape for delegated writes."""

    from core.engine.cognition.contracts import stable_id

    return stable_id(
        "cognition_activation",
        {"head_id": head_id, "generation": generation, "review": review_receipt_id},
    )


def require_service_principal(
    principal: AgentPrincipalV1Alpha1,
    *,
    product_id: str,
    binding: DelegatedServicePrincipalBindingV1Alpha1,
) -> None:
    """Deny any holder that is not an exact, product-scoped SERVICE principal."""

    if principal.principal_kind is not PrincipalKind.SERVICE:
        raise _deny(DelegatedDenyCode.PRINCIPAL_NOT_SERVICE, principal.principal_kind.value)
    if principal.product_id != product_id:
        raise _deny(DelegatedDenyCode.PRINCIPAL_UNAVAILABLE, "cross-product principal")
    if str(principal.principal_id) != binding.principal_ref or str(principal.principal_digest) != (
        binding.principal_digest
    ):
        raise _deny(DelegatedDenyCode.PRINCIPAL_UNAVAILABLE, "registration snapshot mismatch")


def require_delegated_lineage(
    *,
    delegator_ref: str | None,
    beneficiary_principal_ref: str,
    beneficiary_actor_ref: str,
    commit_actor_ref: str,
    approval_actor_ref: str,
    authority_class: AuthorityClass,
    delegation_ceiling: tuple[AuthorityClass, ...],
) -> str:
    """Deny beneficiary self-mint, self-renew, self-transfer, and self-widen.

    The delegator must exist, must not be the beneficiary principal or the
    authenticated beneficiary actor, and must be the durable actor that
    committed and approved the grant revision.  The declared ceiling must
    already contain the exercised class, so no widening is possible here.
    """

    if delegator_ref is None:
        raise _deny(DelegatedDenyCode.GRANT_SELF_ISSUED, "grant is not delegated")
    if delegator_ref in {beneficiary_principal_ref, beneficiary_actor_ref}:
        raise _deny(DelegatedDenyCode.GRANT_SELF_ISSUED, "delegator is the beneficiary")
    if commit_actor_ref != delegator_ref or approval_actor_ref != delegator_ref:
        raise _deny(DelegatedDenyCode.GRANT_SELF_ISSUED, "commit lineage does not match the delegator")
    if commit_actor_ref in {beneficiary_principal_ref, beneficiary_actor_ref}:
        raise _deny(DelegatedDenyCode.GRANT_SELF_ISSUED, "beneficiary committed its own grant")
    if authority_class not in delegation_ceiling:
        raise _deny(DelegatedDenyCode.GRANT_MISMATCH, "grant exceeds its declared delegation ceiling")
    return delegator_ref


def require_distinct_producer(
    *,
    producer_actor_id: str,
    service_principal_ref: str,
    authenticated_actor_ref: str,
    model_participant: DelegatedModelParticipantV1Alpha1 | None,
) -> None:
    """Delegated SERVICE self-review is denied when it created the proposal."""

    if producer_actor_id in {service_principal_ref, authenticated_actor_ref}:
        raise _deny(DelegatedDenyCode.SELF_REVIEW_FORBIDDEN, producer_actor_id)
    if model_participant is not None and model_participant.participant_principal_ref == service_principal_ref:
        raise _deny(DelegatedDenyCode.PARTICIPANT_FORGED, "participant equals the reviewing service")


__all__ = [
    "ACTIVATION_AUTHORITY_CLASS",
    "ACTIVATION_OPERATION",
    "CONSEQUENCE_CLASS",
    "DELEGATED_ACTIVATION_POLICY",
    "DELEGATED_ACTIVATION_RECEIPT_VERSION",
    "DELEGATED_ACTIVATION_REQUEST_VERSION",
    "DELEGATED_APPROVAL_RECEIPT_VERSION",
    "DELEGATED_MODEL_PARTICIPANT_VERSION",
    "DELEGATED_PRINCIPAL_BINDING_VERSION",
    "DELEGATED_RECORD_SPACE",
    "REVIEW_AUTHORITY_CLASS",
    "REVIEW_OPERATION",
    "DelegatedCognitionActivationReceiptV1Alpha1",
    "DelegatedCognitionActivationRequestV1Alpha1",
    "DelegatedCognitionApprovalReceiptV1Alpha1",
    "DelegatedCognitionAuthorityError",
    "DelegatedDenyCode",
    "DelegatedGrantEvidenceV1Alpha1",
    "DelegatedModelParticipantV1Alpha1",
    "DelegatedServicePrincipalBindingV1Alpha1",
    "DELEGATED_REVIEW_RATIONALE",
    "delegated_activation_event_id",
    "delegated_review_request_id",
    "delegated_scope_ref",
    "derive_delegated_cognition_material",
    "require_delegated_lineage",
    "require_distinct_producer",
    "require_service_principal",
]
