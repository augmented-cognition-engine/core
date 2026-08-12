"""Rebuildable resource-plane projections over the immutable Intelligence ledgers."""

from __future__ import annotations

from collections.abc import Iterable
from datetime import datetime
from typing import Any

from pydantic import BaseModel, TypeAdapter

from ace.application.intelligence_resource_plane import (
    IntelligenceResourceProjectionBatch,
    IntelligenceResourceProjectionReader,
)
from ace.core.contracts import canonical_json
from ace.core.records import ImmutableRecordStore, ImmutableRecordV1
from ace.intelligence.contracts.ledger import IntelligenceRecordKind
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
    ) -> None:
        if not modes or len(modes) != len(set(modes)):
            raise ValueError("projection modes must be a non-empty unique sequence")
        self.store = store
        self.modes = modes

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


__all__ = [
    "IntelligenceLedgerProjectionError",
    "IntelligenceLedgerResourceProjectionReader",
]
