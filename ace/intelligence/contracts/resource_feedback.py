"""Exact, attributed feedback against one projected Intelligence resource.

This contract records a human correction proposal.  It deliberately does not
change the target, source trust, ranking, resolution, or recalculation state.
Those effects require a later governed maintenance decision with new evidence.
"""

from __future__ import annotations

from datetime import UTC, datetime
from enum import StrEnum
from typing import Literal, Self

from pydantic import ConfigDict, Field, field_validator, model_validator

from ace.core.contracts import FrozenContract, canonical_hash
from ace.core.records import AppendOnlyTransactionReceiptV1, ImmutableRecordReferenceV1
from ace.core.runtime_use import AuthenticatedRuntimeContextV1Alpha1, AuthorityUseReceiptV1Alpha1
from ace.intelligence.contracts.common import validate_digest, validate_product_id, validate_reference
from ace.intelligence.contracts.resource_plane import (
    IntelligenceResourceKind,
    IntelligenceResourceReferenceV1Alpha1,
)

RESOURCE_FEEDBACK_REQUEST_VERSION = "ace.intelligence.resource-feedback-request/v1alpha1"
RESOURCE_FEEDBACK_RECEIPT_VERSION = "ace.intelligence.resource-feedback-receipt/v1alpha1"
RESOURCE_FEEDBACK_ADMISSION_VERSION = "ace.intelligence.resource-feedback-admission/v1alpha1"

MAX_RESOURCE_FEEDBACK_EVIDENCE = 32
CORRECTABLE_RESOURCE_KINDS = frozenset(
    {
        IntelligenceResourceKind.OBSERVATION,
        IntelligenceResourceKind.ENTITY,
        IntelligenceResourceKind.SIGNAL,
        IntelligenceResourceKind.SHIFT,
        IntelligenceResourceKind.BRIEF,
    }
)


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


class IntelligenceResourceCorrectionIntent(StrEnum):
    OUTDATED = "outdated"
    ENTITY_MAPPING_WRONG = "entity_mapping_wrong"
    MISSING_SOURCE = "missing_source"
    SOURCE_OVERWEIGHTED = "source_overweighted"


class IntelligenceResourceFeedbackRequestV1Alpha1(_StrictFrozenContract):
    """One idempotent actor request targeting an exact projected revision."""

    contract: Literal["ace.intelligence.resource-feedback-request/v1alpha1"] = RESOURCE_FEEDBACK_REQUEST_VERSION
    authenticated_context: AuthenticatedRuntimeContextV1Alpha1
    product_id: str
    authority_grant_ref: str
    request_key: str
    target: IntelligenceResourceReferenceV1Alpha1
    correction_intent: IntelligenceResourceCorrectionIntent
    note: str = Field(min_length=1, max_length=4_000)
    evidence: tuple[IntelligenceResourceReferenceV1Alpha1, ...] = Field(
        default_factory=tuple,
        max_length=MAX_RESOURCE_FEEDBACK_EVIDENCE,
    )
    requested_at: datetime
    feedback_id: str | None = None
    feedback_digest: str | None = None

    @field_validator("product_id")
    @classmethod
    def validate_scope(cls, value: str) -> str:
        return validate_product_id(value)

    @field_validator("authority_grant_ref", "request_key")
    @classmethod
    def validate_refs(cls, value: str, info) -> str:
        return validate_reference(value, name=info.field_name)

    @field_validator("note")
    @classmethod
    def validate_note(cls, value: str) -> str:
        if value != value.strip():
            raise ValueError("note must be trimmed")
        return value

    @field_validator("requested_at")
    @classmethod
    def normalize_requested_at(cls, value: datetime) -> datetime:
        return _aware(value, name="requested_at")

    @field_validator("evidence")
    @classmethod
    def normalize_evidence(
        cls,
        value: tuple[IntelligenceResourceReferenceV1Alpha1, ...],
    ) -> tuple[IntelligenceResourceReferenceV1Alpha1, ...]:
        keys = [(item.resource_kind.value, item.resource_id, item.revision, item.resource_digest) for item in value]
        if len(keys) != len(set(keys)):
            raise ValueError("evidence references must be unique")
        return tuple(sorted(value, key=lambda item: (item.resource_kind.value, item.resource_id, item.revision)))

    @field_validator("feedback_digest")
    @classmethod
    def validate_feedback_digest(cls, value: str | None) -> str | None:
        return None if value is None else validate_digest(value)

    @model_validator(mode="after")
    def validate_exact_scope_and_identity(self) -> Self:
        context = self.authenticated_context
        if context.product_id != self.product_id or self.target.product_id != self.product_id:
            raise ValueError("feedback request crossed authenticated product scope")
        if context.actor_ref == "":
            raise ValueError("feedback request requires an attributed actor")
        if not (context.authenticated_at <= self.requested_at < context.expires_at):
            raise ValueError("feedback request fell outside its authentication window")
        if self.target.resource_kind not in CORRECTABLE_RESOURCE_KINDS:
            raise ValueError("target kind is not a user-correctable Intelligence object")
        if any(item.product_id != self.product_id for item in self.evidence):
            raise ValueError("feedback evidence crossed product scope")
        if any(item == self.target for item in self.evidence):
            raise ValueError("target cannot also be submitted as correction evidence")

        identity_material = {
            "product_id": self.product_id,
            "actor_ref": context.actor_ref,
            "request_key": self.request_key,
        }
        content_material = {
            **identity_material,
            "authority_grant_ref": self.authority_grant_ref,
            "target": self.target.model_dump(mode="json"),
            "correction_intent": self.correction_intent.value,
            "note": self.note,
            "evidence": [item.model_dump(mode="json") for item in self.evidence],
        }
        identity_hash = canonical_hash(identity_material)
        content_hash = canonical_hash(content_material)
        expected_id = f"resource_feedback:{identity_hash[:32]}"
        expected_digest = f"sha256:{content_hash}"
        if self.feedback_id is not None and self.feedback_id != expected_id:
            raise ValueError("feedback_id does not match actor-scoped request identity")
        if self.feedback_digest is not None and self.feedback_digest != expected_digest:
            raise ValueError("feedback_digest does not match exact correction material")
        object.__setattr__(self, "feedback_id", expected_id)
        object.__setattr__(self, "feedback_digest", expected_digest)
        return self


