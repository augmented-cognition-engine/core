"""Immutable TP5 contracts for inspectable world-dynamics hypotheses.

Transition hypotheses remain separate from evidence, belief projections,
predictions, and observed outcomes.  Deterministic Core code owns product
scope, identity, lifecycle, and rule execution; models may only propose
bounded material.
"""

from __future__ import annotations

import math
from datetime import datetime
from enum import StrEnum
from typing import Any, Literal, Self

from pydantic import Field, field_validator, model_validator

from core.engine.grounded_state.belief_contracts import (
    MAX_PACK_RECORDS,
    MAX_REASONS,
    ProviderUsageV1,
    ReviewAuthority,
    TypedEvidenceEndpointV1,
    _aware,
    _product,
    _refs,
)
from core.engine.grounded_state.contracts import (
    MAX_REFS,
    CausalStrength,
    FrozenContract,
    ProbabilityEstimateV1,
    StateValue,
    SupportingEvidenceOriginV1,
    TransitionReviewState,
    canonical_hash,
    stable_id,
)

TRANSITION_PROPOSAL_VERSION = "ace.grounded-state.transition-proposal/v1"
TRANSITION_CHALLENGE_VERSION = "ace.grounded-state.transition-challenge/v1"
TRANSITION_REVIEW_VERSION = "ace.grounded-state.transition-review/v1"
TRANSITION_REVISION_VERSION = "ace.grounded-state.transition-revision/v1"
TRANSITION_BRANCH_INPUT_VERSION = "ace.grounded-state.transition-branch-input/v1"
TRANSITION_OUTCOME_VERSION = "ace.grounded-state.transition-outcome/v1"
TRANSITION_CALIBRATION_VERSION = "ace.grounded-state.transition-calibration/v1"

TP5_ONTOLOGY_VERSION = "ace.grounded-state.transition-ontology/v1"
TP5_RESOLVER_POLICY_VERSION = "ace.grounded-state.transition-resolver/v1"
TP5_CHALLENGE_POLICY_VERSION = "ace.grounded-state.transition-challenge/v1"
TP5_CALIBRATION_POLICY_VERSION = "ace.grounded-state.transition-calibration/v1"

MAX_TRANSITION_RULES = 50
MAX_TRANSITION_HYPOTHESES = 100


class StateValueType(StrEnum):
    BOOLEAN = "boolean"
    INTEGER = "integer"
    NUMBER = "number"
    STRING = "string"
    CATEGORICAL = "categorical"


class ConditionOperator(StrEnum):
    EQ = "eq"
    NE = "ne"
    GT = "gt"
    GTE = "gte"
    LT = "lt"
    LTE = "lte"
    IN = "in"
    NOT_IN = "not_in"
    EXISTS = "exists"
    ABSENT = "absent"


class TransitionRuleKind(StrEnum):
    PRECONDITION = "precondition"
    CONSTRAINT = "constraint"


class TransitionTriggerKind(StrEnum):
    ACTION = "action"
    EVENT = "event"
    STATE_CHANGE = "state_change"
    DOMAIN_RULE = "domain_rule"


class TransitionDerivationRoute(StrEnum):
    TEMPORAL_SEQUENCE = "temporal_sequence"
    ACCEPTED_MECHANISM = "accepted_mechanism"
    DOMAIN_RULE = "domain_rule"
    EXTENSION_DYNAMICS = "extension_dynamics"
    HUMAN_AUTHORED = "human_authored"
    MODEL_PROPOSED = "model_proposed"


class TransitionOutcomeDisposition(StrEnum):
    MATCHED = "matched"
    CONTRADICTED = "contradicted"
    MIXED = "mixed"
    UNRESOLVED = "unresolved"
    OUT_OF_SCOPE = "out_of_scope"


def _value_matches(value: StateValue, value_type: StateValueType) -> bool:
    if value_type is StateValueType.BOOLEAN:
        return isinstance(value, bool)
    if value_type is StateValueType.INTEGER:
        return isinstance(value, int) and not isinstance(value, bool)
    if value_type is StateValueType.NUMBER:
        return isinstance(value, (int, float)) and not isinstance(value, bool) and math.isfinite(float(value))
    if value_type in {StateValueType.STRING, StateValueType.CATEGORICAL}:
        return isinstance(value, str) and bool(value.strip())
    return False


