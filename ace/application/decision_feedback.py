"""Governed PREPARED Decision -> Outcome -> feedback composition.

This application service closes the narrow conformance loop without promoting
prepared fixtures into LIVE scoring.  Core authorizes and receipts every write,
persists Decision and Outcome records, and governs the policy-state commit.
Intelligence resolves pack eligibility and computes only a bounded proposal.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Callable, Literal, Protocol, TypeVar

from pydantic import BaseModel

from ace.application.domain_activation import (
    CommittedActivationBinding,
    CommittedDomainActivation,
    bind_committed_activation,
)
from ace.core.contracts import canonical_hash
from ace.core.decisions import (
    DecisionIntentV1Alpha1,
    DecisionV1Alpha1,
    OutcomeIntentV1Alpha1,
    OutcomeV1Alpha1,
)
from ace.core.reasoning import (
    GovernedActionAuthorizationProjection,
    GovernedActionAuthorizationRequestV1Alpha1,
    GovernedOperationBindingV1Alpha1,
)
from ace.core.records import (
    AppendOnlyTransactionReceiptV1,
    AppendOnlyTransactionRequestV1,
    ImmutableRecordReferenceV1,
    ImmutableRecordStore,
    ImmutableRecordV1,
)
from ace.core.state import (
    CoreAuthorityResolver,
    GovernedStateCommitReceiptV1,
    GovernedStateCommitRequestV1,
    GovernedStateHeadPreconditionV1Alpha1,
    GovernedStateRevisionV1,
    GovernedStateStore,
)
from ace.intelligence.contracts.feedback import (
    FeedbackPolicyStateV1Alpha1,
    FeedbackPolicyV1,
    FeedbackProposalIntentV1Alpha1,
    FeedbackProposalV1Alpha1,
    OutcomeProvenanceReturnV1Alpha1,
)
from ace.intelligence.contracts.resource_plane import (
    IntelligenceResourceAvailability,
    IntelligenceResourceRecordV1Alpha1,
    IntelligenceResourceReferenceV1Alpha1,
)
from ace.intelligence.contracts.resources import IntelligenceResourceMode
from ace.intelligence.packs.runtime import (
    PreparedActivationBindingError,
    ResolvedFeedbackPolicy,
    resolve_feedback_policy,
)

PREPARED_FEEDBACK_RECORD_SPACE = "prepared"
PREPARED_FEEDBACK_STATE_KIND = "prepared_feedback_policy"


class GovernedActionAuthorizer(Protocol):
    async def authorize_action(
        self,
        request: GovernedActionAuthorizationRequestV1Alpha1,
    ) -> GovernedActionAuthorizationProjection: ...


class ConsumedIntelligenceResourcePort(Protocol):
    """Resolve one exact public Intelligence revision without granting authority."""

    async def load_exact(
        self,
        reference: IntelligenceResourceReferenceV1Alpha1,
        *,
        evaluated_at: datetime,
    ) -> IntelligenceResourceRecordV1Alpha1 | None: ...


class PreparedDecisionFeedbackError(RuntimeError):
    """The prepared Decision/Outcome/feedback loop failed closed."""


class PreparedDecisionFeedbackReplayConflict(PreparedDecisionFeedbackError):
    """Stable P1E identity already binds different material."""


@dataclass(frozen=True, slots=True)
class PreparedDecisionAdmission:
    decision: DecisionV1Alpha1
    record: ImmutableRecordReferenceV1
    authorization: GovernedActionAuthorizationProjection
    transaction_receipt: AppendOnlyTransactionReceiptV1
    mode: Literal[IntelligenceResourceMode.PREPARED] = IntelligenceResourceMode.PREPARED
    live_effect: Literal[False] = False


@dataclass(frozen=True, slots=True)
class PreparedOutcomeAdmission:
    outcome: OutcomeV1Alpha1
    record: ImmutableRecordReferenceV1
    provenance_return: OutcomeProvenanceReturnV1Alpha1
    provenance_record: ImmutableRecordReferenceV1
    authorization: GovernedActionAuthorizationProjection
    transaction_receipt: AppendOnlyTransactionReceiptV1
    mode: Literal[IntelligenceResourceMode.PREPARED] = IntelligenceResourceMode.PREPARED
    live_effect: Literal[False] = False


@dataclass(frozen=True, slots=True)
class PreparedFeedbackProposalAdmission:
    proposal: FeedbackProposalV1Alpha1
    record: ImmutableRecordReferenceV1
    authorization: GovernedActionAuthorizationProjection
    transaction_receipt: AppendOnlyTransactionReceiptV1
    mode: Literal[IntelligenceResourceMode.PREPARED] = IntelligenceResourceMode.PREPARED
    live_effect: Literal[False] = False


@dataclass(frozen=True, slots=True)
class PreparedFeedbackCommit:
    state: FeedbackPolicyStateV1Alpha1
    commit_receipt: GovernedStateCommitReceiptV1
    mode: Literal[IntelligenceResourceMode.PREPARED] = IntelligenceResourceMode.PREPARED
    live_effect: Literal[False] = False


@dataclass(frozen=True, slots=True)
class EffectivePreparedFeedback:
    policy: FeedbackPolicyV1
    value: float
    state: FeedbackPolicyStateV1Alpha1 | None
    commit_receipt: GovernedStateCommitReceiptV1 | None
    mode: Literal[IntelligenceResourceMode.PREPARED] = IntelligenceResourceMode.PREPARED
    live_effect: Literal[False] = False


TModel = TypeVar("TModel", bound=BaseModel)


def _activation_precondition(
    binding: CommittedActivationBinding,
) -> GovernedStateHeadPreconditionV1Alpha1:
    receipt = binding.commit_receipt
    return GovernedStateHeadPreconditionV1Alpha1(
        state_kind=receipt.state_kind,
        product_id=receipt.product_id,
        state_id=receipt.state_id,
        sequence=receipt.sequence,
        revision_id=receipt.revision_id,
        commit_receipt_id=str(receipt.receipt_id),
    )


def _record(
    value: BaseModel,
    *,
    product_id: str,
    record_kind: str,
    record_key: str,
    as_of: datetime,
    available_at: datetime,
    processing_order: int = 0,
) -> ImmutableRecordV1:
    return ImmutableRecordV1(
        product_id=product_id,
        record_space=PREPARED_FEEDBACK_RECORD_SPACE,
        record_kind=record_kind,
        record_key=record_key,
        payload_contract=str(value.contract),
        payload=value.model_dump(mode="python"),
        as_of=as_of,
        available_at=available_at,
        processing_order=processing_order,
    )


class PreparedDecisionFeedbackService:
    """Close one prepared loop while preserving Core authority and history."""

    def __init__(
        self,
        *,
        binding: CommittedActivationBinding,
        record_store: ImmutableRecordStore,
        governed_store: GovernedStateStore,
        authority: CoreAuthorityResolver,
        authorizer: GovernedActionAuthorizer,
        operation_binding: GovernedOperationBindingV1Alpha1,
        intelligence_resources: ConsumedIntelligenceResourcePort,
        clock: Callable[[], datetime],
    ) -> None:
        try:
            self.binding = bind_committed_activation(
                pack=binding.prepared_binding.pack,
                committed=CommittedDomainActivation(
                    revision=binding.prepared_binding.revision,
                    commit_receipt=binding.commit_receipt,
                ),
            )
        except Exception as exc:
            raise PreparedDecisionFeedbackError("a valid Core-committed activation binding is required") from exc
        self.record_store = record_store
        self.governed_store = governed_store
        self.authority = authority
        self.authorizer = authorizer
        self.operation_binding = GovernedOperationBindingV1Alpha1.model_validate(
            operation_binding.model_dump(mode="python")
        )
        self.intelligence_resources = intelligence_resources
        self.clock = clock
        if self.operation_binding.product_id != self.product_id:
            raise PreparedDecisionFeedbackError("operation binding crossed the committed product scope")

    @property
    def product_id(self) -> str:
        return self.binding.prepared_binding.revision.spec.product_id

    def _policy(self, policy_id: str) -> ResolvedFeedbackPolicy:
        try:
            return resolve_feedback_policy(
                self.binding.prepared_binding,
                policy_id=policy_id,
            )
        except PreparedActivationBindingError as exc:
            raise PreparedDecisionFeedbackError(str(exc)) from exc

    async def _load_exact(
        self,
        reference: ImmutableRecordReferenceV1,
        *,
        record_kind: str,
        model: type[TModel],
    ) -> TModel:
        if (
            reference.product_id != self.product_id
            or reference.record_space != PREPARED_FEEDBACK_RECORD_SPACE
            or reference.record_kind != record_kind
        ):
            raise PreparedDecisionFeedbackError(f"{record_kind} reference crossed exact PREPARED product scope")
        try:
            stored = await self.record_store.load_record(
                reference.storage_id,
                product_id=self.product_id,
                record_space=PREPARED_FEEDBACK_RECORD_SPACE,
                record_kind=record_kind,
            )
        except Exception as exc:
            raise PreparedDecisionFeedbackError(f"{record_kind} exact load failed closed") from exc
        if stored is None or stored.reference() != reference:
            raise PreparedDecisionFeedbackError(f"{record_kind} exact immutable record is unavailable")
        try:
            value = model.model_validate(stored.payload)
        except (TypeError, ValueError) as exc:
            raise PreparedDecisionFeedbackError(f"{record_kind} payload failed exact revalidation") from exc
        if stored.payload_contract != str(value.contract):
            raise PreparedDecisionFeedbackError(f"{record_kind} envelope does not match its exact payload contract")
        return value

    async def _require_consumed_intelligence(
        self,
        references: tuple[IntelligenceResourceReferenceV1Alpha1, ...],
        *,
        decided_at: datetime,
    ) -> tuple[IntelligenceResourceReferenceV1Alpha1, ...]:
        if not references:
            raise PreparedDecisionFeedbackError("Outcome provenance return requires consumed Intelligence")
        try:
            exact = tuple(
                IntelligenceResourceReferenceV1Alpha1.model_validate(item.model_dump(mode="python"))
                for item in references
            )
        except (AttributeError, TypeError, ValueError) as exc:
            raise PreparedDecisionFeedbackError("consumed Intelligence references failed exact revalidation") from exc
        keys = tuple(
            (item.resource_kind.value, item.resource_id, item.revision, item.resource_digest) for item in exact
        )
        if len(keys) != len(set(keys)):
            raise PreparedDecisionFeedbackError("consumed Intelligence references must be unique")
        ordered = tuple(
            sorted(
                exact,
                key=lambda item: (
                    item.resource_kind.value,
                    item.resource_id,
                    item.revision,
                    item.resource_digest,
                ),
            )
        )
        for reference in ordered:
            if (
                reference.product_id != self.product_id
                or reference.as_of > decided_at
                or reference.available_at > decided_at
            ):
                raise PreparedDecisionFeedbackError(
                    "consumed Intelligence crossed product scope or Decision availability"
                )
            try:
                record = await self.intelligence_resources.load_exact(
                    reference,
                    evaluated_at=decided_at,
                )
            except Exception as exc:
                raise PreparedDecisionFeedbackError("consumed Intelligence exact load failed closed") from exc
            if (
                record is None
                or record.reference != reference
                or record.availability is not IntelligenceResourceAvailability.AVAILABLE
            ):
                raise PreparedDecisionFeedbackError(
                    "consumed Intelligence exact revision is unavailable or not available"
                )
        return ordered

    async def _authorize(
        self,
        *,
        authorization_key: str,
        operation: str,
        subject_ref: str,
        subject_digest: str,
        authenticated_context,
        requested_at: datetime,
    ) -> GovernedActionAuthorizationProjection:
        request = GovernedActionAuthorizationRequestV1Alpha1(
            authorization_key=authorization_key,
            product_id=self.product_id,
            authenticated_context=authenticated_context,
            execution_binding=self.operation_binding,
            operation=operation,
            subject_ref=subject_ref,
            subject_digest=subject_digest,
            requested_at=requested_at,
            required_state_preconditions=(_activation_precondition(self.binding),),
        )
        try:
            return await self.authorizer.authorize_action(request)
        except Exception as exc:
            raise PreparedDecisionFeedbackError(f"Core authorization for {operation} failed closed") from exc

    async def _append(
        self,
        value: BaseModel,
        *,
        record_kind: str,
        record_key: str,
        as_of: datetime,
        authorization: GovernedActionAuthorizationProjection,
        transaction_key: str,
    ) -> tuple[ImmutableRecordReferenceV1, AppendOnlyTransactionReceiptV1]:
        record = _record(
            value,
            product_id=self.product_id,
            record_kind=record_kind,
            record_key=record_key,
            as_of=as_of,
            available_at=authorization.authorized_at,
        )
        request = AppendOnlyTransactionRequestV1(
            product_id=self.product_id,
            record_space=PREPARED_FEEDBACK_RECORD_SPACE,
            transaction_key=transaction_key,
            records=(record,),
            submitted_at=authorization.authorized_at,
            governed_state_preconditions=authorization.state_preconditions,
        )
        try:
            receipt = await self.record_store.append(request)
        except Exception as exc:
            raise PreparedDecisionFeedbackError(f"authorized {record_kind} append failed closed") from exc
        if receipt != request.receipt():
            raise PreparedDecisionFeedbackReplayConflict(
                f"authorized {record_kind} append returned divergent receipt material"
            )
        return record.reference(), receipt

    async def _load_single_record_replay(
        self,
        *,
        transaction_key: str,
        record_kind: str,
        model: type[TModel],
    ) -> tuple[TModel, ImmutableRecordReferenceV1, AppendOnlyTransactionReceiptV1] | None:
        try:
            receipt = await self.record_store.load_transaction_receipt(
                product_id=self.product_id,
                record_space=PREPARED_FEEDBACK_RECORD_SPACE,
                transaction_key=transaction_key,
            )
        except Exception as exc:
            raise PreparedDecisionFeedbackError(f"{record_kind} replay receipt load failed closed") from exc
        if receipt is None:
            return None
        if len(receipt.records) != 1 or receipt.records[0].record_kind != record_kind:
            raise PreparedDecisionFeedbackReplayConflict(f"{record_kind} replay transaction has an invalid exact shape")
        reference = receipt.records[0]
        value = await self._load_exact(reference, record_kind=record_kind, model=model)
        return value, reference, receipt

    async def _load_outcome_replay(
        self,
        *,
        transaction_key: str,
    ) -> (
        tuple[
            OutcomeV1Alpha1,
            ImmutableRecordReferenceV1,
            OutcomeProvenanceReturnV1Alpha1,
            ImmutableRecordReferenceV1,
            AppendOnlyTransactionReceiptV1,
        ]
        | None
    ):
        try:
            receipt = await self.record_store.load_transaction_receipt(
                product_id=self.product_id,
                record_space=PREPARED_FEEDBACK_RECORD_SPACE,
                transaction_key=transaction_key,
            )
        except Exception as exc:
            raise PreparedDecisionFeedbackError("outcome replay receipt load failed closed") from exc
        if receipt is None:
            return None
        by_kind = {item.record_kind: item for item in receipt.records}
        if len(receipt.records) != 2 or set(by_kind) != {"outcome", "outcome_provenance_return"}:
            raise PreparedDecisionFeedbackReplayConflict("outcome replay transaction has an invalid exact shape")
        outcome_ref = by_kind["outcome"]
        provenance_ref = by_kind["outcome_provenance_return"]
        outcome = await self._load_exact(outcome_ref, record_kind="outcome", model=OutcomeV1Alpha1)
        provenance = await self._load_exact(
            provenance_ref,
            record_kind="outcome_provenance_return",
            model=OutcomeProvenanceReturnV1Alpha1,
        )
        if (
            provenance.outcome != outcome_ref
            or provenance.decision != outcome.intent.decision
            or provenance.actor_ref != outcome.intent.authenticated_context.actor_ref
            or provenance.returned_at != outcome.authorization.authorized_at
        ):
            raise PreparedDecisionFeedbackReplayConflict(
                "outcome provenance replay does not bind the exact Outcome, Decision, actor, and authorization"
            )
        return outcome, outcome_ref, provenance, provenance_ref, receipt

    async def record_decision(
        self,
        intent: DecisionIntentV1Alpha1,
        *,
        policy_id: str,
    ) -> PreparedDecisionAdmission:
        try:
            validated = DecisionIntentV1Alpha1.model_validate(intent.model_dump(mode="python"))
        except (AttributeError, TypeError, ValueError) as exc:
            raise PreparedDecisionFeedbackError("Decision intent failed exact revalidation") from exc
        policy = self._policy(policy_id).policy
        if (
            validated.product_id != self.product_id
            or validated.subject.record_space != PREPARED_FEEDBACK_RECORD_SPACE
            or validated.subject.record_kind != "brief"
            or validated.actor_role_ref != policy.persona_id
            or validated.decision_type != policy.decision_type
            or validated.disposition not in policy.eligible_decision_dispositions
            or validated.action_disposition not in policy.eligible_action_dispositions
        ):
            raise PreparedDecisionFeedbackError("Decision is outside exact pack-declared PREPARED feedback eligibility")
        await self._load_exact(validated.subject, record_kind="brief", model=_OpaquePayload)
        transaction_key = f"decision_intent:{validated.intent_id}"
        replay = await self._load_single_record_replay(
            transaction_key=transaction_key,
            record_kind="decision",
            model=DecisionV1Alpha1,
        )
        if replay is not None:
            decision, record, receipt = replay
            if decision.intent != validated:
                raise PreparedDecisionFeedbackReplayConflict(
                    "stable Decision intent identity already binds different material"
                )
            return PreparedDecisionAdmission(
                decision=decision,
                record=record,
                authorization=decision.authorization,
                transaction_receipt=receipt,
            )
        authorization = await self._authorize(
            authorization_key=f"decision:{validated.intent_id}",
            operation="record_decision",
            subject_ref=str(validated.intent_id),
            subject_digest=str(validated.intent_digest),
            authenticated_context=validated.authenticated_context,
            requested_at=validated.decided_at,
        )
        decision = DecisionV1Alpha1(intent=validated, authorization=authorization)
        record, receipt = await self._append(
            decision,
            record_kind="decision",
            record_key=str(decision.decision_id),
            as_of=validated.decided_at,
            authorization=authorization,
            transaction_key=transaction_key,
        )
        return PreparedDecisionAdmission(
            decision=decision,
            record=record,
            authorization=authorization,
            transaction_receipt=receipt,
        )

    async def record_outcome(
        self,
        intent: OutcomeIntentV1Alpha1,
        *,
        policy_id: str,
        consumed_intelligence: tuple[IntelligenceResourceReferenceV1Alpha1, ...],
    ) -> PreparedOutcomeAdmission:
        try:
            validated = OutcomeIntentV1Alpha1.model_validate(intent.model_dump(mode="python"))
        except (AttributeError, TypeError, ValueError) as exc:
            raise PreparedDecisionFeedbackError("Outcome intent failed exact revalidation") from exc
        policy = self._policy(policy_id).policy
        decision = await self._load_exact(
            validated.decision,
            record_kind="decision",
            model=DecisionV1Alpha1,
        )
        exact_consumed = await self._require_consumed_intelligence(
            consumed_intelligence,
            decided_at=decision.intent.decided_at,
        )
        if (
            decision.intent.actor_role_ref != policy.persona_id
            or decision.intent.decision_type != policy.decision_type
            or decision.intent.disposition not in policy.eligible_decision_dispositions
            or decision.intent.action_disposition not in policy.eligible_action_dispositions
            or validated.outcome_type != policy.outcome_type
            or validated.measure_id != policy.measure_id
        ):
            raise PreparedDecisionFeedbackError("Outcome is outside exact pack-declared PREPARED feedback eligibility")
        transaction_key = f"outcome_intent:{validated.intent_id}"
        replay = await self._load_outcome_replay(transaction_key=transaction_key)
        if replay is not None:
            outcome, record, provenance, provenance_record, receipt = replay
            if outcome.intent != validated or provenance.consumed_intelligence != exact_consumed:
                raise PreparedDecisionFeedbackReplayConflict(
                    "stable Outcome intent identity already binds different Outcome or provenance material"
                )
            return PreparedOutcomeAdmission(
                outcome=outcome,
                record=record,
                provenance_return=provenance,
                provenance_record=provenance_record,
                authorization=outcome.authorization,
                transaction_receipt=receipt,
            )
        authorization = await self._authorize(
            authorization_key=f"outcome:{validated.intent_id}",
            operation="record_outcome",
            subject_ref=str(validated.intent_id),
            subject_digest=str(validated.intent_digest),
            authenticated_context=validated.authenticated_context,
            requested_at=validated.recorded_at,
        )
        outcome = OutcomeV1Alpha1(intent=validated, authorization=authorization)
        outcome_record = _record(
            outcome,
            product_id=self.product_id,
            record_kind="outcome",
            record_key=str(outcome.outcome_id),
            as_of=validated.observed_at,
            available_at=authorization.authorized_at,
        )
        provenance = OutcomeProvenanceReturnV1Alpha1(
            product_id=self.product_id,
            actor_ref=validated.authenticated_context.actor_ref,
            decision=validated.decision,
            outcome=outcome_record.reference(),
            consumed_intelligence=exact_consumed,
            returned_at=authorization.authorized_at,
        )
        provenance_record = _record(
            provenance,
            product_id=self.product_id,
            record_kind="outcome_provenance_return",
            record_key=str(provenance.return_id),
            as_of=validated.observed_at,
            available_at=authorization.authorized_at,
            processing_order=1,
        )
        append_request = AppendOnlyTransactionRequestV1(
            product_id=self.product_id,
            record_space=PREPARED_FEEDBACK_RECORD_SPACE,
            transaction_key=transaction_key,
            records=(outcome_record, provenance_record),
            submitted_at=authorization.authorized_at,
            governed_state_preconditions=authorization.state_preconditions,
        )
        try:
            receipt = await self.record_store.append(append_request)
        except Exception as exc:
            raise PreparedDecisionFeedbackError("authorized Outcome provenance append failed closed") from exc
        if receipt != append_request.receipt():
            raise PreparedDecisionFeedbackReplayConflict(
                "authorized Outcome provenance append returned divergent receipt material"
            )
        return PreparedOutcomeAdmission(
            outcome=outcome,
            record=outcome_record.reference(),
            provenance_return=provenance,
            provenance_record=provenance_record.reference(),
            authorization=authorization,
            transaction_receipt=receipt,
        )

    async def effective_policy(self, policy_id: str) -> EffectivePreparedFeedback:
        policy = self._policy(policy_id).policy
        state_id = f"feedback_policy:{canonical_hash([self.product_id, policy_id])[:32]}"
        try:
            head = await self.governed_store.load_head(
                state_kind=PREPARED_FEEDBACK_STATE_KIND,
                product_id=self.product_id,
                state_id=state_id,
            )
        except Exception as exc:
            raise PreparedDecisionFeedbackError("feedback state head load failed closed") from exc
        if head is None:
            return EffectivePreparedFeedback(
                policy=policy,
                value=policy.initial_value,
                state=None,
                commit_receipt=None,
            )
        revision = await self.governed_store.load_revision(
            head.revision_id,
            product_id=self.product_id,
        )
        receipt = await self.governed_store.load_receipt(
            head.commit_receipt_id,
            product_id=self.product_id,
        )
        if revision is None or receipt is None:
            raise PreparedDecisionFeedbackError("feedback state head does not resolve exact revision and receipt")
        try:
            state = FeedbackPolicyStateV1Alpha1.model_validate(revision.payload)
        except (TypeError, ValueError) as exc:
            raise PreparedDecisionFeedbackError("feedback state payload failed exact revalidation") from exc
        if (
            revision.state_kind != PREPARED_FEEDBACK_STATE_KIND
            or revision.state_id != state.state_id
            or revision.revision_id != state.revision_id
            or revision.material_hash != str(state.revision_digest).removeprefix("sha256:")
            or revision.payload_contract != state.contract
            or state.policy_digest != policy.policy_digest
            or state.activation_revision != self.binding.prepared_binding.reference
            or state.pack != self.binding.prepared_binding.revision.spec.pack
            or not policy.minimum_value <= state.value <= policy.maximum_value
            or receipt.revision_id != revision.revision_id
        ):
            raise PreparedDecisionFeedbackError(
                "feedback state crossed exact policy, activation, Pack, bounds, or receipt"
            )
        return EffectivePreparedFeedback(
            policy=policy,
            value=state.value,
            state=state,
            commit_receipt=receipt,
        )

    async def propose_feedback(
        self,
        outcome_reference: ImmutableRecordReferenceV1,
        *,
        policy_id: str,
        proposed_at: datetime,
    ) -> PreparedFeedbackProposalAdmission:
        resolved = self._policy(policy_id)
        policy = resolved.policy
        outcome = await self._load_exact(
            outcome_reference,
            record_kind="outcome",
            model=OutcomeV1Alpha1,
        )
        decision = await self._load_exact(
            outcome.intent.decision,
            record_kind="decision",
            model=DecisionV1Alpha1,
        )
        if (
            decision.intent.actor_role_ref != policy.persona_id
            or decision.intent.decision_type != policy.decision_type
            or decision.intent.disposition not in policy.eligible_decision_dispositions
            or decision.intent.action_disposition not in policy.eligible_action_dispositions
            or outcome.intent.outcome_type != policy.outcome_type
            or outcome.intent.measure_id != policy.measure_id
        ):
            raise PreparedDecisionFeedbackError("Decision and Outcome are outside exact feedback policy eligibility")
        adjustments = {item.outcome_value_json: item.delta for item in policy.adjustments}
        adjustment = adjustments.get(outcome.intent.value_json)
        if adjustment is None:
            raise PreparedDecisionFeedbackError("Outcome value has no exact declarative adjustment")
        effective = await self.effective_policy(policy_id)
        proposed_value = min(
            policy.maximum_value,
            max(policy.minimum_value, effective.value + adjustment),
        )
        proposal_intent = FeedbackProposalIntentV1Alpha1(
            product_id=self.product_id,
            activation_revision=self.binding.prepared_binding.reference,
            pack=self.binding.prepared_binding.revision.spec.pack,
            policy_id=policy.policy_id,
            policy_digest=policy.policy_digest,
            decision=outcome.intent.decision,
            outcome=outcome_reference,
            prior_state_revision_id=(None if effective.state is None else str(effective.state.revision_id)),
            prior_value=float(effective.value),
            outcome_value_json=outcome.intent.value_json,
            adjustment=float(adjustment),
            proposed_value=float(proposed_value),
            proposed_at=proposed_at,
        )
        transaction_key = f"feedback_proposal_intent:{proposal_intent.intent_id}"
        replay = await self._load_single_record_replay(
            transaction_key=transaction_key,
            record_kind="feedback_proposal",
            model=FeedbackProposalV1Alpha1,
        )
        if replay is not None:
            replayed, record, receipt = replay
            if replayed.intent != proposal_intent:
                raise PreparedDecisionFeedbackReplayConflict(
                    "stable feedback proposal intent already binds different material"
                )
            return PreparedFeedbackProposalAdmission(
                proposal=replayed,
                record=record,
                authorization=replayed.authorization,
                transaction_receipt=receipt,
            )
        authorization = await self._authorize(
            authorization_key=f"feedback_proposal:{proposal_intent.intent_id}",
            operation="propose_feedback",
            subject_ref=str(proposal_intent.intent_id),
            subject_digest=str(proposal_intent.intent_digest),
            authenticated_context=outcome.intent.authenticated_context,
            requested_at=proposal_intent.proposed_at,
        )
        proposal = FeedbackProposalV1Alpha1(
            intent=proposal_intent,
            authorization=authorization,
        )
        record, receipt = await self._append(
            proposal,
            record_kind="feedback_proposal",
            record_key=str(proposal.proposal_id),
            as_of=outcome.intent.observed_at,
            authorization=authorization,
            transaction_key=transaction_key,
        )
        return PreparedFeedbackProposalAdmission(
            proposal=proposal,
            record=record,
            authorization=authorization,
            transaction_receipt=receipt,
        )

    async def commit_feedback(
        self,
        proposal_reference: ImmutableRecordReferenceV1,
        *,
        actor_ref: str,
        approval_receipt_ref: str,
        committed_at: datetime,
    ) -> PreparedFeedbackCommit:
        proposal = await self._load_exact(
            proposal_reference,
            record_kind="feedback_proposal",
            model=FeedbackProposalV1Alpha1,
        )
        intent = proposal.intent
        policy = self._policy(intent.policy_id).policy
        if (
            intent.policy_digest != policy.policy_digest
            or intent.activation_revision != self.binding.prepared_binding.reference
            or intent.pack != self.binding.prepared_binding.revision.spec.pack
            or not policy.minimum_value <= intent.proposed_value <= policy.maximum_value
        ):
            raise PreparedDecisionFeedbackError("feedback proposal crossed exact policy, activation, Pack, or bounds")
        current = await self.effective_policy(policy.policy_id)
        current_revision_id = None if current.state is None else str(current.state.revision_id)
        if (
            current.state is not None
            and current.state.source_proposal == proposal_reference
            and current.state.value == intent.proposed_value
        ):
            if current.commit_receipt is None:
                raise PreparedDecisionFeedbackError("effective feedback replay is missing its Core commit receipt")
            return PreparedFeedbackCommit(
                state=current.state,
                commit_receipt=current.commit_receipt,
            )
        if current_revision_id != intent.prior_state_revision_id:
            raise PreparedDecisionFeedbackError("feedback proposal no longer targets the exact current policy revision")
        state = FeedbackPolicyStateV1Alpha1(
            product_id=self.product_id,
            activation_revision=self.binding.prepared_binding.reference,
            pack=self.binding.prepared_binding.revision.spec.pack,
            policy_id=policy.policy_id,
            policy_digest=policy.policy_digest,
            sequence=1 if current.state is None else current.state.sequence + 1,
            prior_revision_id=current_revision_id,
            value=float(intent.proposed_value),
            source_proposal=proposal_reference,
            effective_at=committed_at,
        )
        approval = await self.authority.resolve_approval(
            receipt_ref=approval_receipt_ref,
            product_id=self.product_id,
            subject_ref=str(proposal.proposal_id),
            actor_ref=actor_ref,
            effective_at=committed_at,
        )
        revision = GovernedStateRevisionV1(
            state_kind=PREPARED_FEEDBACK_STATE_KIND,
            product_id=self.product_id,
            state_id=str(state.state_id),
            sequence=state.sequence,
            revision_id=str(state.revision_id),
            material_hash=str(state.revision_digest).removeprefix("sha256:"),
            prior_revision_id=state.prior_revision_id,
            approval_subject_ref=str(proposal.proposal_id),
            payload_contract=state.contract,
            payload=state.model_dump(mode="python"),
        )
        request = GovernedStateCommitRequestV1(
            revision=revision,
            expected_head_revision_id=current_revision_id,
            actor_ref=actor_ref,
            approval=approval,
            committed_at=committed_at,
        )
        try:
            receipt = await self.governed_store.commit(request)
        except Exception as exc:
            raise PreparedDecisionFeedbackError("Core governed feedback commit failed closed") from exc
        if receipt != request.receipt():
            raise PreparedDecisionFeedbackReplayConflict(
                "Core governed feedback commit returned divergent receipt material"
            )
        return PreparedFeedbackCommit(state=state, commit_receipt=receipt)


class _OpaquePayload(BaseModel):
    """Strict enough for exact envelope checks while keeping Core payload opaque."""

    contract: str

    model_config = {"extra": "allow"}


__all__ = [
    "PREPARED_FEEDBACK_RECORD_SPACE",
    "PREPARED_FEEDBACK_STATE_KIND",
    "EffectivePreparedFeedback",
    "GovernedActionAuthorizer",
    "PreparedDecisionAdmission",
    "PreparedDecisionFeedbackError",
    "PreparedDecisionFeedbackReplayConflict",
    "PreparedDecisionFeedbackService",
    "PreparedFeedbackCommit",
    "PreparedFeedbackProposalAdmission",
    "PreparedOutcomeAdmission",
]
