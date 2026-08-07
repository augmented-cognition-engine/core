"""Domain-neutral governed-state commit contracts owned by ACE Core.

The contracts in this module deliberately treat higher-layer payloads as opaque
JSON.  Core owns product fencing, resolved authority, optimistic head checks,
commit receipts, and audit identity without learning the payload vocabulary.
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any, Literal, Protocol, Self

from pydantic import Field, field_validator, model_validator

from ace.core.contracts import FrozenContract, canonical_hash, stable_id

GOVERNED_STATE_REVISION_VERSION = "ace.core.governed-state-revision/v1alpha1"
GOVERNED_STATE_HEAD_VERSION = "ace.core.governed-state-head/v1alpha1"
GOVERNED_STATE_HEAD_PRECONDITION_VERSION = "ace.core.governed-state-head-precondition/v1alpha1"
GOVERNED_STATE_COMMIT_RECEIPT_VERSION = "ace.core.governed-state-commit-receipt/v1alpha1"


def _aware(value: datetime, name: str) -> datetime:
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError(f"{name} must include a timezone")
    return value.astimezone(UTC)


class ResolvedApprovalReceiptV1(FrozenContract):
    """Core resolution of an existing approval receipt for exact material."""

    receipt_ref: str = Field(min_length=1, max_length=240)
    product_id: str = Field(min_length=1, max_length=240)
    subject_ref: str = Field(min_length=1, max_length=240)
    actor_ref: str = Field(min_length=1, max_length=240)
    disposition: Literal["approved"] = "approved"
    receipt_hash: str = Field(pattern=r"^[a-f0-9]{64}$")
    approved_at: datetime

    @field_validator("approved_at")
    @classmethod
    def validate_approved_at(cls, value: datetime) -> datetime:
        return _aware(value, "approved_at")


class ResolvedAuthorityGrantV1(FrozenContract):
    """Core resolution of one currently applicable product-scoped grant."""

    grant_ref: str = Field(min_length=1, max_length=240)
    product_id: str = Field(min_length=1, max_length=240)
    authority: str = Field(min_length=1, max_length=120)
    state: Literal["active"] = "active"
    grant_hash: str = Field(pattern=r"^[a-f0-9]{64}$")
    effective_at: datetime
    expires_at: datetime | None = None

    @field_validator("effective_at", "expires_at")
    @classmethod
    def validate_times(cls, value: datetime | None, info) -> datetime | None:
        return _aware(value, info.field_name) if value is not None else None

    @model_validator(mode="after")
    def validate_expiry(self) -> Self:
        if self.expires_at is not None and self.expires_at <= self.effective_at:
            raise ValueError("resolved authority grant must not already be expired")
        return self


class GovernedStateRevisionV1(FrozenContract):
    """Opaque higher-layer revision admitted to Core's durable state plane."""

    contract: Literal["ace.core.governed-state-revision/v1alpha1"] = GOVERNED_STATE_REVISION_VERSION
    state_kind: str = Field(min_length=1, max_length=120)
    product_id: str = Field(min_length=1, max_length=240)
    state_id: str = Field(min_length=1, max_length=240)
    sequence: int = Field(ge=1)
    revision_id: str = Field(min_length=1, max_length=240)
    material_hash: str = Field(pattern=r"^[a-f0-9]{64}$")
    prior_revision_id: str | None = Field(default=None, max_length=240)
    approval_subject_ref: str = Field(min_length=1, max_length=240)
    payload_contract: str = Field(min_length=1, max_length=240)
    payload: dict[str, Any]

    @model_validator(mode="after")
    def validate_lineage(self) -> Self:
        if self.sequence == 1 and self.prior_revision_id is not None:
            raise ValueError("the first governed-state revision cannot name a prior revision")
        if self.sequence > 1 and self.prior_revision_id is None:
            raise ValueError("later governed-state revisions require a prior revision")
        return self


