"""Versioned contracts for the provider-free TP0 temporal reference corpus."""

from __future__ import annotations

import re
from datetime import datetime
from enum import StrEnum
from typing import Any, Literal, Self

from pydantic import Field, field_validator, model_validator

from core.engine.grounded_state.contracts import (
    BeliefStatus,
    FrozenContract,
    GroundedEvidenceRecordV1,
    RolloutBranchKind,
    StateValue,
    TemporalScopeV1,
    canonical_hash,
    stable_id,
)

TEMPORAL_REFERENCE_CASE_VERSION = "ace.grounded-state.temporal-reference-case/v1"
TEMPORAL_REFERENCE_EXPECTATION_VERSION = "ace.grounded-state.temporal-reference-expectation/v1"
TEMPORAL_REFERENCE_CORPUS_VERSION = "ace.grounded-state.temporal-reference-corpus/v1"

_CASE_KEY = re.compile(r"^[a-z0-9][a-z0-9_-]{2,119}$")
_INPUT_KEY = re.compile(r"^[a-z][a-z0-9_-]{0,79}$")
_ENDPOINT_IDENTITY = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:/-]{0,239}$")
_SHA256 = re.compile(r"^[a-f0-9]{64}$")


class ReferenceCategory(StrEnum):
    EXACT_REPLAY = "exact_replay"
    SOURCE_VERSION_REPLACEMENT = "source_version_replacement"
    RESTATEMENT = "restatement"
    INDEPENDENT_CORROBORATION = "independent_corroboration"
    TEMPORAL_CHANGE = "temporal_change"
    SAME_INTERVAL_CONTRADICTION = "same_interval_contradiction"
    OPEN_INTERVAL = "open_interval"
    CLOSED_INTERVAL = "closed_interval"
    OVERLAPPING_INTERVAL = "overlapping_interval"
    INFERRED_TIME = "inferred_time"
    UNKNOWN_TIME = "unknown_time"
    SEPARATED_TIME_MEANINGS = "separated_time_meanings"
    ENTITY_ALIAS = "entity_alias"
    ENTITY_COLLISION = "entity_collision"
    AMBIGUOUS_MENTION = "ambiguous_mention"
    ENTITY_CHANGE = "entity_change"
    SOURCE_DUPLICATION = "source_duplication"
    SOURCE_INDEPENDENCE_FAILURE = "source_independence_failure"
    BELIEF_STALE = "belief_stale"
    BELIEF_SUPERSEDED = "belief_superseded"
    BELIEF_PROVISIONAL = "belief_provisional"
    BELIEF_CONTESTED = "belief_contested"
    BELIEF_UNKNOWN = "belief_unknown"
    REACTION_SEQUENCE = "reaction_sequence"
    TEMPORAL_SEQUENCE_NO_CAUSATION = "temporal_sequence_no_causation"
    MECHANISTIC_HYPOTHESIS = "mechanistic_hypothesis"
    CONTRARY_MECHANISM_EVIDENCE = "contrary_mechanism_evidence"
    HUMAN_GATED_CAUSAL_CLAIM = "human_gated_causal_claim"
    UNRELATED_NEGATIVE_CONTROL = "unrelated_negative_control"
    CROSS_PRODUCT_ISOLATION = "cross_product_isolation"
    ACTION_NO_ACTION_ROLLOUT = "action_no_action_rollout"
    INVALID_ROLLOUT_INPUT = "invalid_rollout_input"
    PREDICTION_NOT_OBSERVATION = "prediction_not_observation"


REQUIRED_REFERENCE_CATEGORIES = frozenset(ReferenceCategory)
REQUIRED_MAINTAINER_REVIEW_CASE_KEYS = frozenset(
    {
        "alias_registry_version_change",
        "ambiguous_heron_mention",
        "attributed_source_dependency",
        "causal_claim_requires_human_gate",
        "contested_delivery_belief",
        "entity_alias_same_identity",
        "entity_legal_name_change",
        "entity_name_collision",
        "independent_factory_corroboration",
        "lexically_similar_unrelated_control",
        "mechanism_supported_transition",
        "mechanism_with_contrary_evidence",
        "overlapping_capacity_reports",
        "price_reaction_not_causal_fact",
        "restatement_not_corroboration",
        "same_interval_operating_conflict",
        "sequence_without_causal_promotion",
        "world_state_changes_over_time",
    }
)