class StateVariableV1(FrozenContract):
    subject: TypedEvidenceEndpointV1
    predicate: str = Field(min_length=1, max_length=160)
    value_type: StateValueType
    unit: str | None = Field(default=None, min_length=1, max_length=120)
    allowed_values: tuple[StateValue, ...] = Field(default_factory=tuple, max_length=100)
    minimum: float | None = None
    maximum: float | None = None

    @field_validator("allowed_values", mode="before")
    @classmethod
    def normalize_values(cls, value: Any) -> tuple[Any, ...]:
        if value is None:
            return ()
        if not isinstance(value, (list, tuple, set, frozenset)):
            raise ValueError("allowed_values must be a bounded collection")
        return tuple(sorted(set(value), key=canonical_hash))

    @model_validator(mode="after")
    def validate_domain(self) -> Self:
        if self.minimum is not None and not math.isfinite(self.minimum):
            raise ValueError("state variable minimum must be finite")
        if self.maximum is not None and not math.isfinite(self.maximum):
            raise ValueError("state variable maximum must be finite")
        if self.minimum is not None and self.maximum is not None and self.maximum < self.minimum:
            raise ValueError("state variable maximum must not precede minimum")
        numeric = self.value_type in {StateValueType.INTEGER, StateValueType.NUMBER}
        if not numeric and (self.minimum is not None or self.maximum is not None or self.unit is not None):
            raise ValueError("bounds and units are reserved for numeric state variables")
        if self.allowed_values and self.value_type is not StateValueType.CATEGORICAL:
            raise ValueError("allowed_values are reserved for categorical state variables")
        if self.value_type is StateValueType.CATEGORICAL and not self.allowed_values:
            raise ValueError("categorical state variables require an explicit bounded domain")
        if any(not _value_matches(item, self.value_type) for item in self.allowed_values):
            raise ValueError("allowed values must match the declared state value type")
        return self

    def variable_id(self) -> str:
        return stable_id("state_variable", self)


class StateConditionV1(FrozenContract):
    variable: StateVariableV1
    operator: ConditionOperator
    value: StateValue = None

    @model_validator(mode="after")
    def validate_condition(self) -> Self:
        existence = self.operator in {ConditionOperator.EXISTS, ConditionOperator.ABSENT}
        if existence and self.value is not None:
            raise ValueError("existence conditions cannot carry a comparison value")
        if not existence and self.value is None:
            raise ValueError("comparison conditions require a value")
        if self.operator in {ConditionOperator.IN, ConditionOperator.NOT_IN}:
            if not isinstance(self.value, list) or not self.value:
                raise ValueError("membership conditions require a non-empty value list")
            if any(not _value_matches(item, self.variable.value_type) for item in self.value):
                raise ValueError("membership values must match the state variable type")
        elif not existence and not _value_matches(self.value, self.variable.value_type):
            raise ValueError("condition value must match the state variable type")
        if self.operator in {ConditionOperator.GT, ConditionOperator.GTE, ConditionOperator.LT, ConditionOperator.LTE}:
            if self.variable.value_type not in {StateValueType.INTEGER, StateValueType.NUMBER}:
                raise ValueError("ordered comparisons require a numeric state variable")
        return self


class StateAssignmentV1(FrozenContract):
    variable: StateVariableV1
    value: StateValue

    @model_validator(mode="after")
    def validate_assignment(self) -> Self:
        if not _value_matches(self.value, self.variable.value_type):
            raise ValueError("assigned value must match the state variable type")
        if self.variable.allowed_values and self.value not in self.variable.allowed_values:
            raise ValueError("assigned value is outside the declared categorical domain")
        if isinstance(self.value, (int, float)) and not isinstance(self.value, bool):
            numeric = float(self.value)
            if self.variable.minimum is not None and numeric < self.variable.minimum:
                raise ValueError("assigned value violates the variable minimum")
            if self.variable.maximum is not None and numeric > self.variable.maximum:
                raise ValueError("assigned value violates the variable maximum")
        return self


class TransitionRuleV1(FrozenContract):
    rule_id: str | None = None
    kind: TransitionRuleKind
    condition: StateConditionV1
    rationale: str = Field(min_length=1, max_length=1_000)
    rule_source_ref: str = Field(min_length=1, max_length=240)

    @model_validator(mode="after")
    def derive_identity(self) -> Self:
        expected = stable_id("transition_rule", self.model_dump(mode="json", exclude={"rule_id"}))
        if self.rule_id is not None and self.rule_id != expected:
            raise ValueError("transition rule identity does not match deterministic material")
        object.__setattr__(self, "rule_id", expected)
        return self


class TransitionTriggerV1(FrozenContract):
    kind: TransitionTriggerKind
    description: str = Field(min_length=1, max_length=1_000)
    trigger_ref: str = Field(min_length=1, max_length=240)


