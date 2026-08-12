"""Provider-neutral contracts for preregistered Agent Memory evaluation.

These contracts describe measurement evidence only. They do not change memory,
ranking, retention, consolidation, promotion, composition, authority, delivery,
or external effects. AM4-dependent cases are inert gated coordinates until an
accepted AM4 artifact is supplied by its owning lane.
"""

from __future__ import annotations

from datetime import UTC, datetime
from enum import StrEnum
from typing import Literal, Self

from pydantic import ConfigDict, Field, field_validator, model_validator

from ace.core.agent_composition import ExactArtifactReferenceV1Alpha1
from ace.core.contracts import FrozenContract, canonical_hash

MEMORY_EVALUATION_CORPUS_VERSION = "ace.intelligence.agent-memory-evaluation-corpus/v1alpha1"
MEMORY_EVALUATION_PROTOCOL_VERSION = "ace.intelligence.agent-memory-evaluation-protocol/v1alpha1"
MEMORY_CONDITION_ASSIGNMENT_VERSION = "ace.intelligence.agent-memory-condition-assignment/v1alpha1"
MEMORY_RUN_OBSERVATION_VERSION = "ace.intelligence.agent-memory-run-observation/v1alpha1"
MEMORY_MATCHED_COMPARISON_VERSION = "ace.intelligence.agent-memory-matched-comparison/v1alpha1"

MAX_ITEMS = 256
EXPECTED_CONDITIONS = {"memory", "no_memory", "full_context"}


class _Contract(FrozenContract):
    model_config = ConfigDict(
        extra="forbid",
        frozen=True,
        strict=True,
        revalidate_instances="always",
        validate_default=True,
        allow_inf_nan=False,
    )


def _bounded(value: str, *, name: str, maximum: int = 240) -> str:
    if not value or value != value.strip() or len(value) > maximum:
        raise ValueError(f"{name} must be non-empty, trimmed, and at most {maximum} characters")
    return value


def _aware(value: datetime, *, name: str) -> datetime:
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError(f"{name} must include a timezone")
    return value.astimezone(UTC)


def _digest(value: str, *, name: str) -> str:
    if len(value) != 71 or not value.startswith("sha256:") or value != value.lower():
        raise ValueError(f"{name} must use lowercase sha256:<64-hex> syntax")
    try:
        int(value[7:], 16)
    except ValueError as exc:
        raise ValueError(f"{name} must use lowercase sha256:<64-hex> syntax") from exc
    return value


def _unique_strings(values: tuple[str, ...], *, name: str, minimum: int = 0) -> tuple[str, ...]:
    if not minimum <= len(values) <= MAX_ITEMS:
        raise ValueError(f"{name} must contain between {minimum} and {MAX_ITEMS} values")
    normalized = tuple(sorted(_bounded(item, name=name) for item in values))
    if len(normalized) != len(set(normalized)):
        raise ValueError(f"{name} must be unique")
    return normalized


def _unique_refs(
    values: tuple[ExactArtifactReferenceV1Alpha1, ...], *, name: str, minimum: int = 0
) -> tuple[ExactArtifactReferenceV1Alpha1, ...]:
    if not minimum <= len(values) <= MAX_ITEMS:
        raise ValueError(f"{name} must contain between {minimum} and {MAX_ITEMS} values")
    keys = [(item.artifact_contract, item.artifact_id, item.artifact_digest) for item in values]
    if len(keys) != len(set(keys)):
        raise ValueError(f"{name} must be unique")
    return tuple(sorted(values, key=lambda item: (item.artifact_contract, item.artifact_id, item.artifact_digest)))


def _identity(instance: _Contract, *, prefix: str, id_field: str, digest_field: str) -> None:
    material = instance.model_dump(mode="json", exclude={id_field, digest_field})
    digest = canonical_hash(material)
    expected_id = f"{prefix}:{digest[:32]}"
    expected_digest = f"sha256:{digest}"
    if getattr(instance, id_field) not in {None, expected_id}:
        raise ValueError(f"{id_field} does not match exact contract material")
    if getattr(instance, digest_field) not in {None, expected_digest}:
        raise ValueError(f"{digest_field} does not match exact contract material")
    object.__setattr__(instance, id_field, expected_id)
    object.__setattr__(instance, digest_field, expected_digest)


