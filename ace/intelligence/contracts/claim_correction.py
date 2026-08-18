"""Claim-bound correction (J8) — proposal-only, never a silent mutation.

Binds a correction to the exact ``claim_id``/``citation_id`` pair of a
grounded Ask answer, then reuses the existing proposal-only feedback
machinery (``IntelligenceResourceFeedbackRequestV1Alpha1`` /
``IntelligenceResourceFeedbackService``) verbatim to record it. This module
adds no new durable write path — it only proves, at the type level, that the
underlying feedback record was scoped to one exact claim and citation before
it was written.
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Literal, Self

from pydantic import ConfigDict, Field, field_validator, model_validator

from ace.core.contracts import FrozenContract, canonical_hash
from ace.core.runtime_use import AuthenticatedRuntimeContextV1Alpha1
from ace.intelligence.contracts.common import validate_product_id, validate_reference
from ace.intelligence.contracts.resource_feedback import (
    IntelligenceResourceCorrectionIntent,
    IntelligenceResourceFeedbackAdmissionV1Alpha1,
)
from ace.intelligence.contracts.resource_plane import IntelligenceResourceKind, IntelligenceResourceReferenceV1Alpha1

CLAIM_CORRECTION_REQUEST_VERSION = "ace.intelligence.claim-correction-request/v1alpha1"
CLAIM_CORRECTION_ADMISSION_VERSION = "ace.intelligence.claim-correction-admission/v1alpha1"

MAX_CLAIM_CORRECTION_EVIDENCE = 32
MAX_CLAIM_CORRECTION_NOTE_CHARS = 3_800


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


class ClaimCorrectionRequestV1Alpha1(_StrictFrozenContract):
    """One idempotent actor request correcting one exact claim/citation pair."""

    contract: Literal["ace.intelligence.claim-correction-request/v1alpha1"] = CLAIM_CORRECTION_REQUEST_VERSION
    authenticated_context: AuthenticatedRuntimeContextV1Alpha1
    product_id: str
    authority_grant_ref: str
    request_key: str
    target: IntelligenceResourceReferenceV1Alpha1
    claim_id: str
    citation_id: str
    correction_intent: IntelligenceResourceCorrectionIntent
    note: str = Field(min_length=1, max_length=MAX_CLAIM_CORRECTION_NOTE_CHARS)
    evidence: tuple[IntelligenceResourceReferenceV1Alpha1, ...] = Field(
        default_factory=tuple, max_length=MAX_CLAIM_CORRECTION_EVIDENCE
    )
    requested_at: datetime
    correction_id: str | None = None
    correction_digest: str | None = None

    @field_validator("product_id")
    @classmethod
    def validate_product_scope(cls, value: str) -> str:
        return validate_product_id(value)

    @field_validator("authority_grant_ref", "request_key", "claim_id", "citation_id")
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
        cls, value: tuple[IntelligenceResourceReferenceV1Alpha1, ...]
    ) -> tuple[IntelligenceResourceReferenceV1Alpha1, ...]:
        keys = [(item.resource_kind.value, item.resource_id, item.revision, item.resource_digest) for item in value]
        if len(keys) != len(set(keys)):
            raise ValueError("evidence references must be unique")
        return tuple(sorted(value, key=lambda item: (item.resource_kind.value, item.resource_id, item.revision)))

    @model_validator(mode="after")
    def validate_exact_scope_and_identity(self) -> Self:
        context = self.authenticated_context
        if context.product_id != self.product_id or self.target.product_id != self.product_id:
            raise ValueError("claim correction request crossed authenticated product scope")
        if not (context.authenticated_at <= self.requested_at < context.expires_at):
            raise ValueError("claim correction request fell outside its authentication window")
        if self.target.resource_kind is not IntelligenceResourceKind.BRIEF:
            raise ValueError("a claim-bound correction may only target a Brief resource")
        if any(item.product_id != self.product_id for item in self.evidence):
            raise ValueError("claim correction evidence crossed product scope")

        identity_material = {
            "product_id": self.product_id,
            "actor_ref": context.actor_ref,
            "request_key": self.request_key,
            "claim_id": self.claim_id,
            "citation_id": self.citation_id,
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
        expected_id = f"claim_correction:{identity_hash[:32]}"
        expected_digest = f"sha256:{content_hash}"
        if self.correction_id is not None and self.correction_id != expected_id:
            raise ValueError("correction_id does not match actor-scoped request identity")
        if self.correction_digest is not None and self.correction_digest != expected_digest:
            raise ValueError("correction_digest does not match exact correction material")
        object.__setattr__(self, "correction_id", expected_id)
        object.__setattr__(self, "correction_digest", expected_digest)
        return self

    @property
    def feedback_note(self) -> str:
        return f"[claim:{self.claim_id}][citation:{self.citation_id}] {self.note}"


class ClaimCorrectionAdmissionV1Alpha1(_StrictFrozenContract):
    """Proof that the recorded proposal-only feedback was bound to this exact claim/citation."""

    contract: Literal["ace.intelligence.claim-correction-admission/v1alpha1"] = CLAIM_CORRECTION_ADMISSION_VERSION
    request: ClaimCorrectionRequestV1Alpha1
    feedback: IntelligenceResourceFeedbackAdmissionV1Alpha1

    @model_validator(mode="after")
    def validate_binding(self) -> Self:
        underlying = self.feedback.feedback.request
        if (
            underlying.product_id != self.request.product_id
            or underlying.target != self.request.target
            or underlying.correction_intent != self.request.correction_intent
            or underlying.evidence != self.request.evidence
            or underlying.authenticated_context.actor_ref != self.request.authenticated_context.actor_ref
            or underlying.note != self.request.feedback_note
        ):
            raise ValueError("claim correction admission does not prove the exact claim/citation-bound proposal")
        return self


__all__ = [
    "CLAIM_CORRECTION_ADMISSION_VERSION",
    "CLAIM_CORRECTION_REQUEST_VERSION",
    "ClaimCorrectionAdmissionV1Alpha1",
    "ClaimCorrectionRequestV1Alpha1",
]
