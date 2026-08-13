"""Rebuildable resource-plane projections over the immutable Intelligence ledgers."""

from __future__ import annotations

from collections import defaultdict
from collections.abc import Iterable
from datetime import datetime
from typing import Any, Protocol

from pydantic import BaseModel, TypeAdapter

from ace.application.intelligence_resource_plane import (
    IntelligenceResourceProjectionBatch,
    IntelligenceResourceProjectionReader,
)
from ace.application.monitoring import LIVE_MONITORING_RECORD_SPACE
from ace.core.contracts import canonical_json
from ace.core.records import ImmutableRecordStore, ImmutableRecordV1
from ace.intelligence.contracts.ledger import IntelligenceRecordKind
from ace.intelligence.contracts.monitoring import (
    MONITORING_LIFECYCLE_RECORD_KIND,
    MonitoringLifecycleReceiptV1Alpha1,
    MonitoringLifecycleState,
    MonitoringTargetKind,
)
from ace.intelligence.contracts.resource_plane import (
    IntelligenceResourceAvailability,
    IntelligenceResourceCursorV1Alpha1,
    IntelligenceResourceKind,
    IntelligenceResourcePageState,
    IntelligenceResourceQueryV1Alpha1,
    IntelligenceResourceRecordV1Alpha1,
    IntelligenceResourceReferenceV1Alpha1,
)
from ace.intelligence.contracts.resources import (
    BriefV1Alpha1,
    CanonicalJsonValueV1Alpha1,
    CaseV1Alpha1,
    EntitySnapshotV1Alpha1,
    IntelligenceResourceMode,
    LineageReferenceV1Alpha1,
    LineageResourceKind,
    ObservationV1Alpha1,
    ShiftV1Alpha1,
    SignalV1Alpha1,
)

_JSON_OBJECT = TypeAdapter(dict[str, Any])

_RESOURCE_MODELS: dict[IntelligenceRecordKind, type[BaseModel]] = {
    IntelligenceRecordKind.OBSERVATION: ObservationV1Alpha1,
    IntelligenceRecordKind.ENTITY_SNAPSHOT: EntitySnapshotV1Alpha1,
    IntelligenceRecordKind.SHIFT: ShiftV1Alpha1,
    IntelligenceRecordKind.SIGNAL: SignalV1Alpha1,
    IntelligenceRecordKind.CASE: CaseV1Alpha1,
    IntelligenceRecordKind.BRIEF: BriefV1Alpha1,
}
_PUBLIC_TO_LEDGER: dict[IntelligenceResourceKind, IntelligenceRecordKind] = {
    IntelligenceResourceKind.OBSERVATION: IntelligenceRecordKind.OBSERVATION,
    IntelligenceResourceKind.ENTITY: IntelligenceRecordKind.ENTITY_SNAPSHOT,
    IntelligenceResourceKind.SHIFT: IntelligenceRecordKind.SHIFT,
    IntelligenceResourceKind.SIGNAL: IntelligenceRecordKind.SIGNAL,
    IntelligenceResourceKind.CASE: IntelligenceRecordKind.CASE,
    IntelligenceResourceKind.BRIEF: IntelligenceRecordKind.BRIEF,
}
_LEDGER_TO_PUBLIC = {value: key for key, value in _PUBLIC_TO_LEDGER.items()}
LEDGER_RESOURCE_KINDS = frozenset(_PUBLIC_TO_LEDGER)
MONITORING_RESOURCE_KINDS = frozenset({IntelligenceResourceKind.MONITOR, IntelligenceResourceKind.SUBSCRIPTION})
_LINEAGE_TO_PUBLIC: dict[LineageResourceKind, IntelligenceResourceKind] = {
    LineageResourceKind.OBSERVATION: IntelligenceResourceKind.OBSERVATION,
    LineageResourceKind.ENTITY_SNAPSHOT: IntelligenceResourceKind.ENTITY,
    LineageResourceKind.SIGNAL: IntelligenceResourceKind.SIGNAL,
    LineageResourceKind.SHIFT: IntelligenceResourceKind.SHIFT,
    LineageResourceKind.CASE: IntelligenceResourceKind.CASE,
    LineageResourceKind.BRIEF: IntelligenceResourceKind.BRIEF,
}
_LINEAGE_CONTRACTS: dict[LineageResourceKind, str] = {
    LineageResourceKind.OBSERVATION: "ace.intelligence.observation/v1alpha1",
    LineageResourceKind.ENTITY_SNAPSHOT: "ace.intelligence.entity-snapshot/v1alpha1",
    LineageResourceKind.SIGNAL: "ace.intelligence.signal/v1alpha1",
    LineageResourceKind.SHIFT: "ace.intelligence.shift/v1alpha1",
    LineageResourceKind.CASE: "ace.intelligence.case/v1alpha1",
    LineageResourceKind.BRIEF: "ace.intelligence.brief/v1alpha1",
}