class MemoryEvaluationCondition(StrEnum):
    MEMORY = "memory"
    NO_MEMORY = "no_memory"
    FULL_CONTEXT = "full_context"


class EvaluationCaseGate(StrEnum):
    RUNNABLE_AM3 = "runnable_am3"
    FUTURE_ACCEPTED_AM4 = "future_accepted_am4"


class MeasureAvailability(StrEnum):
    AVAILABLE = "available"
    UNAVAILABLE = "unavailable"
    NOT_APPLICABLE = "not_applicable"


class MeasureDirection(StrEnum):
    HIGHER_IS_BETTER = "higher_is_better"
    LOWER_IS_BETTER = "lower_is_better"
    DESCRIPTIVE = "descriptive"
    ZERO_TOLERANCE = "zero_tolerance"


class MeasureUnit(StrEnum):
    BASIS_POINTS = "basis_points"
    COUNT = "count"
    TOKENS = "tokens"
    MILLISECONDS = "milliseconds"
    MICROUNITS = "microunits"


class MemoryMeasure(StrEnum):
    INGESTION_COMPLETENESS_BPS = "ingestion_completeness_bps"
    REPLAY_CORRECTNESS_BPS = "replay_correctness_bps"
    EXTRACTION_PRECISION_BPS = "extraction_precision_bps"
    EXTRACTION_RECALL_BPS = "extraction_recall_bps"
    SOURCE_SPAN_ACCURACY_BPS = "source_span_accuracy_bps"
    IDENTITY_ERROR_BPS = "identity_error_bps"
    UNRESOLVED_IDENTITY_BPS = "unresolved_identity_bps"
    CORRECTION_RECALL_BPS = "correction_recall_bps"
    CONTRADICTION_RECALL_BPS = "contradiction_recall_bps"
    UNCERTAINTY_RECALL_BPS = "uncertainty_recall_bps"
    INSTRUCTION_POLICY_RECALL_BPS = "instruction_policy_recall_bps"
    RETRIEVAL_PRECISION_BPS = "retrieval_precision_bps"
    RETRIEVAL_RECALL_BPS = "retrieval_recall_bps"
    RANK_QUALITY_BPS = "rank_quality_bps"
    CITATION_CORRECTNESS_BPS = "citation_correctness_bps"
    OMISSION_COVERAGE_BPS = "omission_coverage_bps"
    UNAUTHORIZED_RETRIEVAL_COUNT = "unauthorized_retrieval_count"
    STALE_INFLUENCE_COUNT = "stale_influence_count"
    SUPERSEDED_INFLUENCE_COUNT = "superseded_influence_count"
    CONTEXT_TOKENS = "context_tokens"
    RESIDUAL_WINDOW_TOKENS = "residual_window_tokens"
    LATENCY_MS = "latency_ms"
    PROVIDER_CALLS = "provider_calls"
    CACHE_REUSE_COUNT = "cache_reuse_count"
    COST_MICROUNITS = "cost_microunits"
    DEPENDENCY_INVALIDATION_BPS = "dependency_invalidation_bps"
    SELECTED_RATE_BPS = "selected_rate_bps"
    INJECTED_RATE_BPS = "injected_rate_bps"
    REFLECTED_RATE_BPS = "reflected_rate_bps"
    DECISION_MATERIAL_RATE_BPS = "decision_material_rate_bps"
    TASK_CORRECTNESS_BPS = "task_correctness_bps"


class MaterialInfluenceDisposition(StrEnum):
    OBSERVED = "observed"
    NOT_OBSERVED = "not_observed"
    UNDERPOWERED = "underpowered"


class BenefitDisposition(StrEnum):
    BENEFICIAL = "beneficial"
    HARMFUL = "harmful"
    NEUTRAL = "neutral"
    UNDERPOWERED = "underpowered"


