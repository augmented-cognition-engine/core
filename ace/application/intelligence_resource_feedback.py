"""Governed write service for exact Intelligence-resource feedback."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Protocol

from ace.core.agent_composition import AuthorityClass
from ace.core.records import AppendOnlyTransactionRequestV1, ImmutableRecordStore, ImmutableRecordV1
from ace.core.runtime_use import AuthorityUseReceiptV1Alpha1
from ace.intelligence.contracts.resource_feedback import (
    IntelligenceResourceFeedbackAdmissionV1Alpha1,
    IntelligenceResourceFeedbackReceiptV1Alpha1,
    IntelligenceResourceFeedbackRequestV1Alpha1,
)
from ace.intelligence.contracts.resource_plane import (
    IntelligenceResourceRecordV1Alpha1,
    IntelligenceResourceReferenceV1Alpha1,
)

RESOURCE_FEEDBACK_RECORD_SPACE = "feedback"
RESOURCE_FEEDBACK_RECORD_KIND = "resource_feedback"
RESOURCE_FEEDBACK_OPERATION = "submit_intelligence_resource_feedback"
RESOURCE_FEEDBACK_AUTHORITY = AuthorityClass.DERIVE_PROPOSE.value


class IntelligenceResourceFeedbackError(RuntimeError):
    """The exact feedback proposal failed closed."""


class IntelligenceResourceFeedbackReplayConflict(IntelligenceResourceFeedbackError):
    """An actor-scoped request key was already used for different material."""


class IntelligenceResourceFeedbackDenied(IntelligenceResourceFeedbackError):
    """Current Core authority did not permit this proposal."""


class IntelligenceResourceFeedbackUnavailable(IntelligenceResourceFeedbackError):
    """Required exact resource or immutable storage could not be reached."""


class IntelligenceResourceFeedbackTargetPort(Protocol):
    async def load_exact(
        self,
        reference: IntelligenceResourceReferenceV1Alpha1,
        *,
        evaluated_at: datetime,
    ) -> IntelligenceResourceRecordV1Alpha1 | None: ...


class IntelligenceResourceFeedbackAuthorizationPort(Protocol):
    async def resolve_authority_use(
        self,
        *,
        context,
        use_subject_ref: str,
        use_subject_digest: str,
        operation: str,
        authority: str,
        grant_ref: str,
        evaluated_at: datetime,
    ) -> AuthorityUseReceiptV1Alpha1: ...


def _aware(value: datetime, *, name: str) -> datetime:
    if value.tzinfo is None or value.utcoffset() is None:
        raise IntelligenceResourceFeedbackError(f"{name} must include a timezone")
    return value.astimezone(UTC)


def _exact_request(value: IntelligenceResourceFeedbackRequestV1Alpha1) -> IntelligenceResourceFeedbackRequestV1Alpha1:
    try:
        return IntelligenceResourceFeedbackRequestV1Alpha1.model_validate(value.model_dump(mode="python"))
    except (AttributeError, TypeError, ValueError) as exc:
        raise IntelligenceResourceFeedbackError("resource feedback request failed exact revalidation") from exc


class IntelligenceResourceFeedbackService:
    """Record an attributed proposal without mutating the target or claiming effects."""

    def __init__(
        self,
        *,
        records: ImmutableRecordStore,
        targets: IntelligenceResourceFeedbackTargetPort,
        authority: IntelligenceResourceFeedbackAuthorizationPort,
    ) -> None:
        self.records = records
        self.targets = targets
        self.authority = authority

    async def _require_exact_resource(
        self,
        reference: IntelligenceResourceReferenceV1Alpha1,
        *,
        evaluated_at: datetime,
        label: str,
    ) -> IntelligenceResourceRecordV1Alpha1:
        try:
            record = await self.targets.load_exact(reference, evaluated_at=evaluated_at)
        except Exception as exc:
            raise IntelligenceResourceFeedbackUnavailable(f"{label} exact load failed closed") from exc
        if record is None or record.reference != reference:
            raise IntelligenceResourceFeedbackError(f"{label} exact revision is unavailable")
        return record

    async def _load_replay(
        self,
        request: IntelligenceResourceFeedbackRequestV1Alpha1,
    ) -> IntelligenceResourceFeedbackAdmissionV1Alpha1 | None:
        transaction_key = f"resource_feedback:{request.feedback_id}"
        try:
            transaction = await self.records.load_transaction_receipt(
                product_id=request.product_id,
                record_space=RESOURCE_FEEDBACK_RECORD_SPACE,
                transaction_key=transaction_key,
            )
        except Exception as exc:
            raise IntelligenceResourceFeedbackUnavailable("feedback replay receipt load failed closed") from exc
        if transaction is None:
            return None
        if len(transaction.records) != 1:
            raise IntelligenceResourceFeedbackReplayConflict("feedback replay transaction has an invalid shape")
        reference = transaction.records[0]
        if reference.record_kind != RESOURCE_FEEDBACK_RECORD_KIND or reference.record_key != request.feedback_id:
            raise IntelligenceResourceFeedbackReplayConflict("feedback replay crossed its stable request identity")
        try:
            stored = await self.records.load_record(
                reference.storage_id,
                product_id=request.product_id,
                record_space=RESOURCE_FEEDBACK_RECORD_SPACE,
                record_kind=RESOURCE_FEEDBACK_RECORD_KIND,
            )
        except Exception as exc:
            raise IntelligenceResourceFeedbackUnavailable("feedback replay resource load failed closed") from exc
        if stored is None or stored.reference() != reference:
            raise IntelligenceResourceFeedbackReplayConflict("feedback replay resource is unavailable")
        try:
            feedback = IntelligenceResourceFeedbackReceiptV1Alpha1.model_validate(stored.payload)
        except (TypeError, ValueError) as exc:
            raise IntelligenceResourceFeedbackReplayConflict("feedback replay payload is invalid") from exc
        if (
            stored.payload_contract != feedback.contract
            or feedback.request.feedback_id != request.feedback_id
            or feedback.request.feedback_digest != request.feedback_digest
        ):
            raise IntelligenceResourceFeedbackReplayConflict(
                "request_key was already used for different correction material"
            )
        return IntelligenceResourceFeedbackAdmissionV1Alpha1(
            feedback=feedback,
            record=reference,
            transaction=transaction,
        )

    async def submit(
        self,
        value: IntelligenceResourceFeedbackRequestV1Alpha1,
        *,
        evaluated_at: datetime,
    ) -> IntelligenceResourceFeedbackAdmissionV1Alpha1:
        request = _exact_request(value)
        evaluated = _aware(evaluated_at, name="evaluated_at")
        if evaluated != request.requested_at:
            raise IntelligenceResourceFeedbackError("feedback evaluation must equal its attributed request time")

        await self._require_exact_resource(request.target, evaluated_at=evaluated, label="target")
        for evidence in request.evidence:
            await self._require_exact_resource(evidence, evaluated_at=evaluated, label="evidence")

        try:
            resolved = await self.authority.resolve_authority_use(
                context=request.authenticated_context,
                use_subject_ref=str(request.feedback_id),
                use_subject_digest=str(request.feedback_digest),
                operation=RESOURCE_FEEDBACK_OPERATION,
                authority=RESOURCE_FEEDBACK_AUTHORITY,
                grant_ref=request.authority_grant_ref,
                evaluated_at=evaluated,
            )
            authority = AuthorityUseReceiptV1Alpha1.model_validate(resolved.model_dump(mode="python"))
        except Exception as exc:
            raise IntelligenceResourceFeedbackDenied("current feedback authority denied the request") from exc
        if (
            authority.product_id != request.product_id
            or authority.actor_ref != request.authenticated_context.actor_ref
            or authority.authenticated_context != request.authenticated_context
            or authority.use_subject_ref != request.feedback_id
            or authority.use_subject_digest != request.feedback_digest
            or authority.operation != RESOURCE_FEEDBACK_OPERATION
            or authority.authority != RESOURCE_FEEDBACK_AUTHORITY
            or authority.grant_ref != request.authority_grant_ref
            or authority.evaluated_at != evaluated
        ):
            raise IntelligenceResourceFeedbackError("authority resolver did not preserve the exact feedback request")

        replay = await self._load_replay(request)
        if replay is not None:
            return replay

        feedback = IntelligenceResourceFeedbackReceiptV1Alpha1(
            request=request,
            authority_use=authority,
            recorded_at=evaluated,
        )
        record = ImmutableRecordV1(
            product_id=request.product_id,
            record_space=RESOURCE_FEEDBACK_RECORD_SPACE,
            record_kind=RESOURCE_FEEDBACK_RECORD_KIND,
            record_key=str(request.feedback_id),
            payload_contract=feedback.contract,
            payload=feedback.model_dump(mode="python"),
            as_of=request.target.as_of,
            available_at=evaluated,
            processing_order=0,
        )
        transaction_request = AppendOnlyTransactionRequestV1(
            product_id=request.product_id,
            record_space=RESOURCE_FEEDBACK_RECORD_SPACE,
            transaction_key=f"resource_feedback:{request.feedback_id}",
            records=(record,),
            submitted_at=evaluated,
            governed_state_preconditions=(authority.state_head_precondition,),
        )
        try:
            transaction = await self.records.append(transaction_request)
        except Exception as exc:
            raise IntelligenceResourceFeedbackUnavailable("authorized feedback append failed closed") from exc
        if transaction != transaction_request.receipt():
            raise IntelligenceResourceFeedbackReplayConflict("feedback append returned divergent receipt material")
        return IntelligenceResourceFeedbackAdmissionV1Alpha1(
            feedback=feedback,
            record=record.reference(),
            transaction=transaction,
        )


__all__ = [
    "RESOURCE_FEEDBACK_AUTHORITY",
    "RESOURCE_FEEDBACK_OPERATION",
    "RESOURCE_FEEDBACK_RECORD_KIND",
    "RESOURCE_FEEDBACK_RECORD_SPACE",
    "IntelligenceResourceFeedbackAuthorizationPort",
    "IntelligenceResourceFeedbackDenied",
    "IntelligenceResourceFeedbackError",
    "IntelligenceResourceFeedbackReplayConflict",
    "IntelligenceResourceFeedbackService",
    "IntelligenceResourceFeedbackTargetPort",
    "IntelligenceResourceFeedbackUnavailable",
]
