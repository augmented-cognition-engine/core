"""Immutable TP7 contracts for explicit promotion into ACE cognitive memory.

Promotion is a reviewed bridge between the grounded-state plane and the
existing ``insight`` memory plane.  A proposal can be model-authored, but only
an authenticated human or an allow-listed deterministic policy can author an
authoritative lifecycle disposition.
"""

from __future__ import annotations

from datetime import datetime
from enum import StrEnum
from typing import Any, Literal, Self

from pydantic import Field, field_validator, model_validator

from core.engine.grounded_state.belief_contracts import ReviewAuthority, _aware, _product, _refs
from core.engine.grounded_state.contracts import FrozenContract, canonical_hash
from core.engine.grounded_state.rollout_contracts import EvidenceCoverageState, ProviderExecutionV1

PROMOTION_PROPOSAL_VERSION = "ace.grounded-state.promotion-proposal/v1"
PROMOTION_REVIEW_VERSION = "ace.grounded-state.promotion-review/v1"
PROMOTION_RECEIPT_VERSION = "ace.grounded-state.promotion-receipt/v1"
PROMOTION_MEMORY_LINEAGE_VERSION = "ace.grounded-state.promotion-memory-lineage/v1"
PROMOTION_RETRIEVAL_VERSION = "ace.grounded-state.promotion-retrieval/v1"

TP7_PROMOTION_POLICY_VERSION = "ace.grounded-state.promotion-policy/v1"
TP7_PROMOTION_RESOLVER_VERSION = "ace.grounded-state.promotion-resolver/v1"
TP7_PROMOTION_REVIEW_POLICY_VERSION = "ace.grounded-state.promotion-review-policy/v1"
TP7_PROMOTION_ONTOLOGY_VERSION = "ace.grounded-state.promotion-ontology/v1"
TP7_MEMORY_ONTOLOGY_VERSION = "ace.cognitive-memory.ontology/v1"

MAX_PROMOTION_EVIDENCE = 64
MAX_PROMOTION_TRANSITIONS = 16
MAX_PROMOTION_LINEAGE = 32
MAX_PROMOTION_REASONS = 50
MAX_PROMOTION_CONTENT_CHARS = 8_000


class PromotionTargetKind(StrEnum):
    DURABLE_CONCLUSION = "durable_conclusion"
    DECISION = "decision"
    CORRECTION = "correction"
    STABLE_PREFERENCE = "stable_preference"
    REUSABLE_REASONING_PATTERN = "reusable_reasoning_pattern"


class PromotionOriginMeaning(StrEnum):
    GROUNDED_REASONING_CONCLUSION = "grounded_reasoning_conclusion"
    TASK_DECISION = "task_decision"
    HUMAN_CORRECTION = "human_correction"
    STABLE_PREFERENCE = "stable_preference"
    REUSABLE_REASONING_PATTERN = "reusable_reasoning_pattern"


class PromotionMemoryMeaning(StrEnum):
    DURABLE_CONCLUSION = "durable_conclusion"
    DECISION = "decision"
    CORRECTION = "correction"
    PREFERENCE = "preference"
    PATTERN = "pattern"


class PromotionDisposition(StrEnum):
    ACCEPTED = "accepted"
    REJECTED = "rejected"
    EXPIRED = "expired"
    CONTESTED = "contested"
    INVALIDATED = "invalidated"
    SUPERSEDED = "superseded"
    FAILED = "failed"
    DEGRADED = "degraded"


class PromotionEffectiveState(StrEnum):
    ACTIVE = "active"
    REJECTED = "rejected"
    EXPIRED = "expired"
    CONTESTED = "contested"
    INVALIDATED = "invalidated"
    SUPERSEDED = "superseded"
    FAILED = "failed"
    DEGRADED = "degraded"