class CorrectnessDisposition(StrEnum):
    CORRECT = "correct"
    INCORRECT = "incorrect"
    MIXED = "mixed"
    UNDERPOWERED = "underpowered"


class CausalityDisposition(StrEnum):
    NOT_ESTABLISHED = "not_established"


class MemoryMeasureDefinitionV1Alpha1(_Contract):
    measure: MemoryMeasure
    unit: MeasureUnit
    direction: MeasureDirection
    missing_yields_underpowered: bool = True


class MemoryEvaluationCaseV1Alpha1(_Contract):
    case_id: str
    title: str
    coverage_tags: tuple[str, ...] = Field(min_length=1, max_length=MAX_ITEMS)
    required_measures: tuple[MemoryMeasure, ...] = Field(min_length=1, max_length=len(MemoryMeasure))
    gate: EvaluationCaseGate
    future_required_coordinate: str | None = None

    @field_validator("case_id", "title")
    @classmethod
    def validate_text(cls, value: str, info) -> str:
        return _bounded(value, name=info.field_name)

    @field_validator("coverage_tags")
    @classmethod
    def normalize_tags(cls, value: tuple[str, ...]) -> tuple[str, ...]:
        return _unique_strings(value, name="coverage_tags", minimum=1)

    @field_validator("required_measures")
    @classmethod
    def normalize_measures(cls, value: tuple[MemoryMeasure, ...]) -> tuple[MemoryMeasure, ...]:
        if len(value) != len(set(value)):
            raise ValueError("required measures must be unique")
        return tuple(sorted(value, key=lambda item: item.value))

    @model_validator(mode="after")
    def validate_gate(self) -> Self:
        if self.gate is EvaluationCaseGate.FUTURE_ACCEPTED_AM4:
            if self.future_required_coordinate != "future_accepted_am4_coordinate":
                raise ValueError("AM4-gated cases require only the exact future accepted AM4 coordinate placeholder")
        elif self.future_required_coordinate is not None:
            raise ValueError("AM3-runnable cases cannot require an AM4 coordinate")
        return self


class MemoryEvaluationCorpusV1Alpha1(_Contract):
    contract: Literal["ace.intelligence.agent-memory-evaluation-corpus/v1alpha1"] = MEMORY_EVALUATION_CORPUS_VERSION
    corpus_key: str
    synthetic_only: Literal[True] = True
    source_artifacts: tuple[ExactArtifactReferenceV1Alpha1, ...] = Field(min_length=4, max_length=MAX_ITEMS)
    cases: tuple[MemoryEvaluationCaseV1Alpha1, ...] = Field(min_length=1, max_length=MAX_ITEMS)
    frozen_at: datetime
    corpus_id: str | None = None
    corpus_digest: str | None = None

    @field_validator("corpus_key")
    @classmethod
    def validate_key(cls, value: str) -> str:
        return _bounded(value, name="corpus_key")

    @field_validator("source_artifacts")
    @classmethod
    def normalize_sources(
        cls, value: tuple[ExactArtifactReferenceV1Alpha1, ...]
    ) -> tuple[ExactArtifactReferenceV1Alpha1, ...]:
        return _unique_refs(value, name="source_artifacts", minimum=4)

    @field_validator("cases")
    @classmethod
    def normalize_cases(
        cls, value: tuple[MemoryEvaluationCaseV1Alpha1, ...]
    ) -> tuple[MemoryEvaluationCaseV1Alpha1, ...]:
        ids = [item.case_id for item in value]
        if len(ids) != len(set(ids)):
            raise ValueError("corpus case identities must be unique")
        return tuple(sorted(value, key=lambda item: item.case_id))

    @field_validator("frozen_at")
    @classmethod
    def normalize_time(cls, value: datetime) -> datetime:
        return _aware(value, name="frozen_at")

    @field_validator("corpus_digest")
    @classmethod
    def validate_digest(cls, value: str | None) -> str | None:
        return _digest(value, name="corpus_digest") if value is not None else None

    @model_validator(mode="after")
    def derive_identity(self) -> Self:
        _identity(self, prefix="memory_evaluation_corpus", id_field="corpus_id", digest_field="corpus_digest")
        return self