class IntelligenceResourceFeedbackReceiptV1Alpha1(_StrictFrozenContract):
    """Attributed immutable evidence that the proposal was recorded, and only that."""

    contract: Literal["ace.intelligence.resource-feedback-receipt/v1alpha1"] = RESOURCE_FEEDBACK_RECEIPT_VERSION
    request: IntelligenceResourceFeedbackRequestV1Alpha1
    authority_use: AuthorityUseReceiptV1Alpha1
    recorded_at: datetime
    disposition: Literal["recorded_proposal_only"] = "recorded_proposal_only"
    changes_target: Literal[False] = False
    changes_source_trust: Literal[False] = False
    changes_ranking: Literal[False] = False
    triggers_recalculation: Literal[False] = False
    receipt_id: str | None = None
    receipt_digest: str | None = None

    @field_validator("recorded_at")
    @classmethod
    def normalize_recorded_at(cls, value: datetime) -> datetime:
        return _aware(value, name="recorded_at")

    @field_validator("receipt_digest")
    @classmethod
    def validate_receipt_digest(cls, value: str | None) -> str | None:
        return None if value is None else validate_digest(value)

    @model_validator(mode="after")
    def validate_attribution_and_identity(self) -> Self:
        request = self.request
        authority = self.authority_use
        if (
            authority.product_id != request.product_id
            or authority.actor_ref != request.authenticated_context.actor_ref
            or authority.authenticated_context != request.authenticated_context
            or authority.use_subject_ref != request.feedback_id
            or authority.use_subject_digest != request.feedback_digest
            or authority.grant_ref != request.authority_grant_ref
            or authority.evaluated_at != self.recorded_at
        ):
            raise ValueError("feedback receipt did not preserve exact attribution and authority")
        material = self.model_dump(mode="json", exclude={"receipt_id", "receipt_digest"})
        digest = canonical_hash(material)
        expected_id = f"resource_feedback_receipt:{digest[:32]}"
        expected_digest = f"sha256:{digest}"
        if self.receipt_id is not None and self.receipt_id != expected_id:
            raise ValueError("receipt_id does not match exact recorded feedback")
        if self.receipt_digest is not None and self.receipt_digest != expected_digest:
            raise ValueError("receipt_digest does not match exact recorded feedback")
        object.__setattr__(self, "receipt_id", expected_id)
        object.__setattr__(self, "receipt_digest", expected_digest)
        return self


class IntelligenceResourceFeedbackAdmissionV1Alpha1(_StrictFrozenContract):
    """Transport-safe result containing the resource and Core durability proofs."""

    contract: Literal["ace.intelligence.resource-feedback-admission/v1alpha1"] = RESOURCE_FEEDBACK_ADMISSION_VERSION
    feedback: IntelligenceResourceFeedbackReceiptV1Alpha1
    record: ImmutableRecordReferenceV1
    transaction: AppendOnlyTransactionReceiptV1

    @model_validator(mode="after")
    def validate_durability_proofs(self) -> Self:
        feedback = self.feedback
        if (
            self.record.product_id != feedback.request.product_id
            or self.record.record_kind != "resource_feedback"
            or self.record.record_key != feedback.request.feedback_id
            or self.record.payload_contract != feedback.contract
            or self.record not in self.transaction.records
            or self.transaction.product_id != feedback.request.product_id
            or self.transaction.governed_state_preconditions != (feedback.authority_use.state_head_precondition,)
        ):
            raise ValueError("feedback admission does not prove the exact immutable append")
        return self


__all__ = [
    "CORRECTABLE_RESOURCE_KINDS",
    "RESOURCE_FEEDBACK_ADMISSION_VERSION",
    "RESOURCE_FEEDBACK_RECEIPT_VERSION",
    "RESOURCE_FEEDBACK_REQUEST_VERSION",
    "IntelligenceResourceCorrectionIntent",
    "IntelligenceResourceFeedbackAdmissionV1Alpha1",
    "IntelligenceResourceFeedbackReceiptV1Alpha1",
    "IntelligenceResourceFeedbackRequestV1Alpha1",
]