class PromotionMaterialV1(FrozenContract):
    target_kind: PromotionTargetKind
    origin_meaning: PromotionOriginMeaning
    memory_meaning: PromotionMemoryMeaning
    content: str = Field(min_length=1, max_length=MAX_PROMOTION_CONTENT_CHARS)
    content_hash: str | None = None
    domain_path: str = Field(min_length=1, max_length=240)
    tags: tuple[str, ...] = Field(default_factory=tuple, max_length=50)

    @field_validator("tags", mode="before")
    @classmethod
    def normalize_tags(cls, value: Any) -> tuple[str, ...]:
        return _refs(value, limit=50, name="promotion tags")

    @model_validator(mode="after")
    def validate_meanings(self) -> Self:
        allowed = {
            PromotionTargetKind.DURABLE_CONCLUSION: (
                PromotionOriginMeaning.GROUNDED_REASONING_CONCLUSION,
                PromotionMemoryMeaning.DURABLE_CONCLUSION,
            ),
            PromotionTargetKind.DECISION: (
                PromotionOriginMeaning.TASK_DECISION,
                PromotionMemoryMeaning.DECISION,
            ),
            PromotionTargetKind.CORRECTION: (
                PromotionOriginMeaning.HUMAN_CORRECTION,
                PromotionMemoryMeaning.CORRECTION,
            ),
            PromotionTargetKind.STABLE_PREFERENCE: (
                PromotionOriginMeaning.STABLE_PREFERENCE,
                PromotionMemoryMeaning.PREFERENCE,
            ),
            PromotionTargetKind.REUSABLE_REASONING_PATTERN: (
                PromotionOriginMeaning.REUSABLE_REASONING_PATTERN,
                PromotionMemoryMeaning.PATTERN,
            ),
        }
        if (self.origin_meaning, self.memory_meaning) != allowed[self.target_kind]:
            raise ValueError("promotion target, source meaning, and memory meaning are incompatible")
        expected_hash = canonical_hash({"content": self.content, "memory_meaning": self.memory_meaning.value})
        if self.content_hash is not None and self.content_hash != expected_hash:
            raise ValueError("promotion content hash does not match exact reusable material")
        object.__setattr__(self, "content_hash", expected_hash)
        return self


class PromotionEvidenceVersionV1(FrozenContract):
    product_id: str
    record_id: str = Field(min_length=1, max_length=240)
    record_kind: str = Field(min_length=1, max_length=120)
    record_version: str = Field(min_length=1, max_length=240)
    content_hash: str = Field(pattern=r"^[a-f0-9]{64}$")
    coverage_state: EvidenceCoverageState = EvidenceCoverageState.SUPPORTED
    source_instruction_authority: Literal[False] = False

    @field_validator("product_id")
    @classmethod
    def validate_product(cls, value: str) -> str:
        return _product(value)


class PromotionTransitionRevisionV1(FrozenContract):
    revision_id: str = Field(min_length=1, max_length=240)
    revision_hash: str = Field(pattern=r"^[a-f0-9]{64}$")