class CorpusMaturity(StrEnum):
    SEED = "seed"
    CANDIDATE = "candidate"
    FROZEN = "frozen"


class RelationshipClassification(StrEnum):
    EXACT_REPLAY = "exact_replay"
    SOURCE_VERSION_REPLACEMENT = "source_version_replacement"
    RESTATEMENT = "restatement"
    CORROBORATES = "corroborates"
    STATE_TRANSITION = "state_transition"
    SAME_INTERVAL_CONTRADICTION = "same_interval_contradiction"
    OVERLAPS = "overlaps"
    PRECEDES = "precedes"
    REACTS_TO = "reacts_to"
    ALIAS_OF = "alias_of"
    AMBIGUOUS_ENTITY = "ambiguous_entity"
    ENTITY_CHANGED = "entity_changed"
    DUPLICATE_SOURCE = "duplicate_source"
    SOURCE_DEPENDENCY = "source_dependency"
    MECHANISTIC_SUPPORT = "mechanistic_support"
    CONTRARY_EVIDENCE = "contrary_evidence"
    CAUSAL_CANDIDATE = "causal_candidate"
    CAUSES = "causes"
    BACKGROUND_EVIDENCE = "background_evidence"
    UNRELATED = "unrelated"
    CROSS_PRODUCT_ISOLATED = "cross_product_isolated"
    NO_RELATIONSHIP = "no_relationship"


class EligibilityState(StrEnum):
    ELIGIBLE = "eligible"
    INELIGIBLE = "ineligible"
    REQUIRES_HUMAN_REVIEW = "requires_human_review"
    INVALID_INPUT = "invalid_input"


class StateRecordMeaning(StrEnum):
    EVIDENCE = "evidence"
    BELIEF_STATE = "belief_state"
    TRANSITION_HYPOTHESIS = "transition_hypothesis"
    SIMULATED_CONSEQUENCE = "simulated_consequence"
    PREDICTION = "prediction"
    OBSERVED_OUTCOME = "observed_outcome"


class RelationshipEndpointKind(StrEnum):
    EVIDENCE = "evidence"
    ENTITY = "entity"
    EVENT = "event"
    MENTION = "mention"
    STATE = "state"
    TRANSITION_HYPOTHESIS = "transition_hypothesis"


class ReviewRequirement(StrEnum):
    DETERMINISTIC = "deterministic"
    MAINTAINER_ADJUDICATION = "maintainer_adjudication"


class ReviewStatus(StrEnum):
    NOT_REQUIRED = "not_required"
    PENDING = "pending"
    COMPLETED = "completed"


class ReviewDecision(StrEnum):
    ACCEPTED = "accepted"
    REJECTED = "rejected"


def _normalized_strings(value: Any, *, name: str, limit: int = 200) -> tuple[str, ...]:
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


class ReferenceEvidenceV1(FrozenContract):
    input_key: str
    record: GroundedEvidenceRecordV1

    @field_validator("input_key")
    @classmethod
    def validate_input_key(cls, value: str) -> str:
        if not _INPUT_KEY.fullmatch(value):
            raise ValueError("input_key must be a bounded lowercase stable key")
        return value


