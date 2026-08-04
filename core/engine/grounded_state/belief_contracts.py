"""Immutable TP4 contracts for reviewed assertions and belief-state projection.

The contracts keep source evidence, reviewed epistemic assertions, projected
belief, and derived external-world insight as separate record meanings.  All
authoritative identities are product-scoped and derived from canonical
material; provider output can propose material but cannot choose scope, mint an
authoritative assertion identity, or accept its own proposal.
"""

from __future__ import annotations

from datetime import datetime
from enum import StrEnum
from typing import Any, Literal, Self

from pydantic import Field, field_validator, model_validator

from core.engine.grounded_state.contracts import (
    MAX_REFS,
    BeliefStatus,
    FrozenContract,
    StateValue,
    TemporalScopeV1,
    canonical_hash,
    stable_id,
)

EPISTEMIC_ASSERTION_PROPOSAL_VERSION = "ace.grounded-state.epistemic-assertion-proposal/v1"
ASSERTION_REVIEW_VERSION = "ace.grounded-state.assertion-review/v1"
EPISTEMIC_ASSERTION_VERSION = "ace.grounded-state.epistemic-assertion/v1"
TYPED_EVIDENCE_ENDPOINT_VERSION = "ace.grounded-state.typed-evidence-endpoint/v1"
BOUNDED_EVIDENCE_PACK_VERSION = "ace.grounded-state.evidence-pack/v1"
PROJECTION_ENTRY_VERSION = "ace.grounded-state.projection-entry/v1"
BELIEF_PROJECTION_VERSION = "ace.grounded-state.belief-projection/v1"
COUNTEREVIDENCE_RECEIPT_VERSION = "ace.grounded-state.counterevidence-search/v1"
INFERENCE_RECEIPT_VERSION = "ace.grounded-state.inference-receipt/v1"
EXTERNAL_WORLD_INSIGHT_VERSION = "ace.grounded-state.external-world-insight/v1"
INCREMENTAL_REPROJECTION_VERSION = "ace.grounded-state.incremental-reprojection/v1"

TP4_ONTOLOGY_VERSION = "ace.grounded-state.epistemic-ontology/v1"
TP4_RESOLVER_POLICY_VERSION = "ace.grounded-state.belief-resolver/v1"
TP4_PROJECTION_POLICY_VERSION = "ace.grounded-state.belief-projection/v1"
TP4_ASSERTION_POLICY_VERSION = "ace.grounded-state.assertion-policy/v1"
TP4_INFERENCE_POLICY_VERSION = "ace.grounded-state.external-insight/v1"

MAX_PACK_RECORDS = 200
MAX_PACK_CHARS = 64_000
MAX_PROJECTION_ENTRIES = 200
MAX_REOPENED_ASSERTIONS = 200
MAX_REASONS = 100


def _aware(value: datetime, name: str) -> datetime:
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError(f"{name} must include a timezone")
    return value


def _product(value: str) -> str:
    if not value.startswith("product:") or len(value) > 168 or any(char.isspace() for char in value):
        raise ValueError("product_id must be a bounded product record identity")
    return value


def _refs(value: Any, *, limit: int = MAX_REFS, name: str = "references") -> tuple[str, ...]:
    if value is None:
        return ()
    if not isinstance(value, (list, tuple, set, frozenset)):
        raise ValueError(f"{name} must be a collection")
    normalized = tuple(sorted(set(value)))
    if len(normalized) > limit:
        raise ValueError(f"{name} exceeds the {limit}-item bound")
    if any(not isinstance(item, str) or not item.strip() or len(item) > 1_000 for item in normalized):
        raise ValueError(f"{name} must contain bounded non-empty strings")
    return normalized


class EpistemicRelation(StrEnum):
    SUPPORTS = "supports"
    CORROBORATES = "corroborates"
    CONTRADICTS = "contradicts"
    SUPERSEDES = "supersedes"
    CAUSES = "causes"


class EvidenceEndpointKind(StrEnum):
    SOURCE = "source"
    ENTITY = "entity"
    ALIAS = "alias"
    CLAIM = "claim"
    EVENT = "event"
    EVENT_PARTICIPANT = "event_participant"
    EVIDENCE_RELATION = "evidence_relation"
    EXTRACTION_FAILURE = "extraction_failure"
    INSIGHT = "insight"
    DECISION = "decision"
    STATE = "state"


_ENDPOINT_PREFIXES: dict[EvidenceEndpointKind, tuple[str, ...]] = {
    EvidenceEndpointKind.SOURCE: ("grounded_source:",),
    EvidenceEndpointKind.ENTITY: ("grounded_entity:", "entity:"),
    EvidenceEndpointKind.ALIAS: ("grounded_alias:",),
    EvidenceEndpointKind.CLAIM: ("grounded_claim:",),
    EvidenceEndpointKind.EVENT: ("grounded_event:",),
    EvidenceEndpointKind.EVENT_PARTICIPANT: ("grounded_event_participant:",),
    EvidenceEndpointKind.EVIDENCE_RELATION: ("grounded_evidence_relation:",),
    EvidenceEndpointKind.EXTRACTION_FAILURE: ("grounded_extraction_failure:",),
    EvidenceEndpointKind.INSIGHT: ("insight:", "graph_insight:"),
    EvidenceEndpointKind.DECISION: ("decision:", "graph_decision:"),
    EvidenceEndpointKind.STATE: ("grounded_state:", "belief_state:"),
}


class ReviewDisposition(StrEnum):
    PROPOSED = "proposed"
    ACCEPTED = "accepted"
    REJECTED = "rejected"
    REOPENED = "reopened"


class ReviewAuthority(StrEnum):
    MODEL = "model"
    DETERMINISTIC_POLICY = "deterministic_policy"
    HUMAN = "human"


class InferenceRoute(StrEnum):
    DETERMINISTIC_RULE = "deterministic_rule"
    HUMAN_AUTHORED = "human_authored"
    MODEL_PROPOSED = "model_proposed"


