"""Application services for governed delivery, export, and external effects."""

from __future__ import annotations

import asyncio
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Callable, Protocol

from pydantic_core import to_json

from ace.application.agent_composition_lifecycle import PreparedLifecycleDeliveryV1Alpha1
from ace.core.agent_composition import ExactArtifactReferenceV1Alpha1
from ace.core.contracts import FrozenContract, canonical_hash
from ace.core.external_operations import (
    AdministrativeExportManifestV1Alpha1,
    DeliveryState,
    DestinationDeliveryAdmissionV1Alpha1,
    DestinationDeliveryAttemptV1Alpha1,
    DestinationDeliveryIntentV1Alpha1,
    DestinationDeliveryLookupV1Alpha1,
    DestinationDeliveryResultV1Alpha1,
    DestinationRevisionV1Alpha1,
    EffectState,
    ExternalEffectAdmissionV1Alpha1,
    ExternalEffectAttemptV1Alpha1,
    ExternalEffectIntentV1Alpha1,
    ExternalEffectLookupV1Alpha1,
    ExternalEffectResultV1Alpha1,
    ExternalOperation,
    ExternalOperationAuthorityV1Alpha1,
    ExternalOperationCancellationV1Alpha1,
    LookupDisposition,
    PortabilityReceiptV1Alpha1,
    exact_external_reference,
)
from ace.core.records import (
    AppendOnlyTransactionReceiptV1,
    AppendOnlyTransactionRequestV1,
    ImmutableRecordReplayConflict,
    ImmutableRecordStore,
    ImmutableRecordV1,
)
from ace.core.runtime_use import AuthenticatedRuntimeContextV1Alpha1, CapabilityArtifactIdentityV1Alpha1

EXTERNAL_OPERATION_RECORD_SPACE = "external_operations"


def _aware(value: datetime, *, name: str) -> datetime:
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError(f"{name} must include a timezone")
    return value.astimezone(UTC)


def delivery_payload_digest(artifacts: tuple[ExactArtifactReferenceV1Alpha1, ...]) -> str:
    return f"sha256:{canonical_hash([item.model_dump(mode='json') for item in artifacts])}"


def export_manifest_checksum(
    *,
    included: tuple[ExactArtifactReferenceV1Alpha1, ...],
    omitted_refs: tuple[str, ...],
    redacted_refs: tuple[str, ...],
    retention_policy_ref: str,
    erasure_dependency_refs: tuple[str, ...],
    data_class_policy_ref: str,
) -> str:
    return f"sha256:{canonical_hash({'included': [item.model_dump(mode='json') for item in included], 'omitted_refs': omitted_refs, 'redacted_refs': redacted_refs, 'retention_policy_ref': retention_policy_ref, 'erasure_dependency_refs': erasure_dependency_refs, 'data_class_policy_ref': data_class_policy_ref})}"


class ExternalOperationError(RuntimeError):
    """An external operation failed closed before unsafe reuse or substitution."""


class ExternalOperationReplayConflict(ExternalOperationError):
    """A stable idempotency identity already binds different material."""


class ExternalOperationCancelled(ExternalOperationError):
    """A current cancellation prevented the operation from being attempted."""


class ExternalOperationAuthorityPort(Protocol):
    async def resolve(
        self,
        *,
        authenticated_context: AuthenticatedRuntimeContextV1Alpha1,
        operation: ExternalOperation,
        use_subject: ExactArtifactReferenceV1Alpha1,
        destination_revision: DestinationRevisionV1Alpha1 | None,
        recipient_ref: str | None,
        evaluated_at: datetime,
    ) -> ExternalOperationAuthorityV1Alpha1: ...


class ExternalDestinationAdapter(Protocol):
    @property
    def artifact_identity(self) -> CapabilityArtifactIdentityV1Alpha1: ...

    async def send_delivery(
        self,
        *,
        intent: DestinationDeliveryIntentV1Alpha1,
        attempt: DestinationDeliveryAttemptV1Alpha1,
    ) -> DestinationDeliveryResultV1Alpha1: ...

    async def lookup_delivery(
        self,
        *,
        intent: DestinationDeliveryIntentV1Alpha1,
        attempt: DestinationDeliveryAttemptV1Alpha1,
    ) -> DestinationDeliveryLookupV1Alpha1: ...

    async def execute_effect(
        self,
        *,
        intent: ExternalEffectIntentV1Alpha1,
        attempt: ExternalEffectAttemptV1Alpha1,
    ) -> ExternalEffectResultV1Alpha1: ...

    async def lookup_effect(
        self,
        *,
        intent: ExternalEffectIntentV1Alpha1,
        attempt: ExternalEffectAttemptV1Alpha1,
    ) -> ExternalEffectLookupV1Alpha1: ...


