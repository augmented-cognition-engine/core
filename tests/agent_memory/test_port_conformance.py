from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest

from ace.core.agent_memory import (
    AgentMemoryScopeV1Alpha1,
    ErasureDependencyProofV1Alpha1,
    LedgerCoordinateV1Alpha1,
    LifecycleEventV1Alpha1,
    LifecycleOperation,
    LifecycleState,
    MemoryVisibility,
    RetentionClass,
)
from ace.core.agent_memory_ports import (
    AgentMemoryPortError,
    AgentMemoryPortFailureCode,
    MemoryDependencyIndex,
)
from ace.core.records import (
    AppendOnlyTransactionRequestV1,
    ImmutableRecordPreconditionFailed,
    ImmutableRecordV1,
)
from ace.core.state import GovernedStateHeadPreconditionV1Alpha1, GovernedStateHeadV1
from ace.intelligence.contracts.agent_memory import (
    AgentMemoryQueryV1Alpha1,
    CandidateReceiptV1Alpha1,
    CandidateRecordV1Alpha1,
    MemoryEpistemicState,
    MemoryGraphProjectionRepository,
    MemoryQueryRepository,
    MemorySemanticFamily,
)
from ace.testing.immutable_records import InMemoryImmutableRecordStore

pytestmark = pytest.mark.unit

NOW = datetime(2026, 8, 11, 20, 0, tzinfo=UTC)
PRODUCT = "product:agent-memory-port"


def _scope() -> AgentMemoryScopeV1Alpha1:
    return AgentMemoryScopeV1Alpha1(
        product_id=PRODUCT,
        actor_id="principal:memory-operator",
        visibility=MemoryVisibility.RESTRICTED,
        retention_class=RetentionClass.RESTRICTED,
        authority_receipt_ref="authority_receipt:memory-port",
    )


class _InMemoryDependencyIndex:
    def __init__(self) -> None:
        self.dependencies: dict[tuple[str, str], tuple[str, ...]] = {}
        self.removed: set[str] = set()

    async def record_dependencies(
        self,
        *,
        scope: AgentMemoryScopeV1Alpha1,
        root_ref: str,
        dependent_refs: tuple[str, ...],
        idempotency_key: str,
    ) -> str:
        key = (str(scope.scope_id), root_ref)
        normalized = tuple(sorted(set(dependent_refs)))
        existing = self.dependencies.get(key)
        if existing is not None and existing != normalized:
            raise AgentMemoryPortError(
                AgentMemoryPortFailureCode.CONFLICT,
                "dependency identity already binds different material",
                retry_safe=False,
            )
        self.dependencies[key] = normalized
        return f"dependency_index_snapshot:{idempotency_key}"

    async def enumerate_dependencies(
        self,
        *,
        scope: AgentMemoryScopeV1Alpha1,
        root_ref: str,
    ) -> tuple[str, ...]:
        return self.dependencies.get((str(scope.scope_id), root_ref), ())

    async def verify_erasure(self, event: LifecycleEventV1Alpha1) -> ErasureDependencyProofV1Alpha1:
        if event.operation is not LifecycleOperation.REQUEST_ERASURE:
            raise AgentMemoryPortError(
                AgentMemoryPortFailureCode.INVALID_CONTRACT,
                "proof verification requires the exact erase-pending request event",
                retry_safe=False,
            )
        dependencies = await self.enumerate_dependencies(scope=event.scope, root_ref=event.target_ref)
        removed = tuple(sorted(ref for ref in dependencies if ref in self.removed))
        if removed != dependencies:
            raise AgentMemoryPortError(
                AgentMemoryPortFailureCode.DEPENDENCY_INCOMPLETE,
                "not every enumerated dependency was removed",
                retry_safe=False,
            )
        return ErasureDependencyProofV1Alpha1(
            scope=event.scope,
            target_ref=event.target_ref,
            erasure_request_event_ref=str(event.event_id),
            dependency_index_snapshot_ref="dependency_index_snapshot:erase-1",
            enumerated_dependency_refs=dependencies,
            removed_dependency_refs=removed,
            verifier_ref="service:memory-erasure-verifier",
            authority_receipt_ref=event.authority_receipt_ref,
            verified_at=NOW,
        )