class ProviderUsageV1(FrozenContract):
    model_calls: int = Field(default=0, ge=0)
    input_tokens: int = Field(default=0, ge=0)
    output_tokens: int = Field(default=0, ge=0)
    estimated_cost_usd: float = Field(default=0.0, ge=0)
    latency_ms: int = Field(default=0, ge=0)
    failures: tuple[str, ...] = Field(default_factory=tuple, max_length=MAX_REASONS)

    @field_validator("failures", mode="before")
    @classmethod
    def normalize_failures(cls, value: Any) -> tuple[str, ...]:
        return _refs(value, limit=MAX_REASONS, name="provider failures")


class TypedEvidenceEndpointV1(FrozenContract):
    contract_version: Literal["ace.grounded-state.typed-evidence-endpoint/v1"] = TYPED_EVIDENCE_ENDPOINT_VERSION
    product_id: str
    kind: EvidenceEndpointKind
    record_id: str = Field(min_length=1, max_length=240)
    record_version: str = Field(min_length=1, max_length=240)
    content_hash: str = Field(pattern=r"^[a-f0-9]{64}$")

    @field_validator("product_id")
    @classmethod
    def validate_product(cls, value: str) -> str:
        return _product(value)

    @model_validator(mode="after")
    def validate_kind(self) -> Self:
        if not self.record_id.startswith(_ENDPOINT_PREFIXES[self.kind]):
            raise ValueError("typed endpoint kind does not match its stable record identity")
        return self

    def endpoint_hash(self) -> str:
        return canonical_hash(self)


class EvidencePackItemV1(FrozenContract):
    endpoint: TypedEvidenceEndpointV1
    temporal: TemporalScopeV1 = Field(default_factory=TemporalScopeV1)
    published_at: datetime | None = None
    ingested_at: datetime
    extracted_at: datetime | None = None
    ace_created_at: datetime
    source_id: str = Field(min_length=1, max_length=500)
    publisher_id: str = Field(min_length=1, max_length=240)
    compact_content: str | None = Field(default=None, max_length=8_000)
    source_confidence: float | None = Field(default=None, ge=0, le=1)
    candidate_rank: int | None = Field(default=None, ge=1, le=200)
    selection_signals: tuple[str, ...] = Field(default_factory=tuple, max_length=20)
    degraded_reasons: tuple[str, ...] = Field(default_factory=tuple, max_length=MAX_REASONS)

    @field_validator("published_at", "ingested_at", "extracted_at", "ace_created_at")
    @classmethod
    def validate_times(cls, value: datetime | None, info) -> datetime | None:
        return _aware(value, info.field_name) if value is not None else None

    @field_validator("selection_signals", "degraded_reasons", mode="before")
    @classmethod
    def normalize_strings(cls, value: Any, info) -> tuple[str, ...]:
        limit = 20 if info.field_name == "selection_signals" else MAX_REASONS
        return _refs(value, limit=limit, name=info.field_name)


class BoundedEvidencePackV1(FrozenContract):
    contract_version: Literal["ace.grounded-state.evidence-pack/v1"] = BOUNDED_EVIDENCE_PACK_VERSION
    pack_id: str | None = None
    pack_hash: str | None = None
    product_id: str
    as_of: datetime
    query_hash: str = Field(pattern=r"^[a-f0-9]{64}$")
    candidate_receipt_id: str = Field(min_length=1, max_length=240)
    candidate_receipt_hash: str = Field(pattern=r"^[a-f0-9]{64}$")
    resolver_policy_version: str = Field(min_length=1, max_length=160)
    ontology_version: str = Field(min_length=1, max_length=160)
    items: tuple[EvidencePackItemV1, ...] = Field(default_factory=tuple, max_length=MAX_PACK_RECORDS)
    candidate_count: int = Field(ge=0, le=MAX_PACK_RECORDS)
    selected_count: int = Field(ge=0, le=MAX_PACK_RECORDS)
    max_records: int = Field(ge=1, le=MAX_PACK_RECORDS)
    max_chars: int = Field(ge=1, le=MAX_PACK_CHARS)
    selected_chars: int = Field(ge=0, le=MAX_PACK_CHARS)
    omitted_evidence_refs: tuple[str, ...] = Field(default_factory=tuple, max_length=MAX_PACK_RECORDS)
    omissions: tuple[str, ...] = Field(default_factory=tuple, max_length=MAX_REASONS)
    fallbacks: tuple[str, ...] = Field(default_factory=tuple, max_length=MAX_REASONS)
    failures: tuple[str, ...] = Field(default_factory=tuple, max_length=MAX_REASONS)
    degraded_reasons: tuple[str, ...] = Field(default_factory=tuple, max_length=MAX_REASONS)
    truncated: bool = False
    provider_usage: ProviderUsageV1 = Field(default_factory=ProviderUsageV1)

    @field_validator("product_id")
    @classmethod
    def validate_product(cls, value: str) -> str:
        return _product(value)

    @field_validator("as_of")
    @classmethod
    def validate_as_of(cls, value: datetime) -> datetime:
        return _aware(value, "as_of")

    @field_validator("items", mode="before")
    @classmethod
    def normalize_items(cls, value: Any) -> tuple[Any, ...]:
        if not isinstance(value, (list, tuple)):
            raise ValueError("evidence-pack items must be a bounded collection")
        return tuple(
            sorted(
                value,
                key=lambda item: (
                    item.endpoint.record_id
                    if isinstance(item, EvidencePackItemV1)
                    else str(item.get("endpoint", {}).get("record_id", ""))
                ),
            )
        )

    @field_validator("omitted_evidence_refs", "omissions", "fallbacks", "failures", "degraded_reasons", mode="before")
    @classmethod
    def normalize_reasons(cls, value: Any, info) -> tuple[str, ...]:
        limit = MAX_PACK_RECORDS if info.field_name == "omitted_evidence_refs" else MAX_REASONS
        return _refs(value, limit=limit, name=info.field_name)

    @model_validator(mode="after")
    def derive_identity(self) -> Self:
        if any(item.endpoint.product_id != self.product_id for item in self.items):
            raise ValueError("evidence-pack items cannot cross product scope")
        if self.selected_count != len(self.items):
            raise ValueError("selected_count must equal the number of retained pack items")
        if self.candidate_count < self.selected_count + len(self.omitted_evidence_refs):
            raise ValueError("candidate count cannot be smaller than selected plus explicitly omitted evidence")
        actual_chars = sum(len(item.compact_content or "") for item in self.items)
        if self.selected_chars != actual_chars:
            raise ValueError("selected_chars must reconcile bounded compact content")
        if self.truncated != bool(self.omitted_evidence_refs or self.selected_count < self.candidate_count):
            raise ValueError("truncation must be visible whenever candidates are omitted")
        material = self.model_dump(mode="json", exclude={"pack_id", "pack_hash"})
        expected_hash = canonical_hash(material)
        expected_id = f"grounded_evidence_pack:{expected_hash[:32]}"
        if self.pack_hash is not None and self.pack_hash != expected_hash:
            raise ValueError("pack_hash does not match deterministic evidence-pack material")
        if self.pack_id is not None and self.pack_id != expected_id:
            raise ValueError("pack_id does not match deterministic evidence-pack material")
        object.__setattr__(self, "pack_hash", expected_hash)
        object.__setattr__(self, "pack_id", expected_id)
        return self