class PromotionProposalV1(FrozenContract):
    contract_version: Literal["ace.grounded-state.promotion-proposal/v1"] = PROMOTION_PROPOSAL_VERSION
    proposal_id: str | None = None
    proposal_hash: str | None = None
    product_id: str
    material: PromotionMaterialV1
    task_id: str = Field(min_length=1, max_length=240)
    task_receipt_hash: str = Field(pattern=r"^[a-f0-9]{64}$")
    decision_receipt_id: str = Field(min_length=1, max_length=240)
    decision_receipt_hash: str = Field(pattern=r"^[a-f0-9]{64}$")
    context_pack_id: str = Field(min_length=1, max_length=240)
    context_pack_hash: str = Field(pattern=r"^[a-f0-9]{64}$")
    evidence_pack_id: str = Field(min_length=1, max_length=240)
    evidence_pack_hash: str = Field(pattern=r"^[a-f0-9]{64}$")
    evidence_versions: tuple[PromotionEvidenceVersionV1, ...] = Field(
        min_length=1,
        max_length=MAX_PROMOTION_EVIDENCE,
    )
    belief_projection_id: str = Field(min_length=1, max_length=240)
    belief_projection_hash: str = Field(pattern=r"^[a-f0-9]{64}$")
    transition_revisions: tuple[PromotionTransitionRevisionV1, ...] = Field(
        default_factory=tuple,
        max_length=MAX_PROMOTION_TRANSITIONS,
    )
    rollout_revision_id: str = Field(min_length=1, max_length=240)
    rollout_revision_hash: str = Field(pattern=r"^[a-f0-9]{64}$")
    reasoning_use_receipt_id: str = Field(min_length=1, max_length=240)
    reasoning_use_receipt_hash: str = Field(pattern=r"^[a-f0-9]{64}$")
    proposer_authority: ReviewAuthority
    proposer_ref: str = Field(min_length=1, max_length=240)
    proposed_at: datetime
    provenance: dict[str, Any]
    correction_observation_id: str | None = Field(default=None, max_length=240)
    prior_promotion_receipt_ids: tuple[str, ...] = Field(
        default_factory=tuple,
        max_length=MAX_PROMOTION_LINEAGE,
    )
    omissions: tuple[str, ...] = Field(default_factory=tuple, max_length=MAX_PROMOTION_REASONS)
    failures: tuple[str, ...] = Field(default_factory=tuple, max_length=MAX_PROMOTION_REASONS)
    degraded_reasons: tuple[str, ...] = Field(default_factory=tuple, max_length=MAX_PROMOTION_REASONS)
    contested_input_refs: tuple[str, ...] = Field(default_factory=tuple, max_length=MAX_PROMOTION_EVIDENCE)
    promotion_policy_version: str = Field(default=TP7_PROMOTION_POLICY_VERSION, min_length=1, max_length=160)
    resolver_version: str = Field(default=TP7_PROMOTION_RESOLVER_VERSION, min_length=1, max_length=160)
    review_policy_version: str = Field(default=TP7_PROMOTION_REVIEW_POLICY_VERSION, min_length=1, max_length=160)
    ontology_version: str = Field(default=TP7_PROMOTION_ONTOLOGY_VERSION, min_length=1, max_length=160)
    memory_ontology_version: str = Field(default=TP7_MEMORY_ONTOLOGY_VERSION, min_length=1, max_length=160)
    source_instruction_authority: Literal[False] = False
    simulated_state_is_observation: Literal[False] = False

    @field_validator("product_id")
    @classmethod
    def validate_product(cls, value: str) -> str:
        return _product(value)

    @field_validator("proposed_at")
    @classmethod
    def validate_time(cls, value: datetime) -> datetime:
        return _aware(value, "proposed_at")

    @field_validator("evidence_versions", mode="before")
    @classmethod
    def normalize_evidence(cls, value: Any) -> tuple[Any, ...]:
        if not isinstance(value, (list, tuple)):
            raise ValueError("promotion evidence versions must be a bounded collection")
        return tuple(
            sorted(
                value,
                key=lambda item: (
                    item.record_id if isinstance(item, PromotionEvidenceVersionV1) else str(item.get("record_id", ""))
                ),
            )
        )

    @field_validator("transition_revisions", mode="before")
    @classmethod
    def normalize_transitions(cls, value: Any) -> tuple[Any, ...]:
        if not isinstance(value, (list, tuple)):
            raise ValueError("promotion transition revisions must be a bounded collection")
        return tuple(
            sorted(
                value,
                key=lambda item: (
                    item.revision_id
                    if isinstance(item, PromotionTransitionRevisionV1)
                    else str(item.get("revision_id", ""))
                ),
            )
        )

    @field_validator(
        "prior_promotion_receipt_ids",
        "omissions",
        "failures",
        "degraded_reasons",
        "contested_input_refs",
        mode="before",
    )
    @classmethod
    def normalize_refs(cls, value: Any, info) -> tuple[str, ...]:
        limit = MAX_PROMOTION_EVIDENCE if info.field_name == "contested_input_refs" else MAX_PROMOTION_LINEAGE
        if info.field_name in {"omissions", "failures", "degraded_reasons"}:
            limit = MAX_PROMOTION_REASONS
        return _refs(value, limit=limit, name=info.field_name)

    @model_validator(mode="after")
    def derive_identity(self) -> Self:
        if any(item.product_id != self.product_id for item in self.evidence_versions):
            raise ValueError("promotion evidence versions cannot cross product scope")
        if len({item.record_id for item in self.evidence_versions}) != len(self.evidence_versions):
            raise ValueError("promotion evidence versions must have unique exact record identities")
        if self.material.target_kind is PromotionTargetKind.CORRECTION:
            if not self.correction_observation_id or not self.prior_promotion_receipt_ids:
                raise ValueError("a correction promotion requires exact correction and prior receipt lineage")
        elif self.correction_observation_id is not None:
            raise ValueError("only correction promotion can cite a correction observation")
        material = self.model_dump(mode="json", exclude={"proposal_id", "proposal_hash"})
        expected_hash = canonical_hash(material)
        expected_id = f"grounded_promotion_proposal:{expected_hash[:32]}"
        if self.proposal_hash is not None and self.proposal_hash != expected_hash:
            raise ValueError("promotion proposal hash does not match exact material")
        if self.proposal_id is not None and self.proposal_id != expected_id:
            raise ValueError("promotion proposal identity does not match exact material")
        object.__setattr__(self, "proposal_hash", expected_hash)
        object.__setattr__(self, "proposal_id", expected_id)
        return self


