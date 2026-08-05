"""Immutable TP6 contracts for bounded consequence simulation and reasoning use.

TP6 keeps retrieved evidence, believed state, transition hypotheses, simulated
state, model proposals, independent challenge, later observations, and durable
memory as distinct meanings. Core owns scope, identity, lifecycle, and replay;
model output is proposal material only.
"""

from __future__ import annotations

from datetime import datetime
from enum import StrEnum
from typing import Any, Literal, Self

from pydantic import Field, field_validator, model_validator

from core.engine.grounded_state.belief_contracts import (
    MAX_PACK_RECORDS,
    MAX_REASONS,
    BeliefStateProjectionV1,
    BoundedEvidencePackV1,
    ReviewAuthority,
    _aware,
    _product,
    _refs,
)
from core.engine.grounded_state.contracts import (
    MAX_REFS,
    ConsequenceRolloutRequestV1,
    FrozenContract,
    ProbabilityEstimateV1,
    RolloutBranchKind,
    canonical_hash,
)
from core.engine.grounded_state.transition_contracts import (
    StateAssignmentV1,
    StateSnapshotV1,
)

EVIDENCE_QUERY_VERSION = "ace.grounded-state.evidence-query/v1"
REASONING_EVIDENCE_PACK_VERSION = "ace.grounded-state.reasoning-evidence-pack/v1"
ROLLOUT_PROPOSAL_VERSION = "ace.grounded-state.rollout-proposal/v1"
ROLLOUT_EXECUTION_VERSION = "ace.grounded-state.rollout-execution/v1"
MODEL_BRANCH_PROPOSAL_VERSION = "ace.grounded-state.model-branch-proposal/v1"
ROLLOUT_CHALLENGE_VERSION = "ace.grounded-state.rollout-challenge/v1"
CONSEQUENCE_ROLLOUT_VERSION = "ace.grounded-state.consequence-rollout/v1"
REASONING_CONTEXT_USE_VERSION = "ace.grounded-state.reasoning-context-use/v1"
ROLLOUT_OUTCOME_VERSION = "ace.grounded-state.rollout-outcome/v1"
ROLLOUT_RECONCILIATION_VERSION = "ace.grounded-state.rollout-reconciliation/v1"

TP6_EVIDENCE_QUERY_POLICY_VERSION = "ace.grounded-state.evidence-query/v1"
TP6_ROLLOUT_POLICY_VERSION = "ace.grounded-state.consequence-rollout/v1"
TP6_CHALLENGE_POLICY_VERSION = "ace.grounded-state.rollout-challenge/v1"
TP6_SYNTHESIS_POLICY_VERSION = "ace.grounded-state.rollout-synthesis/v1"
TP6_REASONING_USE_POLICY_VERSION = "ace.grounded-state.reasoning-use/v1"
TP6_RECONCILIATION_POLICY_VERSION = "ace.grounded-state.rollout-reconciliation/v1"

MAX_ROLLOUT_BRANCHES = 8
MAX_ROLLOUT_STEPS = 32
MAX_BRANCH_TRANSITIONS = 16
MAX_ROLLOUT_HORIZON_SECONDS = 31_536_000
MAX_CONTEXT_CHARS = 64_000
MAX_ASSUMPTIONS = 50
MAX_CONSTRAINTS = 50


class EvidenceCoverageState(StrEnum):
    SUPPORTED = "supported"
    PROVISIONAL = "provisional"
    CONTESTED = "contested"
    SUPERSEDED = "superseded"
    STALE = "stale"
    REJECTED = "rejected"
    UNKNOWN = "unknown"
    MISSING = "missing"
    TRUNCATED = "truncated"


class RolloutDerivationRoute(StrEnum):
    DETERMINISTIC_TRANSITION = "deterministic_transition"
    MODEL_PROPOSED = "model_proposed"
    NO_ACTION_BASELINE = "no_action_baseline"


class RolloutDisposition(StrEnum):
    ELIGIBLE = "eligible"
    DEGRADED = "degraded"
    BLOCKED = "blocked"


class RolloutOutcomeDisposition(StrEnum):
    MATCHED = "matched"
    CONTRADICTED = "contradicted"
    MIXED = "mixed"
    UNRESOLVED = "unresolved"


class ProviderExecutionV1(FrozenContract):
    provider: str | None = Field(default=None, max_length=160)
    model: str | None = Field(default=None, max_length=240)
    configuration_hash: str | None = Field(default=None, pattern=r"^[a-f0-9]{64}$")
    calls: int = Field(default=0, ge=0)
    input_tokens: int = Field(default=0, ge=0)
    output_tokens: int = Field(default=0, ge=0)
    latency_ms: int = Field(default=0, ge=0)
    retries: int = Field(default=0, ge=0)
    estimated_cost_usd: float = Field(default=0.0, ge=0)
    billing_semantics: str = Field(default="no_provider_call", min_length=1, max_length=240)
    failures: tuple[str, ...] = Field(default_factory=tuple, max_length=MAX_REASONS)
    fallbacks: tuple[str, ...] = Field(default_factory=tuple, max_length=MAX_REASONS)

    @field_validator("failures", "fallbacks", mode="before")
    @classmethod
    def normalize_reasons(cls, value: Any, info) -> tuple[str, ...]:
        return _refs(value, limit=MAX_REASONS, name=info.field_name)

    @model_validator(mode="after")
    def validate_route(self) -> Self:
        if self.calls == 0 and any(
            (self.provider, self.model, self.input_tokens, self.output_tokens, self.retries, self.estimated_cost_usd)
        ):
            raise ValueError("zero-call provider execution cannot report provider consumption")
        if self.calls > 0 and not (self.provider and self.model and self.configuration_hash):
            raise ValueError("provider calls require exact provider, model, and configuration identity")
        return self