class CounterevidenceSearchReceiptV1(FrozenContract):
    contract_version: Literal["ace.grounded-state.counterevidence-search/v1"] = COUNTEREVIDENCE_RECEIPT_VERSION
    receipt_id: str | None = None
    receipt_hash: str | None = None
    product_id: str
    assertion_material_hash: str = Field(pattern=r"^[a-f0-9]{64}$")
    as_of: datetime
    evidence_pack_id: str = Field(min_length=1, max_length=240)
    evidence_pack_hash: str = Field(pattern=r"^[a-f0-9]{64}$")
    searched_evidence_refs: tuple[str, ...] = Field(default_factory=tuple, max_length=MAX_PACK_RECORDS)
    contrary_evidence_refs: tuple[str, ...] = Field(default_factory=tuple, max_length=MAX_PACK_RECORDS)
    missing_inputs: tuple[str, ...] = Field(default_factory=tuple, max_length=MAX_REASONS)
    index_versions: dict[str, str] = Field(default_factory=dict)
    policy_version: str = Field(min_length=1, max_length=160)
    max_records: int = Field(ge=1, le=MAX_PACK_RECORDS)
    records_searched: int = Field(ge=0, le=MAX_PACK_RECORDS)
    omissions: tuple[str, ...] = Field(default_factory=tuple, max_length=MAX_REASONS)
    fallbacks: tuple[str, ...] = Field(default_factory=tuple, max_length=MAX_REASONS)
    failures: tuple[str, ...] = Field(default_factory=tuple, max_length=MAX_REASONS)
    degraded_reasons: tuple[str, ...] = Field(default_factory=tuple, max_length=MAX_REASONS)
    completed: bool
    provider_usage: ProviderUsageV1 = Field(default_factory=ProviderUsageV1)

    @field_validator("product_id")
    @classmethod
    def validate_product(cls, value: str) -> str:
        return _product(value)

    @field_validator("as_of")
    @classmethod
    def validate_as_of(cls, value: datetime) -> datetime:
        return _aware(value, "as_of")

    @field_validator(
        "searched_evidence_refs",
        "contrary_evidence_refs",
        "missing_inputs",
        "omissions",
        "fallbacks",
        "failures",
        "degraded_reasons",
        mode="before",
    )
    @classmethod
    def normalize_refs(cls, value: Any, info) -> tuple[str, ...]:
        limit = MAX_PACK_RECORDS if info.field_name.endswith("evidence_refs") else MAX_REASONS
        return _refs(value, limit=limit, name=info.field_name)

    @model_validator(mode="after")
    def derive_identity(self) -> Self:
        if self.records_searched != len(self.searched_evidence_refs):
            raise ValueError("counterevidence searched count must reconcile exact references")
        if set(self.contrary_evidence_refs) - set(self.searched_evidence_refs):
            raise ValueError("contrary evidence must come from the searched evidence set")
        if self.completed and (
            self.missing_inputs or self.omissions or self.fallbacks or self.failures or self.degraded_reasons
        ):
            raise ValueError("a completed counterevidence search cannot hide incomplete or degraded inputs")
        material = self.model_dump(mode="json", exclude={"receipt_id", "receipt_hash"})
        expected_hash = canonical_hash(material)
        expected_id = f"grounded_counterevidence:{expected_hash[:32]}"
        if self.receipt_hash is not None and self.receipt_hash != expected_hash:
            raise ValueError("counterevidence receipt hash does not match material")
        if self.receipt_id is not None and self.receipt_id != expected_id:
            raise ValueError("counterevidence receipt identity does not match material")
        object.__setattr__(self, "receipt_hash", expected_hash)
        object.__setattr__(self, "receipt_id", expected_id)
        return self


