"""Authorized, append-only composition for measured Intelligence impact.

The service exact-loads the public Core lifecycle chain, delegates only the
provider-free classification to :mod:`ace.intelligence.impact`, and atomically
appends the evaluation plus an optional non-effective governance proposal.
"""

from __future__ import annotations

from dataclasses import dataclass

from pydantic_core import to_json

from ace.core.action_execution import (
    ActionAdmissionV1Alpha1,
    ActionTerminalV1Alpha1,
    GovernedActionAuthorizer,
)
from ace.core.action_review import ActionReviewDisposition, ActionReviewReceiptV1Alpha1
from ace.core.contracts import canonical_hash
from ace.core.decisions import DecisionV1Alpha1, OutcomeV1Alpha1
from ace.core.reasoning import (
    ContextUseReceiptV1Alpha1,
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
from ace.intelligence.contracts.impact import (
    IMPACT_EVALUATION_VERSION,
    IMPACT_GOVERNANCE_PROPOSAL_VERSION,
    ImpactConditionsV1Alpha1,
    ImpactEvaluationRequestV1Alpha1,
    ImpactEvaluationV1Alpha1,
    ImpactEvidenceV1Alpha1,
    ImpactGovernanceProposalV1Alpha1,
    ImpactOutcomeMeasuresV1Alpha1,
)
from ace.intelligence.impact import ResolvedImpactEvidence, evaluate_measured_impact

MEASURED_IMPACT_RECORD_SPACE = "measured_impact"
IMPACT_EVALUATION_RECORD_KIND = "impact_evaluation"
IMPACT_PROPOSAL_RECORD_KIND = "impact_governance_proposal"


class MeasuredImpactError(ValueError):
    """Measured-impact resolution, authorization, append, or replay failed closed."""


class MeasuredImpactReplayConflict(MeasuredImpactError):
    """A stable evaluation key already binds different exact material."""


@dataclass(frozen=True, slots=True)
class MeasuredImpactAdmission:
    evaluation: ImpactEvaluationV1Alpha1
    proposal: ImpactGovernanceProposalV1Alpha1 | None
    transaction_receipt: AppendOnlyTransactionReceiptV1
    replayed: bool


def _transaction_key(evaluation_key: str) -> str:
    return f"measured_impact:{canonical_hash([evaluation_key, 'measured_impact'])[:32]}"


def _record(value, *, kind: str, as_of, available_at, processing_order: int) -> ImmutableRecordV1:
    key = str(value.evaluation_id if kind == IMPACT_EVALUATION_RECORD_KIND else value.proposal_id)
    return ImmutableRecordV1(
        product_id=value.product_id,
        record_space=MEASURED_IMPACT_RECORD_SPACE,
        record_kind=kind,
        record_key=key,
        payload_contract=value.contract,
        payload=value.model_dump(mode="python"),
        as_of=as_of,
        available_at=available_at,
        processing_order=processing_order,
    )


class MeasuredImpactService:
    """Compose exact evidence into one durable, proposal-only impact result."""

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
            raise MeasuredImpactError("measured-impact exact record load failed closed") from None
        if record is None or record.reference() != reference:
            raise MeasuredImpactError("measured-impact exact record is unavailable or changed")
        return record

    async def _load_model(self, reference: ImmutableRecordReferenceV1, *, kind: str, model):
        if reference.record_kind != kind:
            raise MeasuredImpactError(f"measured-impact expected exact {kind} reference")
        record = await self._load_exact(reference)
        try:
            value = model.model_validate_json(to_json(record.payload))
        except Exception:
            raise MeasuredImpactError(f"measured-impact {kind} payload failed exact revalidation") from None
        if record.payload_contract != value.contract:
            raise MeasuredImpactError(f"measured-impact {kind} crossed its payload contract")
        return value

    @staticmethod
    def _after_cutoff(reference: ImmutableRecordReferenceV1 | None, *, cutoff_at) -> bool:
        return reference is not None and reference.available_at > cutoff_at

    async def _resolve_variant(
        self,
        *,
        request: ImpactEvaluationRequestV1Alpha1,
        target: ImmutableRecordReferenceV1,
        attribution: ImmutableRecordReferenceV1 | None,
        decision_reference: ImmutableRecordReferenceV1,
        review_reference: ImmutableRecordReferenceV1 | None,
        admission_reference: ImmutableRecordReferenceV1 | None,
        terminal_reference: ImmutableRecordReferenceV1 | None,
        outcome_reference: ImmutableRecordReferenceV1 | None,
        outcome_unavailable_reason: str | None,
        conditions: ImpactConditionsV1Alpha1,
        label: str,
    ) -> tuple[ImpactOutcomeMeasuresV1Alpha1 | None, set[str]]:
        reasons: set[str] = set()
        variant_references = tuple(
            item
            for item in (
                attribution,
                decision_reference,
                review_reference,
                admission_reference,
                terminal_reference,
                outcome_reference,
            )
            if item is not None
        )
        if any(self._after_cutoff(item, cutoff_at=request.cutoff_at) for item in variant_references):
            # Availability metadata is part of the exact reference. Do not load
            # or inspect post-cutoff payloads merely to explain their exclusion.
            return None, {"evidence_after_cutoff"}
        if request.criterion.frozen_at > conditions.observation_window_start:
            reasons.add("criterion_or_conditions_not_frozen_prospectively")
        if attribution is None:
            reasons.add("missing_exact_attribution")
        else:
            attribution_value = await self._load_model(
                attribution,
                kind="context_use",
                model=ContextUseReceiptV1Alpha1,
            )
            if (
                attribution_value.product_id != request.product_id
                or attribution_value.context.storage_id != target.storage_id
                or attribution_value.context.material_digest != target.material_hash
            ):
                reasons.add("attribution_target_mismatch")
            if not attribution_value.output_referenced:
                reasons.add("attribution_not_material_to_output")

        decision = await self._load_model(decision_reference, kind="decision", model=DecisionV1Alpha1)
        if decision.intent.subject != target:
            reasons.add("decision_target_mismatch")
        if conditions.frozen_at > decision.intent.decided_at:
            reasons.add("criterion_or_conditions_not_frozen_prospectively")

        terminal: ActionTerminalV1Alpha1 | None = None
        action_references = (review_reference, admission_reference, terminal_reference)
        if request.criterion.requires_reviewed_action and any(item is None for item in action_references):
            reasons.add("reviewed_action_unavailable")
        elif all(item is not None for item in action_references):
            assert review_reference is not None
            assert admission_reference is not None
            assert terminal_reference is not None
            review = await self._load_model(
                review_reference,
                kind="action_review",
                model=ActionReviewReceiptV1Alpha1,
            )
            admission = await self._load_model(
                admission_reference,
                kind="action_admission",
                model=ActionAdmissionV1Alpha1,
            )
            terminal = await self._load_model(
                terminal_reference,
                kind="action_terminal",
                model=ActionTerminalV1Alpha1,
            )
            if (
                review.disposition is not ActionReviewDisposition.APPROVE
                or review.intent.decision != decision_reference
                or admission.intent != review.intent
                or admission.plan != review.plan
                or terminal.action_key != admission.intent.action_key
                or terminal.admission.receipt_id != admission.receipt_id
                or terminal.admission.receipt_digest != admission.receipt_digest
            ):
                reasons.add("reviewed_action_chain_mismatch")

        if outcome_reference is None:
            if outcome_unavailable_reason is None:
                raise MeasuredImpactError(f"{label} outcome absence lost its explicit reason")
            reasons.add("outcome_unavailable")
            return None, reasons
        outcome = await self._load_model(outcome_reference, kind="outcome", model=OutcomeV1Alpha1)
        if outcome.intent.decision != decision_reference:
            reasons.add("outcome_decision_mismatch")
        if (
            outcome.intent.outcome_type != request.criterion.outcome_type
            or outcome.intent.measure_id != request.criterion.measure_id
        ):
            reasons.add("outcome_measure_mismatch")
        if not (conditions.observation_window_start <= outcome.intent.observed_at <= conditions.observation_window_end):
            reasons.add("outcome_outside_declared_window")
        if terminal is not None and outcome.intent.observed_at < terminal.result.completed_at:
            reasons.add("outcome_predates_action_result")
        try:
            measures = ImpactOutcomeMeasuresV1Alpha1.model_validate_json(outcome.intent.value_json)
        except Exception:
            raise MeasuredImpactError(f"{label} Outcome does not carry exact impact measures") from None
        if measures.primary_value is None:
            reasons.add("outcome_unavailable")
        return measures, reasons

    async def _resolve_evidence(
        self,
        request: ImpactEvaluationRequestV1Alpha1,
        evidence: ImpactEvidenceV1Alpha1,
    ) -> ResolvedImpactEvidence:
        treatment, treatment_reasons = await self._resolve_variant(
            request=request,
            target=request.target,
            attribution=evidence.treatment_attribution,
            decision_reference=evidence.treatment_decision,
            review_reference=evidence.treatment_action_review,
            admission_reference=evidence.treatment_action_admission,
            terminal_reference=evidence.treatment_action_terminal,
            outcome_reference=evidence.treatment_outcome,
            outcome_unavailable_reason=evidence.treatment_outcome_unavailable_reason,
            conditions=evidence.treatment_conditions,
            label="treatment",
        )
        control, control_reasons = await self._resolve_variant(
            request=request,
            target=request.control,
            attribution=evidence.control_attribution,
            decision_reference=evidence.control_decision,
            review_reference=evidence.control_action_review,
            admission_reference=evidence.control_action_admission,
            terminal_reference=evidence.control_action_terminal,
            outcome_reference=evidence.control_outcome,
            outcome_unavailable_reason=evidence.control_outcome_unavailable_reason,
            conditions=evidence.control_conditions,
            label="control",
        )
        reasons = treatment_reasons | control_reasons
        if evidence.treatment_conditions.conditions_digest != evidence.control_conditions.conditions_digest:
            reasons.add("condition_mismatch")
        return ResolvedImpactEvidence(
            evidence_id=str(evidence.evidence_id),
            treatment=treatment,
            control=control,
            exclusion_reasons=tuple(sorted(reasons)),
        )

    async def _replay(
        self,
        *,
        product_id: str,
        evaluation_key: str,
        expected_request_digest: str | None,
    ) -> MeasuredImpactAdmission | None:
        try:
            transaction = await self.store.load_transaction_receipt(
                product_id=product_id,
                record_space=MEASURED_IMPACT_RECORD_SPACE,
                transaction_key=_transaction_key(evaluation_key),
            )
        except Exception:
            raise MeasuredImpactError("measured-impact transaction load failed closed") from None
        if transaction is None:
            return None
        if len(transaction.records) not in {1, 2}:
            raise MeasuredImpactReplayConflict("measured-impact transaction has an invalid exact shape")
        if transaction.records[0].record_kind != IMPACT_EVALUATION_RECORD_KIND:
            raise MeasuredImpactReplayConflict("measured-impact transaction does not begin with an evaluation")
        if len(transaction.records) == 2 and transaction.records[1].record_kind != IMPACT_PROPOSAL_RECORD_KIND:
            raise MeasuredImpactReplayConflict("measured-impact transaction has an invalid proposal record")
        loaded: list[ImmutableRecordV1] = []
        for reference in transaction.records:
            record = await self._load_exact(reference)
            loaded.append(record)
        try:
            evaluation = ImpactEvaluationV1Alpha1.model_validate_json(to_json(loaded[0].payload))
            proposal = (
                ImpactGovernanceProposalV1Alpha1.model_validate_json(to_json(loaded[1].payload))
                if len(loaded) == 2
                else None
            )
        except Exception:
            raise MeasuredImpactReplayConflict("measured-impact transaction failed exact contract replay") from None
        if (
            loaded[0].payload_contract != IMPACT_EVALUATION_VERSION
            or loaded[0].record_key != evaluation.evaluation_id
            or loaded[0].as_of != evaluation.cutoff_at
            or loaded[0].available_at != evaluation.evaluated_at
            or transaction.committed_at != evaluation.evaluated_at
            or evaluation.evaluation_key != evaluation_key
        ):
            raise MeasuredImpactReplayConflict("measured-impact evaluation crossed its durable envelope")
        if proposal is not None and (
            loaded[1].payload_contract != IMPACT_GOVERNANCE_PROPOSAL_VERSION
            or loaded[1].record_key != proposal.proposal_id
            or proposal.evaluation_id != evaluation.evaluation_id
            or proposal.evaluation_digest != evaluation.evaluation_digest
            or proposal.proposed_at != evaluation.evaluated_at
        ):
            raise MeasuredImpactReplayConflict("measured-impact proposal crossed its durable envelope")
        if expected_request_digest is not None and evaluation.request_digest != expected_request_digest:
            raise MeasuredImpactReplayConflict("evaluation key already binds different exact request material")
        return MeasuredImpactAdmission(
            evaluation=evaluation,
            proposal=proposal,
            transaction_receipt=transaction,
            replayed=True,
        )

    async def evaluate(self, request: ImpactEvaluationRequestV1Alpha1) -> MeasuredImpactAdmission:
        """Authorize and append one exact evaluation plus non-effective proposal."""

        try:
            validated = ImpactEvaluationRequestV1Alpha1.model_validate(request.model_dump(mode="python"))
        except Exception:
            raise MeasuredImpactError("measured-impact request failed exact revalidation") from None
        replay = await self._replay(
            product_id=validated.product_id,
            evaluation_key=validated.evaluation_key,
            expected_request_digest=str(validated.request_digest),
        )
        if replay is not None:
            return replay

        await self._load_exact(validated.target)
        await self._load_exact(validated.control)
        resolved = tuple([await self._resolve_evidence(validated, item) for item in validated.evidence])
        required = (
            validated.criterion.state_head_precondition,
            self.operation_binding.state_head_precondition,
        )
        authorization_request = GovernedActionAuthorizationRequestV1Alpha1(
            authorization_key=(
                f"measured_impact_authorization:{canonical_hash([validated.evaluation_key, validated.request_digest])[:32]}"
            ),
            product_id=validated.product_id,
            authenticated_context=validated.authenticated_context,
            execution_binding=self.operation_binding,
            operation="append_immutable_records",
            subject_ref=f"measured_impact_subject:{str(validated.request_digest)[7:39]}",
            subject_digest=str(validated.request_digest),
            requested_at=validated.requested_at,
            required_state_preconditions=required,
        )
        try:
            authorization = await self.authorizer.authorize_action(authorization_request)
        except Exception:
            raise MeasuredImpactError("current authority denied the exact measured-impact append") from None
        if not (validated.requested_at <= authorization.authorized_at < validated.authenticated_context.expires_at):
            raise MeasuredImpactError("measured-impact authorization is outside the authenticated request window")
        expected_preconditions = authorization_request.required_state_preconditions
        if authorization.state_preconditions != expected_preconditions:
            raise MeasuredImpactError("measured-impact authorization changed the frozen governed heads")
        evaluation, proposal = evaluate_measured_impact(
            validated,
            resolved,
            evaluated_at=authorization.authorized_at,
        )
        records = [
            _record(
                evaluation,
                kind=IMPACT_EVALUATION_RECORD_KIND,
                as_of=evaluation.cutoff_at,
                available_at=evaluation.evaluated_at,
                processing_order=0,
            )
        ]
        if proposal is not None:
            records.append(
                _record(
                    proposal,
                    kind=IMPACT_PROPOSAL_RECORD_KIND,
                    as_of=evaluation.cutoff_at,
                    available_at=evaluation.evaluated_at,
                    processing_order=1,
                )
            )
        append = AppendOnlyTransactionRequestV1(
            product_id=validated.product_id,
            record_space=MEASURED_IMPACT_RECORD_SPACE,
            transaction_key=_transaction_key(validated.evaluation_key),
            records=tuple(records),
            submitted_at=evaluation.evaluated_at,
            governed_state_preconditions=authorization.state_preconditions,
        )
        try:
            transaction = await self.store.append(append)
        except (ImmutableRecordReplayConflict, ImmutableRecordPersistenceError):
            replay = await self._replay(
                product_id=validated.product_id,
                evaluation_key=validated.evaluation_key,
                expected_request_digest=str(validated.request_digest),
            )
            if replay is None:
                raise MeasuredImpactError("atomic measured-impact append failed closed") from None
            return replay
        except Exception:
            raise MeasuredImpactError("atomic measured-impact append failed closed") from None
        if transaction != append.receipt():
            raise MeasuredImpactReplayConflict("measured-impact append returned divergent receipt material")
        return MeasuredImpactAdmission(
            evaluation=evaluation,
            proposal=proposal,
            transaction_receipt=transaction,
            replayed=False,
        )


__all__ = [
    "IMPACT_EVALUATION_RECORD_KIND",
    "IMPACT_PROPOSAL_RECORD_KIND",
    "MEASURED_IMPACT_RECORD_SPACE",
    "MeasuredImpactAdmission",
    "MeasuredImpactError",
    "MeasuredImpactReplayConflict",
    "MeasuredImpactService",
]
