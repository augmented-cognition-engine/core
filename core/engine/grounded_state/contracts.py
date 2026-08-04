"""Immutable v1 contracts for grounded epistemic state, dynamics, and rollout inputs.

The contracts deliberately keep four meanings separate:

* evidence records describe what a source supplied;
* belief-state assertions describe ACE's reproducible as-of assessment;
* transition hypotheses describe proposed world dynamics; and
* rollout requests freeze the alternatives ACE intends to simulate.

No model output can turn one meaning into another merely by changing a type
label. Stable identities are product-scoped and derived from canonical inputs.
"""

from __future__ import annotations

import hashlib
import json
import re
from datetime import datetime
from enum import StrEnum
from typing import Any, Literal, Mapping, Self

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

EVIDENCE_RECORD_VERSION = "ace.grounded-state.evidence-record/v1"
BELIEF_STATE_ASSERTION_VERSION = "ace.grounded-state.belief-state-assertion/v1"
TRANSITION_HYPOTHESIS_VERSION = "ace.grounded-state.transition-hypothesis/v1"
CONSEQUENCE_ROLLOUT_REQUEST_VERSION = "ace.grounded-state.consequence-rollout-request/v1"

MAX_CONTENT_CHARS = 8_000
MAX_REFS = 200
MAX_STATE_VALUE_CHARS = 16_000
_PRODUCT_ID = re.compile(r"^product:[A-Za-z0-9][A-Za-z0-9._-]{0,159}$")
_REFERENCE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:/-]{0,239}$")
_SHA256 = re.compile(r"^[a-f0-9]{64}$")

StateValue = bool | int | float | str | list[Any] | dict[str, Any] | None


def canonical_hash(value: Any) -> str:
    """Return the SHA-256 digest of a deterministic JSON representation."""
    if isinstance(value, BaseModel):
        value = value.model_dump(mode="json")
    encoded = json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode()
    return hashlib.sha256(encoded).hexdigest()


def stable_id(prefix: str, value: Any) -> str:
    """Build a bounded stable identifier from canonical material semantics."""
    return f"{prefix}:{canonical_hash(value)[:32]}"


def _aware(value: datetime, name: str) -> datetime:
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError(f"{name} must include a timezone")
    return value


def _normalized_refs(value: Any) -> tuple[str, ...]:
    if value is None:
        return ()
    if not isinstance(value, (list, tuple, set, frozenset)):
        raise ValueError("references must be a collection")
    refs = tuple(sorted(set(value)))
    if len(refs) > MAX_REFS:
        raise ValueError(f"references exceed the {MAX_REFS}-item bound")
    if any(not isinstance(ref, str) or not _REFERENCE.fullmatch(ref) for ref in refs):
        raise ValueError("references must use bounded stable identifiers")
    return refs


def _validate_product_id(product_id: str) -> str:
    if not _PRODUCT_ID.fullmatch(product_id):
        raise ValueError("product_id must be a product-scoped record identifier")
    return product_id


def _validate_sha256(value: str) -> str:
    normalized = value.lower()
    if not _SHA256.fullmatch(normalized):
        raise ValueError("hash must be a lowercase SHA-256 digest")
    return normalized


def _validate_state_value(value: StateValue) -> StateValue:
    try:
        serialized = json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
    except (TypeError, ValueError) as exc:
        raise ValueError("state values must be JSON serializable") from exc
    if len(serialized) > MAX_STATE_VALUE_CHARS:
        raise ValueError("state value exceeds the bounded serialized size")
    return value


class FrozenContract(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)


class TimePrecision(StrEnum):
    EXACT = "exact"
    DAY = "day"
    MONTH = "month"
    RANGE = "range"
    INFERRED = "inferred"
    UNKNOWN = "unknown"


class EvidenceKind(StrEnum):
    SOURCE_DOCUMENT = "source_document"
    CLAIM = "claim"
    EVENT = "event"
    ENTITY = "entity"
    ALIAS = "alias"
    MENTION = "mention"