class EpistemicAssertionProposalV1(FrozenContract):
    contract_version: Literal["ace.grounded-state.epistemic-assertion-proposal/v1"] = (
        EPISTEMIC_ASSERTION_PROPOSAL_VERSION
    )
    proposal_id: str | None = None
    product_id: str
    subject: TypedEvidenceEndpointV1
    relation: EpistemicRelation
    object: TypedEvidenceEndpointV1
    belief_subject: TypedEvidenceEndpointV1 | None = None
    belief_predicate: str | None = Field(default=None, min_length=1, max_length=160)
    belief_value: StateValue = None
    supersedes_assertion_refs: tuple[str, ...] = Field(default_factory=tuple, max_length=MAX_REFS)
    validity: TemporalScopeV1 = Field(default_factory=TemporalScopeV1)
    occurred_at: datetime | None = None
    proposed_at: datetime
    evidence_pack_id: str = Field(min_length=1, max_length=240)
    evidence_pack_hash: str = Field(pattern=r"^[a-f0-9]{64}$")
    supporting_evidence_refs: tuple[str, ...] = Field(default_factory=tuple, max_length=MAX_REFS)
    contrary_evidence_refs: tuple[str, ...] = Field(default_factory=tuple, max_length=MAX_REFS)
    source_origin_ids: tuple[str, ...] = Field(default_factory=tuple, max_length=MAX_REFS)
    source_confidence: float | None = Field(default=None, ge=0, le=1)
    epistemic_confidence: float = Field(default=0.5, ge=0, le=1)
    freshness: float | None = Field(default=None, ge=0, le=1)
    rationale: str = Field(min_length=1, max_length=2_000)
    proposer_authority: Literal["model", "human", "deterministic_policy"]
    proposer_ref: str = Field(min_length=1, max_length=240)
    model: str | None = Field(default=None, max_length=200)
    provider: str | None = Field(default=None, max_length=120)
    prompt_version: str | None = Field(default=None, max_length=160)
    ontology_version: str = Field(default=TP4_ONTOLOGY_VERSION, min_length=1, max_length=160)
    assertion_policy_version: str = Field(default=TP4_ASSERTION_POLICY_VERSION, min_length=1, max_length=160)
    omissions: tuple[str, ...] = Field(default_factory=tuple, max_length=MAX_REASONS)
    degraded_reasons: tuple[str, ...] = Field(default_factory=tuple, max_length=MAX_REASONS)

    @field_validator("product_id")
    @classmethod
    def validate_product(cls, value: str) -> str:
        return _product(value)

    @field_validator("occurred_at", "proposed_at")
    @classmethod
    def validate_times(cls, value: datetime | None, info) -> datetime | None:
        return _aware(value, info.field_name) if value is not None else None

    @field_validator(
        "supporting_evidence_refs",
        "contrary_evidence_refs",
        "source_origin_ids",
        "supersedes_assertion_refs",
        "omissions",
        "degraded_reasons",
        mode="before",
    )
    @classmethod
    def normalize_refs(cls, value: Any, info) -> tuple[str, ...]:
        return _refs(
            value,
            limit=MAX_REFS if info.field_name not in {"omissions", "degraded_reasons"} else MAX_REASONS,
            name=info.field_name,
        )

    def semantic_material(self) -> dict[str, Any]:
        return {
            "contract_version": self.contract_version,
            "product_id": self.product_id,
            "subject": self.subject.model_dump(mode="json"),
            "relation": self.relation.value,
            "object": self.object.model_dump(mode="json"),
            "belief_subject": self.belief_subject.model_dump(mode="json") if self.belief_subject else None,
            "belief_predicate": self.belief_predicate,
            "belief_value": self.belief_value,
            "supersedes_assertion_refs": self.supersedes_assertion_refs,
            "validity": self.validity.model_dump(mode="json"),
            "occurred_at": self.occurred_at.isoformat() if self.occurred_at else None,
            "ontology_version": self.ontology_version,
        }

    def assertion_id(self) -> str:
        return stable_id("grounded_epistemic_assertion", self.semantic_material())

    def review_material_hash(self) -> str:
        return canonical_hash(self.model_dump(mode="json", exclude={"proposal_id"}))

    @model_validator(mode="after")
    def derive_identity(self) -> Self:
        if self.subject.product_id != self.product_id or self.object.product_id != self.product_id:
            raise ValueError("assertion proposal endpoints cannot cross product scope")
        if (self.belief_subject is None) != (self.belief_predicate is None):
            raise ValueError("projected belief subject and predicate must be supplied together")
        if self.belief_subject is not None and self.belief_subject.product_id != self.product_id:
            raise ValueError("projected belief subject cannot cross product scope")
        if self.supersedes_assertion_refs and self.relation is not EpistemicRelation.SUPERSEDES:
            raise ValueError("superseding assertion references require a supersedes relation")
        if self.subject.record_id == self.object.record_id:
            raise ValueError("epistemic assertions require distinct endpoints")
        if set(self.supporting_evidence_refs) & set(self.contrary_evidence_refs):
            raise ValueError("supporting and contrary evidence must be disjoint")
        expected = stable_id(
            "grounded_assertion_proposal",
            self.model_dump(mode="json", exclude={"proposal_id"}),
        )
        if self.proposal_id is not None and self.proposal_id != expected:
            raise ValueError("proposal_id does not match deterministic proposal material")
        object.__setattr__(self, "proposal_id", expected)
        return self


class AssertionReviewV1(FrozenContract):
    contract_version: Literal["ace.grounded-state.assertion-review/v1"] = ASSERTION_REVIEW_VERSION
    review_id: str | None = None
    product_id: str
    proposal_id: str = Field(min_length=1, max_length=240)
    assertion_id: str = Field(min_length=1, max_length=240)
    reviewed_material_hash: str = Field(pattern=r"^[a-f0-9]{64}$")
    disposition: ReviewDisposition
    authority: ReviewAuthority
    reviewer_ref: str = Field(min_length=1, max_length=240)
    reviewed_at: datetime
    rationale: str = Field(min_length=1, max_length=2_000)
    counterevidence_receipt_id: str | None = Field(default=None, max_length=240)
    counterevidence_receipt_hash: str | None = Field(default=None, pattern=r"^[a-f0-9]{64}$")
    policy_version: str = Field(min_length=1, max_length=160)
    omissions: tuple[str, ...] = Field(default_factory=tuple, max_length=MAX_REASONS)
    failures: tuple[str, ...] = Field(default_factory=tuple, max_length=MAX_REASONS)
    degraded_reasons: tuple[str, ...] = Field(default_factory=tuple, max_length=MAX_REASONS)

    @field_validator("product_id")
    @classmethod
    def validate_product(cls, value: str) -> str:
        return _product(value)

    @field_validator("reviewed_at")
    @classmethod
    def validate_reviewed_at(cls, value: datetime) -> datetime:
        return _aware(value, "reviewed_at")

    @field_validator("omissions", "failures", "degraded_reasons", mode="before")
    @classmethod
    def normalize_reasons(cls, value: Any, info) -> tuple[str, ...]:
        return _refs(value, limit=MAX_REASONS, name=info.field_name)

    @model_validator(mode="after")
    def derive_identity(self) -> Self:
        if self.authority is ReviewAuthority.MODEL and self.disposition is ReviewDisposition.ACCEPTED:
            raise ValueError("a model may not accept its own or another assertion proposal")
        if bool(self.counterevidence_receipt_id) != bool(self.counterevidence_receipt_hash):
            raise ValueError("counterevidence receipt identity and hash must be supplied together")
        expected = stable_id("grounded_assertion_review", self.model_dump(mode="json", exclude={"review_id"}))
        if self.review_id is not None and self.review_id != expected:
            raise ValueError("review_id does not match deterministic review material")
        object.__setattr__(self, "review_id", expected)
        return self