class BeliefExpectationV1(FrozenContract):
    product_id: str
    as_of: datetime
    subject: str = Field(min_length=1, max_length=240)
    predicate: str = Field(min_length=1, max_length=160)
    status: BeliefStatus
    value: StateValue = None
    validity: TemporalScopeV1 = Field(default_factory=TemporalScopeV1)
    supporting_evidence_keys: tuple[str, ...] = Field(default_factory=tuple, max_length=200)
    contradicting_evidence_keys: tuple[str, ...] = Field(default_factory=tuple, max_length=200)
    superseding_assertion_refs: tuple[str, ...] = Field(default_factory=tuple, max_length=200)
    missing_reason: str | None = Field(default=None, max_length=1_000)
    status_reason: str | None = Field(default=None, max_length=1_000)

    @field_validator("as_of")
    @classmethod
    def validate_as_of(cls, value: datetime) -> datetime:
        if value.tzinfo is None or value.utcoffset() is None:
            raise ValueError("as_of must include a timezone")
        return value

    @field_validator("product_id")
    @classmethod
    def validate_product_id(cls, value: str) -> str:
        if not value.startswith("product:"):
            raise ValueError("belief expectation product_id must be product-scoped")
        return value

    @field_validator(
        "supporting_evidence_keys",
        "contradicting_evidence_keys",
        "superseding_assertion_refs",
        mode="before",
    )
    @classmethod
    def normalize_evidence_keys(cls, value: Any, info) -> tuple[str, ...]:
        return _normalized_strings(value, name=info.field_name)

    @model_validator(mode="after")
    def validate_status_meaning(self) -> Self:
        support = set(self.supporting_evidence_keys)
        contrary = set(self.contradicting_evidence_keys)
        if support & contrary:
            raise ValueError("belief expectation support and contradiction keys must be disjoint")
        if self.status is BeliefStatus.UNKNOWN:
            if self.value is not None or not (self.missing_reason or "").strip():
                raise ValueError("unknown belief expectations require no value and a missing_reason")
            if support or contrary or self.superseding_assertion_refs:
                raise ValueError("unknown belief expectations cannot claim evidential resolution or supersession")
        else:
            if self.value is None:
                raise ValueError("non-unknown belief expectations require an expected value")
            if self.missing_reason is not None:
                raise ValueError("missing_reason is reserved for unknown belief expectations")
        if self.status is BeliefStatus.CONTESTED and (not support or not contrary):
            raise ValueError("contested belief expectations require supporting and contradicting inputs")
        if self.status not in {BeliefStatus.UNKNOWN, BeliefStatus.CONTESTED} and not support:
            raise ValueError("resolved belief expectations require at least one supporting input")
        if self.status is BeliefStatus.SUPERSEDED:
            if not self.superseding_assertion_refs:
                raise ValueError("superseded belief expectations require a successor assertion reference")
        elif self.superseding_assertion_refs:
            raise ValueError("superseding assertion references are reserved for superseded beliefs")
        if self.status is BeliefStatus.STALE:
            if not (self.status_reason or "").strip():
                raise ValueError("stale belief expectations require an explicit status_reason")
        elif self.status_reason is not None:
            raise ValueError("status_reason is reserved for stale belief expectations")
        return self


class RelationshipEndpointV1(FrozenContract):
    product_id: str
    kind: RelationshipEndpointKind
    identity: str = Field(min_length=1, max_length=240)

    @field_validator("product_id")
    @classmethod
    def validate_product_id(cls, value: str) -> str:
        if not value.startswith("product:"):
            raise ValueError("relationship endpoint product_id must be product-scoped")
        return value

    @field_validator("identity")
    @classmethod
    def validate_identity(cls, value: str) -> str:
        if not _ENDPOINT_IDENTITY.fullmatch(value):
            raise ValueError("relationship endpoint identity must be a bounded stable reference")
        return value

    @model_validator(mode="after")
    def validate_kind_namespace(self) -> Self:
        if self.kind is not RelationshipEndpointKind.EVIDENCE and not self.identity.startswith(f"{self.kind.value}:"):
            raise ValueError("non-evidence relationship identity must match its endpoint-kind namespace")
        return self


class RelationshipExpectationV1(FrozenContract):
    classification: RelationshipClassification
    subject: RelationshipEndpointV1
    object: RelationshipEndpointV1 | None = None
    supporting_evidence_keys: tuple[str, ...] = Field(min_length=1, max_length=200)
    rationale: str = Field(min_length=1, max_length=2_000)

    @field_validator("supporting_evidence_keys", mode="before")
    @classmethod
    def normalize_evidence_keys(cls, value: Any, info) -> tuple[str, ...]:
        return _normalized_strings(value, name=info.field_name)


class EligibilityExpectationV1(FrozenContract):
    state: EligibilityState
    reasons: tuple[str, ...] = Field(min_length=1, max_length=50)

    @field_validator("reasons", mode="before")
    @classmethod
    def normalize_reasons(cls, value: Any) -> tuple[str, ...]:
        return _normalized_strings(value, name="eligibility reasons", limit=50)