class PromotionReviewV1(FrozenContract):
    contract_version: Literal["ace.grounded-state.promotion-review/v1"] = PROMOTION_REVIEW_VERSION
    review_id: str | None = None
    review_hash: str | None = None
    product_id: str
    proposal_id: str = Field(min_length=1, max_length=240)
    proposal_hash: str = Field(pattern=r"^[a-f0-9]{64}$")
    disposition: PromotionDisposition
    authority: ReviewAuthority
    reviewer_ref: str = Field(min_length=1, max_length=240)
    authority_scope: str = Field(min_length=1, max_length=240)
    rationale: str = Field(min_length=1, max_length=2_000)
    reviewed_at: datetime
    policy_version: str = Field(default=TP7_PROMOTION_REVIEW_POLICY_VERSION, min_length=1, max_length=160)
    deterministic_rule_id: str | None = Field(default=None, max_length=240)

    @field_validator("product_id")
    @classmethod
    def validate_product(cls, value: str) -> str:
        return _product(value)

    @field_validator("reviewed_at")
    @classmethod
    def validate_time(cls, value: datetime) -> datetime:
        return _aware(value, "reviewed_at")

    @model_validator(mode="after")
    def derive_identity(self) -> Self:
        if self.authority is ReviewAuthority.MODEL:
            raise ValueError("a model cannot govern the authoritative promotion lifecycle")
        if self.authority is ReviewAuthority.DETERMINISTIC_POLICY and not self.deterministic_rule_id:
            raise ValueError("deterministic promotion disposition requires an exact allow-listed rule")
        if self.authority is ReviewAuthority.HUMAN and self.deterministic_rule_id is not None:
            raise ValueError("human promotion review cannot claim deterministic-policy authority")
        material = self.model_dump(mode="json", exclude={"review_id", "review_hash"})
        expected_hash = canonical_hash(material)
        expected_id = f"grounded_promotion_review:{expected_hash[:32]}"
        if self.review_hash is not None and self.review_hash != expected_hash:
            raise ValueError("promotion review hash does not match exact material")
        if self.review_id is not None and self.review_id != expected_id:
            raise ValueError("promotion review identity does not match exact material")
        object.__setattr__(self, "review_hash", expected_hash)
        object.__setattr__(self, "review_id", expected_id)
        return self