class EpistemicAssertionV1(FrozenContract):
    contract_version: Literal["ace.grounded-state.epistemic-assertion/v1"] = EPISTEMIC_ASSERTION_VERSION
    assertion_id: str
    revision_id: str | None = None
    revision: int = Field(ge=1)
    product_id: str
    proposal_id: str
    subject: TypedEvidenceEndpointV1
    relation: EpistemicRelation
    object: TypedEvidenceEndpointV1
    belief_subject: TypedEvidenceEndpointV1 | None = None
    belief_predicate: str | None = Field(default=None, min_length=1, max_length=160)
    belief_value: StateValue = None
    supersedes_assertion_refs: tuple[str, ...] = Field(default_factory=tuple, max_length=MAX_REFS)
    validity: TemporalScopeV1 = Field(default_factory=TemporalScopeV1)
    occurred_at: datetime | None = None
    disposition: ReviewDisposition
    review_id: str
    review_authority: ReviewAuthority
    reviewed_material_hash: str = Field(pattern=r"^[a-f0-9]{64}$")
    evidence_pack_id: str
    evidence_pack_hash: str = Field(pattern=r"^[a-f0-9]{64}$")
    supporting_evidence_refs: tuple[str, ...] = Field(default_factory=tuple, max_length=MAX_REFS)
    contrary_evidence_refs: tuple[str, ...] = Field(default_factory=tuple, max_length=MAX_REFS)
    source_origin_ids: tuple[str, ...] = Field(default_factory=tuple, max_length=MAX_REFS)
    counterevidence_receipt_id: str | None = None
    counterevidence_receipt_hash: str | None = Field(default=None, pattern=r"^[a-f0-9]{64}$")
    source_confidence: float | None = Field(default=None, ge=0, le=1)
    epistemic_confidence: float = Field(ge=0, le=1)
    freshness: float | None = Field(default=None, ge=0, le=1)
    ontology_version: str
    resolver_policy_version: str
    created_at: datetime
    prior_revision_id: str | None = None
    omissions: tuple[str, ...] = Field(default_factory=tuple, max_length=MAX_REASONS)
    failures: tuple[str, ...] = Field(default_factory=tuple, max_length=MAX_REASONS)
    degraded_reasons: tuple[str, ...] = Field(default_factory=tuple, max_length=MAX_REASONS)
    material_hash: str | None = None

    @field_validator("product_id")
    @classmethod
    def validate_product(cls, value: str) -> str:
        return _product(value)

    @field_validator("occurred_at", "created_at")
    @classmethod
    def validate_times(cls, value: datetime | None, info) -> datetime | None:
        return _aware(value, info.field_name) if value is not None else None

    @field_validator(
        "supporting_evidence_refs",
        "contrary_evidence_refs",
        "source_origin_ids",
        "supersedes_assertion_refs",
        "omissions",
        "failures",
        "degraded_reasons",
        mode="before",
    )
    @classmethod
    def normalize_refs(cls, value: Any, info) -> tuple[str, ...]:
        limit = MAX_REFS if info.field_name not in {"omissions", "failures", "degraded_reasons"} else MAX_REASONS
        return _refs(value, limit=limit, name=info.field_name)

    @model_validator(mode="after")
    def validate_assertion(self) -> Self:
        if self.subject.product_id != self.product_id or self.object.product_id != self.product_id:
            raise ValueError("epistemic assertion endpoints cannot cross product scope")
        if (self.belief_subject is None) != (self.belief_predicate is None):
            raise ValueError("projected belief subject and predicate must be supplied together")
        if self.belief_subject is not None and self.belief_subject.product_id != self.product_id:
            raise ValueError("projected belief subject cannot cross product scope")
        if self.supersedes_assertion_refs and self.relation is not EpistemicRelation.SUPERSEDES:
            raise ValueError("superseding assertion references require a supersedes relation")
        if self.disposition is ReviewDisposition.ACCEPTED:
            if not self.supporting_evidence_refs:
                raise ValueError("accepted assertions require relevant supporting evidence")
            if self.review_authority is ReviewAuthority.MODEL:
                raise ValueError("model authority cannot accept an epistemic assertion")
        if self.disposition is ReviewDisposition.REOPENED and self.prior_revision_id is None:
            raise ValueError("reopened assertions must retain their prior revision")
        if self.relation is EpistemicRelation.CAUSES and self.disposition is ReviewDisposition.ACCEPTED:
            if (
                self.review_authority is not ReviewAuthority.HUMAN
                or len(self.source_origin_ids) < 2
                or self.counterevidence_receipt_id is None
                or self.counterevidence_receipt_hash is None
                or self.failures
                or self.degraded_reasons
            ):
                raise ValueError(
                    "accepted causes assertions require exact human review, completed counterevidence search, and at least two independent source origins"
                )
        if set(self.supporting_evidence_refs) & set(self.contrary_evidence_refs):
            raise ValueError("supporting and contrary evidence must be disjoint")
        material = self.model_dump(mode="json", exclude={"revision_id", "material_hash"})
        expected_hash = canonical_hash(material)
        expected_revision = f"grounded_assertion_revision:{expected_hash[:32]}"
        if self.material_hash is not None and self.material_hash != expected_hash:
            raise ValueError("assertion material_hash does not match exact revision material")
        if self.revision_id is not None and self.revision_id != expected_revision:
            raise ValueError("assertion revision identity does not match exact material")
        object.__setattr__(self, "material_hash", expected_hash)
        object.__setattr__(self, "revision_id", expected_revision)
        return self


