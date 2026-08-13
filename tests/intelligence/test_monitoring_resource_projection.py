from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest

from ace.application import (
    CompositeIntelligenceResourceProjectionReader,
    IntelligenceLedgerResourceProjectionReader,
    MonitoringResourceProjectionReader,
)
from ace.application.monitoring import LIVE_MONITORING_RECORD_SPACE
from ace.core import ImmutableRecordV1
from ace.core.runtime_use import AuthenticatedRuntimeContextV1Alpha1
from ace.intelligence import (
    ExactMaterialReferenceV1Alpha1,
    IntelligenceResourceAvailability,
    IntelligenceResourceKind,
    IntelligenceResourcePageState,
    IntelligenceResourceQueryV1Alpha1,
    MonitoringLifecycleAction,
    MonitoringLifecycleReceiptV1Alpha1,
    MonitoringLifecycleState,
    MonitoringTargetKind,
    monitoring_lifecycle_identity,
)
from ace.intelligence.contracts.monitoring import MONITORING_LIFECYCLE_RECORD_KIND
from ace.testing import InMemoryImmutableRecordStore

pytestmark = pytest.mark.unit

PRODUCT = "product:monitoring-projection"
NOW = datetime(2026, 8, 12, 20, 0, tzinfo=UTC)
TARGET = ExactMaterialReferenceV1Alpha1(
    reference="monitor:ai-releases",
    digest="sha256:" + "a" * 64,
)
PERSONA = ExactMaterialReferenceV1Alpha1(
    reference="persona_binding:executive",
    digest="sha256:" + "b" * 64,
)


def _receipt(
    *,
    sequence: int,
    state_before: MonitoringLifecycleState | None,
    state_after: MonitoringLifecycleState,
    prior: MonitoringLifecycleReceiptV1Alpha1 | None = None,
    target_kind: MonitoringTargetKind = MonitoringTargetKind.MONITOR,
) -> MonitoringLifecycleReceiptV1Alpha1:
    lifecycle = monitoring_lifecycle_identity(
        product_id=PRODUCT,
        target_kind=target_kind,
        target=TARGET,
        persona_binding=PERSONA,
    )
    action = {
        1: MonitoringLifecycleAction.CREATE,
        2: MonitoringLifecycleAction.PAUSE,
        3: MonitoringLifecycleAction.REVOKE,
    }[sequence]
    return MonitoringLifecycleReceiptV1Alpha1(
        product_id=PRODUCT,
        owner_ref="principal:executive",
        target_kind=target_kind,
        target=TARGET,
        persona_binding=PERSONA,
        lifecycle=lifecycle,
        request=ExactMaterialReferenceV1Alpha1(
            reference=f"monitoring_request:{sequence}",
            digest="sha256:" + f"{sequence}" * 64,
        ),
        action=action,
        sequence=sequence,
        state_before=state_before,
        state_after=state_after,
        prior_receipt=prior.reference() if prior is not None else None,
        applied_at=NOW + timedelta(minutes=sequence),
    )


def _record(receipt: MonitoringLifecycleReceiptV1Alpha1) -> ImmutableRecordV1:
    return ImmutableRecordV1(
        product_id=PRODUCT,
        record_space=LIVE_MONITORING_RECORD_SPACE,
        record_kind=MONITORING_LIFECYCLE_RECORD_KIND,
        record_key=str(receipt.receipt_id),
        payload_contract=receipt.contract,
        payload=receipt.model_dump(mode="python"),
        as_of=receipt.applied_at,
        available_at=receipt.applied_at,
        processing_order=0,
    )


def _store(*receipts: MonitoringLifecycleReceiptV1Alpha1) -> InMemoryImmutableRecordStore:
    store = InMemoryImmutableRecordStore()
    records = [_record(receipt) for receipt in receipts]
    store.records.update({str(record.storage_id): record for record in records})
    return store


def _query(
    *kinds: IntelligenceResourceKind,
    subject_refs: tuple[str, ...] = (),
) -> IntelligenceResourceQueryV1Alpha1:
    return IntelligenceResourceQueryV1Alpha1(
        authenticated_context=AuthenticatedRuntimeContextV1Alpha1(
            product_id=PRODUCT,
            actor_ref="principal:executive",
            authentication_receipt_ref="authentication_receipt:monitoring",
            authentication_receipt_digest="sha256:" + "c" * 64,
            authenticated_at=NOW,
            expires_at=NOW + timedelta(hours=1),
        ),
        product_id=PRODUCT,
        authority_grant_ref="authority_grant:monitoring-read",
        resource_kinds=kinds,
        subject_refs=subject_refs,
        as_of=NOW + timedelta(minutes=10),
        available_at=NOW + timedelta(minutes=10),
        page_size=20,
    )