class PromotionReceiptV1(FrozenContract):
    contract_version: Literal["ace.grounded-state.promotion-receipt/v1"] = PROMOTION_RECEIPT_VERSION
    receipt_id: str | None = None
    receipt_hash: str | None = None
    product_id: str
    proposal_id: str = Field(min_length=1, max_length=240)
    proposal_hash: str = Field(pattern=r"^[a-f0-9]{64}$")
    review_id: str = Field(min_length=1, max_length=240)
    review_hash: str = Field(pattern=r"^[a-f0-9]{64}$")
    disposition: PromotionDisposition
    memory_id: str | None = Field(default=None, max_length=240)
    memory_hash: str | None = Field(default=None, pattern=r"^[a-f0-9]{64}$")
    supersedes_receipt_ids: tuple[str, ...] = Field(default_factory=tuple, max_length=MAX_PROMOTION_LINEAGE)
    invalidates_receipt_ids: tuple[str, ...] = Field(default_factory=tuple, max_length=MAX_PROMOTION_LINEAGE)
    contests_receipt_ids: tuple[str, ...] = Field(default_factory=tuple, max_length=MAX_PROMOTION_LINEAGE)
    expires_at: datetime | None = None
    effective_at: datetime
    reasons: tuple[str, ...] = Field(default_factory=tuple, max_length=MAX_PROMOTION_REASONS)
    provider_usage: ProviderExecutionV1 = Field(default_factory=ProviderExecutionV1)
    beneficial_impact_supported: Literal[False] = False

    @field_validator("product_id")
    @classmethod
    def validate_product(cls, value: str) -> str:
        return _product(value)

    @field_validator("effective_at", "expires_at")
    @classmethod
    def validate_times(cls, value: datetime | None, info) -> datetime | None:
        return _aware(value, info.field_name) if value is not None else None

    @field_validator(
        "supersedes_receipt_ids",
        "invalidates_receipt_ids",
        "contests_receipt_ids",
        "reasons",
        mode="before",
    )
    @classmethod
    def normalize_refs(cls, value: Any, info) -> tuple[str, ...]:
        limit = MAX_PROMOTION_REASONS if info.field_name == "reasons" else MAX_PROMOTION_LINEAGE
        return _refs(value, limit=limit, name=info.field_name)

    @model_validator(mode="after")
    def derive_identity(self) -> Self:
        memory_fields = (self.memory_id, self.memory_hash)
        if self.disposition is PromotionDisposition.ACCEPTED:
            if any(value is None for value in memory_fields):
                raise ValueError("accepted promotion requires exact existing-memory lineage")
        elif any(value is not None for value in memory_fields):
            raise ValueError("non-accepted promotion cannot create durable memory")
        if self.expires_at is not None and self.expires_at <= self.effective_at:
            raise ValueError("promotion expiry must follow its effective time")
        relation_groups = (
            set(self.supersedes_receipt_ids),
            set(self.invalidates_receipt_ids),
            set(self.contests_receipt_ids),
        )
        if any(left & right for index, left in enumerate(relation_groups) for right in relation_groups[index + 1 :]):
            raise ValueError("one prior promotion receipt cannot have conflicting lifecycle meanings")
        material = self.model_dump(mode="json", exclude={"receipt_id", "receipt_hash"})
        expected_hash = canonical_hash(material)
        expected_id = f"grounded_promotion_receipt:{expected_hash[:32]}"
        if self.receipt_hash is not None and self.receipt_hash != expected_hash:
            raise ValueError("promotion receipt hash does not match exact lifecycle material")
        if self.receipt_id is not None and self.receipt_id != expected_id:
            raise ValueError("promotion receipt identity does not match exact lifecycle material")
        object.__setattr__(self, "receipt_hash", expected_hash)
        object.__setattr__(self, "receipt_id", expected_id)
        return self