class ProjectionTargetV1(FrozenContract):
    subject: TypedEvidenceEndpointV1
    predicate: str = Field(min_length=1, max_length=160)


class ProjectionAssertionEntryV1(FrozenContract):
    contract_version: Literal["ace.grounded-state.projection-entry/v1"] = PROJECTION_ENTRY_VERSION
    entry_id: str | None = None
    product_id: str
    as_of: datetime
    subject: TypedEvidenceEndpointV1
    predicate: str = Field(min_length=1, max_length=160)
    value: StateValue = None
    validity: TemporalScopeV1 = Field(default_factory=TemporalScopeV1)
    status: BeliefStatus
    operational: bool
    accepted_assertion_id: str | None = None
    assertion_revision_id: str | None = None
    review_id: str | None = None
    evidence_pack_id: str
    evidence_pack_hash: str = Field(pattern=r"^[a-f0-9]{64}$")
    supporting_evidence_refs: tuple[str, ...] = Field(default_factory=tuple, max_length=MAX_REFS)
    contradicting_evidence_refs: tuple[str, ...] = Field(default_factory=tuple, max_length=MAX_REFS)
    superseding_assertion_refs: tuple[str, ...] = Field(default_factory=tuple, max_length=MAX_REFS)
    missing_evidence: tuple[str, ...] = Field(default_factory=tuple, max_length=MAX_REFS)
    source_confidence: float | None = Field(default=None, ge=0, le=1)
    epistemic_confidence: float = Field(ge=0, le=1)
    freshness: float | None = Field(default=None, ge=0, le=1)
    ontology_version: str
    resolver_policy_version: str
    omissions: tuple[str, ...] = Field(default_factory=tuple, max_length=MAX_REASONS)
    degraded_reasons: tuple[str, ...] = Field(default_factory=tuple, max_length=MAX_REASONS)

    @field_validator("product_id")
    @classmethod
    def validate_product(cls, value: str) -> str:
        return _product(value)

    @field_validator("as_of")
    @classmethod
    def validate_as_of(cls, value: datetime) -> datetime:
        return _aware(value, "as_of")

    @field_validator(
        "supporting_evidence_refs",
        "contradicting_evidence_refs",
        "superseding_assertion_refs",
        "missing_evidence",
        "omissions",
        "degraded_reasons",
        mode="before",
    )
    @classmethod
    def normalize_refs(cls, value: Any, info) -> tuple[str, ...]:
        limit = MAX_REFS if info.field_name not in {"omissions", "degraded_reasons"} else MAX_REASONS
        return _refs(value, limit=limit, name=info.field_name)

    @model_validator(mode="after")
    def derive_identity(self) -> Self:
        linked = (self.accepted_assertion_id, self.assertion_revision_id, self.review_id)
        if self.operational and (self.status is BeliefStatus.UNKNOWN or not all(linked)):
            raise ValueError("every operational projection entry must link accepted assertion and review material")
        if self.operational and not self.supporting_evidence_refs:
            raise ValueError("operational projection entries require exact supporting evidence")
        if self.status is BeliefStatus.UNKNOWN:
            if self.value is not None or self.epistemic_confidence != 0 or not self.missing_evidence:
                raise ValueError("unknown projection requires no value, zero confidence, and explicit missing evidence")
        if self.subject.product_id != self.product_id:
            raise ValueError("projection entries cannot cross product scope")
        expected = stable_id("grounded_projection_entry", self.model_dump(mode="json", exclude={"entry_id"}))
        if self.entry_id is not None and self.entry_id != expected:
            raise ValueError("projection entry identity does not match deterministic material")
        object.__setattr__(self, "entry_id", expected)
        return self