@pytest.mark.asyncio
async def test_monitoring_projection_returns_only_the_current_exact_revision() -> None:
    created = _receipt(
        sequence=1,
        state_before=None,
        state_after=MonitoringLifecycleState.ACTIVE,
    )
    paused = _receipt(
        sequence=2,
        state_before=MonitoringLifecycleState.ACTIVE,
        state_after=MonitoringLifecycleState.PAUSED,
        prior=created,
    )
    batch = await MonitoringResourceProjectionReader(store=_store(created, paused)).read(
        query=_query(IntelligenceResourceKind.MONITOR, subject_refs=("principal:executive",)),
        after=None,
        limit=20,
    )

    assert batch.state is IntelligenceResourcePageState.COMPLETE
    assert len(batch.records) == 1
    current = batch.records[0]
    assert current.reference.resource_kind is IntelligenceResourceKind.MONITOR
    assert current.reference.resource_id == paused.lifecycle.reference
    assert current.reference.revision == 2
    assert current.supersedes is not None
    assert current.supersedes.revision == 1
    assert current.payload is not None
    assert current.payload.parsed_value()["state_after"] == "paused"


@pytest.mark.asyncio
async def test_revoked_monitor_is_tombstoned_without_payload() -> None:
    created = _receipt(
        sequence=1,
        state_before=None,
        state_after=MonitoringLifecycleState.ACTIVE,
    )
    paused = _receipt(
        sequence=2,
        state_before=MonitoringLifecycleState.ACTIVE,
        state_after=MonitoringLifecycleState.PAUSED,
        prior=created,
    )
    revoked = _receipt(
        sequence=3,
        state_before=MonitoringLifecycleState.PAUSED,
        state_after=MonitoringLifecycleState.REVOKED,
        prior=paused,
    )
    batch = await MonitoringResourceProjectionReader(store=_store(created, paused, revoked)).read(
        query=_query(IntelligenceResourceKind.MONITOR),
        after=None,
        limit=20,
    )
    assert batch.records[0].availability is IntelligenceResourceAvailability.TOMBSTONED
    assert batch.records[0].payload is None
    assert batch.records[0].reference.revision == 3


@pytest.mark.asyncio
async def test_subscription_lifecycle_projects_as_a_distinct_resource_family() -> None:
    created = _receipt(
        sequence=1,
        state_before=None,
        state_after=MonitoringLifecycleState.ACTIVE,
        target_kind=MonitoringTargetKind.SUBSCRIPTION,
    )
    batch = await MonitoringResourceProjectionReader(store=_store(created)).read(
        query=_query(IntelligenceResourceKind.SUBSCRIPTION),
        after=None,
        limit=20,
    )
    assert len(batch.records) == 1
    assert batch.records[0].reference.resource_kind is IntelligenceResourceKind.SUBSCRIPTION


@pytest.mark.asyncio
async def test_incomplete_lifecycle_degrades_instead_of_inventing_current_state() -> None:
    created = _receipt(
        sequence=1,
        state_before=None,
        state_after=MonitoringLifecycleState.ACTIVE,
    )
    paused = _receipt(
        sequence=2,
        state_before=MonitoringLifecycleState.ACTIVE,
        state_after=MonitoringLifecycleState.PAUSED,
        prior=created,
    )
    batch = await MonitoringResourceProjectionReader(store=_store(paused)).read(
        query=_query(IntelligenceResourceKind.MONITOR),
        after=None,
        limit=20,
    )
    assert batch.records == ()
    assert batch.state is IntelligenceResourcePageState.DEGRADED
    assert batch.degraded_reason_refs[0].startswith("degraded_reason:incomplete-")


@pytest.mark.asyncio
async def test_composite_reader_merges_contributors_and_owns_unsupported_degradation() -> None:
    created = _receipt(
        sequence=1,
        state_before=None,
        state_after=MonitoringLifecycleState.ACTIVE,
    )
    store = _store(created)
    reader = CompositeIntelligenceResourceProjectionReader(
        IntelligenceLedgerResourceProjectionReader(store=store, degrade_unsupported=False),
        MonitoringResourceProjectionReader(store=store, degrade_unsupported=False),
    )
    batch = await reader.read(
        query=_query(IntelligenceResourceKind.MONITOR, IntelligenceResourceKind.ACTION),
        after=None,
        limit=20,
    )
    assert len(batch.records) == 1
    assert batch.records[0].reference.resource_kind is IntelligenceResourceKind.MONITOR
    assert batch.state is IntelligenceResourcePageState.DEGRADED
    assert batch.degraded_reason_refs == ("degraded_reason:unsupported-action",)


def test_composite_reader_rejects_overlapping_resource_owners() -> None:
    store = InMemoryImmutableRecordStore()
    with pytest.raises(ValueError, match="overlap"):
        CompositeIntelligenceResourceProjectionReader(
            MonitoringResourceProjectionReader(store=store),
            MonitoringResourceProjectionReader(store=store),
        )