class IntelligenceLedgerProjectionError(RuntimeError):
    """An immutable ledger record could not be projected exactly."""


class IntelligenceResourceProjectionContributor(Protocol):
    """A disjoint owner of one or more public resource projection families."""

    @property
    def supported_kinds(self) -> frozenset[IntelligenceResourceKind]: ...

    async def read(
        self,
        *,
        query: IntelligenceResourceQueryV1Alpha1,
        after: IntelligenceResourceCursorV1Alpha1 | None,
        limit: int,
    ) -> IntelligenceResourceProjectionBatch: ...


def _resource_times(resource: BaseModel) -> tuple[datetime, datetime]:
    as_of = resource.as_of
    if isinstance(resource, ObservationV1Alpha1):
        return as_of, resource.ingested_at
    if isinstance(resource, EntitySnapshotV1Alpha1):
        return as_of, resource.projected_at
    if isinstance(resource, (ShiftV1Alpha1, SignalV1Alpha1)):
        return as_of, resource.detected_at
    if isinstance(resource, CaseV1Alpha1):
        return as_of, resource.assembled_at
    if isinstance(resource, BriefV1Alpha1):
        return as_of, resource.generated_at
    raise IntelligenceLedgerProjectionError("unsupported immutable Intelligence resource")


def _resource_title(resource: BaseModel) -> str:
    if isinstance(resource, ObservationV1Alpha1):
        return f"Observation from {resource.source_ref}"
    if isinstance(resource, EntitySnapshotV1Alpha1):
        return resource.entity_ref
    return str(resource.title)


def _resource_summary(resource: BaseModel) -> str | None:
    if isinstance(resource, (ShiftV1Alpha1, SignalV1Alpha1)):
        return resource.summary
    if isinstance(resource, CaseV1Alpha1):
        return resource.purpose
    if isinstance(resource, BriefV1Alpha1):
        return resource.executive_summary
    return None


def _resource_subjects(resource: BaseModel) -> tuple[str, ...]:
    if isinstance(resource, EntitySnapshotV1Alpha1):
        return (resource.entity_ref,)
    if isinstance(resource, (ObservationV1Alpha1, ShiftV1Alpha1, SignalV1Alpha1, CaseV1Alpha1)):
        return resource.subject_refs
    return ()


def _lineage_reference(
    lineage: LineageReferenceV1Alpha1,
    *,
    product_id: str,
) -> IntelligenceResourceReferenceV1Alpha1:
    if lineage.resource_kind not in _LINEAGE_TO_PUBLIC:
        raise IntelligenceLedgerProjectionError(
            "lineage kind lacks an exact resource contract in this projection slice"
        )
    return IntelligenceResourceReferenceV1Alpha1(
        product_id=product_id,
        resource_kind=_LINEAGE_TO_PUBLIC[lineage.resource_kind],
        resource_id=lineage.resource_id,
        resource_digest=lineage.resource_digest,
        resource_contract=_LINEAGE_CONTRACTS[lineage.resource_kind],
        revision=1,
        as_of=lineage.resource_as_of,
        available_at=lineage.resource_available_at,
    )


def _decode_record(
    record: ImmutableRecordV1,
    *,
    mode: IntelligenceResourceMode,
    ledger_kind: IntelligenceRecordKind,
) -> BaseModel:
    model = _RESOURCE_MODELS[ledger_kind]
    if record.record_space != mode.value or record.record_kind != ledger_kind.value:
        raise IntelligenceLedgerProjectionError("immutable record crossed its ledger bucket")
    try:
        resource = model.model_validate_json(_JSON_OBJECT.dump_json(record.payload))
    except (TypeError, ValueError) as exc:
        raise IntelligenceLedgerProjectionError("immutable Intelligence payload failed exact replay") from exc
    as_of, available_at = _resource_times(resource)
    if (
        resource.product_id != record.product_id
        or resource.mode is not mode
        or resource.resource_id != record.record_key
        or resource.contract != record.payload_contract
        or as_of != record.as_of
        or available_at != record.available_at
    ):
        raise IntelligenceLedgerProjectionError("immutable record envelope does not match its Intelligence payload")
    return resource