class RolloutEligibilityExpectationV1(EligibilityExpectationV1):
    required_branch_kinds: tuple[RolloutBranchKind, ...] = Field(default_factory=tuple, max_length=3)
    unavailable_inputs: tuple[str, ...] = Field(default_factory=tuple, max_length=50)

    @field_validator("required_branch_kinds", mode="before")
    @classmethod
    def normalize_branch_kinds(cls, value: Any) -> tuple[Any, ...]:
        if value is None:
            return ()
        if not isinstance(value, (list, tuple, set, frozenset)):
            raise ValueError("required_branch_kinds must be a collection")
        return tuple(sorted(set(value), key=str))

    @field_validator("unavailable_inputs", mode="before")
    @classmethod
    def normalize_unavailable_inputs(cls, value: Any) -> tuple[str, ...]:
        return _normalized_strings(value, name="unavailable_inputs", limit=50)

    @model_validator(mode="after")
    def validate_rollout_eligibility(self) -> Self:
        branches = set(self.required_branch_kinds)
        has_alternative = RolloutBranchKind.ACTION in branches or RolloutBranchKind.ALTERNATIVE in branches
        if self.state is EligibilityState.ELIGIBLE:
            if RolloutBranchKind.NO_ACTION not in branches or not has_alternative:
                raise ValueError("eligible rollouts require no_action and at least one action or alternative branch")
            if self.unavailable_inputs:
                raise ValueError("eligible rollouts cannot declare unavailable inputs")
        if self.state is EligibilityState.INVALID_INPUT and not self.unavailable_inputs:
            raise ValueError("invalid rollout inputs must name the unavailable inputs")
        return self


class ReviewedJudgmentV1(FrozenContract):
    judgment_hash: str
    decision: ReviewDecision
    rationale: str = Field(min_length=1, max_length=2_000)

    @field_validator("judgment_hash")
    @classmethod
    def validate_judgment_hash(cls, value: str) -> str:
        if not _SHA256.fullmatch(value):
            raise ValueError("judgment_hash must be a lowercase SHA-256 digest")
        return value


class ReviewDispositionV1(FrozenContract):
    requirement: ReviewRequirement
    status: ReviewStatus
    reviewer: str | None = Field(default=None, min_length=1, max_length=240)
    reviewed_at: datetime | None = None
    review_ref: str | None = Field(default=None, min_length=1, max_length=240)
    disposition: str | None = Field(default=None, min_length=1, max_length=2_000)
    reviewed_expectation_hash: str | None = None
    judgments: tuple[ReviewedJudgmentV1, ...] = Field(default_factory=tuple, max_length=100)

    @field_validator("reviewed_at")
    @classmethod
    def validate_review_time(cls, value: datetime | None) -> datetime | None:
        if value is not None and (value.tzinfo is None or value.utcoffset() is None):
            raise ValueError("reviewed_at must include a timezone")
        return value

    @field_validator("review_ref")
    @classmethod
    def validate_review_ref(cls, value: str | None) -> str | None:
        if value is not None and not _ENDPOINT_IDENTITY.fullmatch(value):
            raise ValueError("review_ref must be a bounded stable reference")
        return value

    @field_validator("reviewed_expectation_hash")
    @classmethod
    def validate_expectation_hash(cls, value: str | None) -> str | None:
        if value is not None and not _SHA256.fullmatch(value):
            raise ValueError("reviewed_expectation_hash must be a lowercase SHA-256 digest")
        return value

    @field_validator("judgments", mode="before")
    @classmethod
    def normalize_judgments(cls, value: Any) -> Any:
        if not isinstance(value, (list, tuple)):
            return value

        def judgment_hash(item: Any) -> str:
            if isinstance(item, ReviewedJudgmentV1):
                return item.judgment_hash
            if isinstance(item, dict):
                return str(item.get("judgment_hash", ""))
            return ""

        return tuple(sorted(value, key=judgment_hash))

    @model_validator(mode="after")
    def validate_review_disposition(self) -> Self:
        completed_fields = (
            self.reviewer,
            self.reviewed_at,
            self.review_ref,
            self.disposition,
            self.reviewed_expectation_hash,
        )
        if self.requirement is ReviewRequirement.DETERMINISTIC:
            if (
                self.status is not ReviewStatus.NOT_REQUIRED
                or any(item is not None for item in completed_fields)
                or self.judgments
            ):
                raise ValueError("deterministic expectations must use not_required without reviewer claims")
        elif self.status is ReviewStatus.PENDING:
            if any(item is not None for item in completed_fields) or self.judgments:
                raise ValueError("pending adjudication must not fabricate review completion details")
        elif self.status is ReviewStatus.COMPLETED:
            if any(item is None for item in completed_fields) or not self.judgments:
                raise ValueError(
                    "completed adjudication requires reviewer, time, review reference, disposition, expectation hash, and judgments"
                )
            hashes = [judgment.judgment_hash for judgment in self.judgments]
            if len(hashes) != len(set(hashes)):
                raise ValueError("completed adjudication judgment hashes must be unique")
        else:
            raise ValueError("maintainer adjudication must be pending or completed")
        return self