class EvidenceQueryV1(FrozenContract):
    contract_version: Literal["ace.grounded-state.evidence-query/v1"] = EVIDENCE_QUERY_VERSION
    query_id: str | None = None
    query_hash: str | None = None
    product_id: str
    task_id: str = Field(min_length=1, max_length=240)
    invocation_id: str = Field(min_length=1, max_length=240)
    authorization_scope_hash: str = Field(pattern=r"^[a-f0-9]{64}$")
    question: str = Field(min_length=1, max_length=4_000)
    as_of: datetime
    entity_refs: tuple[str, ...] = Field(default_factory=tuple, max_length=MAX_REFS)
    allowed_record_kinds: tuple[str, ...] = Field(default_factory=tuple, max_length=100)
    allowed_source_ids: tuple[str, ...] = Field(default_factory=tuple, max_length=100)
    occurred_after: datetime | None = None
    occurred_before: datetime | None = None
    include_unknown_time: bool = True
    max_candidates: int = Field(default=200, ge=1, le=200)
    max_records: int = Field(default=20, ge=1, le=MAX_PACK_RECORDS)
    max_chars: int = Field(default=16_000, ge=1, le=MAX_CONTEXT_CHARS)
    resolver_policy_version: str = Field(default=TP6_EVIDENCE_QUERY_POLICY_VERSION, min_length=1, max_length=160)

    @field_validator("product_id")
    @classmethod
    def validate_product(cls, value: str) -> str:
        return _product(value)

    @field_validator("as_of", "occurred_after", "occurred_before")
    @classmethod
    def validate_times(cls, value: datetime | None, info) -> datetime | None:
        return _aware(value, info.field_name) if value is not None else None

    @field_validator("entity_refs", "allowed_record_kinds", "allowed_source_ids", mode="before")
    @classmethod
    def normalize_refs(cls, value: Any, info) -> tuple[str, ...]:
        return _refs(value, limit=MAX_REFS, name=info.field_name)

    @model_validator(mode="after")
    def derive_identity(self) -> Self:
        if self.occurred_after and self.occurred_before and self.occurred_before < self.occurred_after:
            raise ValueError("evidence query time bounds are inverted")
        material = self.model_dump(mode="json", exclude={"query_id", "query_hash"})
        expected_hash = canonical_hash(material)
        expected_id = f"grounded_evidence_query:{expected_hash[:32]}"
        if self.query_hash is not None and self.query_hash != expected_hash:
            raise ValueError("evidence query hash does not match exact trusted query material")
        if self.query_id is not None and self.query_id != expected_id:
            raise ValueError("evidence query identity does not match exact trusted query material")
        object.__setattr__(self, "query_hash", expected_hash)
        object.__setattr__(self, "query_id", expected_id)
        return self


class EvidenceCoverageV1(FrozenContract):
    state: EvidenceCoverageState
    evidence_refs: tuple[str, ...] = Field(default_factory=tuple, max_length=MAX_PACK_RECORDS)
    reason: str = Field(min_length=1, max_length=1_000)

    @field_validator("evidence_refs", mode="before")
    @classmethod
    def normalize_refs(cls, value: Any) -> tuple[str, ...]:
        return _refs(value, limit=MAX_PACK_RECORDS, name="coverage evidence_refs")


class ReasoningEvidencePackV1(FrozenContract):
    contract_version: Literal["ace.grounded-state.reasoning-evidence-pack/v1"] = REASONING_EVIDENCE_PACK_VERSION
    context_pack_id: str | None = None
    context_pack_hash: str | None = None
    product_id: str
    task_id: str = Field(min_length=1, max_length=240)
    invocation_id: str = Field(min_length=1, max_length=240)
    query_id: str = Field(min_length=1, max_length=240)
    query_hash: str = Field(pattern=r"^[a-f0-9]{64}$")
    evidence_pack: BoundedEvidencePackV1
    index_versions: dict[str, str] = Field(default_factory=dict)
    coverage: tuple[EvidenceCoverageV1, ...] = Field(default_factory=tuple, max_length=20)
    selected_record_refs: tuple[str, ...] = Field(default_factory=tuple, max_length=MAX_PACK_RECORDS)
    untrusted_data_label: Literal["UNTRUSTED_EVIDENCE_DATA_ONLY"] = "UNTRUSTED_EVIDENCE_DATA_ONLY"
    source_instruction_authority: Literal[False] = False
    execution_authority: Literal[False] = False
    omissions: tuple[str, ...] = Field(default_factory=tuple, max_length=MAX_REASONS)
    failures: tuple[str, ...] = Field(default_factory=tuple, max_length=MAX_REASONS)
    degraded_reasons: tuple[str, ...] = Field(default_factory=tuple, max_length=MAX_REASONS)
    provider_usage: ProviderExecutionV1 = Field(default_factory=ProviderExecutionV1)

    @field_validator("product_id")
    @classmethod
    def validate_product(cls, value: str) -> str:
        return _product(value)

    @field_validator("selected_record_refs", "omissions", "failures", "degraded_reasons", mode="before")
    @classmethod
    def normalize_refs(cls, value: Any, info) -> tuple[str, ...]:
        limit = MAX_PACK_RECORDS if info.field_name == "selected_record_refs" else MAX_REASONS
        return _refs(value, limit=limit, name=info.field_name)

    @model_validator(mode="after")
    def derive_identity(self) -> Self:
        if self.evidence_pack.product_id != self.product_id:
            raise ValueError("reasoning evidence pack cannot cross product scope")
        expected_refs = tuple(sorted(item.endpoint.record_id for item in self.evidence_pack.items))
        if self.selected_record_refs != expected_refs:
            raise ValueError("reasoning evidence pack must account for every exact selected record")
        if self.evidence_pack.truncated and not any(
            item.state is EvidenceCoverageState.TRUNCATED for item in self.coverage
        ):
            raise ValueError("truncated evidence must remain visible in reasoning coverage")
        material = self.model_dump(mode="json", exclude={"context_pack_id", "context_pack_hash"})
        expected_hash = canonical_hash(material)
        expected_id = f"grounded_reasoning_pack:{expected_hash[:32]}"
        if self.context_pack_hash is not None and self.context_pack_hash != expected_hash:
            raise ValueError("reasoning context-pack hash does not match exact material")
        if self.context_pack_id is not None and self.context_pack_id != expected_id:
            raise ValueError("reasoning context-pack identity does not match exact material")
        object.__setattr__(self, "context_pack_hash", expected_hash)
        object.__setattr__(self, "context_pack_id", expected_id)
        return self


class BranchAssumptionV1(FrozenContract):
    assumption_id: str | None = None
    branch_id: str = Field(min_length=1, max_length=120)
    statement: str = Field(min_length=1, max_length=2_000)
    evidence_refs: tuple[str, ...] = Field(default_factory=tuple, max_length=MAX_REFS)
    supported: bool

    @field_validator("evidence_refs", mode="before")
    @classmethod
    def normalize_refs(cls, value: Any) -> tuple[str, ...]:
        return _refs(value, limit=MAX_REFS, name="assumption evidence_refs")

    @model_validator(mode="after")
    def derive_identity(self) -> Self:
        expected = f"rollout_assumption:{canonical_hash(self.model_dump(mode='json', exclude={'assumption_id'}))[:32]}"
        if self.assumption_id is not None and self.assumption_id != expected:
            raise ValueError("rollout assumption identity does not match exact material")
        object.__setattr__(self, "assumption_id", expected)
        return self


