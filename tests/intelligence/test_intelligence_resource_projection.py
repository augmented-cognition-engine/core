from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest

from ace.application import IntelligenceLedgerResourceProjectionReader
from ace.core import ImmutableRecordV1, canonical_hash
from ace.core.runtime_use import AuthenticatedRuntimeContextV1Alpha1
from ace.intelligence import (
    ActivationRevisionReferenceV1Alpha1,
    CanonicalJsonValueV1Alpha1,
    EntitySnapshotV1Alpha1,
    IntelligenceRecordKind,
    IntelligenceResourceCursorV1Alpha1,
    IntelligenceResourceKind,
    IntelligenceResourceMode,
    IntelligenceResourcePageState,
    IntelligenceResourceQueryV1Alpha1,
    LineageReferenceV1Alpha1,
    LineageRelation,
    LineageResourceKind,
    SignalV1Alpha1,
)
from ace.testing import InMemoryImmutableRecordStore

pytestmark = pytest.mark.unit

PRODUCT = "product:resource-projection"
NOW = datetime(2026, 8, 12, 20, 0, tzinfo=UTC)


def _activation() -> ActivationRevisionReferenceV1Alpha1:
    digest = "sha256:" + "a" * 64
    return ActivationRevisionReferenceV1Alpha1(
        product_id=PRODUCT,
        activation_key="generic_intelligence",
        activation_id=f"domain_activation:{canonical_hash([PRODUCT, 'generic_intelligence'])[:32]}",
        revision=1,
        revision_id="activation_revision:" + "a" * 32,
        revision_digest=digest,
    )


def _entity(*, mode: IntelligenceResourceMode) -> EntitySnapshotV1Alpha1:
    return EntitySnapshotV1Alpha1(
        product_id=PRODUCT,
        mode=mode,
        activation_revision=_activation(),
        as_of=NOW,
        entity_ref="entity:ace",
        entity_type_ref="entity_type:system",
        attributes=CanonicalJsonValueV1Alpha1(value_json='{"name":"ACE"}'),
        projected_at=NOW,
        confidence=0.95,
    )


def _signal(
    entity: EntitySnapshotV1Alpha1,
    *,
    mode: IntelligenceResourceMode,
) -> SignalV1Alpha1:
    return SignalV1Alpha1(
        product_id=PRODUCT,
        mode=mode,
        activation_revision=_activation(),
        as_of=NOW + timedelta(minutes=1),
        lineage=(
            LineageReferenceV1Alpha1(
                resource_kind=LineageResourceKind.ENTITY_SNAPSHOT,
                relation=LineageRelation.SUPPORTS,
                resource_id=str(entity.resource_id),
                resource_digest=str(entity.resource_digest),
                resource_as_of=entity.as_of,
                resource_available_at=entity.projected_at,
            ),
        ),
        signal_type_ref="signal_type:material-change",
        title="ACE changed",
        summary="A material change was detected.",
        subject_refs=("entity:ace",),
        details=CanonicalJsonValueV1Alpha1(value_json='{"change":"material"}'),
        detected_at=NOW + timedelta(minutes=1),
        confidence=0.9,
    )


def _record(resource, *, kind: IntelligenceRecordKind) -> ImmutableRecordV1:
    if isinstance(resource, EntitySnapshotV1Alpha1):
        available_at = resource.projected_at
    else:
        available_at = resource.detected_at
    return ImmutableRecordV1(
        product_id=PRODUCT,
        record_space=resource.mode.value,
        record_kind=kind.value,
        record_key=str(resource.resource_id),
        payload_contract=resource.contract,
        payload=resource.model_dump(mode="python"),
        as_of=resource.as_of,
        available_at=available_at,
        processing_order=0,
    )


def _store(*records: ImmutableRecordV1) -> InMemoryImmutableRecordStore:
    store = InMemoryImmutableRecordStore()
    store.records.update({str(item.storage_id): item for item in records})
    return store


def _query(
    *,
    kinds: tuple[IntelligenceResourceKind, ...],
    subject_refs: tuple[str, ...] = (),
    cursor: IntelligenceResourceCursorV1Alpha1 | None = None,
) -> IntelligenceResourceQueryV1Alpha1:
    context = AuthenticatedRuntimeContextV1Alpha1(
        product_id=PRODUCT,
        actor_ref="principal:analyst",
        authentication_receipt_ref="authentication_receipt:projection",
        authentication_receipt_digest="sha256:" + "b" * 64,
        authenticated_at=NOW - timedelta(minutes=5),
        expires_at=NOW + timedelta(minutes=30),
    )
    return IntelligenceResourceQueryV1Alpha1(
        authenticated_context=context,
        product_id=PRODUCT,
        authority_grant_ref="authority_grant:resource-read",
        resource_kinds=kinds,
        subject_refs=subject_refs,
        as_of=NOW + timedelta(minutes=1),
        available_at=NOW + timedelta(minutes=1),
        page_size=10,
        cursor=cursor,
    )