class GovernedStateCommitRequestV1(FrozenContract):
    """Fully resolved request for one exact atomic Core state admission."""

    revision: GovernedStateRevisionV1
    expected_head_revision_id: str | None = Field(default=None, max_length=240)
    actor_ref: str = Field(min_length=1, max_length=240)
    approval: ResolvedApprovalReceiptV1
    authority_grants: tuple[ResolvedAuthorityGrantV1, ...] = ()
    committed_at: datetime

    @field_validator("committed_at")
    @classmethod
    def validate_committed_at(cls, value: datetime) -> datetime:
        return _aware(value, "committed_at")

    @model_validator(mode="after")
    def validate_scope_and_authority(self) -> Self:
        revision = self.revision
        if revision.prior_revision_id != self.expected_head_revision_id:
            raise ValueError("expected head must exactly equal the revision's prior revision")
        if self.approval.product_id != revision.product_id:
            raise ValueError("approval receipt must resolve in the revision product scope")
        if self.approval.subject_ref != revision.approval_subject_ref:
            raise ValueError("approval receipt must resolve to the exact governed-state subject")
        if self.approval.actor_ref != self.actor_ref:
            raise ValueError("approval actor must equal the committing actor")
        if self.approval.approved_at > self.committed_at:
            raise ValueError("approval receipt cannot postdate the Core commit")
        for grant in self.authority_grants:
            if grant.product_id != revision.product_id:
                raise ValueError("authority grant must resolve in the revision product scope")
        return self

    def receipt(self) -> GovernedStateCommitReceiptV1:
        return GovernedStateCommitReceiptV1(
            state_kind=self.revision.state_kind,
            product_id=self.revision.product_id,
            state_id=self.revision.state_id,
            sequence=self.revision.sequence,
            revision_id=self.revision.revision_id,
            material_hash=self.revision.material_hash,
            prior_revision_id=self.revision.prior_revision_id,
            actor_ref=self.actor_ref,
            approval=self.approval,
            authority_grants=self.authority_grants,
            committed_at=self.committed_at,
        )


class GovernedStateCommitReceiptV1(FrozenContract):
    """Durable audit receipt proving committed, but not live, authority."""

    contract: Literal["ace.core.governed-state-commit-receipt/v1alpha1"] = GOVERNED_STATE_COMMIT_RECEIPT_VERSION
    authority_stage: Literal["committed"] = "committed"
    state_kind: str
    product_id: str
    state_id: str
    sequence: int = Field(ge=1)
    revision_id: str
    material_hash: str = Field(pattern=r"^[a-f0-9]{64}$")
    prior_revision_id: str | None = None
    actor_ref: str
    approval: ResolvedApprovalReceiptV1
    authority_grants: tuple[ResolvedAuthorityGrantV1, ...] = ()
    committed_at: datetime
    audit_id: str | None = None
    receipt_id: str | None = None
    receipt_hash: str | None = None

    @field_validator("committed_at")
    @classmethod
    def validate_committed_at(cls, value: datetime) -> datetime:
        return _aware(value, "committed_at")

    @model_validator(mode="after")
    def derive_identity(self) -> Self:
        material = self.model_dump(
            mode="json",
            exclude={"audit_id", "receipt_id", "receipt_hash"},
        )
        digest = canonical_hash(material)
        expected_audit = stable_id("governed_state_audit", material)
        expected_receipt = f"governed_state_commit:{digest[:32]}"
        if self.audit_id is not None and self.audit_id != expected_audit:
            raise ValueError("governed-state audit identity does not match exact commit material")
        if self.receipt_id is not None and self.receipt_id != expected_receipt:
            raise ValueError("governed-state commit identity does not match exact commit material")
        if self.receipt_hash is not None and self.receipt_hash != digest:
            raise ValueError("governed-state commit hash does not match exact commit material")
        object.__setattr__(self, "audit_id", expected_audit)
        object.__setattr__(self, "receipt_id", expected_receipt)
        object.__setattr__(self, "receipt_hash", digest)
        return self