class AdministrativeExportAdapter(Protocol):
    @property
    def artifact_identity(self) -> CapabilityArtifactIdentityV1Alpha1: ...

    async def create_export(
        self,
        *,
        manifest: AdministrativeExportManifestV1Alpha1,
        authority: ExternalOperationAuthorityV1Alpha1,
    ) -> PortabilityReceiptV1Alpha1: ...


@dataclass(frozen=True, slots=True)
class DestinationDeliveryOutcome:
    admission: DestinationDeliveryAdmissionV1Alpha1
    attempt: DestinationDeliveryAttemptV1Alpha1
    result: DestinationDeliveryResultV1Alpha1
    replayed: bool
    recovered_by_lookup: bool


@dataclass(frozen=True, slots=True)
class ExternalEffectOutcome:
    admission: ExternalEffectAdmissionV1Alpha1
    attempt: ExternalEffectAttemptV1Alpha1
    result: ExternalEffectResultV1Alpha1
    replayed: bool
    recovered_by_lookup: bool


class _DurableOperations:
    def __init__(self, store: ImmutableRecordStore) -> None:
        self.store = store

    @staticmethod
    def transaction_key(operation_key: str, stage: str) -> str:
        return f"external_operation:{canonical_hash([operation_key, stage])[:32]}"

    async def append(
        self,
        *,
        operation_key: str,
        stage: str,
        kind: str,
        value: FrozenContract,
        key: str,
        product_id: str,
        as_of: datetime,
        available_at: datetime,
        preconditions=(),
    ) -> AppendOnlyTransactionReceiptV1:
        record = ImmutableRecordV1(
            product_id=product_id,
            record_space=EXTERNAL_OPERATION_RECORD_SPACE,
            record_kind=kind,
            record_key=key,
            payload_contract=str(getattr(value, "contract")),
            payload=value.model_dump(mode="python"),
            as_of=as_of,
            available_at=available_at,
            processing_order=0,
        )
        request = AppendOnlyTransactionRequestV1(
            product_id=product_id,
            record_space=EXTERNAL_OPERATION_RECORD_SPACE,
            transaction_key=self.transaction_key(operation_key, stage),
            records=(record,),
            submitted_at=available_at,
            governed_state_preconditions=preconditions,
        )
        receipt = await self.store.append(request)
        if receipt != request.receipt():
            raise ExternalOperationReplayConflict("external-operation append returned divergent receipt material")
        return receipt

    async def load(self, *, operation_key: str, stage: str, kind: str, product_id: str, model):
        transaction = await self.store.load_transaction_receipt(
            product_id=product_id,
            record_space=EXTERNAL_OPERATION_RECORD_SPACE,
            transaction_key=self.transaction_key(operation_key, stage),
        )
        if transaction is None:
            return None
        if len(transaction.records) != 1 or transaction.records[0].record_kind != kind:
            raise ExternalOperationReplayConflict(f"durable {kind} transaction has an invalid shape")
        reference = transaction.records[0]
        record = await self.store.load_record(
            reference.storage_id,
            product_id=product_id,
            record_space=EXTERNAL_OPERATION_RECORD_SPACE,
            record_kind=kind,
        )
        if record is None or record.reference() != reference:
            raise ExternalOperationReplayConflict(f"durable {kind} record is unavailable")
        try:
            value = model.model_validate_json(to_json(record.payload))
        except Exception:
            raise ExternalOperationReplayConflict(f"durable {kind} failed exact revalidation") from None
        if record.payload_contract != value.contract or record.payload != value.model_dump(mode="python"):
            raise ExternalOperationReplayConflict(f"durable {kind} crossed exact contract material")
        return value, transaction


def _validate_cancellation(
    cancellation: ExternalOperationCancellationV1Alpha1 | None,
    *,
    operation: ExternalOperation,
    subject: ExactArtifactReferenceV1Alpha1,
    expected_ref: str,
    attempted_at: datetime,
) -> None:
    if cancellation is None:
        return
    try:
        cancellation = ExternalOperationCancellationV1Alpha1.model_validate(cancellation.model_dump(mode="python"))
    except Exception:
        raise ExternalOperationError("cancellation failed exact revalidation") from None
    if (
        cancellation.operation is not operation
        or cancellation.subject != subject
        or cancellation.cancellation_ref != expected_ref
        or cancellation.cancelled_at > attempted_at
    ):
        raise ExternalOperationError("cancellation does not bind the exact operation subject")
    raise ExternalOperationCancelled("current cancellation prevented external operation attempt")