class ExpectedSemanticsV1(FrozenContract):
    contract_version: Literal["ace.grounded-state.temporal-reference-expectation/v1"] = (
        TEMPORAL_REFERENCE_EXPECTATION_VERSION
    )
    beliefs: tuple[BeliefExpectationV1, ...] = Field(min_length=1, max_length=20)
    relationships: tuple[RelationshipExpectationV1, ...] = Field(min_length=1, max_length=30)
    prohibited_relationships: tuple[RelationshipExpectationV1, ...] = Field(min_length=1, max_length=30)
    transition_hypothesis: EligibilityExpectationV1
    consequence_rollout: RolloutEligibilityExpectationV1
    record_meanings: tuple[StateRecordMeaning, ...] = Field(min_length=1, max_length=6)
    prohibited_record_meanings: tuple[StateRecordMeaning, ...] = Field(min_length=1, max_length=6)

    @field_validator("beliefs", mode="before")
    @classmethod
    def normalize_beliefs(cls, value: Any) -> Any:
        if not isinstance(value, (list, tuple)):
            return value
        return tuple(sorted(value, key=lambda item: canonical_hash(item)))

    @field_validator("relationships", "prohibited_relationships", mode="before")
    @classmethod
    def normalize_relationships(cls, value: Any) -> Any:
        if not isinstance(value, (list, tuple)):
            return value
        return tuple(sorted(value, key=lambda item: canonical_hash(item)))

    @field_validator("record_meanings", "prohibited_record_meanings", mode="before")
    @classmethod
    def normalize_meanings(cls, value: Any) -> Any:
        if not isinstance(value, (list, tuple, set, frozenset)):
            return value
        return tuple(sorted(set(value), key=str))

    @model_validator(mode="after")
    def validate_record_meanings(self) -> Self:
        object.__setattr__(self, "beliefs", tuple(sorted(self.beliefs, key=canonical_hash)))
        object.__setattr__(self, "relationships", tuple(sorted(self.relationships, key=canonical_hash)))
        object.__setattr__(
            self,
            "prohibited_relationships",
            tuple(sorted(self.prohibited_relationships, key=canonical_hash)),
        )
        expected = set(self.record_meanings)
        prohibited = set(self.prohibited_record_meanings)
        if expected & prohibited:
            raise ValueError("expected and prohibited record meanings must be disjoint")
        simulated = {StateRecordMeaning.PREDICTION, StateRecordMeaning.SIMULATED_CONSEQUENCE}
        if expected & simulated and StateRecordMeaning.OBSERVED_OUTCOME in expected:
            raise ValueError("a prediction or simulated consequence cannot be represented as an observed outcome")
        groups = {
            "beliefs": self.beliefs,
            "relationships": self.relationships,
            "prohibited_relationships": self.prohibited_relationships,
        }
        hashes_by_group = {name: [canonical_hash(item) for item in items] for name, items in groups.items()}
        for name, hashes in hashes_by_group.items():
            if len(hashes) != len(set(hashes)):
                raise ValueError(f"{name} must not contain duplicate semantic expectations")
        if set(hashes_by_group["relationships"]) & set(hashes_by_group["prohibited_relationships"]):
            raise ValueError("the same relationship cannot be both expected and prohibited")
        return self

    def expectation_hash(self) -> str:
        return canonical_hash(self)

    def judgment_hashes(self) -> tuple[str, ...]:
        materials: list[dict[str, Any]] = []
        materials.extend({"kind": "belief", "value": item.model_dump(mode="json")} for item in self.beliefs)
        materials.extend({"kind": "relationship", "value": item.model_dump(mode="json")} for item in self.relationships)
        materials.extend(
            {"kind": "prohibited_relationship", "value": item.model_dump(mode="json")}
            for item in self.prohibited_relationships
        )
        materials.extend(
            (
                {
                    "kind": "transition_hypothesis",
                    "value": self.transition_hypothesis.model_dump(mode="json"),
                },
                {
                    "kind": "consequence_rollout",
                    "value": self.consequence_rollout.model_dump(mode="json"),
                },
                {
                    "kind": "record_meaning_boundary",
                    "value": {
                        "expected": self.record_meanings,
                        "prohibited": self.prohibited_record_meanings,
                    },
                },
            )
        )
        return tuple(
            sorted(
                canonical_hash(
                    {
                        "expectation_contract_version": self.contract_version,
                        **material,
                    }
                )
                for material in materials
            )
        )