class TransitionHypothesisProposalV1(FrozenContract):
    contract_version: Literal["ace.grounded-state.transition-proposal/v1"] = TRANSITION_PROPOSAL_VERSION
    proposal_id: str | None = None
    product_id: str
    projection_id: str = Field(min_length=1, max_length=240)
    projection_hash: str = Field(pattern=r"^[a-f0-9]{64}$")
    projection_entry_refs: tuple[str, ...] = Field(min_length=1, max_length=MAX_REFS)
    evidence_pack_id: str = Field(min_length=1, max_length=240)
    evidence_pack_hash: str = Field(pattern=r"^[a-f0-9]{64}$")
    as_of: datetime
    source: StateConditionV1
    target: StateAssignmentV1
    trigger: TransitionTriggerV1
    mechanism: str | None = Field(default=None, min_length=1, max_length=2_000)
    rules: tuple[TransitionRuleV1, ...] = Field(default_factory=tuple, max_length=MAX_TRANSITION_RULES)
    delay_min_seconds: int = Field(ge=0)
    delay_max_seconds: int = Field(ge=0)
    probability: ProbabilityEstimateV1
    causal_strength: CausalStrength
    derivation_routes: tuple[TransitionDerivationRoute, ...] = Field(min_length=1, max_length=10)
    supporting_evidence_refs: tuple[str, ...] = Field(default_factory=tuple, max_length=MAX_PACK_RECORDS)
    contrary_evidence_refs: tuple[str, ...] = Field(default_factory=tuple, max_length=MAX_PACK_RECORDS)
    supporting_assertion_refs: tuple[str, ...] = Field(default_factory=tuple, max_length=MAX_REFS)
    supporting_evidence_origins: tuple[SupportingEvidenceOriginV1, ...] = Field(
        default_factory=tuple,
        max_length=MAX_PACK_RECORDS,
    )
    proposer_authority: ReviewAuthority
    proposer_ref: str = Field(min_length=1, max_length=240)
    ontology_version: str = Field(default=TP5_ONTOLOGY_VERSION, min_length=1, max_length=160)
    resolver_policy_version: str = Field(default=TP5_RESOLVER_POLICY_VERSION, min_length=1, max_length=160)
    model_version: str | None = Field(default=None, max_length=200)
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

    @field_validator("rules", "supporting_evidence_origins", mode="before")
    @classmethod
    def normalize_models(cls, value: Any) -> tuple[Any, ...]:
        if not isinstance(value, (list, tuple)):
            raise ValueError("transition rules and origins must be bounded collections")
        return tuple(sorted(value, key=canonical_hash))

    @field_validator(
        "projection_entry_refs",
        "supporting_evidence_refs",
        "contrary_evidence_refs",
        "supporting_assertion_refs",
        "omissions",
        "failures",
        "degraded_reasons",
        mode="before",
    )
    @classmethod
    def normalize_refs(cls, value: Any, info) -> tuple[str, ...]:
        if info.field_name in {"omissions", "failures", "degraded_reasons"}:
            limit = MAX_REASONS
        elif info.field_name.endswith("evidence_refs"):
            limit = MAX_PACK_RECORDS
        else:
            limit = MAX_REFS
        return _refs(value, limit=limit, name=info.field_name)

    @field_validator("derivation_routes", mode="before")
    @classmethod
    def normalize_routes(cls, value: Any) -> tuple[Any, ...]:
        if not isinstance(value, (list, tuple, set, frozenset)):
            raise ValueError("derivation routes must be a bounded collection")
        return tuple(sorted(set(value)))

    @model_validator(mode="after")
    def derive_identity(self) -> Self:
        if self.delay_max_seconds < self.delay_min_seconds:
            raise ValueError("transition maximum delay must not precede minimum delay")
        variables = [self.source.variable, self.target.variable, *(rule.condition.variable for rule in self.rules)]
        if any(variable.subject.product_id != self.product_id for variable in variables):
            raise ValueError("transition state variables cannot cross product scope")
        if self.source.variable == self.target.variable and self.source.operator is ConditionOperator.EQ:
            if self.source.value == self.target.value:
                raise ValueError("a transition must change state")
        support = set(self.supporting_evidence_refs)
        contrary = set(self.contrary_evidence_refs)
        if support & contrary:
            raise ValueError("supporting and contrary transition evidence must be disjoint")
        origin_refs = [origin.evidence_ref for origin in self.supporting_evidence_origins]
        if len(origin_refs) != len(set(origin_refs)) or set(origin_refs) - support:
            raise ValueError("source-origin bindings must uniquely identify supporting evidence")
        if self.causal_strength in {CausalStrength.MECHANISTIC, CausalStrength.CAUSAL} and not self.mechanism:
            raise ValueError("mechanistic and causal proposals require an inspectable mechanism")
        material = self.model_dump(mode="json", exclude={"proposal_id"})
        expected = stable_id("grounded_transition_proposal", material)
        if self.proposal_id is not None and self.proposal_id != expected:
            raise ValueError("transition proposal identity does not match deterministic material")
        object.__setattr__(self, "proposal_id", expected)
        return self

    def hypothesis_id(self) -> str:
        return stable_id(
            "grounded_transition",
            {
                "contract_version": TRANSITION_REVISION_VERSION,
                "product_id": self.product_id,
                "source": self.source.model_dump(mode="json"),
                "target": self.target.model_dump(mode="json"),
                "trigger": self.trigger.model_dump(mode="json"),
                "mechanism": self.mechanism,
                "rules": [rule.model_dump(mode="json") for rule in self.rules],
                "delay_min_seconds": self.delay_min_seconds,
                "delay_max_seconds": self.delay_max_seconds,
                "ontology_version": self.ontology_version,
            },
        )

    def review_material_hash(self) -> str:
        return canonical_hash(self.model_dump(mode="json", exclude={"proposal_id"}))