class BranchConstraintV1(FrozenContract):
    constraint_id: str | None = None
    branch_id: str = Field(min_length=1, max_length=120)
    statement: str = Field(min_length=1, max_length=2_000)
    rule_ref: str = Field(min_length=1, max_length=240)
    satisfied: bool | None = None

    @model_validator(mode="after")
    def derive_identity(self) -> Self:
        expected = f"rollout_constraint:{canonical_hash(self.model_dump(mode='json', exclude={'constraint_id'}))[:32]}"
        if self.constraint_id is not None and self.constraint_id != expected:
            raise ValueError("rollout constraint identity does not match exact material")
        object.__setattr__(self, "constraint_id", expected)
        return self


class RolloutProposalV1(FrozenContract):
    contract_version: Literal["ace.grounded-state.rollout-proposal/v1"] = ROLLOUT_PROPOSAL_VERSION
    proposal_id: str | None = None
    proposal_hash: str | None = None
    product_id: str
    task_id: str = Field(min_length=1, max_length=240)
    invocation_id: str = Field(min_length=1, max_length=240)
    context_pack_id: str = Field(min_length=1, max_length=240)
    context_pack_hash: str = Field(pattern=r"^[a-f0-9]{64}$")
    request: ConsequenceRolloutRequestV1
    transition_revision_ids: tuple[str, ...] = Field(default_factory=tuple, max_length=MAX_BRANCH_TRANSITIONS)
    transition_revision_hashes: dict[str, str] = Field(default_factory=dict)
    assumptions: tuple[BranchAssumptionV1, ...] = Field(default_factory=tuple, max_length=MAX_ASSUMPTIONS)
    constraints: tuple[BranchConstraintV1, ...] = Field(default_factory=tuple, max_length=MAX_CONSTRAINTS)
    ontology_version: str = Field(min_length=1, max_length=160)
    resolver_policy_version: str = Field(min_length=1, max_length=160)
    rollout_policy_version: str = Field(default=TP6_ROLLOUT_POLICY_VERSION, min_length=1, max_length=160)
    derivation_route: RolloutDerivationRoute = RolloutDerivationRoute.DETERMINISTIC_TRANSITION
    provider_usage: ProviderExecutionV1 = Field(default_factory=ProviderExecutionV1)

    @field_validator("product_id")
    @classmethod
    def validate_product(cls, value: str) -> str:
        return _product(value)

    @field_validator("transition_revision_ids", mode="before")
    @classmethod
    def normalize_revision_ids(cls, value: Any) -> tuple[str, ...]:
        return _refs(value, limit=MAX_BRANCH_TRANSITIONS, name="transition revision IDs")

    @field_validator("assumptions", "constraints", mode="before")
    @classmethod
    def normalize_models(cls, value: Any) -> tuple[Any, ...]:
        if not isinstance(value, (list, tuple)):
            raise ValueError("rollout assumptions and constraints must be bounded collections")
        return tuple(sorted(value, key=canonical_hash))

    @model_validator(mode="after")
    def derive_identity(self) -> Self:
        if self.request.product_id != self.product_id:
            raise ValueError("rollout proposal cannot cross product scope")
        if set(self.transition_revision_ids) != set(self.transition_revision_hashes):
            raise ValueError("every transition revision requires one exact revision hash")
        branch_ids = {branch.branch_id for branch in self.request.branches}
        if any(item.branch_id not in branch_ids for item in (*self.assumptions, *self.constraints)):
            raise ValueError("assumptions and constraints must target a declared branch")
        if self.derivation_route is RolloutDerivationRoute.MODEL_PROPOSED and self.provider_usage.calls == 0:
            raise ValueError("model-proposed rollout material requires attributable provider execution")
        material = self.model_dump(mode="json", exclude={"proposal_id", "proposal_hash"})
        expected_hash = canonical_hash(material)
        expected_id = f"grounded_rollout_proposal:{expected_hash[:32]}"
        if self.proposal_hash is not None and self.proposal_hash != expected_hash:
            raise ValueError("rollout proposal hash does not match exact material")
        if self.proposal_id is not None and self.proposal_id != expected_id:
            raise ValueError("rollout proposal identity does not match exact material")
        object.__setattr__(self, "proposal_hash", expected_hash)
        object.__setattr__(self, "proposal_id", expected_id)
        return self


class PredictedStateStepV1(FrozenContract):
    simulated_state_id: str | None = None
    branch_id: str = Field(min_length=1, max_length=120)
    ordinal: int = Field(ge=0, le=MAX_ROLLOUT_STEPS)
    predicted_at: datetime
    starting_projection_id: str = Field(min_length=1, max_length=240)
    starting_projection_hash: str = Field(pattern=r"^[a-f0-9]{64}$")
    prior_simulated_state_id: str | None = Field(default=None, max_length=240)
    transition_revision_id: str | None = Field(default=None, max_length=240)
    transition_revision_hash: str | None = Field(default=None, pattern=r"^[a-f0-9]{64}$")
    assignment: StateAssignmentV1 | None = None
    state_snapshot: tuple[StateSnapshotV1, ...] = Field(default_factory=tuple, max_length=MAX_REFS)
    probability: ProbabilityEstimateV1
    derivation_route: RolloutDerivationRoute
    evidence_refs: tuple[str, ...] = Field(default_factory=tuple, max_length=MAX_REFS)
    belief_entry_refs: tuple[str, ...] = Field(default_factory=tuple, max_length=MAX_REFS)
    assumption_refs: tuple[str, ...] = Field(default_factory=tuple, max_length=MAX_ASSUMPTIONS)
    uncertainty_reasons: tuple[str, ...] = Field(default_factory=tuple, max_length=MAX_REASONS)
    record_meaning: Literal["simulated_state"] = "simulated_state"

    @field_validator("predicted_at")
    @classmethod
    def validate_time(cls, value: datetime) -> datetime:
        return _aware(value, "predicted_at")

    @field_validator("state_snapshot", mode="before")
    @classmethod
    def normalize_snapshot(cls, value: Any) -> tuple[Any, ...]:
        if not isinstance(value, (list, tuple)):
            raise ValueError("predicted state snapshot must be a bounded collection")
        # SurrealDB omits nested ``NONE`` values on round-trip.  Validate first
        # so defaulted fields (notably ``value=None`` for unknown belief state)
        # are restored before canonical ordering and identity verification.
        normalized = tuple(
            item if isinstance(item, StateSnapshotV1) else StateSnapshotV1.model_validate(item) for item in value
        )
        return tuple(sorted(normalized, key=canonical_hash))

    @field_validator("evidence_refs", "belief_entry_refs", "assumption_refs", "uncertainty_reasons", mode="before")
    @classmethod
    def normalize_refs(cls, value: Any, info) -> tuple[str, ...]:
        return _refs(value, limit=MAX_REFS, name=info.field_name)

    @model_validator(mode="after")
    def derive_identity(self) -> Self:
        paired = (self.transition_revision_id is None) == (self.transition_revision_hash is None)
        if not paired:
            raise ValueError("transition revision identity and hash must be supplied together")
        if self.ordinal == 0 and (self.assignment is not None or self.transition_revision_id is not None):
            raise ValueError("starting simulated state cannot apply a transition")
        if self.ordinal > 0 and self.derivation_route is RolloutDerivationRoute.DETERMINISTIC_TRANSITION:
            if self.assignment is None or self.transition_revision_id is None:
                raise ValueError("deterministic predicted steps require exact transition and assignment material")
        material = self.model_dump(mode="json", exclude={"simulated_state_id"})
        expected = f"simulated_state:{canonical_hash(material)[:32]}"
        if self.simulated_state_id is not None and self.simulated_state_id != expected:
            raise ValueError("simulated state identity does not match exact predicted material")
        object.__setattr__(self, "simulated_state_id", expected)
        return self


