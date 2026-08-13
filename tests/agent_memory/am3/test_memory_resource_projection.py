from __future__ import annotations

from datetime import timedelta

import pytest

from ace.application import (
    AgentMemoryResourceProjectionReader,
    ContextPlannerService,
    StaticRetrievalStateOwner,
)
from ace.core import AuthenticatedRuntimeContextV1Alpha1
from ace.intelligence import (
    IntelligenceResourceAvailability,
    IntelligenceResourceKind,
    IntelligenceResourcePageState,
    IntelligenceResourceQueryV1Alpha1,
)
from core.engine.core.intelligence_resource_plane import intelligence_resource_projection_reader
from tests.agent_memory.am2.test_assertion_reconciliation import NOW
from tests.agent_memory.am3.test_authorized_recall import (
    _Authority,
    _Instructions,
    _planner_request,
    _policy,
    _recall,
    _seed,
    _snapshot,
)

pytestmark = pytest.mark.unit

PRODUCT = "product:am2"


def _query(*kinds: IntelligenceResourceKind) -> IntelligenceResourceQueryV1Alpha1:
    return IntelligenceResourceQueryV1Alpha1(
        authenticated_context=AuthenticatedRuntimeContextV1Alpha1(
            product_id=PRODUCT,
            actor_ref="principal:memory-analyst",
            authentication_receipt_ref="authentication_receipt:memory-projection",
            authentication_receipt_digest="sha256:" + "f" * 64,
            authenticated_at=NOW,
            expires_at=NOW + timedelta(hours=1),
        ),
        product_id=PRODUCT,
        authority_grant_ref="authority_grant:resource-read",
        resource_kinds=kinds,
        as_of=NOW + timedelta(minutes=10),
        available_at=NOW + timedelta(minutes=10),
        page_size=100,
    )


async def _memory_use_fixture():
    store, _, _, graph_projection = await _seed(second=False)
    policy = _policy()
    snapshot = _snapshot(policy, graph_projection)
    recall = _recall()
    planned = await ContextPlannerService(
        store=store,
        authorization=_Authority(),
        state_owner=StaticRetrievalStateOwner(snapshot),
        instruction_resolver=_Instructions(),
        clock=lambda: NOW + timedelta(minutes=2),
    ).plan(_planner_request(recall, policy, snapshot))
    selected = planned.manifest.selected_candidate_refs
    recorded = await ContextPlannerService(
        store=store,
        authorization=_Authority(),
        state_owner=StaticRetrievalStateOwner(snapshot),
        instruction_resolver=_Instructions(),
        clock=lambda: NOW + timedelta(minutes=3),
    ).record_use(
        request=recall,
        manifest=planned.manifest,
        injected_candidate_refs=selected,
        evidence_refs=("bounded_attribution:resource-plane",),
    )
    return store, planned, recorded


@pytest.mark.asyncio
async def test_context_manifest_memory_use_and_lineage_share_exact_public_provenance() -> None:
    store, planned, recorded = await _memory_use_fixture()
    query = _query(
        IntelligenceResourceKind.CONTEXT_MANIFEST,
        IntelligenceResourceKind.MEMORY_USE,
        IntelligenceResourceKind.EVIDENCE_LINEAGE,
    )

    batch = await AgentMemoryResourceProjectionReader(store=store).read(
        query=query,
        after=None,
        limit=100,
    )

    assert batch.state is IntelligenceResourcePageState.DEGRADED
    by_kind = {
        kind: tuple(item for item in batch.records if item.reference.resource_kind is kind)
        for kind in query.resource_kinds
    }
    assert len(by_kind[IntelligenceResourceKind.CONTEXT_MANIFEST]) == 1
    assert len(by_kind[IntelligenceResourceKind.MEMORY_USE]) == 1
    assert len(by_kind[IntelligenceResourceKind.EVIDENCE_LINEAGE]) == len(recorded.lineages)
    manifest = by_kind[IntelligenceResourceKind.CONTEXT_MANIFEST][0]
    use = by_kind[IntelligenceResourceKind.MEMORY_USE][0]
    assert manifest.availability is IntelligenceResourceAvailability.DEGRADED
    assert manifest.degraded_reason_refs
    assert use.availability is IntelligenceResourceAvailability.AVAILABLE
    assert manifest.reference.resource_id == planned.manifest.artifact_id
    assert use.reference.resource_id == recorded.use.artifact_id
    assert use.provenance == (manifest.reference,)
    assert all(item.provenance == (manifest.reference,) for item in by_kind[IntelligenceResourceKind.EVIDENCE_LINEAGE])
    assert manifest.payload is not None
    assert "captured_payload_json" not in manifest.payload.value_json
    assert "statement" not in manifest.payload.value_json
    assert '"benefit":"unknown"' in use.payload.value_json

    restarted = await AgentMemoryResourceProjectionReader(store=store).read(
        query=query,
        after=None,
        limit=100,
    )
    assert restarted == batch
    host_composed = await intelligence_resource_projection_reader(store).read(
        query=query,
        after=None,
        limit=100,
    )
    assert host_composed == batch


@pytest.mark.asyncio
async def test_missing_manifest_fails_closed_for_memory_use_and_lineage() -> None:
    store, planned, _ = await _memory_use_fixture()
    manifest_storage_id = next(
        key for key, record in store.records.items() if record.record_key == planned.manifest.artifact_id
    )
    del store.records[manifest_storage_id]

    batch = await AgentMemoryResourceProjectionReader(store=store).read(
        query=_query(IntelligenceResourceKind.MEMORY_USE, IntelligenceResourceKind.EVIDENCE_LINEAGE),
        after=None,
        limit=100,
    )

    assert batch.records == ()
    assert batch.state is IntelligenceResourcePageState.DEGRADED
    assert set(batch.degraded_reason_refs) == {
        "degraded_reason:invalid-memory_context_lineage",
        "degraded_reason:invalid-memory_context_use",
    }