class PromotionMemoryLineageV1(FrozenContract):
    contract_version: Literal["ace.grounded-state.promotion-memory-lineage/v1"] = PROMOTION_MEMORY_LINEAGE_VERSION
    lineage_id: str | None = None
    lineage_hash: str | None = None
    product_id: str
    memory_id: str = Field(min_length=1, max_length=240)
    memory_hash: str = Field(pattern=r"^[a-f0-9]{64}$")
    proposal_id: str = Field(min_length=1, max_length=240)
    proposal_hash: str = Field(pattern=r"^[a-f0-9]{64}$")
    receipt_id: str = Field(min_length=1, max_length=240)
    receipt_hash: str = Field(pattern=r"^[a-f0-9]{64}$")
    task_id: str = Field(min_length=1, max_length=240)
    decision_receipt_id: str = Field(min_length=1, max_length=240)
    evidence_pack_id: str = Field(min_length=1, max_length=240)
    evidence_pack_hash: str = Field(pattern=r"^[a-f0-9]{64}$")
    rollout_revision_id: str = Field(min_length=1, max_length=240)
    rollout_revision_hash: str = Field(pattern=r"^[a-f0-9]{64}$")
    predecessor_memory_ids: tuple[str, ...] = Field(default_factory=tuple, max_length=MAX_PROMOTION_LINEAGE)
    correction_observation_id: str | None = Field(default=None, max_length=240)
    created_at: datetime

    @field_validator("product_id")
    @classmethod
    def validate_product(cls, value: str) -> str:
        return _product(value)

    @field_validator("created_at")
    @classmethod
    def validate_time(cls, value: datetime) -> datetime:
        return _aware(value, "created_at")

    @field_validator("predecessor_memory_ids", mode="before")
    @classmethod
    def normalize_refs(cls, value: Any) -> tuple[str, ...]:
        return _refs(value, limit=MAX_PROMOTION_LINEAGE, name="predecessor_memory_ids")

    @model_validator(mode="after")
    def derive_identity(self) -> Self:
        material = self.model_dump(mode="json", exclude={"lineage_id", "lineage_hash"})
        expected_hash = canonical_hash(material)
        expected_id = f"grounded_promotion_memory_lineage:{expected_hash[:32]}"
        if self.lineage_hash is not None and self.lineage_hash != expected_hash:
            raise ValueError("promotion memory lineage hash does not match exact material")
        if self.lineage_id is not None and self.lineage_id != expected_id:
            raise ValueError("promotion memory lineage identity does not match exact material")
        object.__setattr__(self, "lineage_hash", expected_hash)
        object.__setattr__(self, "lineage_id", expected_id)
        return self


class PromotedMemoryProjectionV1(FrozenContract):
    contract_version: Literal["ace.grounded-state.promotion-retrieval/v1"] = PROMOTION_RETRIEVAL_VERSION
    product_id: str
    memory_id: str = Field(min_length=1, max_length=240)
    memory_hash: str = Field(pattern=r"^[a-f0-9]{64}$")
    receipt_id: str = Field(min_length=1, max_length=240)
    receipt_hash: str = Field(pattern=r"^[a-f0-9]{64}$")
    lineage_id: str = Field(min_length=1, max_length=240)
    target_kind: PromotionTargetKind
    memory_meaning: PromotionMemoryMeaning
    content: str = Field(min_length=1, max_length=MAX_PROMOTION_CONTENT_CHARS)
    content_hash: str = Field(pattern=r"^[a-f0-9]{64}$")
    domain_path: str = Field(min_length=1, max_length=240)
    tags: tuple[str, ...] = Field(default_factory=tuple, max_length=50)
    effective_state: PromotionEffectiveState
    evidence_pack_id: str = Field(min_length=1, max_length=240)
    evidence_pack_hash: str = Field(pattern=r"^[a-f0-9]{64}$")
    created_at: datetime

    @field_validator("product_id")
    @classmethod
    def validate_product(cls, value: str) -> str:
        return _product(value)

    @field_validator("created_at")
    @classmethod
    def validate_time(cls, value: datetime) -> datetime:
        return _aware(value, "created_at")

    @field_validator("tags", mode="before")
    @classmethod
    def normalize_tags(cls, value: Any) -> tuple[str, ...]:
        return _refs(value, limit=50, name="promoted memory tags")