class FalsifiableOutcomeV1(FrozenContract):
    outcome_id: str | None = None
    branch_id: str = Field(min_length=1, max_length=120)
    indicator: str = Field(min_length=1, max_length=1_000)
    expected_assignment: StateAssignmentV1
    earliest_at: datetime
    latest_at: datetime
    evidence_required: tuple[str, ...] = Field(default_factory=tuple, max_length=MAX_REFS)

    @field_validator("earliest_at", "latest_at")
    @classmethod
    def validate_times(cls, value: datetime, info) -> datetime:
        return _aware(value, info.field_name)

    @field_validator("evidence_required", mode="before")
    @classmethod
    def normalize_refs(cls, value: Any) -> tuple[str, ...]:
        return _refs(value, limit=MAX_REFS, name="falsifiable outcome evidence")

    @model_validator(mode="after")
    def derive_identity(self) -> Self:
        if self.latest_at < self.earliest_at:
            raise ValueError("falsifiable outcome window is inverted")
        expected = (
            f"rollout_predicted_outcome:{canonical_hash(self.model_dump(mode='json', exclude={'outcome_id'}))[:32]}"
        )
        if self.outcome_id is not None and self.outcome_id != expected:
            raise ValueError("falsifiable outcome identity does not match exact material")
        object.__setattr__(self, "outcome_id", expected)
        return self


class PredictedConsequenceV1(FrozenContract):
    consequence_id: str | None = None
    branch_id: str = Field(min_length=1, max_length=120)
    description: str = Field(min_length=1, max_length=4_000)
    predicted_state_ref: str = Field(min_length=1, max_length=240)
    probability: ProbabilityEstimateV1
    evidence_refs: tuple[str, ...] = Field(default_factory=tuple, max_length=MAX_REFS)
    belief_entry_refs: tuple[str, ...] = Field(default_factory=tuple, max_length=MAX_REFS)
    transition_revision_refs: tuple[str, ...] = Field(default_factory=tuple, max_length=MAX_BRANCH_TRANSITIONS)
    assumption_refs: tuple[str, ...] = Field(default_factory=tuple, max_length=MAX_ASSUMPTIONS)
    derivation_route: RolloutDerivationRoute
    falsifiable_outcome: FalsifiableOutcomeV1
    record_meaning: Literal["simulated_consequence"] = "simulated_consequence"

    @field_validator(
        "evidence_refs",
        "belief_entry_refs",
        "transition_revision_refs",
        "assumption_refs",
        mode="before",
    )
    @classmethod
    def normalize_refs(cls, value: Any, info) -> tuple[str, ...]:
        return _refs(value, limit=MAX_REFS, name=info.field_name)

    @model_validator(mode="after")
    def derive_identity(self) -> Self:
        if self.falsifiable_outcome.branch_id != self.branch_id:
            raise ValueError("predicted consequence and falsifiable outcome must share a branch")
        expected = (
            f"simulated_consequence:{canonical_hash(self.model_dump(mode='json', exclude={'consequence_id'}))[:32]}"
        )
        if self.consequence_id is not None and self.consequence_id != expected:
            raise ValueError("predicted consequence identity does not match exact material")
        object.__setattr__(self, "consequence_id", expected)
        return self


