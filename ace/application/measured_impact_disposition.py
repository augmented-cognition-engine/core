"""Authorized disposition of one exact measured-impact proposal.

The service composes Intelligence's non-effective proposal with Core's generic
Decision and immutable-record contracts.  Acceptance or rejection is durable,
but neither disposition applies the proposed governance action.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Literal, Self

from pydantic import ConfigDict, Field, field_validator, model_validator
from pydantic_core import to_json

from ace.application.measured_impact import (
    IMPACT_EVALUATION_RECORD_KIND,
    IMPACT_PROPOSAL_RECORD_KIND,
    MEASURED_IMPACT_RECORD_SPACE,
)
from ace.core.action_execution import GovernedActionAuthorizer
from ace.core.contracts import FrozenContract, canonical_hash
from ace.core.decisions import (
    DECISION_VERSION,
    DecisionActionDisposition,
    DecisionDisposition,
    DecisionIntentV1Alpha1,
    DecisionV1Alpha1,
)
from ace.core.reasoning import (
    GovernedActionAuthorizationRequestV1Alpha1,
    GovernedOperationBindingV1Alpha1,
)
from ace.core.records import (
    AppendOnlyTransactionReceiptV1,
    AppendOnlyTransactionRequestV1,
    ImmutableRecordPersistenceError,
    ImmutableRecordReferenceV1,
    ImmutableRecordReplayConflict,
    ImmutableRecordStore,
    ImmutableRecordV1,
)
from ace.core.runtime_use import AuthenticatedRuntimeContextV1Alpha1
from ace.intelligence.contracts.impact import (
    IMPACT_EVALUATION_VERSION,
    IMPACT_GOVERNANCE_PROPOSAL_VERSION,
    ImpactEvaluationV1Alpha1,
    ImpactGovernanceProposalV1Alpha1,
)

MEASURED_IMPACT_DISPOSITION_REQUEST_VERSION = "ace.application.measured-impact-disposition-request/v1alpha1"
IMPACT_PROPOSAL_DISPOSITION_DECISION_TYPE = "impact_governance_proposal_disposition"
IMPACT_PROPOSAL_DISPOSITION_RECORD_KIND = "decision"


class _StrictFrozenContract(FrozenContract):
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


class MeasuredImpactDispositionRequestV1Alpha1(_StrictFrozenContract):
    """One exact authenticated principal's accept/reject review of a proposal."""

    contract: Literal["ace.application.measured-impact-disposition-request/v1alpha1"] = (
        MEASURED_IMPACT_DISPOSITION_REQUEST_VERSION
    )
    product_id: str
    authenticated_context: AuthenticatedRuntimeContextV1Alpha1
    evaluation: ImmutableRecordReferenceV1
    proposal: ImmutableRecordReferenceV1
    reviewer_role_ref: str
    disposition: DecisionDisposition
    rationale: str = Field(min_length=1, max_length=10_000)
    decided_at: datetime

    @field_validator("product_id", "reviewer_role_ref")
    @classmethod
    def validate_references(cls, value: str, info) -> str:
        return _bounded(value, name=info.field_name)

    @field_validator("rationale")
    @classmethod
    def validate_rationale(cls, value: str) -> str:
        return _bounded(value, name="rationale", maximum=10_000)

    @field_validator("decided_at")
    @classmethod
    def normalize_decided_at(cls, value: datetime) -> datetime:
        return _aware(value, name="decided_at")

    @field_validator("disposition")
    @classmethod
    def validate_disposition(cls, value: DecisionDisposition) -> DecisionDisposition:
        if value not in {DecisionDisposition.ACCEPT, DecisionDisposition.REJECT}:
            raise ValueError("measured-impact proposal disposition must be accept or reject")
        return value

    @model_validator(mode="after")
    def validate_scope_time_and_exact_closure(self) -> Self:
        if self.authenticated_context.product_id != self.product_id:
            raise ValueError("measured-impact disposition crossed authenticated product scope")
        if self.evaluation.product_id != self.product_id or self.proposal.product_id != self.product_id:
            raise ValueError("measured-impact disposition crossed exact record product scope")
        if (
            self.evaluation.record_space != MEASURED_IMPACT_RECORD_SPACE
            or self.evaluation.record_kind != IMPACT_EVALUATION_RECORD_KIND
            or self.evaluation.processing_order != 0
        ):
            raise ValueError("measured-impact disposition requires one exact evaluation record")
        if (
            self.proposal.record_space != MEASURED_IMPACT_RECORD_SPACE
            or self.proposal.record_kind != IMPACT_PROPOSAL_RECORD_KIND
            or self.proposal.processing_order != 1
        ):
            raise ValueError("measured-impact disposition requires one exact proposal record")
        if self.evaluation.as_of != self.proposal.as_of or self.evaluation.available_at != self.proposal.available_at:
            raise ValueError("measured-impact disposition records did not share one atomic evaluation closure")
        if self.evaluation.available_at > self.decided_at or self.proposal.available_at > self.decided_at:
            raise ValueError("measured-impact proposal was unavailable when disposition was decided")
        if not (self.authenticated_context.authenticated_at <= self.decided_at < self.authenticated_context.expires_at):
            raise ValueError("measured-impact disposition must occur inside the authenticated window")
        return self