class TemporalReferenceCaseV1(FrozenContract):
    contract_version: Literal["ace.grounded-state.temporal-reference-case/v1"] = TEMPORAL_REFERENCE_CASE_VERSION
    case_key: str
    primary_category: ReferenceCategory
    categories: tuple[ReferenceCategory, ...] = Field(min_length=1, max_length=len(ReferenceCategory))
    product_ids: tuple[str, ...] = Field(min_length=1, max_length=8)
    evidence: tuple[ReferenceEvidenceV1, ...] = Field(min_length=1, max_length=20)
    as_of_times: tuple[datetime, ...] = Field(min_length=1, max_length=20)
    expected: ExpectedSemanticsV1
    rationale: str = Field(min_length=1, max_length=4_000)
    review: ReviewDispositionV1

    @field_validator("case_key")
    @classmethod
    def validate_case_key(cls, value: str) -> str:
        if not _CASE_KEY.fullmatch(value):
            raise ValueError("case_key must be a bounded lowercase stable key")
        return value

    @field_validator("categories", mode="before")
    @classmethod
    def normalize_categories(cls, value: Any) -> Any:
        if not isinstance(value, (list, tuple, set, frozenset)):
            return value
        return tuple(sorted(set(value), key=str))

    @field_validator("product_ids", mode="before")
    @classmethod
    def normalize_product_ids(cls, value: Any) -> tuple[str, ...]:
        product_ids = _normalized_strings(value, name="product_ids", limit=8)
        if any(not product_id.startswith("product:") for product_id in product_ids):
            raise ValueError("product_ids must contain product-scoped identifiers")
        return product_ids

    @field_validator("evidence", mode="before")
    @classmethod
    def normalize_evidence_arrival_order(cls, value: Any) -> Any:
        if not isinstance(value, (list, tuple)):
            return value

        def input_key(item: Any) -> str:
            if isinstance(item, ReferenceEvidenceV1):
                return item.input_key
            if isinstance(item, dict):
                return str(item.get("input_key", ""))
            return ""

        return tuple(sorted(value, key=input_key))

    @field_validator("as_of_times", mode="before")
    @classmethod
    def normalize_as_of_times(cls, value: Any) -> Any:
        if not isinstance(value, (list, tuple, set, frozenset)):
            return value
        return tuple(sorted(set(value)))

    @model_validator(mode="after")
    def validate_case(self) -> Self:
        if self.primary_category not in self.categories:
            raise ValueError("primary_category must be included in categories")
        input_keys = [item.input_key for item in self.evidence]
        if len(input_keys) != len(set(input_keys)):
            raise ValueError("evidence input keys must be unique within a case")
        record_products = {item.record.product_id for item in self.evidence}
        if record_products != set(self.product_ids):
            raise ValueError("product_ids must exactly describe the products present in case evidence")
        if ReferenceCategory.CROSS_PRODUCT_ISOLATION in self.categories and len(self.product_ids) < 2:
            raise ValueError("cross-product isolation cases require at least two product scopes")

        known_keys = set(input_keys)
        evidence_by_key = {item.input_key: item.record for item in self.evidence}
        referenced_keys: set[str] = set()
        for belief in self.expected.beliefs:
            if belief.product_id not in self.product_ids:
                raise ValueError("belief expectation product_id must belong to the case product scopes")
            referenced_keys.update(belief.supporting_evidence_keys)
            referenced_keys.update(belief.contradicting_evidence_keys)
            for evidence_key in (*belief.supporting_evidence_keys, *belief.contradicting_evidence_keys):
                record = evidence_by_key.get(evidence_key)
                if record is not None and record.ingested_at > belief.as_of:
                    raise ValueError("belief expectations cannot cite evidence ingested after their as_of cutoff")
        for relationship in (*self.expected.relationships, *self.expected.prohibited_relationships):
            referenced_keys.update(relationship.supporting_evidence_keys)
            for endpoint in (relationship.subject, relationship.object):
                if endpoint is None:
                    continue
                if endpoint.product_id not in self.product_ids:
                    raise ValueError("relationship endpoint product_id must belong to the case product scopes")
                if endpoint.kind is RelationshipEndpointKind.EVIDENCE:
                    referenced_keys.add(endpoint.identity)
        if unknown_keys := referenced_keys - known_keys:
            raise ValueError(f"expected semantics reference unknown evidence keys: {sorted(unknown_keys)}")

        latest_as_of = max(self.as_of_times)
        for relationship in (*self.expected.relationships, *self.expected.prohibited_relationships):
            if any(evidence_by_key[key].ingested_at > latest_as_of for key in relationship.supporting_evidence_keys):
                raise ValueError("relationship expectations cannot cite evidence unavailable at every case as_of time")

        for relationship in self.expected.relationships:
            endpoints = (relationship.subject, relationship.object)
            if relationship.classification is RelationshipClassification.EXACT_REPLAY:
                if endpoints[1] is None or any(
                    endpoint.kind is not RelationshipEndpointKind.EVIDENCE for endpoint in endpoints if endpoint
                ):
                    raise ValueError("exact replay requires two evidence endpoints")
                left = evidence_by_key[relationship.subject.identity]
                right = evidence_by_key[relationship.object.identity]
                if (
                    relationship.subject.identity == relationship.object.identity
                    or left.evidence_id() != right.evidence_id()
                ):
                    raise ValueError("exact replay endpoints must be distinct inputs with one evidence identity")
            if relationship.classification is RelationshipClassification.SOURCE_VERSION_REPLACEMENT:
                if endpoints[1] is None or any(
                    endpoint.kind is not RelationshipEndpointKind.EVIDENCE for endpoint in endpoints if endpoint
                ):
                    raise ValueError("source-version replacement requires two evidence endpoints")
                replacement = evidence_by_key[relationship.subject.identity]
                prior = evidence_by_key[relationship.object.identity]
                same_source_item = (
                    replacement.product_id == prior.product_id
                    and replacement.source_id == prior.source_id
                    and replacement.external_id == prior.external_id
                    and replacement.source_version != prior.source_version
                )
                if not same_source_item or prior.evidence_id() not in replacement.supersedes:
                    raise ValueError(
                        "source-version replacement must bind a new version to the superseded evidence identity"
                    )

        expected_times = {belief.as_of for belief in self.expected.beliefs}
        if expected_times != set(self.as_of_times):
            raise ValueError("as_of_times must exactly match the belief expectation as-of times")
        requires_maintainer_review = (
            self.case_key in REQUIRED_MAINTAINER_REVIEW_CASE_KEYS
            or self.expected.transition_hypothesis.state is EligibilityState.REQUIRES_HUMAN_REVIEW
            or any(
                relationship.classification is RelationshipClassification.CAUSES
                for relationship in self.expected.relationships
            )
        )
        if requires_maintainer_review and self.review.requirement is not ReviewRequirement.MAINTAINER_ADJUDICATION:
            raise ValueError("review-sensitive expectations require maintainer adjudication")
        if self.review.status is ReviewStatus.COMPLETED:
            if self.review.reviewed_expectation_hash != self.expected.expectation_hash():
                raise ValueError("completed review must bind the exact expected-semantics hash")
            reviewed_hashes = {judgment.judgment_hash for judgment in self.review.judgments}
            if reviewed_hashes != set(self.expected.judgment_hashes()):
                raise ValueError("completed review must disposition every current expectation judgment")
        return self

    def case_hash(self) -> str:
        return canonical_hash(self)

    def case_id(self) -> str:
        return stable_id("temporal_reference_case", self)