class BeliefStatus(StrEnum):
    SUPPORTED = "supported"
    PROVISIONAL = "provisional"
    CONTESTED = "contested"
    SUPERSEDED = "superseded"
    STALE = "stale"
    UNKNOWN = "unknown"


class CausalStrength(StrEnum):
    ASSOCIATIVE = "associative"
    PREDICTIVE = "predictive"
    MECHANISTIC = "mechanistic"
    CAUSAL = "causal"


class TransitionReviewState(StrEnum):
    PROPOSED = "proposed"
    PROVISIONAL = "provisional"
    ACCEPTED = "accepted"
    CONTESTED = "contested"
    REJECTED = "rejected"
    SUPERSEDED = "superseded"
    STALE = "stale"


class SupportingEvidenceOriginV1(FrozenContract):
    """Bind one transition evidence record to its asserted source origin."""

    evidence_ref: str = Field(min_length=1, max_length=240)
    source_ref: str = Field(min_length=1, max_length=240)
    origin_group: str = Field(min_length=1, max_length=240)

    @field_validator("evidence_ref", "source_ref", "origin_group")
    @classmethod
    def validate_ref(cls, value: str) -> str:
        if not _REFERENCE.fullmatch(value):
            raise ValueError("evidence-origin fields must be bounded stable references")
        return value


class RolloutBranchKind(StrEnum):
    ACTION = "action"
    NO_ACTION = "no_action"
    ALTERNATIVE = "alternative"


class TemporalScopeV1(FrozenContract):
    """An instant, interval, or explicitly unknown time meaning."""

    occurred_at: datetime | None = None
    valid_from: datetime | None = None
    valid_to: datetime | None = None
    precision: TimePrecision = TimePrecision.UNKNOWN
    inferred_from: tuple[str, ...] = Field(default_factory=tuple, max_length=MAX_REFS)

    @field_validator("occurred_at", "valid_from", "valid_to")
    @classmethod
    def validate_timezone(cls, value: datetime | None, info) -> datetime | None:
        return _aware(value, info.field_name) if value is not None else None

    @field_validator("inferred_from", mode="before")
    @classmethod
    def normalize_inferred_refs(cls, value: Any) -> tuple[str, ...]:
        return _normalized_refs(value)

    @model_validator(mode="after")
    def validate_temporal_meaning(self) -> Self:
        has_instant = self.occurred_at is not None
        has_interval = self.valid_from is not None or self.valid_to is not None
        if has_instant and has_interval:
            raise ValueError("temporal scope must use an instant or an interval, not both")
        if self.valid_from is not None and self.valid_to is not None and self.valid_to < self.valid_from:
            raise ValueError("valid_to must not precede valid_from")
        if self.precision is TimePrecision.UNKNOWN and (has_instant or has_interval):
            raise ValueError("unknown precision cannot carry a fabricated timestamp")
        if self.precision is not TimePrecision.UNKNOWN and not (has_instant or has_interval):
            raise ValueError("known or inferred precision requires an instant or interval")
        if self.precision is TimePrecision.EXACT and not has_instant:
            raise ValueError("exact precision requires one occurred_at instant")
        if self.precision is TimePrecision.RANGE and not has_interval:
            raise ValueError("range precision requires an open or closed validity interval")
        if self.precision is TimePrecision.INFERRED and not self.inferred_from:
            raise ValueError("inferred time requires provenance references")
        if self.precision is not TimePrecision.INFERRED and self.inferred_from:
            raise ValueError("inferred_from is only valid for inferred time")
        return self


class ExtractionProvenanceV1(FrozenContract):
    extractor: str = Field(min_length=1, max_length=200)
    extractor_version: str = Field(min_length=1, max_length=120)
    model: str | None = Field(default=None, max_length=200)
    provider: str | None = Field(default=None, max_length=120)
    prompt_version: str | None = Field(default=None, max_length=120)
    source_span: str | None = Field(default=None, max_length=500)