class TransitionChallengeReceiptV1(FrozenContract):
    contract_version: Literal["ace.grounded-state.transition-challenge/v1"] = TRANSITION_CHALLENGE_VERSION
    receipt_id: str | None = None
    receipt_hash: str | None = None
    product_id: str
    proposal_id: str = Field(min_length=1, max_length=240)
    proposal_material_hash: str = Field(pattern=r"^[a-f0-9]{64}$")
    hypothesis_id: str = Field(min_length=1, max_length=240)
    projection_id: str = Field(min_length=1, max_length=240)
    projection_hash: str = Field(pattern=r"^[a-f0-9]{64}$")
    evidence_pack_id: str = Field(min_length=1, max_length=240)
    evidence_pack_hash: str = Field(pattern=r"^[a-f0-9]{64}$")
    as_of: datetime
    searched_evidence_refs: tuple[str, ...] = Field(default_factory=tuple, max_length=MAX_PACK_RECORDS)
    supporting_evidence_refs: tuple[str, ...] = Field(default_factory=tuple, max_length=MAX_PACK_RECORDS)
    contrary_evidence_refs: tuple[str, ...] = Field(default_factory=tuple, max_length=MAX_PACK_RECORDS)
    missing_inputs: tuple[str, ...] = Field(default_factory=tuple, max_length=MAX_REASONS)
    max_records: int = Field(ge=1, le=MAX_PACK_RECORDS)
    pack_selected_count: int = Field(ge=0, le=MAX_PACK_RECORDS)
    records_searched: int = Field(ge=0, le=MAX_PACK_RECORDS)
    index_versions: dict[str, str] = Field(default_factory=dict)
    completed: bool
    policy_version: str = Field(default=TP5_CHALLENGE_POLICY_VERSION, min_length=1, max_length=160)
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

    @field_validator(
        "searched_evidence_refs",
        "supporting_evidence_refs",
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
        searched = set(self.searched_evidence_refs)
        if self.records_searched != len(searched):
            raise ValueError("transition challenge searched count must reconcile exact references")
        if set(self.supporting_evidence_refs) - searched or set(self.contrary_evidence_refs) - searched:
            raise ValueError("transition support and challenge evidence must come from the searched set")
        incomplete = self.missing_inputs or self.omissions or self.fallbacks or self.failures or self.degraded_reasons
        if self.completed and (incomplete or self.records_searched != self.pack_selected_count):
            raise ValueError("a completed transition challenge cannot hide incomplete or degraded inputs")
        material = self.model_dump(mode="json", exclude={"receipt_id", "receipt_hash"})
        expected_hash = canonical_hash(material)
        expected_id = f"grounded_transition_challenge:{expected_hash[:32]}"
        if self.receipt_hash is not None and self.receipt_hash != expected_hash:
            raise ValueError("transition challenge hash does not match deterministic material")
        if self.receipt_id is not None and self.receipt_id != expected_id:
            raise ValueError("transition challenge identity does not match deterministic material")
        object.__setattr__(self, "receipt_hash", expected_hash)
        object.__setattr__(self, "receipt_id", expected_id)
        return self


class TransitionReviewV1(FrozenContract):
    contract_version: Literal["ace.grounded-state.transition-review/v1"] = TRANSITION_REVIEW_VERSION
    review_id: str | None = None
    product_id: str
    proposal_id: str = Field(min_length=1, max_length=240)
    hypothesis_id: str = Field(min_length=1, max_length=240)
    reviewed_material_hash: str = Field(pattern=r"^[a-f0-9]{64}$")
    challenge_receipt_id: str = Field(min_length=1, max_length=240)
    challenge_receipt_hash: str = Field(pattern=r"^[a-f0-9]{64}$")
    disposition: TransitionReviewState
    authority: ReviewAuthority
    reviewer_ref: str = Field(min_length=1, max_length=240)
    reviewed_at: datetime
    rationale: str = Field(min_length=1, max_length=2_000)
    policy_version: str = Field(default=TP5_RESOLVER_POLICY_VERSION, min_length=1, max_length=160)
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
        if self.authority is ReviewAuthority.MODEL and self.disposition is not TransitionReviewState.PROPOSED:
            raise ValueError("model authority may propose transition material but cannot govern its lifecycle")
        material = self.model_dump(mode="json", exclude={"review_id"})
        expected = stable_id("grounded_transition_review", material)
        if self.review_id is not None and self.review_id != expected:
            raise ValueError("transition review identity does not match deterministic material")
        object.__setattr__(self, "review_id", expected)
        return self


class TransitionHypothesisRevisionV1(FrozenContract):
    contract_version: Literal["ace.grounded-state.transition-revision/v1"] = TRANSITION_REVISION_VERSION
    revision_id: str | None = None
    revision_hash: str | None = None
    hypothesis_id: str = Field(min_length=1, max_length=240)
    revision: int = Field(ge=1)
    product_id: str
    proposal_id: str = Field(min_length=1, max_length=240)
    proposal_material_hash: str = Field(pattern=r"^[a-f0-9]{64}$")
    projection_id: str = Field(min_length=1, max_length=240)
    projection_hash: str = Field(pattern=r"^[a-f0-9]{64}$")
    projection_entry_refs: tuple[str, ...] = Field(min_length=1, max_length=MAX_REFS)
    evidence_pack_id: str = Field(min_length=1, max_length=240)
    evidence_pack_hash: str = Field(pattern=r"^[a-f0-9]{64}$")
    as_of: datetime
    source: StateConditionV1
    target: StateAssignmentV1
    trigger: TransitionTriggerV1
    mechanism: str | None = Field(default=None, min_length=1, max_length=2_000)
    rules: tuple[TransitionRuleV1, ...] = Field(default_factory=tuple, max_length=MAX_TRANSITION_RULES)
    delay_min_seconds: int = Field(ge=0)
    delay_max_seconds: int = Field(ge=0)
    probability: ProbabilityEstimateV1
    causal_strength: CausalStrength
    derivation_routes: tuple[TransitionDerivationRoute, ...] = Field(min_length=1, max_length=10)
    supporting_evidence_refs: tuple[str, ...] = Field(default_factory=tuple, max_length=MAX_PACK_RECORDS)
    contrary_evidence_refs: tuple[str, ...] = Field(default_factory=tuple, max_length=MAX_PACK_RECORDS)
    supporting_assertion_refs: tuple[str, ...] = Field(default_factory=tuple, max_length=MAX_REFS)
    supporting_evidence_origins: tuple[SupportingEvidenceOriginV1, ...] = Field(
        default_factory=tuple,
        max_length=MAX_PACK_RECORDS,
    )
    challenge_receipt_id: str = Field(min_length=1, max_length=240)
    challenge_receipt_hash: str = Field(pattern=r"^[a-f0-9]{64}$")
    challenge_completed: bool
    review_id: str = Field(min_length=1, max_length=240)
    review_state: TransitionReviewState
    review_authority: ReviewAuthority
    rollout_eligible: bool
    ontology_version: str = Field(min_length=1, max_length=160)
    resolver_policy_version: str = Field(min_length=1, max_length=160)
    prior_revision_id: str | None = Field(default=None, max_length=240)
    superseded_revision_refs: tuple[str, ...] = Field(default_factory=tuple, max_length=MAX_REFS)
    stale_at: datetime | None = None
    created_at: datetime
    omissions: tuple[str, ...] = Field(default_factory=tuple, max_length=MAX_REASONS)
    failures: tuple[str, ...] = Field(default_factory=tuple, max_length=MAX_REASONS)
    degraded_reasons: tuple[str, ...] = Field(default_factory=tuple, max_length=MAX_REASONS)
    provider_usage: ProviderUsageV1 = Field(default_factory=ProviderUsageV1)

    @field_validator("product_id")
    @classmethod
    def validate_product(cls, value: str) -> str:
        return _product(value)

    @field_validator("as_of", "stale_at", "created_at")
    @classmethod
    def validate_times(cls, value: datetime | None, info) -> datetime | None:
        return _aware(value, info.field_name) if value is not None else None

    @field_validator("rules", "supporting_evidence_origins", mode="before")
    @classmethod
    def normalize_models(cls, value: Any) -> tuple[Any, ...]:
        if not isinstance(value, (list, tuple)):
            raise ValueError("transition rules and origins must be bounded collections")
        return tuple(sorted(value, key=canonical_hash))

    @field_validator("derivation_routes", mode="before")
    @classmethod
    def normalize_routes(cls, value: Any) -> tuple[Any, ...]:
        if not isinstance(value, (list, tuple, set, frozenset)):
            raise ValueError("derivation routes must be a bounded collection")
        return tuple(sorted(set(value)))

    @field_validator(
        "projection_entry_refs",
        "supporting_evidence_refs",
        "contrary_evidence_refs",
        "supporting_assertion_refs",
        "superseded_revision_refs",
        "omissions",
        "failures",
        "degraded_reasons",
        mode="before",
    )
    @classmethod
    def normalize_refs(cls, value: Any, info) -> tuple[str, ...]:
        if info.field_name in {"omissions", "failures", "degraded_reasons"}:
            limit = MAX_REASONS
        elif info.field_name.endswith("evidence_refs"):
            limit = MAX_PACK_RECORDS
        else:
            limit = MAX_REFS
        return _refs(value, limit=limit, name=info.field_name)

    @model_validator(mode="after")
    def validate_revision(self) -> Self:
        variables = [self.source.variable, self.target.variable, *(rule.condition.variable for rule in self.rules)]
        if any(variable.subject.product_id != self.product_id for variable in variables):
            raise ValueError("transition revision variables cannot cross product scope")
        if self.delay_max_seconds < self.delay_min_seconds:
            raise ValueError("transition maximum delay must not precede minimum delay")
        if self.revision == 1 and self.prior_revision_id is not None:
            raise ValueError("the first transition revision cannot name a prior revision")
        if self.revision > 1 and self.prior_revision_id is None:
            raise ValueError("later transition revisions must retain exact prior revision lineage")
        support = set(self.supporting_evidence_refs)
        contrary = set(self.contrary_evidence_refs)
        if support & contrary:
            raise ValueError("supporting and contrary transition evidence must be disjoint")
        if self.review_state is TransitionReviewState.ACCEPTED and not support:
            raise ValueError("accepted transition hypotheses require supporting evidence")
        if self.review_state is TransitionReviewState.CONTESTED and not contrary:
            raise ValueError("contested transition hypotheses require visible contrary evidence")
        if self.review_state is TransitionReviewState.STALE and self.stale_at is None:
            raise ValueError("stale transition hypotheses require an explicit stale time")
        if self.review_state is not TransitionReviewState.STALE and self.stale_at is not None:
            raise ValueError("stale_at is reserved for stale transition hypotheses")
        if self.review_state is TransitionReviewState.SUPERSEDED and not self.superseded_revision_refs:
            raise ValueError("superseded transition hypotheses require exact supersession lineage")
        eligible_state = self.review_state in {TransitionReviewState.PROVISIONAL, TransitionReviewState.ACCEPTED}
        eligible_strength = self.causal_strength in {CausalStrength.MECHANISTIC, CausalStrength.CAUSAL}
        clean = not (contrary or self.omissions or self.failures or self.degraded_reasons)
        if self.rollout_eligible != bool(eligible_state and eligible_strength and self.challenge_completed and clean):
            raise ValueError("rollout eligibility must fail closed from review, challenge, strength, and degradation")
        if self.causal_strength is CausalStrength.CAUSAL and self.review_state is TransitionReviewState.ACCEPTED:
            source_refs = {origin.source_ref for origin in self.supporting_evidence_origins}
            origin_groups = {origin.origin_group for origin in self.supporting_evidence_origins}
            origin_evidence = {origin.evidence_ref for origin in self.supporting_evidence_origins}
            if (
                self.review_authority is not ReviewAuthority.HUMAN
                or not self.challenge_completed
                or len(support) < 2
                or origin_evidence != support
                or len(source_refs) < 2
                or len(origin_groups) < 2
            ):
                raise ValueError(
                    "accepted causal transitions require exact human review, complete challenge, and independent sources"
                )
        material = self.model_dump(mode="json", exclude={"revision_id", "revision_hash"})
        expected_hash = canonical_hash(material)
        expected_id = f"grounded_transition_revision:{expected_hash[:32]}"
        if self.revision_hash is not None and self.revision_hash != expected_hash:
            raise ValueError("transition revision hash does not match deterministic material")
        if self.revision_id is not None and self.revision_id != expected_id:
            raise ValueError("transition revision identity does not match deterministic material")
        object.__setattr__(self, "revision_hash", expected_hash)
        object.__setattr__(self, "revision_id", expected_id)
        return self


class StateSnapshotV1(FrozenContract):
    entry_id: str = Field(min_length=1, max_length=240)
    subject: TypedEvidenceEndpointV1
    predicate: str = Field(min_length=1, max_length=160)
    value: StateValue = None
    status: str = Field(min_length=1, max_length=40)

    def variable_key(self) -> tuple[str, str]:
        return self.subject.record_id, self.predicate


class RuleEvaluationV1(FrozenContract):
    rule_id: str = Field(min_length=1, max_length=240)
    kind: TransitionRuleKind
    actual_value: StateValue = None
    satisfied: bool | None
    reason: str = Field(min_length=1, max_length=1_000)


class TransitionBranchInputV1(FrozenContract):
    contract_version: Literal["ace.grounded-state.transition-branch-input/v1"] = TRANSITION_BRANCH_INPUT_VERSION
    input_id: str | None = None
    input_hash: str | None = None
    product_id: str
    hypothesis_id: str = Field(min_length=1, max_length=240)
    transition_revision_id: str = Field(min_length=1, max_length=240)
    transition_revision_hash: str = Field(pattern=r"^[a-f0-9]{64}$")
    starting_projection_id: str = Field(min_length=1, max_length=240)
    starting_projection_hash: str = Field(pattern=r"^[a-f0-9]{64}$")
    as_of: datetime
    state_snapshot: tuple[StateSnapshotV1, ...] = Field(default_factory=tuple, max_length=MAX_REFS)
    rule_evaluations: tuple[RuleEvaluationV1, ...] = Field(default_factory=tuple, max_length=MAX_TRANSITION_RULES)
    applicable: bool
    blocked_reasons: tuple[str, ...] = Field(default_factory=tuple, max_length=MAX_REASONS)
    missing_inputs: tuple[str, ...] = Field(default_factory=tuple, max_length=MAX_REASONS)
    degraded_reasons: tuple[str, ...] = Field(default_factory=tuple, max_length=MAX_REASONS)
    policy_version: str = Field(default=TP5_RESOLVER_POLICY_VERSION, min_length=1, max_length=160)

    @field_validator("product_id")
    @classmethod
    def validate_product(cls, value: str) -> str:
        return _product(value)

    @field_validator("as_of")
    @classmethod
    def validate_as_of(cls, value: datetime) -> datetime:
        return _aware(value, "as_of")

    @field_validator("state_snapshot", mode="before")
    @classmethod
    def normalize_snapshot(cls, value: Any) -> tuple[Any, ...]:
        if not isinstance(value, (list, tuple)):
            raise ValueError("state snapshot must be a bounded collection")
        return tuple(
            sorted(
                value,
                key=lambda item: (
                    item.subject.record_id if isinstance(item, StateSnapshotV1) else str(item["subject"]["record_id"]),
                    item.predicate if isinstance(item, StateSnapshotV1) else str(item["predicate"]),
                    item.entry_id if isinstance(item, StateSnapshotV1) else str(item["entry_id"]),
                ),
            )
        )

    @field_validator("rule_evaluations", mode="before")
    @classmethod
    def normalize_evaluations(cls, value: Any) -> tuple[Any, ...]:
        if not isinstance(value, (list, tuple)):
            raise ValueError("rule evaluations must be a bounded collection")
        return tuple(
            sorted(
                value,
                key=lambda item: item.rule_id if isinstance(item, RuleEvaluationV1) else str(item["rule_id"]),
            )
        )

    @field_validator("blocked_reasons", "missing_inputs", "degraded_reasons", mode="before")
    @classmethod
    def normalize_reasons(cls, value: Any, info) -> tuple[str, ...]:
        return _refs(value, limit=MAX_REASONS, name=info.field_name)

    @model_validator(mode="after")
    def derive_identity(self) -> Self:
        if any(item.subject.product_id != self.product_id for item in self.state_snapshot):
            raise ValueError("transition branch inputs cannot cross product scope")
        if self.applicable and (self.blocked_reasons or self.missing_inputs or self.degraded_reasons):
            raise ValueError("an applicable transition branch cannot hide blocked or missing input state")
        material = self.model_dump(mode="json", exclude={"input_id", "input_hash"})
        expected_hash = canonical_hash(material)
        expected_id = f"grounded_transition_input:{expected_hash[:32]}"
        if self.input_hash is not None and self.input_hash != expected_hash:
            raise ValueError("transition branch-input hash does not match deterministic material")
        if self.input_id is not None and self.input_id != expected_id:
            raise ValueError("transition branch-input identity does not match deterministic material")
        object.__setattr__(self, "input_hash", expected_hash)
        object.__setattr__(self, "input_id", expected_id)
        return self


class ObservedTransitionOutcomeV1(FrozenContract):
    contract_version: Literal["ace.grounded-state.transition-outcome/v1"] = TRANSITION_OUTCOME_VERSION
    outcome_id: str | None = None
    outcome_hash: str | None = None
    product_id: str
    hypothesis_id: str = Field(min_length=1, max_length=240)
    transition_revision_id: str = Field(min_length=1, max_length=240)
    transition_revision_hash: str = Field(pattern=r"^[a-f0-9]{64}$")
    observed_at: datetime
    disposition: TransitionOutcomeDisposition
    observed_target: StateAssignmentV1 | None = None
    evidence_pack_id: str = Field(min_length=1, max_length=240)
    evidence_pack_hash: str = Field(pattern=r"^[a-f0-9]{64}$")
    evidence_refs: tuple[str, ...] = Field(default_factory=tuple, max_length=MAX_PACK_RECORDS)
    forecast_ref: str | None = Field(default=None, min_length=1, max_length=240)
    forecast_resolution_ref: str | None = Field(default=None, min_length=1, max_length=240)
    authority: ReviewAuthority
    observer_ref: str = Field(min_length=1, max_length=240)
    rationale: str = Field(min_length=1, max_length=2_000)
    omissions: tuple[str, ...] = Field(default_factory=tuple, max_length=MAX_REASONS)
    failures: tuple[str, ...] = Field(default_factory=tuple, max_length=MAX_REASONS)
    degraded_reasons: tuple[str, ...] = Field(default_factory=tuple, max_length=MAX_REASONS)

    @field_validator("product_id")
    @classmethod
    def validate_product(cls, value: str) -> str:
        return _product(value)

    @field_validator("observed_at")
    @classmethod
    def validate_observed_at(cls, value: datetime) -> datetime:
        return _aware(value, "observed_at")

    @field_validator("evidence_refs", "omissions", "failures", "degraded_reasons", mode="before")
    @classmethod
    def normalize_refs(cls, value: Any, info) -> tuple[str, ...]:
        limit = MAX_PACK_RECORDS if info.field_name == "evidence_refs" else MAX_REASONS
        return _refs(value, limit=limit, name=info.field_name)

    @model_validator(mode="after")
    def derive_identity(self) -> Self:
        if self.observed_target is not None and self.observed_target.variable.subject.product_id != self.product_id:
            raise ValueError("transition outcomes cannot cross product scope")
        if (self.forecast_ref is None) != (self.forecast_resolution_ref is None):
            raise ValueError("forecast and forecast-resolution references must be supplied together")
        if self.disposition in {TransitionOutcomeDisposition.MATCHED, TransitionOutcomeDisposition.CONTRADICTED}:
            if self.observed_target is None or not self.evidence_refs:
                raise ValueError("resolved transition outcomes require observed target material and evidence")
            if self.authority is ReviewAuthority.MODEL:
                raise ValueError("model authority cannot resolve an observed transition outcome")
        if self.disposition is TransitionOutcomeDisposition.UNRESOLVED and self.observed_target is not None:
            raise ValueError("unresolved transition outcomes cannot fabricate an observed target")
        material = self.model_dump(mode="json", exclude={"outcome_id", "outcome_hash"})
        expected_hash = canonical_hash(material)
        expected_id = f"grounded_transition_outcome:{expected_hash[:32]}"
        if self.outcome_hash is not None and self.outcome_hash != expected_hash:
            raise ValueError("transition outcome hash does not match deterministic material")
        if self.outcome_id is not None and self.outcome_id != expected_id:
            raise ValueError("transition outcome identity does not match deterministic material")
        object.__setattr__(self, "outcome_hash", expected_hash)
        object.__setattr__(self, "outcome_id", expected_id)
        return self


class TransitionCalibrationReceiptV1(FrozenContract):
    contract_version: Literal["ace.grounded-state.transition-calibration/v1"] = TRANSITION_CALIBRATION_VERSION
    receipt_id: str | None = None
    receipt_hash: str | None = None
    product_id: str
    hypothesis_id: str = Field(min_length=1, max_length=240)
    transition_revision_id: str = Field(min_length=1, max_length=240)
    transition_revision_hash: str = Field(pattern=r"^[a-f0-9]{64}$")
    original_probability: ProbabilityEstimateV1
    outcome_refs: tuple[str, ...] = Field(default_factory=tuple, max_length=MAX_REFS)
    matched_weight: float = Field(ge=0)
    contradicted_weight: float = Field(ge=0)
    unresolved_count: int = Field(ge=0)
    calibrated_probability: ProbabilityEstimateV1
    calibrated_at: datetime
    policy_version: str = Field(default=TP5_CALIBRATION_POLICY_VERSION, min_length=1, max_length=160)
    omissions: tuple[str, ...] = Field(default_factory=tuple, max_length=MAX_REASONS)
    failures: tuple[str, ...] = Field(default_factory=tuple, max_length=MAX_REASONS)
    degraded_reasons: tuple[str, ...] = Field(default_factory=tuple, max_length=MAX_REASONS)

    @field_validator("product_id")
    @classmethod
    def validate_product(cls, value: str) -> str:
        return _product(value)

    @field_validator("calibrated_at")
    @classmethod
    def validate_calibrated_at(cls, value: datetime) -> datetime:
        return _aware(value, "calibrated_at")

    @field_validator("outcome_refs", "omissions", "failures", "degraded_reasons", mode="before")
    @classmethod
    def normalize_refs(cls, value: Any, info) -> tuple[str, ...]:
        limit = MAX_REFS if info.field_name == "outcome_refs" else MAX_REASONS
        return _refs(value, limit=limit, name=info.field_name)

    @model_validator(mode="after")
    def derive_identity(self) -> Self:
        if not self.outcome_refs and (self.matched_weight or self.contradicted_weight):
            raise ValueError("calibration weights require exact outcome references")
        material = self.model_dump(mode="json", exclude={"receipt_id", "receipt_hash"})
        expected_hash = canonical_hash(material)
        expected_id = f"grounded_transition_calibration:{expected_hash[:32]}"
        if self.receipt_hash is not None and self.receipt_hash != expected_hash:
            raise ValueError("transition calibration hash does not match deterministic material")
        if self.receipt_id is not None and self.receipt_id != expected_id:
            raise ValueError("transition calibration identity does not match deterministic material")
        object.__setattr__(self, "receipt_hash", expected_hash)
        object.__setattr__(self, "receipt_id", expected_id)
        return self
