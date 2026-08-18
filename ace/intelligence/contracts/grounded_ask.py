"""Server-side grounded Ask (J7) — answers are exact, already-grounded claims.

An Ask answer never manufactures new claim or citation material: it only
selects and returns ``GroundedClaimV1Alpha1``/``CitationV1Alpha1`` objects
that already exist, verbatim, on governed ``BriefV1Alpha1`` resources the
asking principal is authorized to read. If nothing citable matches the
question, the honest response is ``AskNoAnswerV1Alpha1`` naming what
coverage is missing, never an uncited ``AskAnswerV1Alpha1``.
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Literal, Self

from pydantic import ConfigDict, Field, field_validator, model_validator

from ace.core.contracts import FrozenContract
from ace.core.runtime_use import AuthenticatedRuntimeContextV1Alpha1, AuthorityUseReceiptV1Alpha1
from ace.intelligence.contracts.common import validate_product_id, validate_reference
from ace.intelligence.contracts.resource_plane import IntelligenceResourceReferenceV1Alpha1
from ace.intelligence.contracts.resources import CitationV1Alpha1, ClaimGroundingKind, GroundedClaimV1Alpha1

ASK_QUESTION_VERSION = "ace.intelligence.ask-question/v1alpha1"
ASK_ANSWER_VERSION = "ace.intelligence.ask-answer/v1alpha1"
ASK_NO_ANSWER_VERSION = "ace.intelligence.ask-no-answer/v1alpha1"

MAX_ASK_CLAIMS = 20
MAX_ASK_QUESTION_CHARS = 2_000
MAX_ASK_SUBJECT_REFS = 256
MAX_ASK_MISSING_COVERAGE = 32
MAX_ASK_SOURCE_BRIEFS = MAX_ASK_CLAIMS
MAX_ASK_CITATIONS = MAX_ASK_CLAIMS * 4


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


def _unique_sorted_refs(
    value: tuple[IntelligenceResourceReferenceV1Alpha1, ...],
) -> tuple[IntelligenceResourceReferenceV1Alpha1, ...]:
    keys = [(item.resource_kind.value, item.resource_id, item.revision) for item in value]
    if len(keys) != len(set(keys)):
        raise ValueError("resource references must be unique")
    return tuple(sorted(value, key=lambda item: (item.resource_kind.value, item.resource_id, item.revision)))


class AskQuestionV1Alpha1(_StrictFrozenContract):
    """One authenticated, product-scoped question over authorized Brief claims."""

    contract: Literal["ace.intelligence.ask-question/v1alpha1"] = ASK_QUESTION_VERSION
    authenticated_context: AuthenticatedRuntimeContextV1Alpha1
    product_id: str
    authority_grant_ref: str
    question: str = Field(min_length=1, max_length=MAX_ASK_QUESTION_CHARS)
    subject_refs: tuple[str, ...] = Field(default_factory=tuple, max_length=MAX_ASK_SUBJECT_REFS)
    as_of: datetime
    available_at: datetime
    max_claims: int = Field(default=5, ge=1, le=MAX_ASK_CLAIMS)

    @field_validator("product_id")
    @classmethod
    def validate_product_scope(cls, value: str) -> str:
        return validate_product_id(value)

    @field_validator("authority_grant_ref")
    @classmethod
    def validate_grant(cls, value: str) -> str:
        return validate_reference(value, name="authority_grant_ref")

    @field_validator("question")
    @classmethod
    def validate_question(cls, value: str) -> str:
        if value != value.strip():
            raise ValueError("question must be trimmed")
        return value

    @field_validator("subject_refs")
    @classmethod
    def normalize_subjects(cls, value: tuple[str, ...]) -> tuple[str, ...]:
        normalized = tuple(sorted(validate_reference(item, name="subject_refs") for item in value))
        if len(normalized) != len(set(normalized)):
            raise ValueError("subject_refs must be unique")
        return normalized

    @field_validator("as_of", "available_at")
    @classmethod
    def normalize_times(cls, value: datetime, info) -> datetime:
        return _aware(value, name=info.field_name)

    @model_validator(mode="after")
    def validate_scope_and_time(self) -> Self:
        if self.authenticated_context.product_id != self.product_id:
            raise ValueError("ask question crossed authenticated product scope")
        if self.available_at < self.as_of:
            raise ValueError("ask available_at cannot precede as_of")
        return self


class AskAnswerV1Alpha1(_StrictFrozenContract):
    """A grounded answer: exact cited claims plus their exact citations."""

    contract: Literal["ace.intelligence.ask-answer/v1alpha1"] = ASK_ANSWER_VERSION
    question: str = Field(min_length=1, max_length=MAX_ASK_QUESTION_CHARS)
    product_id: str
    actor_ref: str
    claims: tuple[GroundedClaimV1Alpha1, ...] = Field(min_length=1, max_length=MAX_ASK_CLAIMS)
    citations: tuple[CitationV1Alpha1, ...] = Field(min_length=1, max_length=MAX_ASK_CITATIONS)
    source_briefs: tuple[IntelligenceResourceReferenceV1Alpha1, ...] = Field(
        min_length=1, max_length=MAX_ASK_SOURCE_BRIEFS
    )
    answered_at: datetime
    authority_use: AuthorityUseReceiptV1Alpha1

    @field_validator("product_id")
    @classmethod
    def validate_product_scope(cls, value: str) -> str:
        return validate_product_id(value)

    @field_validator("claims")
    @classmethod
    def validate_unique_claims(cls, value: tuple[GroundedClaimV1Alpha1, ...]) -> tuple[GroundedClaimV1Alpha1, ...]:
        ids = [item.claim_id for item in value]
        if len(ids) != len(set(ids)):
            raise ValueError("answer claims must use unique content identities")
        return value

    @field_validator("citations")
    @classmethod
    def normalize_citations(cls, value: tuple[CitationV1Alpha1, ...]) -> tuple[CitationV1Alpha1, ...]:
        ids = [item.citation_id for item in value]
        if len(ids) != len(set(ids)):
            raise ValueError("answer citations must use unique content identities")
        return tuple(sorted(value, key=lambda item: item.citation_id or ""))

    @field_validator("source_briefs")
    @classmethod
    def normalize_source_briefs(
        cls, value: tuple[IntelligenceResourceReferenceV1Alpha1, ...]
    ) -> tuple[IntelligenceResourceReferenceV1Alpha1, ...]:
        return _unique_sorted_refs(value)

    @field_validator("answered_at")
    @classmethod
    def normalize_answered_at(cls, value: datetime) -> datetime:
        return _aware(value, name="answered_at")

    @model_validator(mode="after")
    def validate_grounding(self) -> Self:
        if any(claim.grounding_kind is not ClaimGroundingKind.CITED for claim in self.claims):
            raise ValueError("a grounded Ask answer may only surface cited claims")
        citation_ids = {item.citation_id for item in self.citations}
        used = {citation_id for claim in self.claims for citation_id in claim.citation_ids}
        missing = used - citation_ids
        if missing:
            raise ValueError(f"answer claims reference missing citations: {sorted(missing)}")
        unused = citation_ids - used
        if unused:
            raise ValueError(f"answer contains unused citations: {sorted(unused)}")
        if any(ref.product_id != self.product_id for ref in self.source_briefs):
            raise ValueError("answer source Briefs crossed product scope")
        if self.authority_use.product_id != self.product_id or self.authority_use.actor_ref != self.actor_ref:
            raise ValueError("answer authority receipt does not match its exact principal")
        return self


class AskNoAnswerV1Alpha1(_StrictFrozenContract):
    """An honest refusal naming exactly what coverage is missing."""

    contract: Literal["ace.intelligence.ask-no-answer/v1alpha1"] = ASK_NO_ANSWER_VERSION
    question: str = Field(min_length=1, max_length=MAX_ASK_QUESTION_CHARS)
    product_id: str
    actor_ref: str
    missing_coverage: tuple[str, ...] = Field(min_length=1, max_length=MAX_ASK_MISSING_COVERAGE)
    considered_briefs: tuple[IntelligenceResourceReferenceV1Alpha1, ...] = Field(
        default_factory=tuple, max_length=MAX_ASK_SOURCE_BRIEFS
    )
    evaluated_at: datetime
    authority_use: AuthorityUseReceiptV1Alpha1

    @field_validator("product_id")
    @classmethod
    def validate_product_scope(cls, value: str) -> str:
        return validate_product_id(value)

    @field_validator("missing_coverage")
    @classmethod
    def normalize_missing_coverage(cls, value: tuple[str, ...]) -> tuple[str, ...]:
        normalized = tuple(sorted(validate_reference(item, name="missing_coverage") for item in value))
        if len(normalized) != len(set(normalized)):
            raise ValueError("missing_coverage reasons must be unique")
        return normalized

    @field_validator("considered_briefs")
    @classmethod
    def normalize_considered_briefs(
        cls, value: tuple[IntelligenceResourceReferenceV1Alpha1, ...]
    ) -> tuple[IntelligenceResourceReferenceV1Alpha1, ...]:
        return _unique_sorted_refs(value)

    @field_validator("evaluated_at")
    @classmethod
    def normalize_evaluated_at(cls, value: datetime) -> datetime:
        return _aware(value, name="evaluated_at")

    @model_validator(mode="after")
    def validate_scope(self) -> Self:
        if any(ref.product_id != self.product_id for ref in self.considered_briefs):
            raise ValueError("no-answer considered Briefs crossed product scope")
        if self.authority_use.product_id != self.product_id or self.authority_use.actor_ref != self.actor_ref:
            raise ValueError("no-answer authority receipt does not match its exact principal")
        return self


__all__ = [
    "ASK_ANSWER_VERSION",
    "ASK_NO_ANSWER_VERSION",
    "ASK_QUESTION_VERSION",
    "MAX_ASK_CLAIMS",
    "AskAnswerV1Alpha1",
    "AskNoAnswerV1Alpha1",
    "AskQuestionV1Alpha1",
]