class GroundedEvidenceRecordV1(FrozenContract):
    """One immutable, attributed record in the grounded evidence ledger."""

    contract_version: Literal["ace.grounded-state.evidence-record/v1"] = EVIDENCE_RECORD_VERSION
    product_id: str
    kind: EvidenceKind
    external_id: str = Field(min_length=1, max_length=500)
    source_id: str = Field(min_length=1, max_length=240)
    source_version: str = Field(min_length=1, max_length=240)
    content_hash: str
    content: str | None = Field(default=None, max_length=MAX_CONTENT_CHARS)
    temporal: TemporalScopeV1 = Field(default_factory=TemporalScopeV1)
    published_at: datetime | None = None
    ingested_at: datetime
    extracted_at: datetime | None = None
    confidence: float | None = Field(default=None, ge=0, le=1)
    entity_refs: tuple[str, ...] = Field(default_factory=tuple, max_length=MAX_REFS)
    raw_mentions: tuple[str, ...] = Field(default_factory=tuple, max_length=MAX_REFS)
    supersedes: tuple[str, ...] = Field(default_factory=tuple, max_length=MAX_REFS)
    extraction: ExtractionProvenanceV1 | None = None

    @field_validator("product_id")
    @classmethod
    def validate_product(cls, value: str) -> str:
        return _validate_product_id(value)

    @field_validator("content_hash")
    @classmethod
    def validate_content_hash(cls, value: str) -> str:
        return _validate_sha256(value)

    @field_validator("published_at", "ingested_at", "extracted_at")
    @classmethod
    def validate_timestamps(cls, value: datetime | None, info) -> datetime | None:
        return _aware(value, info.field_name) if value is not None else None

    @field_validator("entity_refs", "supersedes", mode="before")
    @classmethod
    def normalize_refs(cls, value: Any) -> tuple[str, ...]:
        return _normalized_refs(value)

    @field_validator("raw_mentions", mode="before")
    @classmethod
    def normalize_mentions(cls, value: Any) -> tuple[str, ...]:
        if value is None:
            return ()
        if not isinstance(value, (list, tuple, set, frozenset)):
            raise ValueError("raw_mentions must be a collection")
        mentions = tuple(sorted(set(value)))
        if len(mentions) > MAX_REFS or any(not isinstance(item, str) or not item.strip() for item in mentions):
            raise ValueError("raw_mentions must contain bounded non-empty strings")
        if any(len(item) > 500 for item in mentions):
            raise ValueError("raw mention exceeds the 500-character bound")
        return mentions

    @model_validator(mode="after")
    def validate_record(self) -> Self:
        if self.kind in {EvidenceKind.CLAIM, EvidenceKind.EVENT} and not (self.content or "").strip():
            raise ValueError("claim and event evidence require bounded content")
        if self.content is not None:
            computed_hash = hashlib.sha256(self.content.encode("utf-8")).hexdigest()
            if self.content_hash != computed_hash:
                raise ValueError("content_hash must equal the SHA-256 digest of supplied content")
        if self.extracted_at is not None and self.extraction is None:
            raise ValueError("extracted evidence requires extraction provenance")
        if self.extraction is not None and self.extracted_at is None:
            raise ValueError("extraction provenance requires extracted_at")
        if self.evidence_id() in self.supersedes:
            raise ValueError("an evidence record cannot supersede itself")
        return self

    def evidence_id(self) -> str:
        return stable_id(
            "grounded_evidence",
            {
                "contract_version": self.contract_version,
                "product_id": self.product_id,
                "kind": self.kind,
                "external_id": self.external_id,
                "source_id": self.source_id,
                "source_version": self.source_version,
                "content_hash": self.content_hash,
            },
        )