class GovernedDestinationDeliveryService:
    def __init__(
        self,
        *,
        store: ImmutableRecordStore,
        authority: ExternalOperationAuthorityPort,
        adapter: ExternalDestinationAdapter,
        destination: DestinationRevisionV1Alpha1,
        clock: Callable[[], datetime],
        timeout_seconds: float = 30.0,
    ) -> None:
        self.durable = _DurableOperations(store)
        self.authority = authority
        self.adapter = adapter
        self.destination = DestinationRevisionV1Alpha1.model_validate(destination.model_dump(mode="python"))
        self.clock = clock
        self.timeout_seconds = timeout_seconds

    def _now(self) -> datetime:
        try:
            return _aware(self.clock(), name="delivery service clock")
        except Exception:
            raise ExternalOperationError("delivery service clock failed closed") from None

    async def _resolve(
        self, intent: DestinationDeliveryIntentV1Alpha1, *, evaluated_at: datetime
    ) -> ExternalOperationAuthorityV1Alpha1:
        try:
            receipt = await self.authority.resolve(
                authenticated_context=intent.authenticated_context,
                operation=ExternalOperation.DELIVERY,
                use_subject=exact_external_reference(intent),
                destination_revision=self.destination,
                recipient_ref=intent.recipient_ref,
                evaluated_at=evaluated_at,
            )
            receipt = ExternalOperationAuthorityV1Alpha1.model_validate(receipt.model_dump(mode="python"))
        except Exception:
            raise ExternalOperationError("current delivery authority or destination policy failed closed") from None
        if (
            receipt.operation is not ExternalOperation.DELIVERY
            or receipt.destination_revision != intent.destination_revision
        ):
            raise ExternalOperationError("delivery authority resolved a different destination revision")
        return receipt

    @staticmethod
    def _validate_intent(
        prepared: PreparedLifecycleDeliveryV1Alpha1,
        intent: DestinationDeliveryIntentV1Alpha1,
        destination: DestinationRevisionV1Alpha1,
    ) -> DestinationDeliveryIntentV1Alpha1:
        try:
            prepared = PreparedLifecycleDeliveryV1Alpha1.model_validate(prepared.model_dump(mode="python"))
            intent = DestinationDeliveryIntentV1Alpha1.model_validate(intent.model_dump(mode="python"))
        except Exception:
            raise ExternalOperationError("prepared handoff or delivery intent failed exact revalidation") from None
        if prepared.external_send_occurred:
            raise ExternalOperationError("AC3 prepared handoff must remain effect-free before AC5 admission")
        if (
            intent.prepared_handoff
            != ExactArtifactReferenceV1Alpha1(
                artifact_id=str(prepared.package_id),
                artifact_digest=str(prepared.package_digest),
                artifact_contract=prepared.contract,
            )
            or intent.product_id != prepared.product_id
            or intent.payload_artifacts != prepared.artifacts
            or intent.payload_digest != delivery_payload_digest(prepared.artifacts)
            or intent.destination_revision != exact_external_reference(destination)
        ):
            raise ExternalOperationError("delivery intent does not bind exact prepared payload and destination")
        return intent

    async def deliver(
        self,
        *,
        prepared: PreparedLifecycleDeliveryV1Alpha1,
        intent: DestinationDeliveryIntentV1Alpha1,
        cancellation: ExternalOperationCancellationV1Alpha1 | None = None,
        attempt_number: int = 1,
    ) -> DestinationDeliveryOutcome:
        intent = self._validate_intent(prepared, intent, self.destination)
        operation_key = intent.idempotency_key
        prior_admission = await self.durable.load(
            operation_key=operation_key,
            stage="delivery_admission",
            kind="destination_delivery_admission",
            product_id=intent.product_id,
            model=DestinationDeliveryAdmissionV1Alpha1,
        )
        prior_attempt = await self.durable.load(
            operation_key=operation_key,
            stage=f"delivery_attempt:{attempt_number}",
            kind="destination_delivery_attempt",
            product_id=intent.product_id,
            model=DestinationDeliveryAttemptV1Alpha1,
        )
        prior_result = await self.durable.load(
            operation_key=operation_key,
            stage=f"delivery_result:{attempt_number}",
            kind="destination_delivery_result",
            product_id=intent.product_id,
            model=DestinationDeliveryResultV1Alpha1,
        )
        if prior_result is not None:
            if prior_admission is None or prior_attempt is None or prior_admission[0].intent != intent:
                raise ExternalOperationReplayConflict("delivery idempotency key crossed exact intent")
            return DestinationDeliveryOutcome(prior_admission[0], prior_attempt[0], prior_result[0], True, False)
        if prior_attempt is not None:
            if prior_admission is None or prior_admission[0].intent != intent:
                raise ExternalOperationReplayConflict("orphaned delivery attempt crossed exact intent")
            lookup = await self._lookup_delivery(intent, prior_attempt[0])
            if lookup.disposition is not LookupDisposition.FOUND:
                raise ExternalOperationError("restart delivery remains unresolved; blind retry is forbidden")
            result = lookup.resolved_result
            assert result is not None
            await self._append_delivery_result(intent, result, attempt_number)
            return DestinationDeliveryOutcome(prior_admission[0], prior_attempt[0], result, True, True)

        now = self._now()
        if now >= intent.expires_at:
            raise ExternalOperationError("delivery intent expired before admission")
        _validate_cancellation(
            cancellation,
            operation=ExternalOperation.DELIVERY,
            subject=exact_external_reference(intent),
            expected_ref=intent.cancellation_ref,
            attempted_at=now,
        )
        if attempt_number > 1 and prior_admission is None:
            raise ExternalOperationReplayConflict("delivery retry requires the original durable admission")
        if attempt_number > 1:
            await self._require_delivery_retry(intent, attempt_number)
        if prior_admission is None:
            post_preparation = await self._resolve(intent, evaluated_at=now)
            admitted_at = self._now()
            admission = DestinationDeliveryAdmissionV1Alpha1(
                intent=intent, post_preparation_authority=post_preparation, admitted_at=admitted_at
            )
            try:
                await self.durable.append(
                    operation_key=operation_key,
                    stage="delivery_admission",
                    kind="destination_delivery_admission",
                    value=admission,
                    key=str(admission.admission_id),
                    product_id=intent.product_id,
                    as_of=intent.requested_at,
                    available_at=admitted_at,
                    preconditions=post_preparation.current_heads,
                )
            except ImmutableRecordReplayConflict:
                raise ExternalOperationReplayConflict("concurrent delivery admission conflicted") from None
        else:
            admission = prior_admission[0]
        pre_send_at = self._now()
        _validate_cancellation(
            cancellation,
            operation=ExternalOperation.DELIVERY,
            subject=exact_external_reference(intent),
            expected_ref=intent.cancellation_ref,
            attempted_at=pre_send_at,
        )
        pre_send = await self._resolve(intent, evaluated_at=pre_send_at)
        attempted_at = self._now()
        attempt = DestinationDeliveryAttemptV1Alpha1(
            admission=exact_external_reference(admission),
            pre_send_authority=pre_send,
            attempt=attempt_number,
            idempotency_key=intent.idempotency_key,
            payload_digest=intent.payload_digest,
            attempted_at=attempted_at,
        )
        await self.durable.append(
            operation_key=operation_key,
            stage=f"delivery_attempt:{attempt_number}",
            kind="destination_delivery_attempt",
            value=attempt,
            key=str(attempt.attempt_id),
            product_id=intent.product_id,
            as_of=intent.requested_at,
            available_at=attempted_at,
            preconditions=pre_send.current_heads,
        )
        try:
            result = await asyncio.wait_for(
                self.adapter.send_delivery(intent=intent, attempt=attempt), timeout=self.timeout_seconds
            )
            result = DestinationDeliveryResultV1Alpha1.model_validate(result.model_dump(mode="python"))
        except TimeoutError:
            result = DestinationDeliveryResultV1Alpha1(
                attempt=exact_external_reference(attempt),
                state=DeliveryState.UNKNOWN,
                failure_code="adapter_timeout_unknown",
                retry_after_lookup=True,
                completed_at=self._now(),
            )
        except Exception:
            result = DestinationDeliveryResultV1Alpha1(
                attempt=exact_external_reference(attempt),
                state=DeliveryState.UNKNOWN,
                failure_code="adapter_failed_unknown",
                retry_after_lookup=True,
                completed_at=self._now(),
            )
        self._validate_result(intent, attempt, result)
        await self._append_delivery_result(intent, result, attempt_number)
        return DestinationDeliveryOutcome(admission, attempt, result, False, False)

    async def reconcile_unknown(
        self,
        *,
        intent: DestinationDeliveryIntentV1Alpha1,
        attempt: DestinationDeliveryAttemptV1Alpha1,
    ) -> DestinationDeliveryLookupV1Alpha1:
        return await self._lookup_delivery(intent, attempt)

    async def _require_delivery_retry(self, intent: DestinationDeliveryIntentV1Alpha1, attempt_number: int) -> None:
        previous = attempt_number - 1
        result_loaded = await self.durable.load(
            operation_key=intent.idempotency_key,
            stage=f"delivery_result:{previous}",
            kind="destination_delivery_result",
            product_id=intent.product_id,
            model=DestinationDeliveryResultV1Alpha1,
        )
        lookup_loaded = await self.durable.load(
            operation_key=intent.idempotency_key,
            stage=f"delivery_lookup:{previous}",
            kind="destination_delivery_lookup",
            product_id=intent.product_id,
            model=DestinationDeliveryLookupV1Alpha1,
        )
        if (
            result_loaded is None
            or result_loaded[0].state is not DeliveryState.UNKNOWN
            or lookup_loaded is None
            or lookup_loaded[0].disposition is not LookupDisposition.NOT_FOUND
            or not lookup_loaded[0].permits_retry
        ):
            raise ExternalOperationError("delivery retry requires exact conclusive not-found lookup evidence")

    async def _lookup_delivery(
        self, intent: DestinationDeliveryIntentV1Alpha1, attempt: DestinationDeliveryAttemptV1Alpha1
    ) -> DestinationDeliveryLookupV1Alpha1:
        loaded = await self.durable.load(
            operation_key=intent.idempotency_key,
            stage=f"delivery_lookup:{attempt.attempt}",
            kind="destination_delivery_lookup",
            product_id=intent.product_id,
            model=DestinationDeliveryLookupV1Alpha1,
        )
        if loaded is not None:
            return loaded[0]
        try:
            lookup = await self.adapter.lookup_delivery(intent=intent, attempt=attempt)
            lookup = DestinationDeliveryLookupV1Alpha1.model_validate(lookup.model_dump(mode="python"))
        except Exception:
            raise ExternalOperationError("delivery lookup failed closed; blind retry is forbidden") from None
        if lookup.attempt != exact_external_reference(attempt) or lookup.idempotency_key != intent.idempotency_key:
            raise ExternalOperationError("delivery lookup crossed exact idempotency or attempt identity")
        if lookup.resolved_result is not None:
            self._validate_result(intent, attempt, lookup.resolved_result)
        await self.durable.append(
            operation_key=intent.idempotency_key,
            stage=f"delivery_lookup:{attempt.attempt}",
            kind="destination_delivery_lookup",
            value=lookup,
            key=str(lookup.lookup_id),
            product_id=intent.product_id,
            as_of=intent.requested_at,
            available_at=lookup.looked_up_at,
        )
        return lookup

    @staticmethod
    def _validate_result(
        intent: DestinationDeliveryIntentV1Alpha1,
        attempt: DestinationDeliveryAttemptV1Alpha1,
        result: DestinationDeliveryResultV1Alpha1,
    ) -> None:
        if result.attempt != exact_external_reference(attempt) or result.completed_at < attempt.attempted_at:
            raise ExternalOperationError("delivery result crossed exact attempt or chronology")
        acknowledgment = result.acknowledgment
        if acknowledgment is not None and (
            acknowledgment.delivery_attempt != exact_external_reference(attempt)
            or acknowledgment.destination_revision != intent.destination_revision
            or acknowledgment.recipient_ref != intent.recipient_ref
            or acknowledgment.idempotency_key != intent.idempotency_key
            or acknowledgment.payload_digest != intent.payload_digest
            or acknowledgment.acknowledged_at < attempt.attempted_at
        ):
            raise ExternalOperationError("destination acknowledgment mismatched exact delivery material")

    async def _append_delivery_result(
        self, intent: DestinationDeliveryIntentV1Alpha1, result: DestinationDeliveryResultV1Alpha1, attempt: int
    ) -> None:
        await self.durable.append(
            operation_key=intent.idempotency_key,
            stage=f"delivery_result:{attempt}",
            kind="destination_delivery_result",
            value=result,
            key=str(result.result_id),
            product_id=intent.product_id,
            as_of=intent.requested_at,
            available_at=result.completed_at,
        )


