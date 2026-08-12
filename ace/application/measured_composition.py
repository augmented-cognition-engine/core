"""Append-only preregistration and closure for measured composition evidence."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Literal, Self

from pydantic import ConfigDict, Field, field_validator, model_validator
from pydantic_core import to_json

from ace.core.contracts import FrozenContract, canonical_hash
from ace.core.records import (
    AppendOnlyTransactionReceiptV1,
    AppendOnlyTransactionRequestV1,
    ImmutableRecordReferenceV1,
    ImmutableRecordStore,
    ImmutableRecordV1,
    immutable_record_storage_id,
)
from ace.core.runtime_use import AuthenticatedRuntimeContextV1Alpha1, AuthorityUseReceiptV1Alpha1
from ace.core.state import GovernedStateHeadPreconditionV1Alpha1
from ace.intelligence.contracts.measured_composition import (
    COMPOSITION_CONDITION_ASSIGNMENT_VERSION,
    COMPOSITION_EVALUATION_PROTOCOL_VERSION,
    COMPOSITION_MATCHED_COMPARISON_VERSION,
    COMPOSITION_POLICY_CHANGE_PROPOSAL_VERSION,
    COMPOSITION_RUN_OBSERVATION_VERSION,
    CompositionConditionAssignmentV1Alpha1,
    CompositionEvaluationProtocolV1Alpha1,
    CompositionMatchedComparisonV1Alpha1,
    CompositionPolicyChangeProposalV1Alpha1,
    CompositionRunObservationV1Alpha1,
    measured_composition_reference,
)
from ace.intelligence.measured_composition import compare_measured_composition

COMPOSITION_EVALUATION_AUTHORITY_RESOLUTION_VERSION = (
    "ace.application.composition-evaluation-authority-resolution/v1alpha1"
)
MEASURED_COMPOSITION_RECORD_SPACE = "measured_composition"
EVALUATION_AUTHORITY_RECORD_KIND = "evaluation_authority"
EVALUATION_PROTOCOL_RECORD_KIND = "evaluation_protocol"
CONDITION_ASSIGNMENT_RECORD_KIND = "condition_assignment"
RUN_OBSERVATION_RECORD_KIND = "run_observation"
MATCHED_COMPARISON_RECORD_KIND = "matched_comparison"
POLICY_CHANGE_PROPOSAL_RECORD_KIND = "policy_change_proposal"


class _Contract(FrozenContract):
    model_config = ConfigDict(
        extra="forbid",
        frozen=True,
        strict=True,
        revalidate_instances="always",
        validate_default=True,
        allow_inf_nan=False,
    )


def _bounded(value: str, *, name: str) -> str:
    if not value or value != value.strip() or len(value) > 240:
        raise ValueError(f"{name} must be a bounded stable reference")
    return value


def _aware(value: datetime, *, name: str) -> datetime:
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError(f"{name} must include a timezone")
    return value.astimezone(UTC)


def _identity(instance: _Contract, *, prefix: str, id_field: str, digest_field: str) -> None:
    material = instance.model_dump(mode="json", exclude={id_field, digest_field})
    digest = canonical_hash(material)
    expected_id = f"{prefix}:{digest[:32]}"
    expected_digest = f"sha256:{digest}"
    if getattr(instance, id_field) not in {None, expected_id}:
        raise ValueError(f"{id_field} does not match exact material")
    if getattr(instance, digest_field) not in {None, expected_digest}:
        raise ValueError(f"{digest_field} does not match exact material")
    object.__setattr__(instance, id_field, expected_id)
    object.__setattr__(instance, digest_field, expected_digest)


class CompositionEvaluationAuthorityResolutionV1Alpha1(_Contract):
    """One present-tense authorization to preregister and append evaluation evidence."""

    contract: Literal["ace.application.composition-evaluation-authority-resolution/v1alpha1"] = (
        COMPOSITION_EVALUATION_AUTHORITY_RESOLUTION_VERSION
    )
    operation: Literal["evaluate_agent_composition"] = "evaluate_agent_composition"
    product_id: str
    actor_ref: str
    authenticated_context: AuthenticatedRuntimeContextV1Alpha1
    authority_use: AuthorityUseReceiptV1Alpha1
    current_heads: tuple[GovernedStateHeadPreconditionV1Alpha1, ...] = Field(min_length=2, max_length=64)
    evaluated_at: datetime
    reusable_authority: Literal[False] = False
    resolution_id: str | None = None
    resolution_digest: str | None = None

    @field_validator("product_id", "actor_ref")
    @classmethod
    def validate_refs(cls, value: str, info) -> str:
        return _bounded(value, name=info.field_name)

    @field_validator("evaluated_at")
    @classmethod
    def normalize_time(cls, value: datetime) -> datetime:
        return _aware(value, name="evaluated_at")

    @field_validator("current_heads")
    @classmethod
    def normalize_heads(
        cls, value: tuple[GovernedStateHeadPreconditionV1Alpha1, ...]
    ) -> tuple[GovernedStateHeadPreconditionV1Alpha1, ...]:
        keys = [(item.state_kind, item.product_id, item.state_id) for item in value]
        if len(keys) != len(set(keys)):
            raise ValueError("evaluation-authority current heads must be unique")
        return tuple(sorted(value, key=lambda item: (item.state_kind, item.product_id, item.state_id)))

    @model_validator(mode="after")
    def validate_scope_and_identity(self) -> Self:
        if (
            self.authenticated_context.product_id != self.product_id
            or self.authenticated_context.actor_ref != self.actor_ref
            or self.authority_use.product_id != self.product_id
            or self.authority_use.actor_ref != self.actor_ref
            or self.authority_use.operation != self.operation
            or self.authority_use.authority != "evaluate_agent_composition"
            or not (
                self.authenticated_context.authenticated_at <= self.evaluated_at < self.authenticated_context.expires_at
            )
        ):
            raise ValueError("evaluation authority crossed current operation, actor, product, or authentication scope")
        if any(item.product_id != self.product_id for item in self.current_heads):
            raise ValueError("evaluation authority crossed governed-head product scope")
        expected = self.authority_use.state_head_precondition
        if expected not in self.current_heads:
            raise ValueError("evaluation authority omits the exact current grant head")
        _identity(
            self,
            prefix="composition_evaluation_authority_resolution",
            id_field="resolution_id",
            digest_field="resolution_digest",
        )
        return self


def evaluation_authority_reference(
    value: CompositionEvaluationAuthorityResolutionV1Alpha1,
):
    from ace.core.agent_composition import ExactArtifactReferenceV1Alpha1

    return ExactArtifactReferenceV1Alpha1(
        artifact_id=str(value.resolution_id),
        artifact_digest=str(value.resolution_digest),
        artifact_contract=value.contract,
    )


class MeasuredCompositionError(ValueError):
    """Measured-composition registration, resolution, or append failed closed."""


@dataclass(frozen=True, slots=True)
class MeasuredCompositionPreregistration:
    authority: ImmutableRecordReferenceV1
    protocol: ImmutableRecordReferenceV1
    transaction_receipt: AppendOnlyTransactionReceiptV1


@dataclass(frozen=True, slots=True)
class MeasuredCompositionClosure:
    comparison: CompositionMatchedComparisonV1Alpha1
    proposal: CompositionPolicyChangeProposalV1Alpha1 | None
    transaction_receipt: AppendOnlyTransactionReceiptV1


_ARTIFACT_LAYOUT = {
    COMPOSITION_EVALUATION_PROTOCOL_VERSION: (EVALUATION_PROTOCOL_RECORD_KIND, CompositionEvaluationProtocolV1Alpha1),
    COMPOSITION_CONDITION_ASSIGNMENT_VERSION: (
        CONDITION_ASSIGNMENT_RECORD_KIND,
        CompositionConditionAssignmentV1Alpha1,
    ),
    COMPOSITION_RUN_OBSERVATION_VERSION: (RUN_OBSERVATION_RECORD_KIND, CompositionRunObservationV1Alpha1),
    COMPOSITION_MATCHED_COMPARISON_VERSION: (MATCHED_COMPARISON_RECORD_KIND, CompositionMatchedComparisonV1Alpha1),
    COMPOSITION_POLICY_CHANGE_PROPOSAL_VERSION: (
        POLICY_CHANGE_PROPOSAL_RECORD_KIND,
        CompositionPolicyChangeProposalV1Alpha1,
    ),
}


def _artifact_record(
    value,
    *,
    product_id: str,
    record_kind: str,
    artifact_id: str,
    as_of: datetime,
    available_at: datetime,
    processing_order: int,
) -> ImmutableRecordV1:
    return ImmutableRecordV1(
        product_id=product_id,
        record_space=MEASURED_COMPOSITION_RECORD_SPACE,
        record_kind=record_kind,
        record_key=artifact_id,
        payload_contract=value.contract,
        payload=value.model_dump(mode="python"),
        as_of=as_of,
        available_at=available_at,
        processing_order=processing_order,
    )


class MeasuredCompositionEvaluationService:
    """Persist frozen protocol, assignments, observations, comparison, and inert proposal."""

    def __init__(self, *, store: ImmutableRecordStore) -> None:
        self.store = store

    async def _load_artifact(self, reference, *, product_id: str):
        layout = _ARTIFACT_LAYOUT.get(reference.artifact_contract)
        if layout is None:
            raise MeasuredCompositionError("unknown measured-composition artifact contract")
        kind, model = layout
        storage_id = immutable_record_storage_id(
            product_id=product_id,
            record_space=MEASURED_COMPOSITION_RECORD_SPACE,
            record_kind=kind,
            record_key=reference.artifact_id,
        )
        try:
            record = await self.store.load_record(
                storage_id,
                product_id=product_id,
                record_space=MEASURED_COMPOSITION_RECORD_SPACE,
                record_kind=kind,
            )
        except Exception:
            raise MeasuredCompositionError("measured-composition exact load failed closed") from None
        if record is None or record.payload_contract != reference.artifact_contract:
            raise MeasuredCompositionError("measured-composition artifact is unavailable")
        try:
            value = model.model_validate_json(to_json(record.payload))
        except Exception:
            raise MeasuredCompositionError("measured-composition artifact failed exact revalidation") from None
        if measured_composition_reference(value) != reference or record.record_key != reference.artifact_id:
            raise MeasuredCompositionError("measured-composition artifact changed from its exact coordinate")
        return value

    async def _append(
        self,
        *,
        product_id: str,
        transaction_key: str,
        records: tuple[ImmutableRecordV1, ...],
        submitted_at: datetime,
        heads: tuple[GovernedStateHeadPreconditionV1Alpha1, ...],
    ) -> AppendOnlyTransactionReceiptV1:
        request = AppendOnlyTransactionRequestV1(
            product_id=product_id,
            record_space=MEASURED_COMPOSITION_RECORD_SPACE,
            transaction_key=transaction_key,
            records=records,
            submitted_at=submitted_at,
            governed_state_preconditions=heads,
        )
        try:
            receipt = await self.store.append(request)
        except Exception:
            raise MeasuredCompositionError("measured-composition append failed closed") from None
        if receipt != request.receipt():
            raise MeasuredCompositionError("measured-composition append returned divergent receipt material")
        return receipt

    async def preregister(
        self,
        *,
        authority: CompositionEvaluationAuthorityResolutionV1Alpha1,
        protocol: CompositionEvaluationProtocolV1Alpha1,
    ) -> MeasuredCompositionPreregistration:
        if (
            authority.product_id != protocol.product_id
            or protocol.evaluation_authority != evaluation_authority_reference(authority)
            or protocol.current_governed_heads != authority.current_heads
            or authority.evaluated_at > protocol.preregistered_at
        ):
            raise MeasuredCompositionError("protocol does not bind the exact present-tense evaluation authority")
        authority_record = _artifact_record(
            authority,
            product_id=protocol.product_id,
            record_kind=EVALUATION_AUTHORITY_RECORD_KIND,
            artifact_id=str(authority.resolution_id),
            as_of=authority.evaluated_at,
            available_at=protocol.preregistered_at,
            processing_order=0,
        )
        protocol_record = _artifact_record(
            protocol,
            product_id=protocol.product_id,
            record_kind=EVALUATION_PROTOCOL_RECORD_KIND,
            artifact_id=str(protocol.protocol_id),
            as_of=protocol.preregistered_at,
            available_at=protocol.preregistered_at,
            processing_order=1,
        )
        receipt = await self._append(
            product_id=protocol.product_id,
            transaction_key=f"measured_composition_preregistration:{protocol.protocol_id}",
            records=(authority_record, protocol_record),
            submitted_at=protocol.preregistered_at,
            heads=protocol.current_governed_heads,
        )
        return MeasuredCompositionPreregistration(
            authority=receipt.records[0], protocol=receipt.records[1], transaction_receipt=receipt
        )

    async def assign(
        self,
        assignment: CompositionConditionAssignmentV1Alpha1,
    ) -> ImmutableRecordReferenceV1:
        protocol = await self._load_artifact(assignment.protocol, product_id=assignment.product_id)
        if (
            assignment.assigned_at < protocol.preregistered_at
            or assignment.task_inputs != protocol.task_inputs
            or assignment.evidence_inputs != protocol.evidence_inputs
            or assignment.context_inputs != protocol.context_inputs
            or assignment.held_constants != protocol.held_constants
        ):
            raise MeasuredCompositionError("assignment changed the preregistered matched condition material")
        record = _artifact_record(
            assignment,
            product_id=assignment.product_id,
            record_kind=CONDITION_ASSIGNMENT_RECORD_KIND,
            artifact_id=str(assignment.assignment_id),
            as_of=assignment.assigned_at,
            available_at=assignment.assigned_at,
            processing_order=0,
        )
        receipt = await self._append(
            product_id=assignment.product_id,
            transaction_key=f"measured_composition_assignment:{assignment.assignment_id}",
            records=(record,),
            submitted_at=assignment.assigned_at,
            heads=protocol.current_governed_heads,
        )
        return receipt.records[0]

    async def observe(self, observation: CompositionRunObservationV1Alpha1) -> ImmutableRecordReferenceV1:
        protocol = await self._load_artifact(observation.protocol, product_id=observation.product_id)
        assignment = await self._load_artifact(observation.assignment, product_id=observation.product_id)
        if (
            observation.pair_key != assignment.pair_key
            or observation.observed_at < assignment.assigned_at
            or any(
                item.artifact_contract not in protocol.admissible_output_contracts
                for item in observation.output_artifacts
            )
        ):
            raise MeasuredCompositionError("observation crossed assignment or admissible-output closure")
        record = _artifact_record(
            observation,
            product_id=observation.product_id,
            record_kind=RUN_OBSERVATION_RECORD_KIND,
            artifact_id=str(observation.observation_id),
            as_of=observation.observed_at,
            available_at=observation.observed_at,
            processing_order=0,
        )
        receipt = await self._append(
            product_id=observation.product_id,
            transaction_key=f"measured_composition_observation:{observation.observation_id}",
            records=(record,),
            submitted_at=observation.observed_at,
            heads=protocol.current_governed_heads,
        )
        return receipt.records[0]

    async def close(
        self,
        *,
        product_id: str,
        protocol_ref,
        assignment_ref,
        observation_refs: tuple,
        current_policy,
        proposed_policy_rule_ref: str,
        compared_at: datetime,
    ) -> MeasuredCompositionClosure:
        protocol = await self._load_artifact(protocol_ref, product_id=product_id)
        assignment = await self._load_artifact(assignment_ref, product_id=product_id)
        observations = tuple([await self._load_artifact(item, product_id=product_id) for item in observation_refs])
        comparison, proposal = compare_measured_composition(
            protocol,
            assignment,
            observations,
            current_policy=current_policy,
            proposed_policy_rule_ref=proposed_policy_rule_ref,
            compared_at=compared_at,
        )
        records = [
            _artifact_record(
                comparison,
                product_id=protocol.product_id,
                record_kind=MATCHED_COMPARISON_RECORD_KIND,
                artifact_id=str(comparison.comparison_id),
                as_of=compared_at,
                available_at=compared_at,
                processing_order=0,
            )
        ]
        if proposal is not None:
            records.append(
                _artifact_record(
                    proposal,
                    product_id=protocol.product_id,
                    record_kind=POLICY_CHANGE_PROPOSAL_RECORD_KIND,
                    artifact_id=str(proposal.proposal_id),
                    as_of=compared_at,
                    available_at=compared_at,
                    processing_order=1,
                )
            )
        receipt = await self._append(
            product_id=protocol.product_id,
            transaction_key=f"measured_composition_closure:{comparison.comparison_id}",
            records=tuple(records),
            submitted_at=compared_at,
            heads=protocol.current_governed_heads,
        )
        return MeasuredCompositionClosure(comparison=comparison, proposal=proposal, transaction_receipt=receipt)


__all__ = [
    "COMPOSITION_EVALUATION_AUTHORITY_RESOLUTION_VERSION",
    "CONDITION_ASSIGNMENT_RECORD_KIND",
    "EVALUATION_AUTHORITY_RECORD_KIND",
    "EVALUATION_PROTOCOL_RECORD_KIND",
    "MATCHED_COMPARISON_RECORD_KIND",
    "MEASURED_COMPOSITION_RECORD_SPACE",
    "POLICY_CHANGE_PROPOSAL_RECORD_KIND",
    "RUN_OBSERVATION_RECORD_KIND",
    "CompositionEvaluationAuthorityResolutionV1Alpha1",
    "MeasuredCompositionClosure",
    "MeasuredCompositionError",
    "MeasuredCompositionEvaluationService",
    "MeasuredCompositionPreregistration",
    "evaluation_authority_reference",
]