class MemoryMatchedCoordinatesV1Alpha1(_Contract):
    task: ExactArtifactReferenceV1Alpha1
    provider: ExactArtifactReferenceV1Alpha1
    model: ExactArtifactReferenceV1Alpha1
    prompt_contract: ExactArtifactReferenceV1Alpha1
    decision_schema: ExactArtifactReferenceV1Alpha1
    toolset: ExactArtifactReferenceV1Alpha1
    configuration: ExactArtifactReferenceV1Alpha1


class MemoryEvaluationProtocolV1Alpha1(_Contract):
    contract: Literal["ace.intelligence.agent-memory-evaluation-protocol/v1alpha1"] = MEMORY_EVALUATION_PROTOCOL_VERSION
    protocol_key: str
    corpus: ExactArtifactReferenceV1Alpha1
    conditions: tuple[MemoryEvaluationCondition, ...] = Field(min_length=3, max_length=3)
    measure_definitions: tuple[MemoryMeasureDefinitionV1Alpha1, ...] = Field(
        min_length=len(MemoryMeasure), max_length=len(MemoryMeasure)
    )
    minimum_beneficial_gain_bps: int = Field(ge=1, le=10_000)
    maximum_full_context_correctness_gap_bps: int = Field(ge=0, le=10_000)
    preregistered_at: datetime
    provider_required: Literal[False] = False
    network_required: Literal[False] = False
    changes_rank_policy: Literal[False] = False
    changes_retention_policy: Literal[False] = False
    changes_consolidation_policy: Literal[False] = False
    changes_promotion_policy: Literal[False] = False
    changes_roster_or_authority: Literal[False] = False
    delivers_or_sends_effect: Literal[False] = False
    protocol_id: str | None = None
    protocol_digest: str | None = None

    @field_validator("protocol_key")
    @classmethod
    def validate_key(cls, value: str) -> str:
        return _bounded(value, name="protocol_key")

    @field_validator("conditions")
    @classmethod
    def normalize_conditions(
        cls, value: tuple[MemoryEvaluationCondition, ...]
    ) -> tuple[MemoryEvaluationCondition, ...]:
        if {item.value for item in value} != EXPECTED_CONDITIONS or len(set(value)) != 3:
            raise ValueError("protocol must freeze memory, no-memory, and full-context exactly once")
        return tuple(sorted(value, key=lambda item: item.value))

    @field_validator("measure_definitions")
    @classmethod
    def normalize_definitions(
        cls, value: tuple[MemoryMeasureDefinitionV1Alpha1, ...]
    ) -> tuple[MemoryMeasureDefinitionV1Alpha1, ...]:
        if {item.measure for item in value} != set(MemoryMeasure) or len(value) != len(MemoryMeasure):
            raise ValueError("protocol must freeze the complete AM6 measure registry exactly once")
        unauthorized = next(item for item in value if item.measure is MemoryMeasure.UNAUTHORIZED_RETRIEVAL_COUNT)
        if unauthorized.direction is not MeasureDirection.ZERO_TOLERANCE:
            raise ValueError("unauthorized retrieval must remain a zero-tolerance measure")
        return tuple(sorted(value, key=lambda item: item.measure.value))

    @field_validator("preregistered_at")
    @classmethod
    def normalize_time(cls, value: datetime) -> datetime:
        return _aware(value, name="preregistered_at")

    @field_validator("protocol_digest")
    @classmethod
    def validate_digest(cls, value: str | None) -> str | None:
        return _digest(value, name="protocol_digest") if value is not None else None

    @model_validator(mode="after")
    def validate_corpus_and_identity(self) -> Self:
        if self.corpus.artifact_contract != MEMORY_EVALUATION_CORPUS_VERSION:
            raise ValueError("protocol requires one exact frozen AM6 corpus")
        _identity(self, prefix="memory_evaluation_protocol", id_field="protocol_id", digest_field="protocol_digest")
        return self