@pytest.mark.asyncio
async def test_immutable_ledgers_project_through_one_public_resource_plane() -> None:
    prepared_entity = _entity(mode=IntelligenceResourceMode.PREPARED)
    live_entity = _entity(mode=IntelligenceResourceMode.LIVE)
    live_signal = _signal(live_entity, mode=IntelligenceResourceMode.LIVE)
    store = _store(
        _record(prepared_entity, kind=IntelligenceRecordKind.ENTITY_SNAPSHOT),
        _record(live_entity, kind=IntelligenceRecordKind.ENTITY_SNAPSHOT),
        _record(live_signal, kind=IntelligenceRecordKind.SIGNAL),
    )
    query = _query(kinds=(IntelligenceResourceKind.ENTITY, IntelligenceResourceKind.SIGNAL))

    batch = await IntelligenceLedgerResourceProjectionReader(store=store).read(
        query=query,
        after=None,
        limit=20,
    )

    assert batch.state is IntelligenceResourcePageState.COMPLETE
    assert [item.reference.resource_kind for item in batch.records] == [
        IntelligenceResourceKind.ENTITY,
        IntelligenceResourceKind.ENTITY,
        IntelligenceResourceKind.SIGNAL,
    ]
    projected_signal = batch.records[-1]
    assert projected_signal.subject_refs == ("entity:ace",)
    assert projected_signal.provenance[0].resource_kind is IntelligenceResourceKind.ENTITY
    assert projected_signal.provenance[0].resource_id == live_entity.resource_id
    assert projected_signal.payload is not None
    assert projected_signal.payload.parsed_value()["mode"] == "live"


@pytest.mark.asyncio
async def test_projection_honors_subject_cursor_limit_and_restart() -> None:
    entity = _entity(mode=IntelligenceResourceMode.LIVE)
    signal = _signal(entity, mode=IntelligenceResourceMode.LIVE)
    store = _store(
        _record(entity, kind=IntelligenceRecordKind.ENTITY_SNAPSHOT),
        _record(signal, kind=IntelligenceRecordKind.SIGNAL),
    )
    first_query = _query(
        kinds=(IntelligenceResourceKind.ENTITY, IntelligenceResourceKind.SIGNAL),
        subject_refs=("entity:ace",),
    )
    first_reader = IntelligenceLedgerResourceProjectionReader(store=store)
    first = await first_reader.read(query=first_query, after=None, limit=1)
    assert len(first.records) == 1

    reference = first.records[0].reference
    cursor = IntelligenceResourceCursorV1Alpha1(
        query_id=str(first_query.query_id),
        after_available_at=reference.available_at,
        after_resource_kind=reference.resource_kind,
        after_resource_id=reference.resource_id,
        after_revision=reference.revision,
    )
    restarted_reader = IntelligenceLedgerResourceProjectionReader(store=store)
    second = await restarted_reader.read(query=first_query, after=cursor, limit=10)

    assert len(second.records) == 1
    assert second.records[0].reference.resource_kind is IntelligenceResourceKind.SIGNAL


@pytest.mark.asyncio
async def test_unsupported_resource_family_is_honestly_degraded() -> None:
    query = _query(kinds=(IntelligenceResourceKind.ACTION,))
    batch = await IntelligenceLedgerResourceProjectionReader(store=_store()).read(
        query=query,
        after=None,
        limit=10,
    )
    assert batch.state is IntelligenceResourcePageState.DEGRADED
    assert batch.records == ()
    assert batch.degraded_reason_refs == ("degraded_reason:unsupported-action",)


@pytest.mark.asyncio
async def test_unavailable_ledger_bucket_does_not_hide_available_truth() -> None:
    entity = _entity(mode=IntelligenceResourceMode.PREPARED)

    class _PartiallyUnavailableStore(InMemoryImmutableRecordStore):
        async def read_as_of(self, **kwargs):
            if kwargs["record_space"] == IntelligenceResourceMode.LIVE.value:
                raise RuntimeError("live ledger is unavailable")
            return await super().read_as_of(**kwargs)

    store = _PartiallyUnavailableStore()
    record = _record(entity, kind=IntelligenceRecordKind.ENTITY_SNAPSHOT)
    store.records[str(record.storage_id)] = record

    batch = await IntelligenceLedgerResourceProjectionReader(store=store).read(
        query=_query(kinds=(IntelligenceResourceKind.ENTITY,)),
        after=None,
        limit=10,
    )
    assert len(batch.records) == 1
    assert batch.state is IntelligenceResourcePageState.DEGRADED
    assert batch.degraded_reason_refs == ("degraded_reason:read-live-entity_snapshot",)


@pytest.mark.asyncio
async def test_projection_does_not_invent_contracts_for_external_lineage() -> None:
    signal = SignalV1Alpha1(
        product_id=PRODUCT,
        mode=IntelligenceResourceMode.LIVE,
        activation_revision=_activation(),
        as_of=NOW + timedelta(minutes=1),
        lineage=(
            LineageReferenceV1Alpha1(
                resource_kind=LineageResourceKind.EVIDENCE,
                relation=LineageRelation.SUPPORTS,
                resource_id="evidence:external",
                resource_digest="sha256:" + "c" * 64,
                resource_as_of=NOW,
                resource_available_at=NOW,
            ),
        ),
        signal_type_ref="signal_type:material-change",
        title="Externally grounded change",
        summary="The evidence contract is not available in this ledger slice.",
        subject_refs=("entity:ace",),
        details=CanonicalJsonValueV1Alpha1(value_json='{"change":"material"}'),
        detected_at=NOW + timedelta(minutes=1),
        confidence=0.9,
    )
    batch = await IntelligenceLedgerResourceProjectionReader(
        store=_store(_record(signal, kind=IntelligenceRecordKind.SIGNAL))
    ).read(
        query=_query(kinds=(IntelligenceResourceKind.SIGNAL,)),
        after=None,
        limit=10,
    )

    assert batch.records == ()
    assert batch.state is IntelligenceResourcePageState.DEGRADED
    assert batch.degraded_reason_refs == ("degraded_reason:read-live-signal",)