class TransitionExecutionReceiptV1(FrozenContract):
    contract_version: Literal["ace.grounded-state.rollout-execution/v1"] = ROLLOUT_EXECUTION_VERSION
    receipt_id: str | None = None
    receipt_hash: str | None = None
    product_id: str
    proposal_id: str = Field(min_length=1, max_length=240)
    proposal_hash: str = Field(pattern=r"^[a-f0-9]{64}$")
    branch_id: str = Field(min_length=1, max_length=120)
    branch_kind: RolloutBranchKind
    starting_projection_id: str = Field(min_length=1, max_length=240)
    starting_projection_hash: str = Field(pattern=r"^[a-f0-9]{64}$")
    as_of: datetime
    horizon: datetime
    applicable_transition_refs: tuple[str, ...] = Field(default_factory=tuple, max_length=MAX_BRANCH_TRANSITIONS)
    blocked_transition_refs: tuple[str, ...] = Field(default_factory=tuple, max_length=MAX_BRANCH_TRANSITIONS)
    transition_revision_hashes: dict[str, str] = Field(default_factory=dict)
    missing_inputs: tuple[str, ...] = Field(default_factory=tuple, max_length=MAX_REASONS)
    constraint_failures: tuple[str, ...] = Field(default_factory=tuple, max_length=MAX_REASONS)
    steps: tuple[PredictedStateStepV1, ...] = Field(default_factory=tuple, max_length=MAX_ROLLOUT_STEPS)
    consequences: tuple[PredictedConsequenceV1, ...] = Field(default_factory=tuple, max_length=MAX_ROLLOUT_STEPS)
    omissions: tuple[str, ...] = Field(default_factory=tuple, max_length=MAX_REASONS)
    failures: tuple[str, ...] = Field(default_factory=tuple, max_length=MAX_REASONS)
    degraded_reasons: tuple[str, ...] = Field(default_factory=tuple, max_length=MAX_REASONS)
    rollout_policy_version: str = Field(default=TP6_ROLLOUT_POLICY_VERSION, min_length=1, max_length=160)
    provider_usage: ProviderExecutionV1 = Field(default_factory=ProviderExecutionV1)

    @field_validator("product_id")
    @classmethod
    def validate_product(cls, value: str) -> str:
        return _product(value)

    @field_validator("as_of", "horizon")
    @classmethod
    def validate_times(cls, value: datetime, info) -> datetime:
        return _aware(value, info.field_name)

    @field_validator("steps", "consequences", mode="before")
    @classmethod
    def normalize_models(cls, value: Any, info) -> tuple[Any, ...]:
        if not isinstance(value, (list, tuple)):
            raise ValueError("rollout steps and consequences must be bounded collections")
        if info.field_name == "steps":
            return tuple(
                sorted(
                    value,
                    key=lambda item: (
                        item.ordinal if isinstance(item, PredictedStateStepV1) else int(item.get("ordinal", 0))
                    ),
                )
            )
        consequences = tuple(
            item if isinstance(item, PredictedConsequenceV1) else PredictedConsequenceV1.model_validate(item)
            for item in value
        )
        return tuple(sorted(consequences, key=canonical_hash))

    @field_validator(
        "applicable_transition_refs",
        "blocked_transition_refs",
        "missing_inputs",
        "constraint_failures",
        "omissions",
        "failures",
        "degraded_reasons",
        mode="before",
    )
    @classmethod
    def normalize_refs(cls, value: Any, info) -> tuple[str, ...]:
        limit = MAX_BRANCH_TRANSITIONS if info.field_name.endswith("transition_refs") else MAX_REASONS
        return _refs(value, limit=limit, name=info.field_name)

    @model_validator(mode="after")
    def derive_identity(self) -> Self:
        if self.horizon <= self.as_of:
            raise ValueError("rollout execution horizon must follow the starting as-of time")
        if set(self.applicable_transition_refs) & set(self.blocked_transition_refs):
            raise ValueError("a transition cannot be both applicable and blocked")
        if any(step.branch_id != self.branch_id for step in self.steps):
            raise ValueError("predicted steps cannot cross rollout branches")
        if any(item.branch_id != self.branch_id for item in self.consequences):
            raise ValueError("predicted consequences cannot cross rollout branches")
        if any(step.predicted_at > self.horizon for step in self.steps):
            raise ValueError("predicted steps cannot exceed the frozen horizon")
        material = self.model_dump(mode="json", exclude={"receipt_id", "receipt_hash"})
        expected_hash = canonical_hash(material)
        expected_id = f"grounded_rollout_execution:{expected_hash[:32]}"
        if self.receipt_hash is not None and self.receipt_hash != expected_hash:
            raise ValueError("transition execution hash does not match exact material")
        if self.receipt_id is not None and self.receipt_id != expected_id:
            raise ValueError("transition execution identity does not match exact material")
        object.__setattr__(self, "receipt_hash", expected_hash)
        object.__setattr__(self, "receipt_id", expected_id)
        return self


class ModelBranchProposalReceiptV1(FrozenContract):
    contract_version: Literal["ace.grounded-state.model-branch-proposal/v1"] = MODEL_BRANCH_PROPOSAL_VERSION
    receipt_id: str | None = None
    receipt_hash: str | None = None
    product_id: str
    rollout_proposal_id: str = Field(min_length=1, max_length=240)
    branch_ids: tuple[str, ...] = Field(default_factory=tuple, max_length=MAX_ROLLOUT_BRANCHES)
    proposed_assumption_refs: tuple[str, ...] = Field(default_factory=tuple, max_length=MAX_ASSUMPTIONS)
    proposed_consequence_refs: tuple[str, ...] = Field(default_factory=tuple, max_length=MAX_ROLLOUT_STEPS)
    authority: Literal["model_proposal_only"] = "model_proposal_only"
    lifecycle_disposition: Literal["proposed"] = "proposed"
    can_accept: Literal[False] = False
    can_challenge_self: Literal[False] = False
    can_resolve_outcomes: Literal[False] = False
    provider_usage: ProviderExecutionV1

    @field_validator("product_id")
    @classmethod
    def validate_product(cls, value: str) -> str:
        return _product(value)

    @field_validator("branch_ids", "proposed_assumption_refs", "proposed_consequence_refs", mode="before")
    @classmethod
    def normalize_refs(cls, value: Any, info) -> tuple[str, ...]:
        return _refs(value, limit=MAX_REFS, name=info.field_name)

    @model_validator(mode="after")
    def derive_identity(self) -> Self:
        if self.provider_usage.calls < 1:
            raise ValueError("model branch proposal requires an attributable provider call")
        material = self.model_dump(mode="json", exclude={"receipt_id", "receipt_hash"})
        expected_hash = canonical_hash(material)
        expected_id = f"grounded_model_branch_proposal:{expected_hash[:32]}"
        if self.receipt_hash is not None and self.receipt_hash != expected_hash:
            raise ValueError("model proposal hash does not match exact material")
        if self.receipt_id is not None and self.receipt_id != expected_id:
            raise ValueError("model proposal identity does not match exact material")
        object.__setattr__(self, "receipt_hash", expected_hash)
        object.__setattr__(self, "receipt_id", expected_id)
        return self


class RolloutChallengeReceiptV1(FrozenContract):
    contract_version: Literal["ace.grounded-state.rollout-challenge/v1"] = ROLLOUT_CHALLENGE_VERSION
    receipt_id: str | None = None
    receipt_hash: str | None = None
    product_id: str
    proposal_id: str = Field(min_length=1, max_length=240)
    proposal_hash: str = Field(pattern=r"^[a-f0-9]{64}$")
    context_pack_id: str = Field(min_length=1, max_length=240)
    context_pack_hash: str = Field(pattern=r"^[a-f0-9]{64}$")
    execution_receipt_refs: tuple[str, ...] = Field(default_factory=tuple, max_length=MAX_ROLLOUT_BRANCHES)
    checked_transition_refs: tuple[str, ...] = Field(default_factory=tuple, max_length=MAX_BRANCH_TRANSITIONS)
    checks: dict[str, bool]
    counterevidence_refs: tuple[str, ...] = Field(default_factory=tuple, max_length=MAX_PACK_RECORDS)
    unsupported_assumption_refs: tuple[str, ...] = Field(default_factory=tuple, max_length=MAX_ASSUMPTIONS)
    missing_inputs: tuple[str, ...] = Field(default_factory=tuple, max_length=MAX_REASONS)
    omissions: tuple[str, ...] = Field(default_factory=tuple, max_length=MAX_REASONS)
    failures: tuple[str, ...] = Field(default_factory=tuple, max_length=MAX_REASONS)
    degraded_reasons: tuple[str, ...] = Field(default_factory=tuple, max_length=MAX_REASONS)
    completed: bool
    independent_authority: ReviewAuthority
    challenger_ref: str = Field(min_length=1, max_length=240)
    challenged_at: datetime
    policy_version: str = Field(default=TP6_CHALLENGE_POLICY_VERSION, min_length=1, max_length=160)
    provider_usage: ProviderExecutionV1 = Field(default_factory=ProviderExecutionV1)

    @field_validator("product_id")
    @classmethod
    def validate_product(cls, value: str) -> str:
        return _product(value)

    @field_validator("challenged_at")
    @classmethod
    def validate_time(cls, value: datetime) -> datetime:
        return _aware(value, "challenged_at")

    @field_validator(
        "execution_receipt_refs",
        "checked_transition_refs",
        "counterevidence_refs",
        "unsupported_assumption_refs",
        "missing_inputs",
        "omissions",
        "failures",
        "degraded_reasons",
        mode="before",
    )
    @classmethod
    def normalize_refs(cls, value: Any, info) -> tuple[str, ...]:
        return _refs(value, limit=MAX_REFS, name=info.field_name)

    @model_validator(mode="after")
    def derive_identity(self) -> Self:
        if self.independent_authority is ReviewAuthority.MODEL:
            raise ValueError("a rollout model proposal cannot accept its own challenge")
        complete = (
            bool(self.checks)
            and all(self.checks.values())
            and not any(
                (
                    self.unsupported_assumption_refs,
                    self.missing_inputs,
                    self.omissions,
                    self.failures,
                    self.degraded_reasons,
                )
            )
        )
        if self.completed != complete:
            raise ValueError("rollout challenge completion must fail closed from exact checks and degraded inputs")
        material = self.model_dump(mode="json", exclude={"receipt_id", "receipt_hash"})
        expected_hash = canonical_hash(material)
        expected_id = f"grounded_rollout_challenge:{expected_hash[:32]}"
        if self.receipt_hash is not None and self.receipt_hash != expected_hash:
            raise ValueError("rollout challenge hash does not match exact material")
        if self.receipt_id is not None and self.receipt_id != expected_id:
            raise ValueError("rollout challenge identity does not match exact material")
        object.__setattr__(self, "receipt_hash", expected_hash)
        object.__setattr__(self, "receipt_id", expected_id)
        return self