def _project_record(
    record: ImmutableRecordV1,
    *,
    mode: IntelligenceResourceMode,
    ledger_kind: IntelligenceRecordKind,
) -> IntelligenceResourceRecordV1Alpha1:
    resource = _decode_record(record, mode=mode, ledger_kind=ledger_kind)
    as_of, available_at = _resource_times(resource)
    return IntelligenceResourceRecordV1Alpha1(
        reference=IntelligenceResourceReferenceV1Alpha1(
            product_id=record.product_id,
            resource_kind=_LEDGER_TO_PUBLIC[ledger_kind],
            resource_id=str(resource.resource_id),
            resource_digest=str(resource.resource_digest),
            resource_contract=str(resource.contract),
            revision=1,
            as_of=as_of,
            available_at=available_at,
        ),
        availability=IntelligenceResourceAvailability.AVAILABLE,
        title=_resource_title(resource),
        summary=_resource_summary(resource),
        subject_refs=_resource_subjects(resource),
        provenance=tuple(_lineage_reference(item, product_id=record.product_id) for item in resource.lineage),
        payload=CanonicalJsonValueV1Alpha1(value_json=canonical_json(resource.model_dump(mode="json"))),
    )


def _after_cursor(
    records: Iterable[IntelligenceResourceRecordV1Alpha1],
    cursor: IntelligenceResourceCursorV1Alpha1 | None,
) -> list[IntelligenceResourceRecordV1Alpha1]:
    ordered = sorted(
        records,
        key=lambda item: (
            item.reference.available_at,
            item.reference.resource_kind.value,
            item.reference.resource_id,
            item.reference.revision,
        ),
    )
    if cursor is None:
        return ordered
    after = (
        cursor.after_available_at,
        cursor.after_resource_kind.value,
        cursor.after_resource_id,
        cursor.after_revision,
    )
    return [
        item
        for item in ordered
        if (
            item.reference.available_at,
            item.reference.resource_kind.value,
            item.reference.resource_id,
            item.reference.revision,
        )
        > after
    ]


class IntelligenceLedgerResourceProjectionReader(IntelligenceResourceProjectionReader):
    """Rebuild the supported public resource slice from PREPARED and LIVE records."""

    def __init__(
        self,
        *,
        store: ImmutableRecordStore,
        modes: tuple[IntelligenceResourceMode, ...] = (
            IntelligenceResourceMode.PREPARED,
            IntelligenceResourceMode.LIVE,
        ),
        degrade_unsupported: bool = True,
    ) -> None:
        if not modes or len(modes) != len(set(modes)):
            raise ValueError("projection modes must be a non-empty unique sequence")
        self.store = store
        self.modes = modes
        self.degrade_unsupported = degrade_unsupported

    @property
    def supported_kinds(self) -> frozenset[IntelligenceResourceKind]:
        return LEDGER_RESOURCE_KINDS

    async def read(
        self,
        *,
        query: IntelligenceResourceQueryV1Alpha1,
        after: IntelligenceResourceCursorV1Alpha1 | None,
        limit: int,
    ) -> IntelligenceResourceProjectionBatch:
        projected: list[IntelligenceResourceRecordV1Alpha1] = []
        degraded: set[str] = set()
        for public_kind in query.resource_kinds:
            ledger_kind = _PUBLIC_TO_LEDGER.get(public_kind)
            if ledger_kind is None:
                if self.degrade_unsupported:
                    degraded.add(f"degraded_reason:unsupported-{public_kind.value}")
                continue
            for mode in self.modes:
                try:
                    records = await self.store.read_as_of(
                        product_id=query.product_id,
                        record_space=mode.value,
                        record_kind=ledger_kind.value,
                        available_at=query.available_at,
                    )
                    projected.extend(
                        _project_record(record, mode=mode, ledger_kind=ledger_kind)
                        for record in records
                        if record.as_of <= query.as_of
                    )
                except Exception:
                    degraded.add(f"degraded_reason:read-{mode.value}-{ledger_kind.value}")

        if query.subject_refs:
            requested = set(query.subject_refs)
            projected = [item for item in projected if not requested.isdisjoint(item.subject_refs)]
        visible = _after_cursor(projected, after)[:limit]
        reasons = tuple(sorted(degraded))
        return IntelligenceResourceProjectionBatch(
            records=tuple(visible),
            state=(IntelligenceResourcePageState.DEGRADED if reasons else IntelligenceResourcePageState.COMPLETE),
            degraded_reason_refs=reasons,
        )


