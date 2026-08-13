from __future__ import annotations

from datetime import timedelta

import pytest

from ace.application import ActionResourceProjectionReader
from ace.core import AuthenticatedRuntimeContextV1Alpha1
from ace.intelligence import (
    IntelligenceResourceAvailability,
    IntelligenceResourceKind,
    IntelligenceResourcePageState,
    IntelligenceResourceQueryV1Alpha1,
)
from core.engine.core.intelligence_resource_plane import intelligence_resource_projection_reader
from tests.test_governed_action_execution import NOW, PRODUCT, _Adapter, _intent, _service, _Store

pytestmark = pytest.mark.unit


def _query() -> IntelligenceResourceQueryV1Alpha1:
    return IntelligenceResourceQueryV1Alpha1(
        authenticated_context=AuthenticatedRuntimeContextV1Alpha1(
            product_id=PRODUCT,
            actor_ref="principal:action-analyst",
            authentication_receipt_ref="authentication_receipt:action-projection",
            authentication_receipt_digest="sha256:" + "9" * 64,
            authenticated_at=NOW,
            expires_at=NOW + timedelta(hours=1),
        ),
        product_id=PRODUCT,
        authority_grant_ref="authority_grant:resource-read",
        resource_kinds=(IntelligenceResourceKind.ACTION,),
        as_of=NOW + timedelta(minutes=10),
        available_at=NOW + timedelta(minutes=10),
        page_size=20,
    )


@pytest.mark.asyncio
async def test_terminal_action_projects_exact_decision_lineage_and_admission_supersession() -> None:
    store = _Store()
    intent = await _intent(store)
    outcome = await _service(store, _Adapter(store)).execute(intent)

    batch = await ActionResourceProjectionReader(store=store).read(
        query=_query(),
        after=None,
        limit=20,
    )

    assert batch.state is IntelligenceResourcePageState.COMPLETE
    assert len(batch.records) == 1
    action = batch.records[0]
    assert action.reference.resource_kind is IntelligenceResourceKind.ACTION
    assert action.reference.resource_id == intent.action_key
    assert action.reference.resource_digest == outcome.terminal.receipt_digest
    assert action.reference.revision == 2
    assert action.availability is IntelligenceResourceAvailability.AVAILABLE
    assert action.supersedes is not None
    assert action.supersedes.revision == 1
    assert action.supersedes.resource_digest == outcome.admission.receipt_digest
    assert action.provenance[0].resource_kind is IntelligenceResourceKind.DECISION
    assert action.provenance[0].resource_id == intent.decision.record_key
    assert action.payload is not None
    assert action.payload.parsed_value()["result"]["disposition"] == "succeeded"

    restarted = await ActionResourceProjectionReader(store=store).read(
        query=_query(),
        after=None,
        limit=20,
    )
    assert restarted == batch
    host_composed = await intelligence_resource_projection_reader(store).read(
        query=_query(),
        after=None,
        limit=20,
    )
    assert host_composed == batch


@pytest.mark.asyncio
async def test_admitted_without_terminal_is_visible_only_as_explicitly_degraded() -> None:
    store = _Store()
    await _service(store, _Adapter(store)).execute(await _intent(store))
    terminal_storage_id = next(key for key, record in store.records.items() if record.record_kind == "action_terminal")
    del store.records[terminal_storage_id]

    batch = await ActionResourceProjectionReader(store=store).read(
        query=_query(),
        after=None,
        limit=20,
    )

    assert batch.state is IntelligenceResourcePageState.DEGRADED
    assert len(batch.records) == 1
    pending = batch.records[0]
    assert pending.reference.revision == 1
    assert pending.availability is IntelligenceResourceAvailability.DEGRADED
    assert pending.degraded_reason_refs == ("degraded_reason:action-terminal-pending",)


@pytest.mark.asyncio
async def test_failed_terminal_is_complete_truth_not_a_fabricated_success() -> None:
    store = _Store()
    await _service(store, _Adapter(store, mode="raise")).execute(await _intent(store))

    batch = await ActionResourceProjectionReader(store=store).read(
        query=_query(),
        after=None,
        limit=20,
    )

    assert batch.state is IntelligenceResourcePageState.COMPLETE
    assert batch.records[0].availability is IntelligenceResourceAvailability.AVAILABLE
    assert "finished failed" in batch.records[0].summary
    assert batch.records[0].payload.parsed_value()["result"]["effect_state"] == "unknown"


@pytest.mark.asyncio
async def test_action_with_missing_decision_is_suppressed_as_broken_lineage() -> None:
    store = _Store()
    await _service(store, _Adapter(store)).execute(await _intent(store))
    decision_storage_id = next(key for key, record in store.records.items() if record.record_kind == "decision")
    del store.records[decision_storage_id]

    batch = await ActionResourceProjectionReader(store=store).read(
        query=_query(),
        after=None,
        limit=20,
    )

    assert batch.records == ()
    assert batch.state is IntelligenceResourcePageState.DEGRADED
    assert batch.degraded_reason_refs == ("degraded_reason:invalid-action-decision-lineage",)