class ConsequenceRolloutRevisionV1(FrozenContract):
    contract_version: Literal["ace.grounded-state.consequence-rollout/v1"] = CONSEQUENCE_ROLLOUT_VERSION
    rollout_revision_id: str | None = None
    rollout_revision_hash: str | None = None
    rollout_id: str = Field(min_length=1, max_length=240)
    revision: int = Field(default=1, ge=1)
    prior_revision_id: str | None = Field(default=None, max_length=240)
    product_id: str
    task_id: str = Field(min_length=1, max_length=240)
    invocation_id: str = Field(min_length=1, max_length=240)
    proposal_id: str = Field(min_length=1, max_length=240)
    proposal_hash: str = Field(pattern=r"^[a-f0-9]{64}$")
    context_pack_id: str = Field(min_length=1, max_length=240)
    context_pack_hash: str = Field(pattern=r"^[a-f0-9]{64}$")
    starting_projection_id: str = Field(min_length=1, max_length=240)
    starting_projection_hash: str = Field(pattern=r"^[a-f0-9]{64}$")
    as_of: datetime
    horizon: datetime
    transition_revision_ids: tuple[str, ...] = Field(default_factory=tuple, max_length=MAX_BRANCH_TRANSITIONS)
    transition_revision_hashes: dict[str, str] = Field(default_factory=dict)
    execution_receipts: tuple[TransitionExecutionReceiptV1, ...] = Field(
        default_factory=tuple,
        max_length=MAX_ROLLOUT_BRANCHES,
    )
    model_proposal_receipt_id: str | None = Field(default=None, max_length=240)
    challenge_receipt_id: str = Field(min_length=1, max_length=240)
    challenge_receipt_hash: str = Field(pattern=r"^[a-f0-9]{64}$")
    challenge_completed: bool
    disposition: RolloutDisposition
    final_synthesis: str = Field(min_length=1, max_length=8_000)
    ontology_version: str = Field(min_length=1, max_length=160)
    resolver_policy_version: str = Field(min_length=1, max_length=160)
    rollout_policy_version: str = Field(min_length=1, max_length=160)
    challenge_policy_version: str = Field(min_length=1, max_length=160)
    synthesis_policy_version: str = Field(default=TP6_SYNTHESIS_POLICY_VERSION, min_length=1, max_length=160)
    omissions: tuple[str, ...] = Field(default_factory=tuple, max_length=MAX_REASONS)
    failures: tuple[str, ...] = Field(default_factory=tuple, max_length=MAX_REASONS)
    degraded_reasons: tuple[str, ...] = Field(default_factory=tuple, max_length=MAX_REASONS)
    provider_usage: ProviderExecutionV1 = Field(default_factory=ProviderExecutionV1)

    @field_validator("product_id")
    @classmethod
    def validate_product(cls, value: str) -> str:
        return _product(value)

    @field_validator("as_of", "horizon")
    @classmethod
    def validate_times(cls, value: datetime, info) -> datetime:
        return _aware(value, info.field_name)

    @field_validator("transition_revision_ids", "omissions", "failures", "degraded_reasons", mode="before")
    @classmethod
    def normalize_refs(cls, value: Any, info) -> tuple[str, ...]:
        limit = MAX_BRANCH_TRANSITIONS if info.field_name == "transition_revision_ids" else MAX_REASONS
        return _refs(value, limit=limit, name=info.field_name)

    @field_validator("execution_receipts", mode="before")
    @classmethod
    def normalize_receipts(cls, value: Any) -> tuple[Any, ...]:
        if not isinstance(value, (list, tuple)):
            raise ValueError("rollout execution receipts must be a bounded collection")
        receipts = tuple(
            item
            if isinstance(item, TransitionExecutionReceiptV1)
            else TransitionExecutionReceiptV1.model_validate(item)
            for item in value
        )
        return tuple(sorted(receipts, key=canonical_hash))

    @model_validator(mode="after")
    def derive_identity(self) -> Self:
        if self.revision == 1 and self.prior_revision_id is not None:
            raise ValueError("the first rollout revision cannot name prior material")
        if self.revision > 1 and self.prior_revision_id is None:
            raise ValueError("later rollout revisions require exact prior lineage")
        if set(self.transition_revision_ids) != set(self.transition_revision_hashes):
            raise ValueError("rollout revision hashes must account for every transition revision")
        if any(
            receipt.product_id != self.product_id
            or receipt.starting_projection_id != self.starting_projection_id
            or receipt.starting_projection_hash != self.starting_projection_hash
            or receipt.as_of != self.as_of
            or receipt.horizon != self.horizon
            for receipt in self.execution_receipts
        ):
            raise ValueError("every rollout branch must share exact product, start, as-of, and horizon material")
        if len({receipt.branch_id for receipt in self.execution_receipts}) != len(self.execution_receipts):
            raise ValueError("rollout branch receipts must have unique identities")
        if self.disposition is RolloutDisposition.ELIGIBLE and (
            not self.challenge_completed or self.omissions or self.failures or self.degraded_reasons
        ):
            raise ValueError("eligible rollout revisions require complete clean independent challenge")
        material = self.model_dump(mode="json", exclude={"rollout_revision_id", "rollout_revision_hash"})
        expected_hash = canonical_hash(material)
        expected_id = f"grounded_rollout_revision:{expected_hash[:32]}"
        if self.rollout_revision_hash is not None and self.rollout_revision_hash != expected_hash:
            raise ValueError("rollout revision hash does not match exact material")
        if self.rollout_revision_id is not None and self.rollout_revision_id != expected_id:
            raise ValueError("rollout revision identity does not match exact material")
        object.__setattr__(self, "rollout_revision_hash", expected_hash)
        object.__setattr__(self, "rollout_revision_id", expected_id)
        return self