class BeliefStateProjectionV1(FrozenContract):
    contract_version: Literal["ace.grounded-state.belief-projection/v1"] = BELIEF_PROJECTION_VERSION
    projection_id: str | None = None
    projection_hash: str | None = None
    revision: int = Field(default=1, ge=1)
    product_id: str
    as_of: datetime
    evidence_pack_id: str
    evidence_pack_hash: str = Field(pattern=r"^[a-f0-9]{64}$")
    ontology_version: str
    resolver_policy_version: str
    projection_policy_version: str
    max_entries: int = Field(default=MAX_PROJECTION_ENTRIES, ge=1, le=MAX_PROJECTION_ENTRIES)
    targets: tuple[ProjectionTargetV1, ...] = Field(default_factory=tuple, max_length=MAX_PROJECTION_ENTRIES)
    entries: tuple[ProjectionAssertionEntryV1, ...] = Field(default_factory=tuple, max_length=MAX_PROJECTION_ENTRIES)
    evaluated_assertion_refs: tuple[str, ...] = Field(default_factory=tuple, max_length=MAX_PROJECTION_ENTRIES)
    assertion_revision_refs: tuple[str, ...] = Field(default_factory=tuple, max_length=MAX_PROJECTION_ENTRIES)
    omitted_assertion_refs: tuple[str, ...] = Field(default_factory=tuple, max_length=MAX_PROJECTION_ENTRIES)
    omissions: tuple[str, ...] = Field(default_factory=tuple, max_length=MAX_REASONS)
    fallbacks: tuple[str, ...] = Field(default_factory=tuple, max_length=MAX_REASONS)
    failures: tuple[str, ...] = Field(default_factory=tuple, max_length=MAX_REASONS)
    degraded_reasons: tuple[str, ...] = Field(default_factory=tuple, max_length=MAX_REASONS)
    provider_usage: ProviderUsageV1 = Field(default_factory=ProviderUsageV1)

    @field_validator("product_id")
    @classmethod
    def validate_product(cls, value: str) -> str:
        return _product(value)

    @field_validator("as_of")
    @classmethod
    def validate_as_of(cls, value: datetime) -> datetime:
        return _aware(value, "as_of")

    @field_validator("entries", mode="before")
    @classmethod
    def normalize_entries(cls, value: Any) -> tuple[Any, ...]:
        if not isinstance(value, (list, tuple)):
            raise ValueError("projection entries must be a bounded collection")
        return tuple(
            sorted(
                value,
                key=lambda item: (
                    item.entry_id if isinstance(item, ProjectionAssertionEntryV1) else str(item.get("entry_id", ""))
                ),
            )
        )

    @field_validator("targets", mode="before")
    @classmethod
    def normalize_targets(cls, value: Any) -> tuple[Any, ...]:
        if not isinstance(value, (list, tuple)):
            raise ValueError("projection targets must be a bounded collection")
        return tuple(
            sorted(
                value,
                key=lambda item: (
                    item.subject.record_id
                    if isinstance(item, ProjectionTargetV1)
                    else str(item["subject"]["record_id"]),
                    item.predicate if isinstance(item, ProjectionTargetV1) else str(item["predicate"]),
                ),
            )
        )

    @field_validator(
        "evaluated_assertion_refs",
        "assertion_revision_refs",
        "omitted_assertion_refs",
        "omissions",
        "fallbacks",
        "failures",
        "degraded_reasons",
        mode="before",
    )
    @classmethod
    def normalize_refs(cls, value: Any, info) -> tuple[str, ...]:
        limit = MAX_PROJECTION_ENTRIES if info.field_name.endswith("assertion_refs") else MAX_REASONS
        return _refs(value, limit=limit, name=info.field_name)

    @model_validator(mode="after")
    def derive_identity(self) -> Self:
        if any(entry.product_id != self.product_id or entry.as_of != self.as_of for entry in self.entries):
            raise ValueError("projection entries must share product and as-of context")
        if any(target.subject.product_id != self.product_id for target in self.targets):
            raise ValueError("projection targets cannot cross product scope")
        if len(self.assertion_revision_refs) != len(self.evaluated_assertion_refs):
            raise ValueError("every evaluated assertion must retain its exact revision reference")
        if len(self.entries) > self.max_entries:
            raise ValueError("projection entries exceed the recorded projection bound")
        material = self.model_dump(mode="json", exclude={"projection_id", "projection_hash"})
        expected_hash = canonical_hash(material)
        expected_id = f"grounded_belief_projection:{expected_hash[:32]}"
        if self.projection_hash is not None and self.projection_hash != expected_hash:
            raise ValueError("projection_hash does not match deterministic projection material")
        if self.projection_id is not None and self.projection_id != expected_id:
            raise ValueError("projection_id does not match deterministic projection material")
        object.__setattr__(self, "projection_hash", expected_hash)
        object.__setattr__(self, "projection_id", expected_id)
        return self


class InferenceReceiptV1(FrozenContract):
    contract_version: Literal["ace.grounded-state.inference-receipt/v1"] = INFERENCE_RECEIPT_VERSION
    receipt_id: str | None = None
    receipt_hash: str | None = None
    product_id: str
    hypothesis_hash: str = Field(pattern=r"^[a-f0-9]{64}$")
    as_of: datetime
    evidence_pack_id: str
    evidence_pack_hash: str = Field(pattern=r"^[a-f0-9]{64}$")
    candidate_receipt_id: str
    candidate_receipt_hash: str = Field(pattern=r"^[a-f0-9]{64}$")
    supporting_assertion_refs: tuple[str, ...] = Field(min_length=1, max_length=MAX_REFS)
    supporting_evidence_refs: tuple[str, ...] = Field(min_length=1, max_length=MAX_REFS)
    counterevidence_receipt_id: str
    counterevidence_receipt_hash: str = Field(pattern=r"^[a-f0-9]{64}$")
    inference_route: InferenceRoute
    ontology_version: str
    resolver_policy_version: str
    inference_policy_version: str
    model_version: str | None = None
    source_confidence: float | None = Field(default=None, ge=0, le=1)
    epistemic_confidence: float = Field(ge=0, le=1)
    freshness: float | None = Field(default=None, ge=0, le=1)
    validity: TemporalScopeV1 = Field(default_factory=TemporalScopeV1)
    review_id: str
    omissions: tuple[str, ...] = Field(default_factory=tuple, max_length=MAX_REASONS)
    failures: tuple[str, ...] = Field(default_factory=tuple, max_length=MAX_REASONS)
    degraded_reasons: tuple[str, ...] = Field(default_factory=tuple, max_length=MAX_REASONS)
    provider_usage: ProviderUsageV1 = Field(default_factory=ProviderUsageV1)

    @field_validator("product_id")
    @classmethod
    def validate_product(cls, value: str) -> str:
        return _product(value)

    @field_validator("as_of")
    @classmethod
    def validate_as_of(cls, value: datetime) -> datetime:
        return _aware(value, "as_of")

    @field_validator(
        "supporting_assertion_refs",
        "supporting_evidence_refs",
        "omissions",
        "failures",
        "degraded_reasons",
        mode="before",
    )
    @classmethod
    def normalize_refs(cls, value: Any, info) -> tuple[str, ...]:
        limit = MAX_REFS if info.field_name.startswith("supporting_") else MAX_REASONS
        return _refs(value, limit=limit, name=info.field_name)

    @model_validator(mode="after")
    def derive_identity(self) -> Self:
        material = self.model_dump(mode="json", exclude={"receipt_id", "receipt_hash"})
        expected_hash = canonical_hash(material)
        expected_id = f"grounded_inference_receipt:{expected_hash[:32]}"
        if self.receipt_hash is not None and self.receipt_hash != expected_hash:
            raise ValueError("inference receipt hash does not match exact material")
        if self.receipt_id is not None and self.receipt_id != expected_id:
            raise ValueError("inference receipt identity does not match exact material")
        object.__setattr__(self, "receipt_hash", expected_hash)
        object.__setattr__(self, "receipt_id", expected_id)
        return self