def _monitoring_kind(receipt: MonitoringLifecycleReceiptV1Alpha1) -> IntelligenceResourceKind:
    if receipt.target_kind is MonitoringTargetKind.MONITOR:
        return IntelligenceResourceKind.MONITOR
    return IntelligenceResourceKind.SUBSCRIPTION


def _monitoring_reference(
    receipt: MonitoringLifecycleReceiptV1Alpha1,
) -> IntelligenceResourceReferenceV1Alpha1:
    return IntelligenceResourceReferenceV1Alpha1(
        product_id=receipt.product_id,
        resource_kind=_monitoring_kind(receipt),
        resource_id=receipt.lifecycle.reference,
        resource_digest=str(receipt.receipt_digest),
        resource_contract=receipt.contract,
        revision=receipt.sequence,
        as_of=receipt.applied_at,
        available_at=receipt.applied_at,
    )


def _monitoring_projection(
    receipt: MonitoringLifecycleReceiptV1Alpha1,
    *,
    previous: MonitoringLifecycleReceiptV1Alpha1 | None,
) -> IntelligenceResourceRecordV1Alpha1:
    tombstoned = receipt.state_after is MonitoringLifecycleState.REVOKED
    label = "Monitor" if receipt.target_kind is MonitoringTargetKind.MONITOR else "Subscription"
    return IntelligenceResourceRecordV1Alpha1(
        reference=_monitoring_reference(receipt),
        availability=(
            IntelligenceResourceAvailability.TOMBSTONED if tombstoned else IntelligenceResourceAvailability.AVAILABLE
        ),
        title=f"{label}: {receipt.target.reference}",
        summary=f"{label} lifecycle is {receipt.state_after.value}.",
        subject_refs=tuple(
            sorted(
                {
                    receipt.owner_ref,
                    receipt.persona_binding.reference,
                    receipt.target.reference,
                }
            )
        ),
        supersedes=_monitoring_reference(previous) if previous is not None else None,
        payload=(
            None
            if tombstoned
            else CanonicalJsonValueV1Alpha1(value_json=canonical_json(receipt.model_dump(mode="json")))
        ),
    )