class ReasoningUseItemV1(FrozenContract):
    item_id: str = Field(min_length=1, max_length=240)
    item_type: Literal["evidence", "belief", "transition", "assumption", "branch", "consequence"]
    content_hash: str = Field(pattern=r"^[a-f0-9]{64}$")
    retrieved: bool
    injected: bool
    reflected: bool
    decision_material: bool
    changed_fields: tuple[str, ...] = Field(default_factory=tuple, max_length=20)
    non_credit_reasons: tuple[str, ...] = Field(default_factory=tuple, max_length=MAX_REASONS)

    @field_validator("changed_fields", "non_credit_reasons", mode="before")
    @classmethod
    def normalize_refs(cls, value: Any, info) -> tuple[str, ...]:
        return _refs(value, limit=MAX_REASONS, name=info.field_name)

    @model_validator(mode="after")
    def validate_states(self) -> Self:
        if self.decision_material and not (self.retrieved and self.injected and self.reflected and self.changed_fields):
            raise ValueError("decision-material rollout use requires retrieval, injection, reflection, and exact delta")
        if self.reflected and not self.injected:
            raise ValueError("reflected rollout material must have been injected")
        if self.injected and not self.retrieved:
            raise ValueError("injected rollout material must have been retrieved")
        return self


class ReasoningContextUseReceiptV1(FrozenContract):
    contract_version: Literal["ace.grounded-state.reasoning-context-use/v1"] = REASONING_CONTEXT_USE_VERSION
    receipt_id: str | None = None
    receipt_hash: str | None = None
    product_id: str
    task_id: str = Field(min_length=1, max_length=240)
    invocation_id: str = Field(min_length=1, max_length=240)
    rollout_revision_id: str = Field(min_length=1, max_length=240)
    rollout_revision_hash: str = Field(pattern=r"^[a-f0-9]{64}$")
    context_pack_id: str = Field(min_length=1, max_length=240)
    context_pack_hash: str = Field(pattern=r"^[a-f0-9]{64}$")
    items: tuple[ReasoningUseItemV1, ...] = Field(default_factory=tuple, max_length=MAX_REFS)
    comparison_state: Literal["matched", "unknown", "unmatched", "failed"]
    comparison_id: str | None = Field(default=None, max_length=240)
    matched_dimensions: tuple[str, ...] = Field(default_factory=tuple, max_length=20)
    treatment_output_hash: str | None = Field(default=None, pattern=r"^[a-f0-9]{64}$")
    control_output_hash: str | None = Field(default=None, pattern=r"^[a-f0-9]{64}$")
    changed_decision_fields: tuple[str, ...] = Field(default_factory=tuple, max_length=20)
    policy_version: str = Field(default=TP6_REASONING_USE_POLICY_VERSION, min_length=1, max_length=160)
    provider_usage: ProviderExecutionV1 = Field(default_factory=ProviderExecutionV1)
    degraded_reasons: tuple[str, ...] = Field(default_factory=tuple, max_length=MAX_REASONS)

    @field_validator("product_id")
    @classmethod
    def validate_product(cls, value: str) -> str:
        return _product(value)

    @field_validator("items", mode="before")
    @classmethod
    def normalize_items(cls, value: Any) -> tuple[Any, ...]:
        if not isinstance(value, (list, tuple)):
            raise ValueError("reasoning use items must be a bounded collection")
        return tuple(sorted(value, key=canonical_hash))

    @field_validator("matched_dimensions", "changed_decision_fields", "degraded_reasons", mode="before")
    @classmethod
    def normalize_refs(cls, value: Any, info) -> tuple[str, ...]:
        return _refs(value, limit=MAX_REASONS, name=info.field_name)

    @model_validator(mode="after")
    def derive_identity(self) -> Self:
        required_matches = {
            "task_hash",
            "provider",
            "model",
            "configuration",
            "decision_schema",
            "toolset",
        }
        material_items = [item for item in self.items if item.decision_material]
        matched = (
            self.comparison_state == "matched"
            and self.comparison_id is not None
            and required_matches <= set(self.matched_dimensions)
            and self.treatment_output_hash is not None
            and self.control_output_hash is not None
            and self.treatment_output_hash != self.control_output_hash
        )
        if material_items and (not matched or not self.changed_decision_fields):
            raise ValueError("decision-material credit requires an exact matched rollout/no-rollout comparison")
        if not matched and material_items:
            raise ValueError("unmatched reasoning use must stop before decision-material credit")
        if self.comparison_state == "unknown" and self.comparison_id is not None:
            raise ValueError("unknown matched-control state cannot fabricate a comparison identity")
        material = self.model_dump(mode="json", exclude={"receipt_id", "receipt_hash"})
        expected_hash = canonical_hash(material)
        expected_id = f"grounded_reasoning_use:{expected_hash[:32]}"
        if self.receipt_hash is not None and self.receipt_hash != expected_hash:
            raise ValueError("reasoning-use receipt hash does not match exact material")
        if self.receipt_id is not None and self.receipt_id != expected_id:
            raise ValueError("reasoning-use receipt identity does not match exact material")
        object.__setattr__(self, "receipt_hash", expected_hash)
        object.__setattr__(self, "receipt_id", expected_id)
        return self