class MemoryConditionPlanV1Alpha1(_Contract):
    condition: MemoryEvaluationCondition
    memory_mode: Literal["authorized_selected", "disabled", "full_authorized_context"]

    @model_validator(mode="after")
    def validate_mode(self) -> Self:
        expected = {
            MemoryEvaluationCondition.MEMORY: "authorized_selected",
            MemoryEvaluationCondition.NO_MEMORY: "disabled",
            MemoryEvaluationCondition.FULL_CONTEXT: "full_authorized_context",
        }
        if self.memory_mode != expected[self.condition]:
            raise ValueError("condition plan changed the frozen memory treatment")
        return self


class MemoryConditionAssignmentV1Alpha1(_Contract):
    contract: Literal["ace.intelligence.agent-memory-condition-assignment/v1alpha1"] = (
        MEMORY_CONDITION_ASSIGNMENT_VERSION
    )
    protocol: ExactArtifactReferenceV1Alpha1
    corpus: ExactArtifactReferenceV1Alpha1
    case_id: str
    matched_coordinates: MemoryMatchedCoordinatesV1Alpha1
    condition_plans: tuple[MemoryConditionPlanV1Alpha1, ...] = Field(min_length=3, max_length=3)
    assigned_at: datetime
    assignment_id: str | None = None
    assignment_digest: str | None = None

    @field_validator("case_id")
    @classmethod
    def validate_case_id(cls, value: str) -> str:
        return _bounded(value, name="case_id")

    @field_validator("condition_plans")
    @classmethod
    def normalize_plans(cls, value: tuple[MemoryConditionPlanV1Alpha1, ...]) -> tuple[MemoryConditionPlanV1Alpha1, ...]:
        if {item.condition.value for item in value} != EXPECTED_CONDITIONS or len(
            set(item.condition for item in value)
        ) != 3:
            raise ValueError("assignment must bind all three frozen conditions exactly once")
        return tuple(sorted(value, key=lambda item: item.condition.value))

    @field_validator("assigned_at")
    @classmethod
    def normalize_time(cls, value: datetime) -> datetime:
        return _aware(value, name="assigned_at")

    @field_validator("assignment_digest")
    @classmethod
    def validate_digest(cls, value: str | None) -> str | None:
        return _digest(value, name="assignment_digest") if value is not None else None

    @model_validator(mode="after")
    def derive_identity(self) -> Self:
        if self.protocol.artifact_contract != MEMORY_EVALUATION_PROTOCOL_VERSION:
            raise ValueError("assignment requires the exact preregistered AM6 protocol")
        if self.corpus.artifact_contract != MEMORY_EVALUATION_CORPUS_VERSION:
            raise ValueError("assignment requires the exact frozen AM6 corpus")
        _identity(
            self, prefix="memory_condition_assignment", id_field="assignment_id", digest_field="assignment_digest"
        )
        return self


class MemoryMeasureObservationV1Alpha1(_Contract):
    measure: MemoryMeasure
    availability: MeasureAvailability
    value: int | None = Field(default=None, ge=0)
    stratum: str | None = None
    unavailable_reason: str | None = None

    @field_validator("stratum", "unavailable_reason")
    @classmethod
    def validate_optional_text(cls, value: str | None, info) -> str | None:
        return _bounded(value, name=info.field_name) if value is not None else None

    @model_validator(mode="after")
    def validate_availability(self) -> Self:
        if self.availability is MeasureAvailability.AVAILABLE:
            if self.value is None or self.unavailable_reason is not None:
                raise ValueError("available measurement requires a value and no unavailable reason")
        elif self.value is not None or self.unavailable_reason is None:
            raise ValueError("unavailable or not-applicable measurement requires a reason and no value")
        if self.measure.value.endswith("_bps") and self.value is not None and self.value > 10_000:
            raise ValueError("basis-point measurements cannot exceed 10,000")
        return self