class BeliefStateAssertionV1(FrozenContract):
    """ACE's reproducible, time-scoped assessment of one world-state value."""

    contract_version: Literal["ace.grounded-state.belief-state-assertion/v1"] = BELIEF_STATE_ASSERTION_VERSION
    product_id: str
    as_of: datetime
    subject: str = Field(min_length=1, max_length=240)
    predicate: str = Field(min_length=1, max_length=160)
    value: StateValue = None
    validity: TemporalScopeV1 = Field(default_factory=TemporalScopeV1)
    status: BeliefStatus
    epistemic_confidence: float = Field(ge=0, le=1)
    source_confidence: float | None = Field(default=None, ge=0, le=1)
    freshness: float | None = Field(default=None, ge=0, le=1)
    supporting_evidence_refs: tuple[str, ...] = Field(default_factory=tuple, max_length=MAX_REFS)
    contradicting_evidence_refs: tuple[str, ...] = Field(default_factory=tuple, max_length=MAX_REFS)
    superseding_assertion_refs: tuple[str, ...] = Field(default_factory=tuple, max_length=MAX_REFS)
    missing_reason: str | None = Field(default=None, max_length=1_000)
    status_reason: str | None = Field(default=None, max_length=1_000)
    ontology_version: str = Field(min_length=1, max_length=120)
    resolver_policy_version: str = Field(min_length=1, max_length=120)

    @field_validator("product_id")
    @classmethod
    def validate_product(cls, value: str) -> str:
        return _validate_product_id(value)

    @field_validator("as_of")
    @classmethod
    def validate_as_of(cls, value: datetime) -> datetime:
        return _aware(value, "as_of")

    @field_validator("value")
    @classmethod
    def validate_value(cls, value: StateValue) -> StateValue:
        return _validate_state_value(value)

    @field_validator(
        "supporting_evidence_refs",
        "contradicting_evidence_refs",
        "superseding_assertion_refs",
        mode="before",
    )
    @classmethod
    def normalize_refs(cls, value: Any) -> tuple[str, ...]:
        return _normalized_refs(value)

    @model_validator(mode="after")
    def validate_belief_state(self) -> Self:
        supporting = set(self.supporting_evidence_refs)
        contradicting = set(self.contradicting_evidence_refs)
        if supporting & contradicting:
            raise ValueError("supporting and contradicting evidence must be disjoint")
        if self.status in {BeliefStatus.SUPPORTED, BeliefStatus.PROVISIONAL}:
            if self.value is None or not supporting:
                raise ValueError("supported and provisional state require a value and supporting evidence")
        if self.status is BeliefStatus.CONTESTED:
            if self.value is None or not supporting or not contradicting:
                raise ValueError("contested state requires a value plus supporting and contradicting evidence")
        if self.status is BeliefStatus.UNKNOWN:
            if self.value is not None or not (self.missing_reason or "").strip():
                raise ValueError("unknown state requires no value and an explicit missing_reason")
            if self.epistemic_confidence != 0:
                raise ValueError("unknown state requires zero epistemic confidence")
            if supporting or contradicting or self.superseding_assertion_refs:
                raise ValueError("unknown state cannot cite evidential support or supersession")
        elif self.missing_reason is not None:
            raise ValueError("missing_reason is reserved for unknown state")
        if self.status is BeliefStatus.SUPERSEDED:
            if self.value is None or not supporting or not self.superseding_assertion_refs:
                raise ValueError("superseded state requires its prior value, support, and a successor assertion")
        if self.status is BeliefStatus.STALE:
            if self.value is None or not supporting or not (self.status_reason or "").strip():
                raise ValueError("stale state requires its prior value, support, and an explicit status_reason")
        elif self.status_reason is not None:
            raise ValueError("status_reason is reserved for stale state")
        if not supporting and (self.source_confidence is not None or self.freshness is not None):
            raise ValueError("source confidence and freshness require supporting evidence")
        return self

    def assertion_id(self) -> str:
        return stable_id(
            "grounded_state",
            {
                "contract_version": self.contract_version,
                "product_id": self.product_id,
                "subject": self.subject,
                "predicate": self.predicate,
                "value": self.value,
                "validity": self.validity.model_dump(mode="json"),
                "ontology_version": self.ontology_version,
            },
        )

    def projection_hash(self) -> str:
        return canonical_hash(self)


class StatePatternV1(FrozenContract):
    subject: str = Field(min_length=1, max_length=240)
    predicate: str = Field(min_length=1, max_length=160)
    value: StateValue = None

    @field_validator("value")
    @classmethod
    def validate_value(cls, value: StateValue) -> StateValue:
        return _validate_state_value(value)