class GovernedAdministrativeExportService:
    def __init__(
        self,
        *,
        store: ImmutableRecordStore,
        authority: ExternalOperationAuthorityPort,
        adapter: AdministrativeExportAdapter,
        clock: Callable[[], datetime],
    ) -> None:
        self.durable = _DurableOperations(store)
        self.authority = authority
        self.adapter = adapter
        self.clock = clock

    def _now(self) -> datetime:
        try:
            return _aware(self.clock(), name="export service clock")
        except Exception:
            raise ExternalOperationError("export service clock failed closed") from None

    async def export(self, manifest: AdministrativeExportManifestV1Alpha1) -> PortabilityReceiptV1Alpha1:
        try:
            manifest = AdministrativeExportManifestV1Alpha1.model_validate(manifest.model_dump(mode="python"))
        except Exception:
            raise ExternalOperationError("administrative export manifest failed exact revalidation") from None
        expected = export_manifest_checksum(
            included=manifest.included,
            omitted_refs=manifest.omitted_refs,
            redacted_refs=manifest.redacted_refs,
            retention_policy_ref=manifest.retention_policy_ref,
            erasure_dependency_refs=manifest.erasure_dependency_refs,
            data_class_policy_ref=manifest.data_class_policy_ref,
        )
        if manifest.checksum != expected:
            raise ExternalOperationError("administrative export checksum does not bind its exact contents")
        loaded = await self.durable.load(
            operation_key=str(manifest.manifest_id),
            stage="portability_receipt",
            kind="portability_receipt",
            product_id=manifest.product_id,
            model=PortabilityReceiptV1Alpha1,
        )
        if loaded is not None:
            if loaded[0].manifest != exact_external_reference(manifest):
                raise ExternalOperationReplayConflict("export manifest identity crossed durable receipt")
            return loaded[0]
        now = self._now()
        if now >= manifest.expires_at:
            raise ExternalOperationError("administrative export expired before admission")
        try:
            authority = await self.authority.resolve(
                authenticated_context=manifest.authenticated_context,
                operation=ExternalOperation.ADMIN_EXPORT,
                use_subject=exact_external_reference(manifest),
                destination_revision=None,
                recipient_ref=None,
                evaluated_at=now,
            )
            authority = ExternalOperationAuthorityV1Alpha1.model_validate(authority.model_dump(mode="python"))
        except Exception:
            raise ExternalOperationError("current administrative-export authority failed closed") from None
        if authority.operation is not ExternalOperation.ADMIN_EXPORT or authority.destination_revision is not None:
            raise ExternalOperationError("delivery or effect authority cannot substitute for administrative export")
        try:
            receipt = await self.adapter.create_export(manifest=manifest, authority=authority)
            receipt = PortabilityReceiptV1Alpha1.model_validate(receipt.model_dump(mode="python"))
        except Exception:
            raise ExternalOperationError("administrative export adapter failed closed") from None
        if (
            receipt.manifest != exact_external_reference(manifest)
            or receipt.authority != authority
            or receipt.artifact_checksum != manifest.checksum
            or receipt.included_count != len(manifest.included)
            or receipt.omitted_count != len(manifest.omitted_refs)
            or receipt.redacted_count != len(manifest.redacted_refs)
            or receipt.created_at < authority.evaluated_at
        ):
            raise ExternalOperationError("portability receipt does not close over exact export manifest")
        await self.durable.append(
            operation_key=str(manifest.manifest_id),
            stage="portability_receipt",
            kind="portability_receipt",
            value=receipt,
            key=str(receipt.receipt_id),
            product_id=manifest.product_id,
            as_of=manifest.requested_at,
            available_at=receipt.created_at,
            preconditions=authority.current_heads,
        )
        return receipt