class MemoryRunObservationV1Alpha1(_Contract):
    contract: Literal["ace.intelligence.agent-memory-run-observation/v1alpha1"] = MEMORY_RUN_OBSERVATION_VERSION
    protocol: ExactArtifactReferenceV1Alpha1
    assignment: ExactArtifactReferenceV1Alpha1
    case_id: str
    condition: MemoryEvaluationCondition
    decision_digest: str | None
    route_ref: str
    tier_ref: str
    evidence_artifacts: tuple[ExactArtifactReferenceV1Alpha1, ...] = Field(max_length=MAX_ITEMS)
    measurements: tuple[MemoryMeasureObservationV1Alpha1, ...] = Field(min_length=1, max_length=MAX_ITEMS)
    observed_at: datetime
    observation_id: str | None = None
    observation_digest: str | None = None

    @field_validator("case_id", "route_ref", "tier_ref")
    @classmethod
    def validate_text(cls, value: str, info) -> str:
        return _bounded(value, name=info.field_name)

    @field_validator("decision_digest")
    @classmethod
    def validate_decision_digest(cls, value: str | None) -> str | None:
        return _digest(value, name="decision_digest") if value is not None else None

    @field_validator("evidence_artifacts")
    @classmethod
    def normalize_evidence(
        cls, value: tuple[ExactArtifactReferenceV1Alpha1, ...]
    ) -> tuple[ExactArtifactReferenceV1Alpha1, ...]:
        return _unique_refs(value, name="evidence_artifacts")

    @field_validator("measurements")
    @classmethod
    def normalize_measurements(
        cls, value: tuple[MemoryMeasureObservationV1Alpha1, ...]
    ) -> tuple[MemoryMeasureObservationV1Alpha1, ...]:
        keys = [(item.measure, item.stratum) for item in value]
        if len(keys) != len(set(keys)):
            raise ValueError("measurement and stratum coordinates must be unique")
        return tuple(sorted(value, key=lambda item: (item.measure.value, item.stratum or "")))

    @field_validator("observed_at")
    @classmethod
    def normalize_time(cls, value: datetime) -> datetime:
        return _aware(value, name="observed_at")

    @field_validator("observation_digest")
    @classmethod
    def validate_digest(cls, value: str | None) -> str | None:
        return _digest(value, name="observation_digest") if value is not None else None

    @model_validator(mode="after")
    def derive_identity(self) -> Self:
        if self.protocol.artifact_contract != MEMORY_EVALUATION_PROTOCOL_VERSION:
            raise ValueError("observation requires the exact AM6 protocol")
        if self.assignment.artifact_contract != MEMORY_CONDITION_ASSIGNMENT_VERSION:
            raise ValueError("observation requires the exact matched assignment")
        _identity(self, prefix="memory_run_observation", id_field="observation_id", digest_field="observation_digest")
        return self