class _InMemorySemanticProjection:
    def __init__(self) -> None:
        self.lifecycle = {
            "memory_assertion:active": LifecycleState.ACTIVE,
            "memory_assertion:erased": LifecycleState.ERASED,
        }
        self.rebuilds: list[LedgerCoordinateV1Alpha1] = []

    async def retrieve(self, request: AgentMemoryQueryV1Alpha1) -> CandidateReceiptV1Alpha1:
        candidates = tuple(
            CandidateRecordV1Alpha1(
                assertion_ref=assertion_ref,
                family=MemorySemanticFamily.LEARNED_FACT,
                epistemic_state=MemoryEpistemicState.ACCEPTED,
                source_id="source:memory-port",
                source_version_id="source_version:memory-port-v1",
                selected=True,
                aggregate_score=0.5,
            )
            for assertion_ref, state in self.lifecycle.items()
            if state is LifecycleState.ACTIVE
        )
        return CandidateReceiptV1Alpha1(
            query_id=request.query_id,
            scope_id=request.scope.scope_id,
            policy_ref=request.policy_ref,
            authorization_filter_receipt_ref="authority_receipt:projection-filter",
            lifecycle_snapshot_ref="lifecycle_snapshot:projection-1",
            candidates=candidates,
            generated_at=NOW,
        )

    async def expand(
        self,
        request: AgentMemoryQueryV1Alpha1,
        *,
        seed_assertion_refs: tuple[str, ...],
        max_depth: int,
        max_nodes: int,
    ) -> CandidateReceiptV1Alpha1:
        del seed_assertion_refs, max_depth, max_nodes
        return await self.retrieve(request)

    async def rebuild(
        self,
        *,
        scope: AgentMemoryScopeV1Alpha1,
        through: LedgerCoordinateV1Alpha1,
    ) -> str:
        del scope
        self.rebuilds.append(through)
        return f"memory_graph_projection:{through.sequence}"


def _record(*, key: str, order: int) -> ImmutableRecordV1:
    return ImmutableRecordV1(
        product_id=PRODUCT,
        record_space="agent_memory",
        record_kind="ledger_event",
        record_key=key,
        payload_contract="ace.core.agent-memory-test-event/v1alpha1",
        payload={"event_ref": f"event:{key}"},
        as_of=NOW,
        available_at=NOW,
        processing_order=order,
    )


@pytest.mark.asyncio
async def test_existing_core_store_preserves_exact_agent_memory_replay() -> None:
    store = InMemoryImmutableRecordStore()
    request = AppendOnlyTransactionRequestV1(
        product_id=PRODUCT,
        record_space="agent_memory",
        transaction_key="transaction:agent-memory-1",
        records=(_record(key="one", order=0),),
        submitted_at=NOW,
    )

    first = await store.append(request)
    replay = await store.append(request)
    reopened = await store.load_transaction_receipt(
        product_id=PRODUCT,
        record_space="agent_memory",
        transaction_key="transaction:agent-memory-1",
    )

    assert first == replay == reopened
    assert len(store.records) == 1


@pytest.mark.asyncio
async def test_atomic_failure_leaves_no_partial_agent_memory_records() -> None:
    store = InMemoryImmutableRecordStore(fail_after_records=1)
    request = AppendOnlyTransactionRequestV1(
        product_id=PRODUCT,
        record_space="agent_memory",
        transaction_key="transaction:agent-memory-atomic-failure",
        records=(
            _record(key="one", order=0),
            _record(key="two", order=1),
        ),
        submitted_at=NOW,
    )

    with pytest.raises(RuntimeError, match="simulated interruption"):
        await store.append(request)

    assert store.records == {}
    assert store.receipts == {}


@pytest.mark.asyncio
async def test_product_scope_is_required_to_reopen_a_record() -> None:
    store = InMemoryImmutableRecordStore()
    record = _record(key="one", order=0)
    await store.append(
        AppendOnlyTransactionRequestV1(
            product_id=PRODUCT,
            record_space="agent_memory",
            transaction_key="transaction:agent-memory-scope",
            records=(record,),
            submitted_at=NOW,
        )
    )

    assert (
        await store.load_record(
            str(record.storage_id),
            product_id="product:foreign",
            record_space="agent_memory",
            record_kind="ledger_event",
        )
        is None
    )


@pytest.mark.asyncio
async def test_exact_prior_state_coordinate_conflicts_before_agent_memory_append() -> None:
    current = GovernedStateHeadV1(
        state_kind="agent_memory_lifecycle",
        product_id=PRODUCT,
        state_id="memory_assertion:one",
        sequence=2,
        revision_id="agent_memory_lifecycle:revision-2",
        commit_receipt_id="append_only_receipt:lifecycle-2",
        updated_at=NOW,
    )
    stale = GovernedStateHeadV1(
        state_kind=current.state_kind,
        product_id=current.product_id,
        state_id=current.state_id,
        sequence=1,
        revision_id="agent_memory_lifecycle:revision-1",
        commit_receipt_id="append_only_receipt:lifecycle-1",
        updated_at=NOW - timedelta(minutes=1),
    )
    store = InMemoryImmutableRecordStore(
        governed_state_heads={(current.state_kind, current.product_id, current.state_id): current}
    )
    request = AppendOnlyTransactionRequestV1(
        product_id=PRODUCT,
        record_space="agent_memory",
        transaction_key="transaction:stale-lifecycle-coordinate",
        records=(_record(key="stale-lifecycle", order=0),),
        submitted_at=NOW,
        governed_state_preconditions=(GovernedStateHeadPreconditionV1Alpha1.from_head(stale),),
    )

    with pytest.raises(ImmutableRecordPreconditionFailed):
        await store.append(request)

    assert store.records == {}
    assert store.receipts == {}