class MeasuredImpactDispositionError(ValueError):
    """Proposal disposition resolution, authorization, append, or replay failed closed."""


class MeasuredImpactDispositionReplayConflict(MeasuredImpactDispositionError):
    """The exact proposal already binds different disposition material."""


@dataclass(frozen=True, slots=True)
class MeasuredImpactDispositionAdmission:
    decision: DecisionV1Alpha1
    transaction_receipt: AppendOnlyTransactionReceiptV1
    replayed: bool

    @property
    def decision_reference(self) -> ImmutableRecordReferenceV1:
        return self.transaction_receipt.records[0]


def _transaction_key(proposal: ImmutableRecordReferenceV1) -> str:
    return f"measured_impact_disposition:{canonical_hash(proposal.model_dump(mode='json'))[:32]}"


class MeasuredImpactDispositionService:
    """Record one exact accept/reject Decision without applying the proposal."""

    def __init__(
        self,
        *,
        store: ImmutableRecordStore,
        authorizer: GovernedActionAuthorizer,
        operation_binding: GovernedOperationBindingV1Alpha1,
    ) -> None:
        self.store = store
        self.authorizer = authorizer
        self.operation_binding = GovernedOperationBindingV1Alpha1.model_validate(
            operation_binding.model_dump(mode="python")
        )

    async def _load_exact(self, reference: ImmutableRecordReferenceV1) -> ImmutableRecordV1:
        try:
            record = await self.store.load_record(
                reference.storage_id,
                product_id=reference.product_id,
                record_space=reference.record_space,
                record_kind=reference.record_kind,
            )
        except Exception:
            raise MeasuredImpactDispositionError("measured-impact disposition exact load failed closed") from None
        if record is None or record.reference() != reference:
            raise MeasuredImpactDispositionError("measured-impact disposition record is unavailable or changed")
        return record

    async def _load_model(self, reference: ImmutableRecordReferenceV1, *, contract: str, model):
        record = await self._load_exact(reference)
        try:
            value = model.model_validate_json(to_json(record.payload))
        except Exception:
            raise MeasuredImpactDispositionError(
                "measured-impact disposition payload failed exact revalidation"
            ) from None
        if record.payload_contract != contract:
            raise MeasuredImpactDispositionError("measured-impact disposition crossed its payload contract")
        return record, value

    async def _resolve(
        self,
        request: MeasuredImpactDispositionRequestV1Alpha1,
    ) -> tuple[ImpactEvaluationV1Alpha1, ImpactGovernanceProposalV1Alpha1, DecisionIntentV1Alpha1]:
        evaluation_record, evaluation = await self._load_model(
            request.evaluation,
            contract=IMPACT_EVALUATION_VERSION,
            model=ImpactEvaluationV1Alpha1,
        )
        proposal_record, proposal = await self._load_model(
            request.proposal,
            contract=IMPACT_GOVERNANCE_PROPOSAL_VERSION,
            model=ImpactGovernanceProposalV1Alpha1,
        )
        await self._load_exact(proposal.target)
        if (
            evaluation_record.record_key != evaluation.evaluation_id
            or evaluation_record.as_of != evaluation.cutoff_at
            or evaluation_record.available_at != evaluation.evaluated_at
            or proposal_record.record_key != proposal.proposal_id
            or proposal_record.as_of != evaluation.cutoff_at
            or proposal_record.available_at != evaluation.evaluated_at
        ):
            raise MeasuredImpactDispositionError("measured-impact disposition crossed its durable envelope")
        if (
            proposal.evaluation_id != evaluation.evaluation_id
            or proposal.evaluation_digest != evaluation.evaluation_digest
            or proposal.target != evaluation.target
            or proposal.proposed_at != evaluation.evaluated_at
        ):
            raise MeasuredImpactDispositionError("proposal did not bind the exact evaluation and target")
        intent = DecisionIntentV1Alpha1(
            product_id=request.product_id,
            authenticated_context=request.authenticated_context,
            subject=request.proposal,
            actor_role_ref=request.reviewer_role_ref,
            decision_type=IMPACT_PROPOSAL_DISPOSITION_DECISION_TYPE,
            disposition=request.disposition,
            action_disposition=DecisionActionDisposition.NO_ACTION,
            action_type=None,
            rationale=request.rationale,
            decided_at=request.decided_at,
        )
        return evaluation, proposal, intent

    async def _replay(
        self,
        *,
        request: MeasuredImpactDispositionRequestV1Alpha1,
        expected_intent: DecisionIntentV1Alpha1,
    ) -> MeasuredImpactDispositionAdmission | None:
        try:
            receipt = await self.store.load_transaction_receipt(
                product_id=request.product_id,
                record_space=MEASURED_IMPACT_RECORD_SPACE,
                transaction_key=_transaction_key(request.proposal),
            )
        except Exception:
            raise MeasuredImpactDispositionError("measured-impact disposition replay load failed closed") from None
        if receipt is None:
            return None
        if len(receipt.records) != 1 or receipt.records[0].record_kind != IMPACT_PROPOSAL_DISPOSITION_RECORD_KIND:
            raise MeasuredImpactDispositionReplayConflict("proposal disposition transaction has an invalid shape")
        record = await self._load_exact(receipt.records[0])
        try:
            decision = DecisionV1Alpha1.model_validate_json(to_json(record.payload))
        except Exception:
            raise MeasuredImpactDispositionReplayConflict("proposal disposition failed exact Decision replay") from None
        if (
            record.payload_contract != DECISION_VERSION
            or record.record_key != decision.decision_id
            or record.as_of != decision.intent.decided_at
            or record.available_at != decision.authorization.authorized_at
            or receipt.committed_at != decision.authorization.authorized_at
            or decision.intent != expected_intent
            or decision.intent.subject != request.proposal
            or decision.intent.decision_type != IMPACT_PROPOSAL_DISPOSITION_DECISION_TYPE
            or decision.intent.action_disposition is not DecisionActionDisposition.NO_ACTION
        ):
            raise MeasuredImpactDispositionReplayConflict("exact proposal already binds different disposition material")
        return MeasuredImpactDispositionAdmission(
            decision=decision,
            transaction_receipt=receipt,
            replayed=True,
        )

    async def decide(
        self,
        request: MeasuredImpactDispositionRequestV1Alpha1,
    ) -> MeasuredImpactDispositionAdmission:
        """Authorize and append one exact non-applying proposal disposition."""

        try:
            validated = MeasuredImpactDispositionRequestV1Alpha1.model_validate(request.model_dump(mode="python"))
        except Exception:
            raise MeasuredImpactDispositionError(
                "measured-impact disposition request failed exact revalidation"
            ) from None
        evaluation, _, intent = await self._resolve(validated)
        replay = await self._replay(request=validated, expected_intent=intent)
        if replay is not None:
            return replay

        required = (
            evaluation.criterion.state_head_precondition,
            self.operation_binding.state_head_precondition,
        )
        authorization_request = GovernedActionAuthorizationRequestV1Alpha1(
            authorization_key=(
                "measured_impact_disposition_authorization:"
                f"{canonical_hash([validated.proposal.storage_id, intent.intent_digest])[:32]}"
            ),
            product_id=validated.product_id,
            authenticated_context=validated.authenticated_context,
            execution_binding=self.operation_binding,
            operation="append_immutable_records",
            subject_ref=str(intent.intent_id),
            subject_digest=str(intent.intent_digest),
            requested_at=validated.decided_at,
            required_state_preconditions=required,
        )
        try:
            authorization = await self.authorizer.authorize_action(authorization_request)
        except Exception:
            raise MeasuredImpactDispositionError(
                "current authority denied the exact measured-impact proposal disposition"
            ) from None
        if not (validated.decided_at <= authorization.authorized_at < validated.authenticated_context.expires_at):
            raise MeasuredImpactDispositionError(
                "measured-impact disposition authorization is outside the authenticated window"
            )
        authorized_preconditions = {
            (item.state_kind, item.product_id, item.state_id): item for item in authorization.state_preconditions
        }
        if any(
            authorized_preconditions.get((item.state_kind, item.product_id, item.state_id)) != item for item in required
        ):
            raise MeasuredImpactDispositionError(
                "measured-impact disposition authorization changed the frozen governed heads"
            )

        decision = DecisionV1Alpha1(intent=intent, authorization=authorization)
        record = ImmutableRecordV1(
            product_id=validated.product_id,
            record_space=MEASURED_IMPACT_RECORD_SPACE,
            record_kind=IMPACT_PROPOSAL_DISPOSITION_RECORD_KIND,
            record_key=str(decision.decision_id),
            payload_contract=decision.contract,
            payload=decision.model_dump(mode="python"),
            as_of=decision.intent.decided_at,
            available_at=decision.authorization.authorized_at,
            processing_order=0,
        )
        append = AppendOnlyTransactionRequestV1(
            product_id=validated.product_id,
            record_space=MEASURED_IMPACT_RECORD_SPACE,
            transaction_key=_transaction_key(validated.proposal),
            records=(record,),
            submitted_at=decision.authorization.authorized_at,
            governed_state_preconditions=authorization.state_preconditions,
        )
        try:
            receipt = await self.store.append(append)
        except (ImmutableRecordReplayConflict, ImmutableRecordPersistenceError):
            replay = await self._replay(request=validated, expected_intent=intent)
            if replay is None:
                raise MeasuredImpactDispositionError("measured-impact disposition append failed closed") from None
            return replay
        except Exception:
            raise MeasuredImpactDispositionError("measured-impact disposition append failed closed") from None
        if receipt != append.receipt():
            raise MeasuredImpactDispositionReplayConflict(
                "measured-impact disposition append returned divergent receipt material"
            )
        return MeasuredImpactDispositionAdmission(
            decision=decision,
            transaction_receipt=receipt,
            replayed=False,
        )


__all__ = [
    "IMPACT_PROPOSAL_DISPOSITION_DECISION_TYPE",
    "IMPACT_PROPOSAL_DISPOSITION_RECORD_KIND",
    "MEASURED_IMPACT_DISPOSITION_REQUEST_VERSION",
    "MeasuredImpactDispositionAdmission",
    "MeasuredImpactDispositionError",
    "MeasuredImpactDispositionReplayConflict",
    "MeasuredImpactDispositionRequestV1Alpha1",
    "MeasuredImpactDispositionService",
]