class GovernedStateHeadV1(FrozenContract):
    """Current committed head for one product-scoped governed state identity."""

    contract: Literal["ace.core.governed-state-head/v1alpha1"] = GOVERNED_STATE_HEAD_VERSION
    state_kind: str
    product_id: str
    state_id: str
    sequence: int = Field(ge=1)
    revision_id: str
    commit_receipt_id: str
    updated_at: datetime
    head_id: str | None = None

    @field_validator("updated_at")
    @classmethod
    def validate_updated_at(cls, value: datetime) -> datetime:
        return _aware(value, "updated_at")

    @model_validator(mode="after")
    def derive_identity(self) -> Self:
        expected = stable_id(
            "governed_state_head",
            {
                "state_kind": self.state_kind,
                "product_id": self.product_id,
                "state_id": self.state_id,
            },
        )
        if self.head_id is not None and self.head_id != expected:
            raise ValueError("governed-state head identity does not match its exact scope")
        object.__setattr__(self, "head_id", expected)
        return self


class GovernedStateHeadPreconditionV1Alpha1(FrozenContract):
    """One exact governed-state head that must remain current at append commit.

    The value is an optimistic-concurrency assertion, not an authority token.
    Append stores compare all six coordinates in the same transaction that
    creates immutable records and their receipt.
    """

    contract: Literal["ace.core.governed-state-head-precondition/v1alpha1"] = GOVERNED_STATE_HEAD_PRECONDITION_VERSION
    state_kind: str = Field(min_length=1, max_length=120)
    product_id: str = Field(min_length=1, max_length=240)
    state_id: str = Field(min_length=1, max_length=240)
    sequence: int = Field(ge=1)
    revision_id: str = Field(min_length=1, max_length=240)
    commit_receipt_id: str = Field(min_length=1, max_length=240)

    @classmethod
    def from_head(cls, head: GovernedStateHeadV1) -> GovernedStateHeadPreconditionV1Alpha1:
        """Copy the exact comparable coordinates from a validated Core head."""

        validated = GovernedStateHeadV1.model_validate(head.model_dump(mode="python"))
        return cls(
            state_kind=validated.state_kind,
            product_id=validated.product_id,
            state_id=validated.state_id,
            sequence=validated.sequence,
            revision_id=validated.revision_id,
            commit_receipt_id=validated.commit_receipt_id,
        )


class CoreAuthorityResolver(Protocol):
    """Port to existing Core approval and authority sources of truth."""

    async def resolve_approval(
        self,
        *,
        receipt_ref: str,
        product_id: str,
        subject_ref: str,
        actor_ref: str,
        effective_at: datetime,
    ) -> ResolvedApprovalReceiptV1: ...

    async def resolve_grant(
        self,
        *,
        grant_ref: str,
        product_id: str,
        authority: str,
        effective_at: datetime,
    ) -> ResolvedAuthorityGrantV1: ...


class GovernedStateStore(Protocol):
    """Core persistence port; hosts supply one transaction-capable adapter."""

    async def commit(self, request: GovernedStateCommitRequestV1) -> GovernedStateCommitReceiptV1: ...

    async def load_head(self, *, state_kind: str, product_id: str, state_id: str) -> GovernedStateHeadV1 | None: ...

    async def load_revision(self, revision_id: str, *, product_id: str) -> GovernedStateRevisionV1 | None: ...

    async def load_receipt(self, receipt_id: str, *, product_id: str) -> GovernedStateCommitReceiptV1 | None: ...


__all__ = [
    "CoreAuthorityResolver",
    "GOVERNED_STATE_COMMIT_RECEIPT_VERSION",
    "GOVERNED_STATE_HEAD_VERSION",
    "GOVERNED_STATE_HEAD_PRECONDITION_VERSION",
    "GOVERNED_STATE_REVISION_VERSION",
    "GovernedStateCommitReceiptV1",
    "GovernedStateCommitRequestV1",
    "GovernedStateHeadV1",
    "GovernedStateHeadPreconditionV1Alpha1",
    "GovernedStateRevisionV1",
    "GovernedStateStore",
    "ResolvedApprovalReceiptV1",
    "ResolvedAuthorityGrantV1",
]