class ProbabilityEstimateV1(FrozenContract):
    lower: float = Field(ge=0, le=1)
    expected: float = Field(ge=0, le=1)
    upper: float = Field(ge=0, le=1)

    @model_validator(mode="after")
    def validate_order(self) -> Self:
        if not self.lower <= self.expected <= self.upper:
            raise ValueError("probability estimate must satisfy lower <= expected <= upper")
        return self


class TransitionHypothesisV1(FrozenContract):
    """A versioned hypothesis about how one world state may become another."""

    contract_version: Literal["ace.grounded-state.transition-hypothesis/v1"] = TRANSITION_HYPOTHESIS_VERSION
    product_id: str
    revision: str = Field(min_length=1, max_length=120)
    source_state: StatePatternV1
    target_state: StatePatternV1
    trigger: str = Field(min_length=1, max_length=500)
    mechanism: str = Field(min_length=1, max_length=2_000)
    preconditions: tuple[str, ...] = Field(default_factory=tuple, max_length=50)
    constraints: tuple[str, ...] = Field(default_factory=tuple, max_length=50)
    delay_min_seconds: int = Field(ge=0)
    delay_max_seconds: int = Field(ge=0)
    probability: ProbabilityEstimateV1
    causal_strength: CausalStrength
    review_state: TransitionReviewState = TransitionReviewState.PROPOSED
    supporting_evidence_refs: tuple[str, ...] = Field(default_factory=tuple, max_length=MAX_REFS)
    contrary_evidence_refs: tuple[str, ...] = Field(default_factory=tuple, max_length=MAX_REFS)
    supporting_evidence_origins: tuple[SupportingEvidenceOriginV1, ...] = Field(
        default_factory=tuple,
        max_length=MAX_REFS,
    )
    human_confirmed: bool = False
    human_review_ref: str | None = Field(default=None, max_length=240)
    source_independence_review_ref: str | None = Field(default=None, max_length=240)
    reviewed_material_hash: str | None = None
    ontology_version: str = Field(min_length=1, max_length=120)
    policy_version: str = Field(min_length=1, max_length=120)

    @field_validator("product_id")
    @classmethod
    def validate_product(cls, value: str) -> str:
        return _validate_product_id(value)

    @field_validator("supporting_evidence_refs", "contrary_evidence_refs", mode="before")
    @classmethod
    def normalize_refs(cls, value: Any) -> tuple[str, ...]:
        return _normalized_refs(value)

    @field_validator("supporting_evidence_origins", mode="before")
    @classmethod
    def normalize_origins(cls, value: Any) -> Any:
        if not isinstance(value, (list, tuple)):
            return value
        return tuple(sorted(value, key=canonical_hash))

    @field_validator("human_review_ref", "source_independence_review_ref")
    @classmethod
    def validate_human_review_ref(cls, value: str | None) -> str | None:
        if value is not None and not _REFERENCE.fullmatch(value):
            raise ValueError("review references must be bounded stable references")
        return value

    @field_validator("reviewed_material_hash")
    @classmethod
    def validate_reviewed_material_hash(cls, value: str | None) -> str | None:
        return _validate_sha256(value) if value is not None else None

    @field_validator("preconditions", "constraints", mode="before")
    @classmethod
    def normalize_rules(cls, value: Any) -> tuple[str, ...]:
        if value is None:
            return ()
        if not isinstance(value, (list, tuple, set, frozenset)):
            raise ValueError("preconditions and constraints must be collections")
        rules = tuple(sorted(set(value)))
        if any(not isinstance(rule, str) or not rule.strip() or len(rule) > 1_000 for rule in rules):
            raise ValueError("preconditions and constraints must be bounded non-empty strings")
        return rules

    @model_validator(mode="after")
    def validate_hypothesis(self) -> Self:
        if self.delay_max_seconds < self.delay_min_seconds:
            raise ValueError("delay_max_seconds must not be less than delay_min_seconds")
        supporting = set(self.supporting_evidence_refs)
        contrary = set(self.contrary_evidence_refs)
        origin_evidence = [origin.evidence_ref for origin in self.supporting_evidence_origins]
        if supporting & contrary:
            raise ValueError("supporting and contrary evidence must be disjoint")
        if len(origin_evidence) != len(set(origin_evidence)):
            raise ValueError("supporting evidence may have only one declared source origin")
        if set(origin_evidence) - supporting:
            raise ValueError("source-origin bindings must reference supporting evidence")
        if self.review_state is TransitionReviewState.ACCEPTED and not supporting:
            raise ValueError("accepted transitions require supporting evidence")
        if self.causal_strength is CausalStrength.CAUSAL:
            source_refs = {origin.source_ref for origin in self.supporting_evidence_origins}
            origin_groups = {origin.origin_group for origin in self.supporting_evidence_origins}
            if (
                self.review_state is not TransitionReviewState.ACCEPTED
                or not self.human_confirmed
                or self.human_review_ref is None
                or self.source_independence_review_ref is None
                or self.reviewed_material_hash is None
                or len(supporting) < 2
                or set(origin_evidence) != supporting
                or len(source_refs) < 2
                or len(origin_groups) < 2
            ):
                raise ValueError(
                    "causal transitions require accepted human confirmation bound to every supporting evidence record and at least two independent source origins"
                )
            if self.reviewed_material_hash != self.review_material_hash():
                raise ValueError("causal review must bind the exact transition review-material hash")
        elif (
            self.human_confirmed
            or self.human_review_ref is not None
            or self.source_independence_review_ref is not None
            or self.reviewed_material_hash is not None
            or self.supporting_evidence_origins
        ):
            raise ValueError("human confirmation fields are reserved for causal transition acceptance")
        return self

    @classmethod
    def review_material_hash_for(cls, value: Mapping[str, Any]) -> str:
        """Hash normalized causal semantics without their review outcome fields."""

        def dump(item: Any) -> Any:
            return item.model_dump(mode="json") if isinstance(item, BaseModel) else item

        origins = [dump(item) for item in value.get("supporting_evidence_origins", ())]
        material = {
            "contract_version": value.get("contract_version", TRANSITION_HYPOTHESIS_VERSION),
            "product_id": value.get("product_id"),
            "revision": value.get("revision"),
            "source_state": dump(value.get("source_state")),
            "target_state": dump(value.get("target_state")),
            "trigger": value.get("trigger"),
            "mechanism": value.get("mechanism"),
            "preconditions": sorted(set(value.get("preconditions", ()))),
            "constraints": sorted(set(value.get("constraints", ()))),
            "delay_min_seconds": value.get("delay_min_seconds"),
            "delay_max_seconds": value.get("delay_max_seconds"),
            "probability": dump(value.get("probability")),
            "causal_strength": value.get("causal_strength"),
            "supporting_evidence_refs": sorted(set(value.get("supporting_evidence_refs", ()))),
            "contrary_evidence_refs": sorted(set(value.get("contrary_evidence_refs", ()))),
            "supporting_evidence_origins": sorted(origins, key=canonical_hash),
            "ontology_version": value.get("ontology_version"),
            "policy_version": value.get("policy_version"),
        }
        return canonical_hash(material)

    def review_material_hash(self) -> str:
        return self.review_material_hash_for(self.model_dump(mode="json"))

    def hypothesis_id(self) -> str:
        return stable_id("state_transition", self)