@pytest.mark.asyncio
async def test_indeterminate_append_requires_receipt_lookup_before_retry() -> None:
    store = InMemoryImmutableRecordStore()
    request = AppendOnlyTransactionRequestV1(
        product_id=PRODUCT,
        record_space="agent_memory",
        transaction_key="transaction:indeterminate-recovery",
        records=(_record(key="indeterminate", order=0),),
        submitted_at=NOW,
    )
    committed = await store.append(request)
    failure = AgentMemoryPortError(
        AgentMemoryPortFailureCode.INDETERMINATE,
        "the transport lost the commit response",
        retry_safe=False,
        receipt_ref=str(committed.receipt_id),
    )

    assert failure.receipt_lookup_required
    recovered = await store.load_transaction_receipt(
        product_id=PRODUCT,
        record_space="agent_memory",
        transaction_key=request.transaction_key,
    )
    assert recovered == committed


@pytest.mark.asyncio
async def test_dependency_index_fails_closed_until_every_derivative_is_removed() -> None:
    index = _InMemoryDependencyIndex()
    assert isinstance(index, MemoryDependencyIndex)
    scope = _scope()
    await index.record_dependencies(
        scope=scope,
        root_ref="memory_assertion:one",
        dependent_refs=("summary:one", "embedding:one", "summary:one"),
        idempotency_key="erase-1",
    )
    erasure_request = LifecycleEventV1Alpha1(
        scope=scope,
        target_ref="memory_assertion:one",
        operation=LifecycleOperation.REQUEST_ERASURE,
        prior_state=LifecycleState.ACTIVE,
        next_state=LifecycleState.ERASE_PENDING,
        actor_ref="principal:memory-operator",
        authority_receipt_ref="authority_receipt:erase-1",
        reason="An authorized operator requested complete erasure.",
        occurred_at=NOW,
        prior_coordinate=LedgerCoordinateV1Alpha1(
            ledger_ref="agent_memory_ledger:port-conformance",
            sequence=1,
            event_ref="agent_memory_lifecycle:activation-1",
            committed_at=NOW - timedelta(minutes=1),
        ),
    )

    index.removed.add("embedding:one")
    with pytest.raises(AgentMemoryPortError) as error:
        await index.verify_erasure(erasure_request)
    assert error.value.code is AgentMemoryPortFailureCode.DEPENDENCY_INCOMPLETE

    index.removed.add("summary:one")
    proof = await index.verify_erasure(erasure_request)
    assert proof.erasure_request_event_ref == erasure_request.event_id
    assert proof.enumerated_dependency_refs == proof.removed_dependency_refs


@pytest.mark.asyncio
async def test_semantic_projection_filters_lifecycle_before_delivery_and_rebuilds_from_coordinate() -> None:
    projection = _InMemorySemanticProjection()
    assert isinstance(projection, MemoryQueryRepository)
    assert isinstance(projection, MemoryGraphProjectionRepository)
    scope = _scope()
    query = AgentMemoryQueryV1Alpha1(
        scope=scope,
        query_digest="sha256:" + "a" * 64,
        eligible_families=(MemorySemanticFamily.LEARNED_FACT,),
        eligible_states=(MemoryEpistemicState.ACCEPTED,),
        receiver_ref="briefing_stage:memory-conformance",
        policy_ref="memory_policy:conformance-v1",
    )

    receipt = await projection.retrieve(query)
    assert [item.assertion_ref for item in receipt.candidates] == ["memory_assertion:active"]
    assert receipt.lifecycle_snapshot_ref == "lifecycle_snapshot:projection-1"

    coordinate = LedgerCoordinateV1Alpha1(
        ledger_ref="agent_memory_ledger:port-conformance",
        sequence=3,
        event_ref="agent_memory_lifecycle:projection-through-3",
        committed_at=NOW,
    )
    snapshot_ref = await projection.rebuild(scope=scope, through=coordinate)
    assert snapshot_ref == "memory_graph_projection:3"
    assert projection.rebuilds == [coordinate]
    assert projection.lifecycle["memory_assertion:erased"] is LifecycleState.ERASED
