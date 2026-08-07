"""Application composition for the durable PREPARED Intelligence ledger.

The service requires an exact Core-committed Domain Activation and its exact
compiled Pack IR. A commit proves durable admission only: this service rejects
LIVE resources and exposes no delivery, learning, or runtime-authority path.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Any, Literal, TypeAlias

from pydantic import TypeAdapter

from ace.application.domain_activation import (
    CommittedActivationBinding,
    CommittedDomainActivation,
    DomainActivationAdmissionError,
    bind_committed_activation,
)
from ace.core.contracts import canonical_json
from ace.core.reasoning import FrozenContextItemV1Alpha1
from ace.core.records import (
    AppendOnlyTransactionReceiptV1,
    AppendOnlyTransactionRequestV1,
    ImmutableRecordReferenceV1,
    ImmutableRecordStore,
    ImmutableRecordV1,
    immutable_record_storage_id,
)
from ace.intelligence.contracts.ledger import (
    AttentionDisposition,
    AttentionDispositionReceiptV1Alpha1,
    AttentionSuppressionReason,
    IntelligenceRecordKind,
    IntelligenceRecordReferenceV1Alpha1,
    PreparedResourceAdmissionV1Alpha1,
    PreparedResourceSetAdmissionV1Alpha1,
    PreparedResourceV1Alpha1,
    resource_available_at,
    resource_kind,
    resource_reference,
)
from ace.intelligence.contracts.resources import (
    BriefV1Alpha1,
    CaseV1Alpha1,
    EntitySnapshotV1Alpha1,
    IntelligenceResourceMode,
    LineageReferenceV1Alpha1,
    LineageResourceKind,
    ObservationV1Alpha1,
    ShiftV1Alpha1,
    SignalV1Alpha1,
)
from ace.intelligence.routing import SignalRoutingError, eligible_signal_routes

PREPARED_RECORD_SPACE = "prepared"

LedgerValue: TypeAlias = PreparedResourceV1Alpha1 | AttentionDispositionReceiptV1Alpha1

_RESOURCE_MODELS: dict[IntelligenceRecordKind, type[PreparedResourceV1Alpha1]] = {
    IntelligenceRecordKind.OBSERVATION: ObservationV1Alpha1,
    IntelligenceRecordKind.ENTITY_SNAPSHOT: EntitySnapshotV1Alpha1,
    IntelligenceRecordKind.SHIFT: ShiftV1Alpha1,
    IntelligenceRecordKind.SIGNAL: SignalV1Alpha1,
    IntelligenceRecordKind.CASE: CaseV1Alpha1,
    IntelligenceRecordKind.BRIEF: BriefV1Alpha1,
}
_LINEAGE_KINDS = {
    LineageResourceKind.OBSERVATION: IntelligenceRecordKind.OBSERVATION,
    LineageResourceKind.ENTITY_SNAPSHOT: IntelligenceRecordKind.ENTITY_SNAPSHOT,
    LineageResourceKind.SHIFT: IntelligenceRecordKind.SHIFT,
    LineageResourceKind.SIGNAL: IntelligenceRecordKind.SIGNAL,
    LineageResourceKind.CASE: IntelligenceRecordKind.CASE,
    LineageResourceKind.BRIEF: IntelligenceRecordKind.BRIEF,
}
_JSON_OBJECT = TypeAdapter(dict[str, Any])


def _payload_json(payload: dict[str, Any]) -> bytes:
    return _JSON_OBJECT.dump_json(payload)


class PreparedIntelligenceAdmissionError(RuntimeError):
    """PREPARED admission or replay failed exact validation."""


@dataclass(frozen=True, slots=True)
class PreparedIntelligenceAdmission:
    """Replayed durable resources plus exact Core and attention receipts."""

    resources: tuple[PreparedResourceV1Alpha1, ...]
    attention_receipt: AttentionDispositionReceiptV1Alpha1
    transaction_receipt: AppendOnlyTransactionReceiptV1
    mode: Literal[IntelligenceResourceMode.PREPARED] = IntelligenceResourceMode.PREPARED
    authority_stage: Literal["committed"] = "committed"

    @property
    def live_authority(self) -> Literal[False]:
        return False


@dataclass(frozen=True, slots=True)
class PreparedResourceSetAdmission:
    """Replayed durable PREPARED resources with no implied attention event."""

    resources: tuple[PreparedResourceV1Alpha1, ...]
    transaction_receipt: AppendOnlyTransactionReceiptV1
    mode: Literal[IntelligenceResourceMode.PREPARED] = IntelligenceResourceMode.PREPARED
    authority_stage: Literal["committed"] = "committed"

    @property
    def live_authority(self) -> Literal[False]:
        return False

    @property
    def attention_receipt(self) -> None:
        return None


def _validated_binding(binding: CommittedActivationBinding) -> CommittedActivationBinding:
    if not isinstance(binding, CommittedActivationBinding):
        raise PreparedIntelligenceAdmissionError("a Core-committed activation binding is required")
    try:
        return bind_committed_activation(
            pack=binding.prepared_binding.pack,
            committed=CommittedDomainActivation(
                revision=binding.prepared_binding.revision,
                commit_receipt=binding.commit_receipt,
            ),
        )
    except (AttributeError, TypeError, ValueError, DomainActivationAdmissionError) as exc:
        raise PreparedIntelligenceAdmissionError(
            "the committed activation and exact Pack IR failed revalidation"
        ) from exc


def _revalidate_batch(
    batch: PreparedResourceAdmissionV1Alpha1,
) -> PreparedResourceAdmissionV1Alpha1:
    try:
        return PreparedResourceAdmissionV1Alpha1.model_validate(batch.model_dump(mode="python"))
    except (AttributeError, TypeError, ValueError) as exc:
        raise PreparedIntelligenceAdmissionError("prepared resource-admission batch failed exact revalidation") from exc


def _revalidate_resource_set(
    batch: PreparedResourceSetAdmissionV1Alpha1,
) -> PreparedResourceSetAdmissionV1Alpha1:
    try:
        return PreparedResourceSetAdmissionV1Alpha1.model_validate(batch.model_dump(mode="python"))
    except (AttributeError, TypeError, ValueError) as exc:
        raise PreparedIntelligenceAdmissionError("prepared resource-set admission failed exact revalidation") from exc


def _record_for_resource(
    resource: PreparedResourceV1Alpha1,
    *,
    processing_order: int,
) -> ImmutableRecordV1:
    return ImmutableRecordV1(
        product_id=resource.product_id,
        record_space=resource.mode.value,
        record_kind=resource_kind(resource).value,
        record_key=str(resource.resource_id),
        payload_contract=resource.contract,
        payload=resource.model_dump(mode="python"),
        as_of=resource.as_of,
        available_at=resource_available_at(resource),
        processing_order=processing_order,
    )


def _record_for_attention(
    receipt: AttentionDispositionReceiptV1Alpha1,
    *,
    processing_order: int,
) -> ImmutableRecordV1:
    return ImmutableRecordV1(
        product_id=receipt.product_id,
        record_space=receipt.mode.value,
        record_kind=IntelligenceRecordKind.ATTENTION_DISPOSITION.value,
        record_key=str(receipt.receipt_id),
        payload_contract=receipt.contract,
        payload=receipt.model_dump(mode="python"),
        as_of=receipt.signal.as_of,
        available_at=receipt.evaluated_at,
        processing_order=processing_order,
    )


def _assert_core_reference(
    record: ImmutableRecordV1,
    reference: ImmutableRecordReferenceV1,
) -> None:
    if record.reference() != reference:
        raise PreparedIntelligenceAdmissionError(
            "stored immutable record does not match its exact transaction reference"
        )


class PreparedIntelligenceLedgerService:
    """Validate, atomically persist, replay, and query PREPARED derivations."""

    def __init__(
        self,
        *,
        binding: CommittedActivationBinding,
        store: ImmutableRecordStore,
    ) -> None:
        self.binding = _validated_binding(binding)
        self.store = store

    @property
    def product_id(self) -> str:
        return self.binding.prepared_binding.revision.spec.product_id

    def _assert_bound_resource(self, resource: PreparedResourceV1Alpha1) -> None:
        if resource.product_id != self.product_id:
            raise PreparedIntelligenceAdmissionError("resource crossed the committed product scope")
        if resource.mode is not IntelligenceResourceMode.PREPARED:
            raise PreparedIntelligenceAdmissionError("durable prepared admission rejects LIVE resources")
        if resource.activation_revision != self.binding.prepared_binding.reference:
            raise PreparedIntelligenceAdmissionError("resource does not use the exact committed activation revision")

    def _decode_resource(
        self,
        record: ImmutableRecordV1,
        kind: IntelligenceRecordKind,
    ) -> PreparedResourceV1Alpha1:
        model = _RESOURCE_MODELS.get(kind)
        if model is None:
            raise PreparedIntelligenceAdmissionError("record is not a resource in this ledger slice")
        if (
            record.product_id != self.product_id
            or record.record_space != PREPARED_RECORD_SPACE
            or record.record_kind != kind.value
        ):
            raise PreparedIntelligenceAdmissionError("stored record crossed its exact ledger scope")
        try:
            resource = model.model_validate_json(_payload_json(record.payload))
        except (TypeError, ValueError) as exc:
            raise PreparedIntelligenceAdmissionError("stored resource failed exact contract replay") from exc
        self._assert_bound_resource(resource)
        exact = resource_reference(resource)
        if (
            record.record_key != exact.resource_id
            or record.payload_contract != exact.resource_contract
            or record.as_of != exact.as_of
            or record.available_at != exact.available_at
        ):
            raise PreparedIntelligenceAdmissionError("stored envelope does not match exact resource material")
        return resource

    async def _resolve_lineage(
        self,
        *,
        resource: PreparedResourceV1Alpha1,
        in_batch: dict[str, PreparedResourceV1Alpha1],
        order_by_id: dict[str, int],
    ) -> tuple[IntelligenceRecordReferenceV1Alpha1, ...]:
        resolved: dict[str, IntelligenceRecordReferenceV1Alpha1] = {}
        current_order = order_by_id[str(resource.resource_id)]
        for lineage in resource.lineage:
            expected_kind = _LINEAGE_KINDS.get(lineage.resource_kind)
            if expected_kind is None:
                raise PreparedIntelligenceAdmissionError("lineage kind is outside the durable prepared resource slice")
            upstream = in_batch.get(lineage.resource_id)
            if upstream is not None:
                if order_by_id[lineage.resource_id] >= current_order:
                    raise PreparedIntelligenceAdmissionError(
                        "lineage target must precede its derivative in deterministic processing order"
                    )
                exact = resource_reference(upstream)
            else:
                storage_id = immutable_record_storage_id(
                    product_id=self.product_id,
                    record_space=PREPARED_RECORD_SPACE,
                    record_kind=expected_kind.value,
                    record_key=lineage.resource_id,
                )
                stored = await self.store.load_record(
                    storage_id,
                    product_id=self.product_id,
                    record_space=PREPARED_RECORD_SPACE,
                    record_kind=expected_kind.value,
                )
                if stored is None:
                    raise PreparedIntelligenceAdmissionError(
                        f"lineage target {lineage.resource_id} is unavailable in exact product scope"
                    )
                upstream = self._decode_resource(stored, expected_kind)
                exact = resource_reference(upstream)
            if exact.resource_kind is not expected_kind:
                raise PreparedIntelligenceAdmissionError("lineage target kind does not match")
            if (
                exact.resource_id != lineage.resource_id
                or exact.resource_digest != lineage.resource_digest
                or exact.as_of != lineage.resource_as_of
                or exact.available_at != lineage.resource_available_at
            ):
                raise PreparedIntelligenceAdmissionError(
                    "lineage target identity, digest, as-of, or availability does not match"
                )
            if exact.as_of > resource.as_of or exact.available_at > resource_available_at(resource):
                raise PreparedIntelligenceAdmissionError(
                    "lineage target was stale or unavailable at derivative processing time"
                )
            resolved[exact.resource_id] = exact
        return tuple(sorted(resolved.values(), key=lambda item: (item.resource_kind.value, item.resource_id)))

    def _attention_receipt(
        self,
        *,
        batch: PreparedResourceAdmissionV1Alpha1,
        signal_lineage: tuple[IntelligenceRecordReferenceV1Alpha1, ...],
    ) -> AttentionDispositionReceiptV1Alpha1:
        try:
            routes = eligible_signal_routes(
                binding=self.binding.prepared_binding,
                signal=batch.signal,
            )
        except SignalRoutingError as exc:
            raise PreparedIntelligenceAdmissionError(str(exc)) from exc
        if len(routes) > 1:
            raise PreparedIntelligenceAdmissionError(
                "the narrow durable ledger requires one unambiguous route or suppression"
            )
        common: dict[str, Any] = {
            "product_id": batch.product_id,
            "activation_revision": batch.activation_revision,
            "pack": batch.pack,
            "signal": resource_reference(batch.signal),
            "source_lineage": signal_lineage,
            "evaluated_at": batch.attention_evaluated_at,
        }
        if routes:
            route = routes[0]
            return AttentionDispositionReceiptV1Alpha1(
                **common,
                disposition=AttentionDisposition.ROUTE,
                routing_rule_id=route.routing_rule_id,
                persona_ids=route.persona_ids,
                brief_template_id=route.brief_template_id,
            )
        return AttentionDispositionReceiptV1Alpha1(
            **common,
            disposition=AttentionDisposition.SUPPRESSED,
            suppression_reason=AttentionSuppressionReason.NO_ELIGIBLE_ROUTE,
        )

    async def admit(
        self,
        batch: PreparedResourceAdmissionV1Alpha1,
    ) -> PreparedIntelligenceAdmission:
        validated_binding = _validated_binding(self.binding)
        validated = _revalidate_batch(batch)
        if validated.product_id != self.product_id:
            raise PreparedIntelligenceAdmissionError("batch crossed the committed product scope")
        if validated.activation_revision != validated_binding.prepared_binding.reference:
            raise PreparedIntelligenceAdmissionError("batch does not use the exact committed activation revision")
        if validated.pack != validated_binding.prepared_binding.revision.spec.pack:
            raise PreparedIntelligenceAdmissionError("batch does not bind the exact committed Pack IR")

        by_id = {str(resource.resource_id): resource for resource in validated.resources()}
        ordered = tuple(by_id[reference.resource_id] for reference in validated.processing_order)
        order_by_id = {str(resource.resource_id): index for index, resource in enumerate(ordered)}
        resolved_lineage: dict[str, tuple[IntelligenceRecordReferenceV1Alpha1, ...]] = {}
        for resource in ordered:
            self._assert_bound_resource(resource)
            resolved_lineage[str(resource.resource_id)] = await self._resolve_lineage(
                resource=resource,
                in_batch=by_id,
                order_by_id=order_by_id,
            )

        attention = self._attention_receipt(
            batch=validated,
            signal_lineage=resolved_lineage[str(validated.signal.resource_id)],
        )
        records = tuple(
            _record_for_resource(resource, processing_order=index) for index, resource in enumerate(ordered)
        ) + (_record_for_attention(attention, processing_order=len(ordered)),)
        request = AppendOnlyTransactionRequestV1(
            product_id=validated.product_id,
            record_space=PREPARED_RECORD_SPACE,
            transaction_key=validated.derivation_key,
            records=records,
            submitted_at=validated.attention_evaluated_at,
        )
        transaction_receipt = await self.store.append(request)
        if transaction_receipt != request.receipt():
            raise PreparedIntelligenceAdmissionError(
                "Core transaction receipt does not bind the exact admission request"
            )
        return await self._replay_receipt(transaction_receipt)

    async def replay(self, *, derivation_key: str) -> PreparedIntelligenceAdmission | None:
        receipt = await self.store.load_transaction_receipt(
            product_id=self.product_id,
            record_space=PREPARED_RECORD_SPACE,
            transaction_key=derivation_key,
        )
        return await self._replay_receipt(receipt) if receipt is not None else None

    async def admit_resource_set(
        self,
        batch: PreparedResourceSetAdmissionV1Alpha1,
    ) -> PreparedResourceSetAdmission:
        """Persist an arbitrary valid PREPARED resource DAG without routing it."""

        validated_binding = _validated_binding(self.binding)
        validated = _revalidate_resource_set(batch)
        if validated.product_id != self.product_id:
            raise PreparedIntelligenceAdmissionError("resource set crossed the committed product scope")
        if validated.activation_revision != validated_binding.prepared_binding.reference:
            raise PreparedIntelligenceAdmissionError(
                "resource set does not use the exact committed activation revision"
            )
        if validated.pack != validated_binding.prepared_binding.revision.spec.pack:
            raise PreparedIntelligenceAdmissionError("resource set does not bind the exact committed Pack IR")

        by_id = {str(resource.resource_id): resource for resource in validated.resources}
        ordered = tuple(by_id[reference.resource_id] for reference in validated.processing_order)
        order_by_id = {str(resource.resource_id): index for index, resource in enumerate(ordered)}
        for resource in ordered:
            self._assert_bound_resource(resource)
            await self._resolve_lineage(
                resource=resource,
                in_batch=by_id,
                order_by_id=order_by_id,
            )

        records = tuple(
            _record_for_resource(resource, processing_order=index) for index, resource in enumerate(ordered)
        )
        request = AppendOnlyTransactionRequestV1(
            product_id=validated.product_id,
            record_space=PREPARED_RECORD_SPACE,
            transaction_key=validated.admission_key,
            records=records,
            submitted_at=validated.admitted_at,
        )
        transaction_receipt = await self.store.append(request)
        if transaction_receipt != request.receipt():
            raise PreparedIntelligenceAdmissionError(
                "Core transaction receipt does not bind the exact resource-set request"
            )
        return await self._replay_resource_set_receipt(transaction_receipt)

    async def replay_resource_set(
        self,
        *,
        admission_key: str,
    ) -> PreparedResourceSetAdmission | None:
        receipt = await self.store.load_transaction_receipt(
            product_id=self.product_id,
            record_space=PREPARED_RECORD_SPACE,
            transaction_key=admission_key,
        )
        return await self._replay_resource_set_receipt(receipt) if receipt is not None else None

    async def load_exact(
        self,
        reference: IntelligenceRecordReferenceV1Alpha1,
    ) -> LedgerValue | None:
        """Load one exact PREPARED resource or attention receipt by public coordinates."""

        try:
            exact = IntelligenceRecordReferenceV1Alpha1.model_validate(reference.model_dump(mode="python"))
        except (AttributeError, TypeError, ValueError) as exc:
            raise PreparedIntelligenceAdmissionError("exact record reference failed revalidation") from exc
        if exact.product_id != self.product_id or exact.mode is not IntelligenceResourceMode.PREPARED:
            raise PreparedIntelligenceAdmissionError("exact record load crossed product or PREPARED scope")
        storage_id = immutable_record_storage_id(
            product_id=self.product_id,
            record_space=PREPARED_RECORD_SPACE,
            record_kind=exact.resource_kind.value,
            record_key=exact.resource_id,
        )
        stored = await self.store.load_record(
            storage_id,
            product_id=self.product_id,
            record_space=PREPARED_RECORD_SPACE,
            record_kind=exact.resource_kind.value,
        )
        if stored is None:
            return None
        if (
            stored.record_key != exact.resource_id
            or stored.payload_contract != exact.resource_contract
            or stored.as_of != exact.as_of
            or stored.available_at != exact.available_at
        ):
            raise PreparedIntelligenceAdmissionError("stored envelope does not match exact public coordinates")
        if exact.resource_kind is IntelligenceRecordKind.ATTENTION_DISPOSITION:
            try:
                attention = AttentionDispositionReceiptV1Alpha1.model_validate_json(_payload_json(stored.payload))
            except (TypeError, ValueError) as exc:
                raise PreparedIntelligenceAdmissionError("stored attention receipt failed exact replay") from exc
            if attention.record_reference() != exact:
                raise PreparedIntelligenceAdmissionError("attention receipt changed exact public identity")
            return attention
        resource = self._decode_resource(stored, exact.resource_kind)
        if resource_reference(resource) != exact:
            raise PreparedIntelligenceAdmissionError("resource changed exact public identity")
        return resource

    async def freeze_exact(
        self,
        reference: IntelligenceRecordReferenceV1Alpha1,
    ) -> FrozenContextItemV1Alpha1 | None:
        """Freeze one exact resource as opaque, explicitly non-authoritative Core context."""

        value = await self.load_exact(reference)
        if value is None:
            return None
        if isinstance(value, AttentionDispositionReceiptV1Alpha1):
            raise PreparedIntelligenceAdmissionError("attention receipts are route policy, not provider context")
        storage_id = immutable_record_storage_id(
            product_id=self.product_id,
            record_space=PREPARED_RECORD_SPACE,
            record_kind=reference.resource_kind.value,
            record_key=reference.resource_id,
        )
        stored = await self.store.load_record(
            storage_id,
            product_id=self.product_id,
            record_space=PREPARED_RECORD_SPACE,
            record_kind=reference.resource_kind.value,
        )
        if stored is None:
            raise PreparedIntelligenceAdmissionError("exact context record disappeared during freeze")
        try:
            frozen_resource = self._decode_resource(stored, reference.resource_kind)
        except (TypeError, ValueError, PreparedIntelligenceAdmissionError) as exc:
            raise PreparedIntelligenceAdmissionError("exact context record changed during freeze revalidation") from exc
        if resource_reference(frozen_resource) != reference:
            raise PreparedIntelligenceAdmissionError("exact context record changed between public load and freeze")
        return FrozenContextItemV1Alpha1(
            product_id=stored.product_id,
            record_space=stored.record_space,
            record_kind=stored.record_kind,
            record_key=stored.record_key,
            storage_id=str(stored.storage_id),
            material_digest=str(stored.material_hash),
            payload_contract=stored.payload_contract,
            as_of=stored.as_of,
            available_at=stored.available_at,
            content_json=canonical_json(_JSON_OBJECT.dump_python(stored.payload, mode="json")),
        )

    async def load_lineage_exact(
        self,
        lineage: LineageReferenceV1Alpha1,
    ) -> PreparedResourceV1Alpha1 | None:
        """Resolve one exact persisted lineage edge without caller-supplied contract guesses."""

        try:
            exact = LineageReferenceV1Alpha1.model_validate(lineage.model_dump(mode="python"))
        except (AttributeError, TypeError, ValueError) as exc:
            raise PreparedIntelligenceAdmissionError("lineage reference failed exact revalidation") from exc
        kind = _LINEAGE_KINDS.get(exact.resource_kind)
        if kind is None:
            raise PreparedIntelligenceAdmissionError("lineage kind is outside the PREPARED resource ledger")
        storage_id = immutable_record_storage_id(
            product_id=self.product_id,
            record_space=PREPARED_RECORD_SPACE,
            record_kind=kind.value,
            record_key=exact.resource_id,
        )
        stored = await self.store.load_record(
            storage_id,
            product_id=self.product_id,
            record_space=PREPARED_RECORD_SPACE,
            record_kind=kind.value,
        )
        if stored is None:
            return None
        resource = self._decode_resource(stored, kind)
        reference = resource_reference(resource)
        if (
            reference.resource_id != exact.resource_id
            or reference.resource_digest != exact.resource_digest
            or reference.as_of != exact.resource_as_of
            or reference.available_at != exact.resource_available_at
        ):
            raise PreparedIntelligenceAdmissionError("persisted lineage target changed exact material")
        return resource

    async def _replay_receipt(
        self,
        receipt: AppendOnlyTransactionReceiptV1,
    ) -> PreparedIntelligenceAdmission:
        if receipt.product_id != self.product_id or receipt.record_space != PREPARED_RECORD_SPACE:
            raise PreparedIntelligenceAdmissionError("transaction receipt crossed ledger scope")
        resources: list[PreparedResourceV1Alpha1] = []
        attention: AttentionDispositionReceiptV1Alpha1 | None = None
        for reference in receipt.records:
            stored = await self.store.load_record(
                reference.storage_id,
                product_id=self.product_id,
                record_space=PREPARED_RECORD_SPACE,
                record_kind=reference.record_kind,
            )
            if stored is None:
                raise PreparedIntelligenceAdmissionError("transaction receipt references a missing immutable record")
            _assert_core_reference(stored, reference)
            try:
                kind = IntelligenceRecordKind(reference.record_kind)
            except ValueError as exc:
                raise PreparedIntelligenceAdmissionError(
                    "transaction contains a record outside the Intelligence ledger"
                ) from exc
            if kind is IntelligenceRecordKind.ATTENTION_DISPOSITION:
                if attention is not None or reference.processing_order != len(receipt.records) - 1:
                    raise PreparedIntelligenceAdmissionError(
                        "transaction must end with exactly one attention disposition"
                    )
                try:
                    attention = AttentionDispositionReceiptV1Alpha1.model_validate_json(_payload_json(stored.payload))
                except (TypeError, ValueError) as exc:
                    raise PreparedIntelligenceAdmissionError("stored attention receipt failed exact replay") from exc
                if (
                    stored.record_key != attention.receipt_id
                    or stored.payload_contract != attention.contract
                    or stored.as_of != attention.signal.as_of
                    or stored.available_at != attention.evaluated_at
                    or attention.product_id != self.product_id
                    or attention.activation_revision != self.binding.prepared_binding.reference
                    or attention.pack != self.binding.prepared_binding.revision.spec.pack
                ):
                    raise PreparedIntelligenceAdmissionError(
                        "stored attention envelope crossed exact activation, Pack, or record material"
                    )
            else:
                resources.append(self._decode_resource(stored, kind))
        if attention is None:
            raise PreparedIntelligenceAdmissionError("transaction is missing its durable attention disposition")
        signal_ids = {str(resource.resource_id) for resource in resources if isinstance(resource, SignalV1Alpha1)}
        if signal_ids != {attention.signal.resource_id}:
            raise PreparedIntelligenceAdmissionError("attention receipt does not bind the transaction's exact Signal")
        return PreparedIntelligenceAdmission(
            resources=tuple(resources),
            attention_receipt=attention,
            transaction_receipt=receipt,
        )

    async def _replay_resource_set_receipt(
        self,
        receipt: AppendOnlyTransactionReceiptV1,
    ) -> PreparedResourceSetAdmission:
        if receipt.product_id != self.product_id or receipt.record_space != PREPARED_RECORD_SPACE:
            raise PreparedIntelligenceAdmissionError("resource-set receipt crossed ledger scope")
        resources: list[PreparedResourceV1Alpha1] = []
        for reference in receipt.records:
            stored = await self.store.load_record(
                reference.storage_id,
                product_id=self.product_id,
                record_space=PREPARED_RECORD_SPACE,
                record_kind=reference.record_kind,
            )
            if stored is None:
                raise PreparedIntelligenceAdmissionError("resource-set receipt references a missing immutable record")
            _assert_core_reference(stored, reference)
            try:
                kind = IntelligenceRecordKind(reference.record_kind)
            except ValueError as exc:
                raise PreparedIntelligenceAdmissionError(
                    "resource-set transaction contains a record outside the Intelligence ledger"
                ) from exc
            if kind is IntelligenceRecordKind.ATTENTION_DISPOSITION:
                raise PreparedIntelligenceAdmissionError(
                    "resource-set transaction must not contain an attention disposition"
                )
            resources.append(self._decode_resource(stored, kind))
        if not resources:
            raise PreparedIntelligenceAdmissionError("resource-set transaction is empty")
        return PreparedResourceSetAdmission(
            resources=tuple(resources),
            transaction_receipt=receipt,
        )

    async def read_as_of(
        self,
        *,
        product_id: str,
        mode: IntelligenceResourceMode,
        kind: IntelligenceRecordKind,
        available_at: datetime,
    ) -> tuple[LedgerValue, ...]:
        if product_id != self.product_id:
            raise PreparedIntelligenceAdmissionError("read crossed the bound product scope")
        records = await self.store.read_as_of(
            product_id=product_id,
            record_space=mode.value,
            record_kind=kind.value,
            available_at=available_at,
        )
        if mode is IntelligenceResourceMode.LIVE:
            return () if not records else self._fail_prepared_as_live()
        values: list[LedgerValue] = []
        for record in records:
            if kind is IntelligenceRecordKind.ATTENTION_DISPOSITION:
                try:
                    receipt = AttentionDispositionReceiptV1Alpha1.model_validate_json(_payload_json(record.payload))
                except (TypeError, ValueError) as exc:
                    raise PreparedIntelligenceAdmissionError(
                        "stored attention receipt failed historical replay"
                    ) from exc
                if receipt.product_id != self.product_id:
                    raise PreparedIntelligenceAdmissionError("historical receipt crossed product scope")
                values.append(receipt)
            else:
                values.append(self._decode_resource(record, kind))
        return tuple(values)

    def _fail_prepared_as_live(self) -> tuple[LedgerValue, ...]:
        raise PreparedIntelligenceAdmissionError("PREPARED records must never appear in the LIVE record space")

    async def count_as_of(
        self,
        *,
        product_id: str,
        mode: IntelligenceResourceMode,
        kind: IntelligenceRecordKind,
        available_at: datetime,
    ) -> int:
        if product_id != self.product_id:
            raise PreparedIntelligenceAdmissionError("count crossed the bound product scope")
        return await self.store.count_as_of(
            product_id=product_id,
            record_space=mode.value,
            record_kind=kind.value,
            available_at=available_at,
        )


__all__ = [
    "PREPARED_RECORD_SPACE",
    "LedgerValue",
    "PreparedIntelligenceAdmission",
    "PreparedIntelligenceAdmissionError",
    "PreparedIntelligenceLedgerService",
    "PreparedResourceSetAdmission",
]