class RolloutBranchInputV1(FrozenContract):
    branch_id: str = Field(min_length=1, max_length=120)
    kind: RolloutBranchKind
    action: str | None = Field(default=None, max_length=2_000)
    transition_hypothesis_ids: tuple[str, ...] = Field(default_factory=tuple, max_length=50)

    @field_validator("branch_id")
    @classmethod
    def validate_branch_id(cls, value: str) -> str:
        if not _REFERENCE.fullmatch(value):
            raise ValueError("branch_id must be a bounded stable identifier")
        return value

    @field_validator("transition_hypothesis_ids", mode="before")
    @classmethod
    def normalize_transitions(cls, value: Any) -> tuple[str, ...]:
        return _normalized_refs(value)

    @model_validator(mode="after")
    def validate_action(self) -> Self:
        if self.kind is RolloutBranchKind.NO_ACTION and self.action is not None:
            raise ValueError("no_action branches must not smuggle in an action")
        if self.kind is not RolloutBranchKind.NO_ACTION and not (self.action or "").strip():
            raise ValueError("action and alternative branches require an explicit action")
        if self.kind is not RolloutBranchKind.NO_ACTION and not self.transition_hypothesis_ids:
            raise ValueError("action and alternative branches require at least one transition hypothesis")
        return self


class ConsequenceRolloutRequestV1(FrozenContract):
    """Immutable comparison inputs for a bounded consequence simulation."""

    contract_version: Literal["ace.grounded-state.consequence-rollout-request/v1"] = CONSEQUENCE_ROLLOUT_REQUEST_VERSION
    product_id: str
    starting_state_id: str = Field(min_length=1, max_length=240)
    starting_state_hash: str
    evidence_pack_id: str = Field(min_length=1, max_length=240)
    evidence_pack_hash: str
    as_of: datetime
    horizon: datetime
    branches: tuple[RolloutBranchInputV1, ...] = Field(min_length=2, max_length=8)
    assumptions: tuple[str, ...] = Field(default_factory=tuple, max_length=50)
    constraints: tuple[str, ...] = Field(default_factory=tuple, max_length=50)
    unavailable_inputs: tuple[str, ...] = Field(default_factory=tuple, max_length=50)
    policy_version: str = Field(min_length=1, max_length=120)
    seed: int | None = None

    @field_validator("product_id")
    @classmethod
    def validate_product(cls, value: str) -> str:
        return _validate_product_id(value)

    @field_validator("starting_state_id", "evidence_pack_id")
    @classmethod
    def validate_refs(cls, value: str) -> str:
        if not _REFERENCE.fullmatch(value):
            raise ValueError("state and pack identifiers must be bounded stable references")
        return value

    @field_validator("starting_state_hash", "evidence_pack_hash")
    @classmethod
    def validate_hashes(cls, value: str) -> str:
        return _validate_sha256(value)

    @field_validator("as_of", "horizon")
    @classmethod
    def validate_times(cls, value: datetime, info) -> datetime:
        return _aware(value, info.field_name)

    @field_validator("branches", mode="before")
    @classmethod
    def normalize_branches(cls, value: Any) -> Any:
        if not isinstance(value, (list, tuple)):
            raise ValueError("branches must be a bounded collection")

        def branch_id(item: Any) -> str:
            if isinstance(item, RolloutBranchInputV1):
                return item.branch_id
            if isinstance(item, dict):
                return str(item.get("branch_id", ""))
            return ""

        return tuple(sorted(value, key=branch_id))

    @field_validator("assumptions", "constraints", "unavailable_inputs", mode="before")
    @classmethod
    def normalize_rules(cls, value: Any) -> tuple[str, ...]:
        if value is None:
            return ()
        if not isinstance(value, (list, tuple, set, frozenset)):
            raise ValueError("assumptions and constraints must be collections")
        rules = tuple(sorted(set(value)))
        if any(not isinstance(rule, str) or not rule.strip() or len(rule) > 1_000 for rule in rules):
            raise ValueError("assumptions and constraints must be bounded non-empty strings")
        return rules

    @model_validator(mode="after")
    def validate_rollout_request(self) -> Self:
        if self.horizon <= self.as_of:
            raise ValueError("rollout horizon must be later than the frozen starting state")
        branch_ids = [branch.branch_id for branch in self.branches]
        if len(branch_ids) != len(set(branch_ids)):
            raise ValueError("rollout branch identifiers must be unique")
        no_action = [branch for branch in self.branches if branch.kind is RolloutBranchKind.NO_ACTION]
        if len(no_action) != 1:
            raise ValueError("rollout comparisons require exactly one no_action branch")
        if not any(branch.kind is not RolloutBranchKind.NO_ACTION for branch in self.branches):
            raise ValueError("rollout comparisons require at least one action or alternative branch")
        return self

    def request_hash(self) -> str:
        return canonical_hash(self)

    def rollout_id(self) -> str:
        return f"consequence_rollout:{self.request_hash()[:32]}"