class RolloutOutcomeObservationV1(FrozenContract):
    contract_version: Literal["ace.grounded-state.rollout-outcome/v1"] = ROLLOUT_OUTCOME_VERSION
    observation_id: str | None = None
    observation_hash: str | None = None
    product_id: str
    rollout_revision_id: str = Field(min_length=1, max_length=240)
    rollout_revision_hash: str = Field(pattern=r"^[a-f0-9]{64}$")
    predicted_outcome_id: str = Field(min_length=1, max_length=240)
    branch_id: str = Field(min_length=1, max_length=120)
    observed_at: datetime
    observed_assignment: StateAssignmentV1 | None = None
    observed_assignment_samples: tuple[StateAssignmentV1, ...] = Field(default_factory=tuple, max_length=50)
    evidence_pack_id: str = Field(min_length=1, max_length=240)
    evidence_pack_hash: str = Field(pattern=r"^[a-f0-9]{64}$")
    evidence_refs: tuple[str, ...] = Field(default_factory=tuple, max_length=MAX_PACK_RECORDS)
    foresight_prediction_ref: str | None = Field(default=None, max_length=240)
    foresight_resolution_ref: str | None = Field(default=None, max_length=240)
    authority: ReviewAuthority
    observer_ref: str = Field(min_length=1, max_length=240)
    rationale: str = Field(min_length=1, max_length=2_000)

    @field_validator("product_id")
    @classmethod
    def validate_product(cls, value: str) -> str:
        return _product(value)

    @field_validator("observed_at")
    @classmethod
    def validate_time(cls, value: datetime) -> datetime:
        return _aware(value, "observed_at")

    @field_validator("evidence_refs", mode="before")
    @classmethod
    def normalize_refs(cls, value: Any) -> tuple[str, ...]:
        return _refs(value, limit=MAX_PACK_RECORDS, name="outcome evidence_refs")

    @field_validator("observed_assignment_samples", mode="before")
    @classmethod
    def normalize_samples(cls, value: Any) -> tuple[Any, ...]:
        if not isinstance(value, (list, tuple)):
            raise ValueError("observed assignment samples must be a bounded collection")
        samples = tuple(
            item if isinstance(item, StateAssignmentV1) else StateAssignmentV1.model_validate(item) for item in value
        )
        return tuple(sorted(samples, key=canonical_hash))

    @model_validator(mode="after")
    def derive_identity(self) -> Self:
        if self.authority is ReviewAuthority.MODEL:
            raise ValueError("model authority cannot resolve a rollout outcome")
        if (self.foresight_prediction_ref is None) != (self.foresight_resolution_ref is None):
            raise ValueError("Foresight prediction and resolution references must be paired")
        assignments = (
            *((self.observed_assignment,) if self.observed_assignment is not None else ()),
            *self.observed_assignment_samples,
        )
        if any(item.variable.subject.product_id != self.product_id for item in assignments):
            raise ValueError("rollout observation cannot cross product scope")
        material = self.model_dump(mode="json", exclude={"observation_id", "observation_hash"})
        expected_hash = canonical_hash(material)
        expected_id = f"grounded_rollout_outcome:{expected_hash[:32]}"
        if self.observation_hash is not None and self.observation_hash != expected_hash:
            raise ValueError("rollout observation hash does not match exact material")
        if self.observation_id is not None and self.observation_id != expected_id:
            raise ValueError("rollout observation identity does not match exact material")
        object.__setattr__(self, "observation_hash", expected_hash)
        object.__setattr__(self, "observation_id", expected_id)
        return self


class RolloutReconciliationReceiptV1(FrozenContract):
    contract_version: Literal["ace.grounded-state.rollout-reconciliation/v1"] = ROLLOUT_RECONCILIATION_VERSION
    receipt_id: str | None = None
    receipt_hash: str | None = None
    product_id: str
    rollout_revision_id: str = Field(min_length=1, max_length=240)
    rollout_revision_hash: str = Field(pattern=r"^[a-f0-9]{64}$")
    predicted_outcome_id: str = Field(min_length=1, max_length=240)
    observation_id: str = Field(min_length=1, max_length=240)
    observation_hash: str = Field(pattern=r"^[a-f0-9]{64}$")
    evidence_pack_id: str = Field(min_length=1, max_length=240)
    evidence_pack_hash: str = Field(pattern=r"^[a-f0-9]{64}$")
    branch_id: str = Field(min_length=1, max_length=120)
    disposition: RolloutOutcomeDisposition
    score: float | None = Field(default=None, ge=0, le=1)
    compatible_branch: bool
    compatible_horizon: bool
    reconciled_at: datetime
    policy_version: str = Field(default=TP6_RECONCILIATION_POLICY_VERSION, min_length=1, max_length=160)
    foresight_prediction_ref: str | None = Field(default=None, max_length=240)
    foresight_resolution_ref: str | None = Field(default=None, max_length=240)
    omissions: tuple[str, ...] = Field(default_factory=tuple, max_length=MAX_REASONS)
    failures: tuple[str, ...] = Field(default_factory=tuple, max_length=MAX_REASONS)
    degraded_reasons: tuple[str, ...] = Field(default_factory=tuple, max_length=MAX_REASONS)

    @field_validator("product_id")
    @classmethod
    def validate_product(cls, value: str) -> str:
        return _product(value)

    @field_validator("reconciled_at")
    @classmethod
    def validate_time(cls, value: datetime) -> datetime:
        return _aware(value, "reconciled_at")

    @field_validator("omissions", "failures", "degraded_reasons", mode="before")
    @classmethod
    def normalize_refs(cls, value: Any, info) -> tuple[str, ...]:
        return _refs(value, limit=MAX_REASONS, name=info.field_name)

    @model_validator(mode="after")
    def derive_identity(self) -> Self:
        compatible = self.compatible_branch and self.compatible_horizon
        if not compatible and (self.disposition is not RolloutOutcomeDisposition.UNRESOLVED or self.score is not None):
            raise ValueError("incompatible branch or horizon must remain unresolved and unscored")
        if compatible and self.disposition is not RolloutOutcomeDisposition.UNRESOLVED and self.score is None:
            raise ValueError("resolved compatible rollout outcomes require a bounded score")
        if (self.foresight_prediction_ref is None) != (self.foresight_resolution_ref is None):
            raise ValueError("Foresight prediction and resolution references must be paired")
        material = self.model_dump(mode="json", exclude={"receipt_id", "receipt_hash"})
        expected_hash = canonical_hash(material)
        expected_id = f"grounded_rollout_reconciliation:{expected_hash[:32]}"
        if self.receipt_hash is not None and self.receipt_hash != expected_hash:
            raise ValueError("rollout reconciliation hash does not match exact material")
        if self.receipt_id is not None and self.receipt_id != expected_id:
            raise ValueError("rollout reconciliation identity does not match exact material")
        object.__setattr__(self, "receipt_hash", expected_hash)
        object.__setattr__(self, "receipt_id", expected_id)
        return self


def projection_binding(projection: BeliefStateProjectionV1) -> tuple[str, str, datetime]:
    """Return the exact immutable starting-state coordinates used by TP6."""
    return str(projection.projection_id), str(projection.projection_hash), projection.as_of