class MonitoringResourceProjectionReader(IntelligenceResourceProjectionReader):
    """Project current Monitor and Subscription lifecycle revisions."""

    def __init__(
        self,
        *,
        store: ImmutableRecordStore,
        degrade_unsupported: bool = True,
    ) -> None:
        self.store = store
        self.degrade_unsupported = degrade_unsupported

    @property
    def supported_kinds(self) -> frozenset[IntelligenceResourceKind]:
        return MONITORING_RESOURCE_KINDS

    async def read(
        self,
        *,
        query: IntelligenceResourceQueryV1Alpha1,
        after: IntelligenceResourceCursorV1Alpha1 | None,
        limit: int,
    ) -> IntelligenceResourceProjectionBatch:
        requested = set(query.resource_kinds)
        relevant = requested & MONITORING_RESOURCE_KINDS
        degraded = {
            f"degraded_reason:unsupported-{kind.value}"
            for kind in requested - MONITORING_RESOURCE_KINDS
            if self.degrade_unsupported
        }
        if not relevant:
            return IntelligenceResourceProjectionBatch(
                records=(),
                state=(IntelligenceResourcePageState.DEGRADED if degraded else IntelligenceResourcePageState.COMPLETE),
                degraded_reason_refs=tuple(sorted(degraded)),
            )
        try:
            records = await self.store.read_as_of(
                product_id=query.product_id,
                record_space=LIVE_MONITORING_RECORD_SPACE,
                record_kind=MONITORING_LIFECYCLE_RECORD_KIND,
                available_at=query.available_at,
            )
        except Exception:
            return IntelligenceResourceProjectionBatch(
                records=(),
                state=IntelligenceResourcePageState.DEGRADED,
                degraded_reason_refs=("degraded_reason:read-monitoring-lifecycle",),
            )

        chains: dict[str, list[MonitoringLifecycleReceiptV1Alpha1]] = defaultdict(list)
        for record in records:
            try:
                receipt = MonitoringLifecycleReceiptV1Alpha1.model_validate(record.payload)
                if (
                    record.product_id != query.product_id
                    or record.record_space != LIVE_MONITORING_RECORD_SPACE
                    or record.record_kind != MONITORING_LIFECYCLE_RECORD_KIND
                    or record.record_key != receipt.receipt_id
                    or record.payload_contract != receipt.contract
                    or record.as_of != receipt.applied_at
                    or record.available_at != receipt.applied_at
                ):
                    raise ValueError("monitoring envelope mismatch")
                if _monitoring_kind(receipt) not in relevant:
                    continue
                if receipt.applied_at <= query.as_of:
                    chains[receipt.lifecycle.reference].append(receipt)
            except Exception:
                degraded.add("degraded_reason:invalid-monitoring-lifecycle")

        projected: list[IntelligenceResourceRecordV1Alpha1] = []
        for lifecycle_id, chain in chains.items():
            ordered = sorted(chain, key=lambda item: item.sequence)
            if [item.sequence for item in ordered] != list(range(1, len(ordered) + 1)):
                degraded.add(f"degraded_reason:incomplete-{lifecycle_id}")
                continue
            if any(
                current.prior_receipt != previous.reference() or current.state_before is not previous.state_after
                for previous, current in zip(ordered, ordered[1:])
            ):
                degraded.add(f"degraded_reason:divergent-{lifecycle_id}")
                continue
            current = ordered[-1]
            public_kind = _monitoring_kind(current)
            if public_kind not in relevant:
                continue
            item = _monitoring_projection(
                current,
                previous=ordered[-2] if len(ordered) > 1 else None,
            )
            if query.subject_refs and set(query.subject_refs).isdisjoint(item.subject_refs):
                continue
            projected.append(item)

        visible = _after_cursor(projected, after)[:limit]
        reasons = tuple(sorted(degraded))
        return IntelligenceResourceProjectionBatch(
            records=tuple(visible),
            state=(IntelligenceResourcePageState.DEGRADED if reasons else IntelligenceResourcePageState.COMPLETE),
            degraded_reason_refs=reasons,
        )


class CompositeIntelligenceResourceProjectionReader(IntelligenceResourceProjectionReader):
    """Merge disjoint rebuildable projection contributors into one stable page."""

    def __init__(self, *contributors: IntelligenceResourceProjectionContributor) -> None:
        if not contributors:
            raise ValueError("at least one resource projection contributor is required")
        supported: set[IntelligenceResourceKind] = set()
        for contributor in contributors:
            overlap = supported & set(contributor.supported_kinds)
            if overlap:
                raise ValueError(f"resource projection contributors overlap: {sorted(item.value for item in overlap)}")
            supported.update(contributor.supported_kinds)
        self.contributors = contributors
        self.supported_kinds = frozenset(supported)

    async def read(
        self,
        *,
        query: IntelligenceResourceQueryV1Alpha1,
        after: IntelligenceResourceCursorV1Alpha1 | None,
        limit: int,
    ) -> IntelligenceResourceProjectionBatch:
        records: list[IntelligenceResourceRecordV1Alpha1] = []
        degraded = {
            f"degraded_reason:unsupported-{kind.value}" for kind in set(query.resource_kinds) - self.supported_kinds
        }
        for contributor in self.contributors:
            if not (set(query.resource_kinds) & contributor.supported_kinds):
                continue
            batch = await contributor.read(query=query, after=after, limit=limit)
            records.extend(batch.records)
            degraded.update(batch.degraded_reason_refs)
        visible = _after_cursor(records, after)[:limit]
        keys = [
            (
                item.reference.resource_kind,
                item.reference.resource_id,
                item.reference.revision,
            )
            for item in visible
        ]
        if len(keys) != len(set(keys)):
            raise IntelligenceLedgerProjectionError("resource projection contributors returned duplicate revisions")
        reasons = tuple(sorted(degraded))
        return IntelligenceResourceProjectionBatch(
            records=tuple(visible),
            state=(IntelligenceResourcePageState.DEGRADED if reasons else IntelligenceResourcePageState.COMPLETE),
            degraded_reason_refs=reasons,
        )


__all__ = [
    "CompositeIntelligenceResourceProjectionReader",
    "IntelligenceLedgerProjectionError",
    "IntelligenceLedgerResourceProjectionReader",
    "IntelligenceResourceProjectionContributor",
    "MonitoringResourceProjectionReader",
]