class GovernedExternalEffectService:
    def __init__(
        self,
        *,
        store: ImmutableRecordStore,
        authority: ExternalOperationAuthorityPort,
        adapter: ExternalDestinationAdapter,
        destination: DestinationRevisionV1Alpha1,
        clock: Callable[[], datetime],
        timeout_seconds: float = 30.0,
    ) -> None:
        self.durable = _DurableOperations(store)
        self.authority = authority
        self.adapter = adapter
        self.destination = DestinationRevisionV1Alpha1.model_validate(destination.model_dump(mode="python"))
        self.clock = clock
        self.timeout_seconds = timeout_seconds

    def _now(self) -> datetime:
        try:
            return _aware(self.clock(), name="effect service clock")
        except Exception:
            raise ExternalOperationError("effect service clock failed closed") from None

    async def _resolve(
        self, intent: ExternalEffectIntentV1Alpha1, *, evaluated_at: datetime
    ) -> ExternalOperationAuthorityV1Alpha1:
        try:
            receipt = await self.authority.resolve(
                authenticated_context=intent.authenticated_context,
                operation=ExternalOperation.EXTERNAL_EFFECT,
                use_subject=exact_external_reference(intent),
                destination_revision=self.destination,
                recipient_ref=intent.recipient_ref,
                evaluated_at=evaluated_at,
            )
            receipt = ExternalOperationAuthorityV1Alpha1.model_validate(receipt.model_dump(mode="python"))
        except Exception:
            raise ExternalOperationError(
                "current external-effect authority or destination policy failed closed"
            ) from None
        if (
            receipt.operation is not ExternalOperation.EXTERNAL_EFFECT
            or receipt.destination_revision != intent.destination_revision
        ):
            raise ExternalOperationError("external-effect authority resolved a different destination revision")
        return receipt

    async def execute(
        self,
        *,
        intent: ExternalEffectIntentV1Alpha1,
        cancellation: ExternalOperationCancellationV1Alpha1 | None = None,
        attempt_number: int = 1,
    ) -> ExternalEffectOutcome:
        try:
            intent = ExternalEffectIntentV1Alpha1.model_validate(intent.model_dump(mode="python"))
        except Exception:
            raise ExternalOperationError("external-effect intent failed exact revalidation") from None
        if intent.destination_revision != exact_external_reference(self.destination):
            raise ExternalOperationError("external-effect intent binds a different destination revision")
        operation_key = intent.idempotency_key
        admission_loaded = await self.durable.load(
            operation_key=operation_key,
            stage="effect_admission",
            kind="external_effect_admission",
            product_id=intent.product_id,
            model=ExternalEffectAdmissionV1Alpha1,
        )
        attempt_loaded = await self.durable.load(
            operation_key=operation_key,
            stage=f"effect_attempt:{attempt_number}",
            kind="external_effect_attempt",
            product_id=intent.product_id,
            model=ExternalEffectAttemptV1Alpha1,
        )
        result_loaded = await self.durable.load(
            operation_key=operation_key,
            stage=f"effect_result:{attempt_number}",
            kind="external_effect_result",
            product_id=intent.product_id,
            model=ExternalEffectResultV1Alpha1,
        )
        if result_loaded is not None:
            if admission_loaded is None or attempt_loaded is None or admission_loaded[0].intent != intent:
                raise ExternalOperationReplayConflict("effect idempotency key crossed exact intent")
            return ExternalEffectOutcome(admission_loaded[0], attempt_loaded[0], result_loaded[0], True, False)
        if attempt_loaded is not None:
            if admission_loaded is None or admission_loaded[0].intent != intent:
                raise ExternalOperationReplayConflict("orphaned effect attempt crossed exact intent")
            lookup = await self._lookup(intent, attempt_loaded[0])
            if lookup.disposition is not LookupDisposition.FOUND:
                raise ExternalOperationError("restart effect remains unresolved; blind retry is forbidden")
            result = lookup.resolved_result
            assert result is not None
            await self._append_effect_result(intent, result, attempt_number)
            return ExternalEffectOutcome(admission_loaded[0], attempt_loaded[0], result, True, True)

        now = self._now()
        if now >= intent.expires_at:
            raise ExternalOperationError("external-effect intent expired before admission")
        _validate_cancellation(
            cancellation,
            operation=ExternalOperation.EXTERNAL_EFFECT,
            subject=exact_external_reference(intent),
            expected_ref=intent.cancellation_ref,
            attempted_at=now,
        )
        if attempt_number > 1 and admission_loaded is None:
            raise ExternalOperationReplayConflict("effect retry requires the original durable admission")
        if attempt_number > 1:
            await self._require_effect_retry(intent, attempt_number)
        if admission_loaded is None:
            post_preparation = await self._resolve(intent, evaluated_at=now)
            admitted_at = self._now()
            admission = ExternalEffectAdmissionV1Alpha1(
                intent=intent, post_preparation_authority=post_preparation, admitted_at=admitted_at
            )
            await self.durable.append(
                operation_key=operation_key,
                stage="effect_admission",
                kind="external_effect_admission",
                value=admission,
                key=str(admission.admission_id),
                product_id=intent.product_id,
                as_of=intent.requested_at,
                available_at=admitted_at,
                preconditions=post_preparation.current_heads,
            )
        else:
            admission = admission_loaded[0]
        pre_effect_at = self._now()
        _validate_cancellation(
            cancellation,
            operation=ExternalOperation.EXTERNAL_EFFECT,
            subject=exact_external_reference(intent),
            expected_ref=intent.cancellation_ref,
            attempted_at=pre_effect_at,
        )
        pre_effect = await self._resolve(intent, evaluated_at=pre_effect_at)
        attempted_at = self._now()
        attempt = ExternalEffectAttemptV1Alpha1(
            admission=exact_external_reference(admission),
            pre_effect_authority=pre_effect,
            attempt=attempt_number,
            idempotency_key=intent.idempotency_key,
            parameters_digest=intent.parameters_digest,
            attempted_at=attempted_at,
        )
        await self.durable.append(
            operation_key=operation_key,
            stage=f"effect_attempt:{attempt_number}",
            kind="external_effect_attempt",
            value=attempt,
            key=str(attempt.attempt_id),
            product_id=intent.product_id,
            as_of=intent.requested_at,
            available_at=attempted_at,
            preconditions=pre_effect.current_heads,
        )
        try:
            result = await asyncio.wait_for(
                self.adapter.execute_effect(intent=intent, attempt=attempt), timeout=self.timeout_seconds
            )
            result = ExternalEffectResultV1Alpha1.model_validate(result.model_dump(mode="python"))
        except TimeoutError:
            result = ExternalEffectResultV1Alpha1(
                attempt=exact_external_reference(attempt),
                state=EffectState.UNKNOWN,
                failure_code="adapter_timeout_unknown",
                retry_after_lookup=True,
                completed_at=self._now(),
            )
        except Exception:
            result = ExternalEffectResultV1Alpha1(
                attempt=exact_external_reference(attempt),
                state=EffectState.UNKNOWN,
                failure_code="adapter_failed_unknown",
                retry_after_lookup=True,
                completed_at=self._now(),
            )
        self._validate_effect_result(attempt, result)
        await self._append_effect_result(intent, result, attempt_number)
        return ExternalEffectOutcome(admission, attempt, result, False, False)

    async def reconcile_unknown(
        self,
        *,
        intent: ExternalEffectIntentV1Alpha1,
        attempt: ExternalEffectAttemptV1Alpha1,
    ) -> ExternalEffectLookupV1Alpha1:
        return await self._lookup(intent, attempt)

    async def _lookup(
        self, intent: ExternalEffectIntentV1Alpha1, attempt: ExternalEffectAttemptV1Alpha1
    ) -> ExternalEffectLookupV1Alpha1:
        loaded = await self.durable.load(
            operation_key=intent.idempotency_key,
            stage=f"effect_lookup:{attempt.attempt}",
            kind="external_effect_lookup",
            product_id=intent.product_id,
            model=ExternalEffectLookupV1Alpha1,
        )
        if loaded is not None:
            return loaded[0]
        try:
            lookup = await self.adapter.lookup_effect(intent=intent, attempt=attempt)
            lookup = ExternalEffectLookupV1Alpha1.model_validate(lookup.model_dump(mode="python"))
        except Exception:
            raise ExternalOperationError("effect lookup failed closed; blind retry is forbidden") from None
        if lookup.attempt != exact_external_reference(attempt) or lookup.idempotency_key != intent.idempotency_key:
            raise ExternalOperationError("effect lookup crossed exact idempotency or attempt identity")
        if lookup.resolved_result is not None:
            self._validate_effect_result(attempt, lookup.resolved_result)
        await self.durable.append(
            operation_key=intent.idempotency_key,
            stage=f"effect_lookup:{attempt.attempt}",
            kind="external_effect_lookup",
            value=lookup,
            key=str(lookup.lookup_id),
            product_id=intent.product_id,
            as_of=intent.requested_at,
            available_at=lookup.looked_up_at,
        )
        return lookup

    async def _require_effect_retry(self, intent: ExternalEffectIntentV1Alpha1, attempt_number: int) -> None:
        previous = attempt_number - 1
        result_loaded = await self.durable.load(
            operation_key=intent.idempotency_key,
            stage=f"effect_result:{previous}",
            kind="external_effect_result",
            product_id=intent.product_id,
            model=ExternalEffectResultV1Alpha1,
        )
        lookup_loaded = await self.durable.load(
            operation_key=intent.idempotency_key,
            stage=f"effect_lookup:{previous}",
            kind="external_effect_lookup",
            product_id=intent.product_id,
            model=ExternalEffectLookupV1Alpha1,
        )
        if (
            result_loaded is None
            or result_loaded[0].state is not EffectState.UNKNOWN
            or lookup_loaded is None
            or lookup_loaded[0].disposition is not LookupDisposition.NOT_FOUND
            or not lookup_loaded[0].permits_retry
        ):
            raise ExternalOperationError("external-effect retry requires exact conclusive not-found lookup evidence")

    @staticmethod
    def _validate_effect_result(attempt: ExternalEffectAttemptV1Alpha1, result: ExternalEffectResultV1Alpha1) -> None:
        if result.attempt != exact_external_reference(attempt) or result.completed_at < attempt.attempted_at:
            raise ExternalOperationError("external-effect result crossed exact attempt or chronology")

    async def _append_effect_result(
        self, intent: ExternalEffectIntentV1Alpha1, result: ExternalEffectResultV1Alpha1, attempt: int
    ) -> None:
        await self.durable.append(
            operation_key=intent.idempotency_key,
            stage=f"effect_result:{attempt}",
            kind="external_effect_result",
            value=result,
            key=str(result.result_id),
            product_id=intent.product_id,
            as_of=intent.requested_at,
            available_at=result.completed_at,
        )


__all__ = [
    "AdministrativeExportAdapter",
    "DestinationDeliveryOutcome",
    "EXTERNAL_OPERATION_RECORD_SPACE",
    "ExternalDestinationAdapter",
    "ExternalEffectOutcome",
    "ExternalOperationAuthorityPort",
    "ExternalOperationCancelled",
    "ExternalOperationError",
    "ExternalOperationReplayConflict",
    "GovernedAdministrativeExportService",
    "GovernedDestinationDeliveryService",
    "GovernedExternalEffectService",
    "delivery_payload_digest",
    "export_manifest_checksum",
]