class ExternalWorldInsightV1(FrozenContract):
    contract_version: Literal["ace.grounded-state.external-world-insight/v1"] = EXTERNAL_WORLD_INSIGHT_VERSION
    insight_id: str | None = None
    material_hash: str | None = None
    product_id: str
    assertion: str = Field(min_length=1, max_length=8_000)
    assertion_hash: str = Field(pattern=r"^[a-f0-9]{64}$")
    as_of: datetime
    validity: TemporalScopeV1 = Field(default_factory=TemporalScopeV1)
    evidence_pack_id: str
    evidence_pack_hash: str = Field(pattern=r"^[a-f0-9]{64}$")
    inference_receipt_id: str
    inference_receipt_hash: str = Field(pattern=r"^[a-f0-9]{64}$")
    supporting_assertion_refs: tuple[str, ...] = Field(min_length=1, max_length=MAX_REFS)
    review_id: str
    review_disposition: ReviewDisposition
    ontology_version: str
    resolver_policy_version: str
    inference_policy_version: str
    source_confidence: float | None = Field(default=None, ge=0, le=1)
    epistemic_confidence: float = Field(ge=0, le=1)
    freshness: float | None = Field(default=None, ge=0, le=1)
    omissions: tuple[str, ...] = Field(default_factory=tuple, max_length=MAX_REASONS)
    degraded_reasons: tuple[str, ...] = Field(default_factory=tuple, max_length=MAX_REASONS)

    @field_validator("product_id")
    @classmethod
    def validate_product(cls, value: str) -> str:
        return _product(value)

    @field_validator("as_of")
    @classmethod
    def validate_as_of(cls, value: datetime) -> datetime:
        return _aware(value, "as_of")

    @field_validator("supporting_assertion_refs", "omissions", "degraded_reasons", mode="before")
    @classmethod
    def normalize_refs(cls, value: Any, info) -> tuple[str, ...]:
        limit = MAX_REFS if info.field_name == "supporting_assertion_refs" else MAX_REASONS
        return _refs(value, limit=limit, name=info.field_name)

    @model_validator(mode="after")
    def derive_identity(self) -> Self:
        if canonical_hash(self.assertion) != self.assertion_hash:
            raise ValueError("external-world assertion_hash must bind exact assertion text")
        if self.review_disposition is not ReviewDisposition.ACCEPTED:
            raise ValueError("external-world insights require an accepted review disposition")
        material = self.model_dump(mode="json", exclude={"insight_id", "material_hash"})
        expected_hash = canonical_hash(material)
        expected_id = f"grounded_external_insight:{expected_hash[:32]}"
        if self.material_hash is not None and self.material_hash != expected_hash:
            raise ValueError("external insight material_hash does not match exact material")
        if self.insight_id is not None and self.insight_id != expected_id:
            raise ValueError("external insight identity does not match exact material")
        object.__setattr__(self, "material_hash", expected_hash)
        object.__setattr__(self, "insight_id", expected_id)
        return self


class IncrementalReprojectionReceiptV1(FrozenContract):
    contract_version: Literal["ace.grounded-state.incremental-reprojection/v1"] = INCREMENTAL_REPROJECTION_VERSION
    receipt_id: str | None = None
    receipt_hash: str | None = None
    product_id: str
    prior_projection_id: str
    prior_projection_hash: str = Field(pattern=r"^[a-f0-9]{64}$")
    resulting_projection_id: str
    resulting_projection_hash: str = Field(pattern=r"^[a-f0-9]{64}$")
    changed_input_refs: tuple[str, ...] = Field(min_length=1, max_length=MAX_REOPENED_ASSERTIONS)
    affected_assertion_refs: tuple[str, ...] = Field(default_factory=tuple, max_length=MAX_REOPENED_ASSERTIONS)
    unaffected_assertion_refs: tuple[str, ...] = Field(default_factory=tuple, max_length=MAX_PROJECTION_ENTRIES)
    reopened_revision_refs: tuple[str, ...] = Field(default_factory=tuple, max_length=MAX_REOPENED_ASSERTIONS)
    reasons: tuple[str, ...] = Field(min_length=1, max_length=MAX_REASONS)
    resolver_policy_version: str
    omissions: tuple[str, ...] = Field(default_factory=tuple, max_length=MAX_REASONS)
    failures: tuple[str, ...] = Field(default_factory=tuple, max_length=MAX_REASONS)
    degraded_reasons: tuple[str, ...] = Field(default_factory=tuple, max_length=MAX_REASONS)
    provider_usage: ProviderUsageV1 = Field(default_factory=ProviderUsageV1)

    @field_validator("product_id")
    @classmethod
    def validate_product(cls, value: str) -> str:
        return _product(value)

    @field_validator(
        "changed_input_refs",
        "affected_assertion_refs",
        "unaffected_assertion_refs",
        "reopened_revision_refs",
        "reasons",
        "omissions",
        "failures",
        "degraded_reasons",
        mode="before",
    )
    @classmethod
    def normalize_refs(cls, value: Any, info) -> tuple[str, ...]:
        if info.field_name == "unaffected_assertion_refs":
            limit = MAX_PROJECTION_ENTRIES
        elif info.field_name in {"reasons", "omissions", "failures", "degraded_reasons"}:
            limit = MAX_REASONS
        else:
            limit = MAX_REOPENED_ASSERTIONS
        return _refs(value, limit=limit, name=info.field_name)

    @model_validator(mode="after")
    def derive_identity(self) -> Self:
        if set(self.affected_assertion_refs) & set(self.unaffected_assertion_refs):
            raise ValueError("affected and unaffected assertion sets must be disjoint")
        if len(self.reopened_revision_refs) != len(self.affected_assertion_refs):
            raise ValueError("every affected assertion requires exactly one reopened revision")
        material = self.model_dump(mode="json", exclude={"receipt_id", "receipt_hash"})
        expected_hash = canonical_hash(material)
        expected_id = f"grounded_reprojection_receipt:{expected_hash[:32]}"
        if self.receipt_hash is not None and self.receipt_hash != expected_hash:
            raise ValueError("reprojection receipt hash does not match exact material")
        if self.receipt_id is not None and self.receipt_id != expected_id:
            raise ValueError("reprojection receipt identity does not match exact material")
        object.__setattr__(self, "receipt_hash", expected_hash)
        object.__setattr__(self, "receipt_id", expected_id)
        return self