class MemoryMatchedComparisonV1Alpha1(_Contract):
    contract: Literal["ace.intelligence.agent-memory-matched-comparison/v1alpha1"] = MEMORY_MATCHED_COMPARISON_VERSION
    protocol: ExactArtifactReferenceV1Alpha1
    assignment: ExactArtifactReferenceV1Alpha1
    case_id: str
    observations: tuple[ExactArtifactReferenceV1Alpha1, ...] = Field(min_length=3, max_length=3)
    paired_and_controlled: bool
    material_influence: MaterialInfluenceDisposition
    benefit: BenefitDisposition
    correctness: CorrectnessDisposition
    causality: Literal[CausalityDisposition.NOT_ESTABLISHED] = CausalityDisposition.NOT_ESTABLISHED
    missing_measurements: tuple[str, ...] = Field(default_factory=tuple, max_length=MAX_ITEMS)
    reasons: tuple[str, ...] = Field(min_length=1, max_length=MAX_ITEMS)
    limitations: tuple[str, ...] = Field(min_length=1, max_length=MAX_ITEMS)
    compared_at: datetime
    changes_any_policy: Literal[False] = False
    changes_authority_or_roster: Literal[False] = False
    comparison_id: str | None = None
    comparison_digest: str | None = None

    @field_validator("case_id")
    @classmethod
    def validate_case_id(cls, value: str) -> str:
        return _bounded(value, name="case_id")

    @field_validator("observations")
    @classmethod
    def normalize_observations(
        cls, value: tuple[ExactArtifactReferenceV1Alpha1, ...]
    ) -> tuple[ExactArtifactReferenceV1Alpha1, ...]:
        return _unique_refs(value, name="observations", minimum=3)

    @field_validator("missing_measurements", "reasons", "limitations")
    @classmethod
    def normalize_text(cls, value: tuple[str, ...], info) -> tuple[str, ...]:
        minimum = 0 if info.field_name == "missing_measurements" else 1
        return _unique_strings(value, name=info.field_name, minimum=minimum)

    @field_validator("compared_at")
    @classmethod
    def normalize_time(cls, value: datetime) -> datetime:
        return _aware(value, name="compared_at")

    @field_validator("comparison_digest")
    @classmethod
    def validate_digest(cls, value: str | None) -> str | None:
        return _digest(value, name="comparison_digest") if value is not None else None

    @model_validator(mode="after")
    def validate_claim_boundary(self) -> Self:
        underpowered = self.benefit is BenefitDisposition.UNDERPOWERED
        if underpowered != bool(self.missing_measurements):
            raise ValueError("underpowered benefit disposition must match explicit missing measurements")
        if underpowered and self.material_influence is not MaterialInfluenceDisposition.UNDERPOWERED:
            raise ValueError("underpowered comparison cannot claim material influence")
        if self.benefit is BenefitDisposition.HARMFUL and self.correctness is CorrectnessDisposition.CORRECT:
            raise ValueError("harmful comparison cannot be labeled fully correct")
        _identity(self, prefix="memory_matched_comparison", id_field="comparison_id", digest_field="comparison_digest")
        return self


def memory_evaluation_reference(value: object) -> ExactArtifactReferenceV1Alpha1:
    layouts = {
        MemoryEvaluationCorpusV1Alpha1: ("corpus_id", "corpus_digest"),
        MemoryEvaluationProtocolV1Alpha1: ("protocol_id", "protocol_digest"),
        MemoryConditionAssignmentV1Alpha1: ("assignment_id", "assignment_digest"),
        MemoryRunObservationV1Alpha1: ("observation_id", "observation_digest"),
        MemoryMatchedComparisonV1Alpha1: ("comparison_id", "comparison_digest"),
    }
    for model, (id_field, digest_field) in layouts.items():
        if isinstance(value, model):
            return ExactArtifactReferenceV1Alpha1(
                artifact_id=str(getattr(value, id_field)),
                artifact_digest=str(getattr(value, digest_field)),
                artifact_contract=value.contract,
            )
    raise TypeError("unsupported Agent Memory evaluation artifact")


__all__ = [
    "MEMORY_CONDITION_ASSIGNMENT_VERSION",
    "MEMORY_EVALUATION_CORPUS_VERSION",
    "MEMORY_EVALUATION_PROTOCOL_VERSION",
    "MEMORY_MATCHED_COMPARISON_VERSION",
    "MEMORY_RUN_OBSERVATION_VERSION",
    "BenefitDisposition",
    "CausalityDisposition",
    "CorrectnessDisposition",
    "EvaluationCaseGate",
    "MaterialInfluenceDisposition",
    "MeasureAvailability",
    "MeasureDirection",
    "MeasureUnit",
    "MemoryConditionAssignmentV1Alpha1",
    "MemoryConditionPlanV1Alpha1",
    "MemoryEvaluationCaseV1Alpha1",
    "MemoryEvaluationCondition",
    "MemoryEvaluationCorpusV1Alpha1",
    "MemoryEvaluationProtocolV1Alpha1",
    "MemoryMatchedComparisonV1Alpha1",
    "MemoryMatchedCoordinatesV1Alpha1",
    "MemoryMeasure",
    "MemoryMeasureDefinitionV1Alpha1",
    "MemoryMeasureObservationV1Alpha1",
    "MemoryRunObservationV1Alpha1",
    "memory_evaluation_reference",
]