class TemporalReferenceCorpusV1(FrozenContract):
    contract_version: Literal["ace.grounded-state.temporal-reference-corpus/v1"] = TEMPORAL_REFERENCE_CORPUS_VERSION
    name: str = Field(min_length=1, max_length=200)
    maturity: CorpusMaturity
    purpose: str = Field(min_length=1, max_length=2_000)
    required_categories: tuple[ReferenceCategory, ...] = Field(
        default_factory=lambda: tuple(sorted(REQUIRED_REFERENCE_CATEGORIES, key=str)),
        min_length=1,
        max_length=len(ReferenceCategory),
    )
    required_review_case_keys: tuple[str, ...] = Field(
        default_factory=lambda: tuple(sorted(REQUIRED_MAINTAINER_REVIEW_CASE_KEYS)),
        min_length=1,
        max_length=100,
    )
    cases: tuple[TemporalReferenceCaseV1, ...] = Field(min_length=1, max_length=100)

    @field_validator("required_categories", mode="before")
    @classmethod
    def normalize_required_categories(cls, value: Any) -> Any:
        if not isinstance(value, (list, tuple, set, frozenset)):
            return value
        return tuple(sorted(set(value), key=str))

    @field_validator("required_review_case_keys", mode="before")
    @classmethod
    def normalize_required_review_case_keys(cls, value: Any) -> tuple[str, ...]:
        return _normalized_strings(value, name="required_review_case_keys", limit=100)

    @field_validator("cases", mode="before")
    @classmethod
    def normalize_case_order(cls, value: Any) -> Any:
        if not isinstance(value, (list, tuple)):
            return value

        def case_key(item: Any) -> str:
            if isinstance(item, TemporalReferenceCaseV1):
                return item.case_key
            if isinstance(item, dict):
                return str(item.get("case_key", ""))
            return ""

        return tuple(sorted(value, key=case_key))

    @model_validator(mode="after")
    def validate_maturity(self) -> Self:
        if set(self.required_review_case_keys) != REQUIRED_MAINTAINER_REVIEW_CASE_KEYS:
            raise ValueError("required_review_case_keys must match the versioned TP0 review policy")
        case_by_key = {case.case_key: case for case in self.cases}
        missing_review_cases = set(self.required_review_case_keys) - set(case_by_key)
        if missing_review_cases:
            raise ValueError(f"required maintainer-review cases are missing: {sorted(missing_review_cases)}")
        incorrectly_declared = [
            key
            for key in self.required_review_case_keys
            if case_by_key[key].review.requirement is not ReviewRequirement.MAINTAINER_ADJUDICATION
        ]
        if incorrectly_declared:
            raise ValueError("versioned subjective cases must require maintainer adjudication")
        if self.maturity is CorpusMaturity.FROZEN:
            incomplete = [
                key
                for key in self.required_review_case_keys
                if case_by_key[key].review.status is not ReviewStatus.COMPLETED
            ]
            if incomplete:
                raise ValueError("a frozen corpus cannot contain incomplete maintainer adjudication")
            rejected = [
                case.case_key
                for case in self.cases
                if any(judgment.decision is ReviewDecision.REJECTED for judgment in case.review.judgments)
            ]
            if rejected:
                raise ValueError("a frozen corpus cannot contain rejected expectation judgments")
        return self

    def category_counts(self) -> dict[str, int]:
        counts = {category.value: 0 for category in ReferenceCategory}
        for case in self.cases:
            for category in case.categories:
                counts[category.value] += 1
        return {key: value for key, value in counts.items() if value}

    def corpus_hash(self) -> str:
        return canonical_hash(
            {
                "contract_version": self.contract_version,
                "maturity": self.maturity.value,
                "required_categories": [category.value for category in self.required_categories],
                "required_review_case_keys": list(self.required_review_case_keys),
                "cases": [case.model_dump(mode="json") for case in self.cases],
            }
        )

    def corpus_id(self) -> str:
        return f"temporal_reference_corpus:{self.corpus_hash()[:32]}"
