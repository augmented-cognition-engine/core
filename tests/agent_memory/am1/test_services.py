from __future__ import annotations

import asyncio
import copy
from datetime import UTC, datetime, timedelta
from typing import Any

import pytest

from ace.application.agent_memory_ingestion import (
    AgentMemoryAuthorizationDenied,
    AgentMemoryReplayConflict,
    AuthorizedAgentMemoryUse,
    ExplicitSessionAdapterRegistry,
    SessionIngestionService,
    SessionReadService,
    normalize_session_proposal,
    normalized_input_digest,
)
from ace.core.agent_memory import (
    AgentMemoryScopeV1Alpha1,
    KnowledgeTimeKind,
    KnowledgeTimeV1Alpha1,
    LifecycleState,
    MemoryVisibility,
    RetentionClass,
)
from ace.core.agent_memory_ingestion import (
    EventListQueryV1Alpha1,
    IdempotencyIdentityV1Alpha1,
    ImportState,
    IngestionMode,
    SessionImportIntentV1Alpha1,
    SessionIngestionStatusV1Alpha1,
    SourceAdapterIdentityV1Alpha1,
    SpanReadQueryV1Alpha1,
)
from ace.core.records import ImmutableRecordPersistenceError
from ace.core.runtime_use import AuthenticatedRuntimeContextV1Alpha1
from ace.testing.immutable_records import InMemoryImmutableRecordStore

pytestmark = pytest.mark.unit

NOW = datetime(2026, 8, 12, 20, 0, tzinfo=UTC)
DIGEST_A = f"sha256:{'a' * 64}"
DIGEST_B = f"sha256:{'b' * 64}"
INPUT_DIGEST = "sha256:d9b8bb1c89ca23a0f7bf58172a1bf61739742552ac6a5551d3b46556349969c8"


class _Authorization:
    def __init__(
        self,
        *,
        deny: bool = False,
        stale: bool = False,
        lifecycle_state: LifecycleState = LifecycleState.ACTIVE,
    ) -> None:
        self.deny = deny
        self.stale = stale
        self.lifecycle_state = lifecycle_state
        self.calls: list[tuple[str, str]] = []

    async def authorize(
        self,
        *,
        context: AuthenticatedRuntimeContextV1Alpha1,
        scope: AgentMemoryScopeV1Alpha1,
        operation: str,
        subject_ref: str,
        evaluated_at: datetime,
    ) -> AuthorizedAgentMemoryUse:
        del context
        self.calls.append((operation, subject_ref))
        if self.deny:
            raise RuntimeError("denied without existence disclosure")
        return AuthorizedAgentMemoryUse(
            product_id=scope.product_id,
            actor_id=scope.actor_id,
            operation=operation,
            subject_ref=subject_ref,
            authority_receipt_ref=scope.authority_receipt_ref,
            evaluated_at=evaluated_at - (timedelta(seconds=1) if self.stale else timedelta()),
            expires_at=evaluated_at + timedelta(minutes=1),
            lifecycle_snapshot_ref="lifecycle_snapshot:fixture-current",
            lifecycle_state=self.lifecycle_state,
        )


class _ReadTrackingStore(InMemoryImmutableRecordStore):
    def __init__(self) -> None:
        super().__init__()
        self.lookup_count = 0

    async def load_record(self, *args: Any, **kwargs: Any):
        self.lookup_count += 1
        return await super().load_record(*args, **kwargs)

    async def read_as_of(self, *args: Any, **kwargs: Any):
        self.lookup_count += 1
        return await super().read_as_of(*args, **kwargs)


def _scope() -> AgentMemoryScopeV1Alpha1:
    return AgentMemoryScopeV1Alpha1(
        product_id="product:agent-memory-am1-fixture",
        actor_id="principal:fixture-user",
        session_id="native-session:fixture-001",
        source_id="source:fixture-session-export",
        visibility=MemoryVisibility.PRIVATE,
        retention_class=RetentionClass.STANDARD,
        authority_receipt_ref="authority_receipt:fixture-import",
    )


def _context(*, product_id: str | None = None, actor_id: str | None = None) -> AuthenticatedRuntimeContextV1Alpha1:
    scope = _scope()
    return AuthenticatedRuntimeContextV1Alpha1(
        product_id=product_id or scope.product_id,
        actor_ref=actor_id or scope.actor_id,
        authentication_receipt_ref="authentication_receipt:fixture",
        authentication_receipt_digest=DIGEST_A,
        authenticated_at=NOW - timedelta(minutes=1),
        expires_at=NOW + timedelta(minutes=5),
    )


def _intent(
    raw: dict[str, Any],
    *,
    immutable_digest: str = INPUT_DIGEST,
) -> SessionImportIntentV1Alpha1:
    registry = ExplicitSessionAdapterRegistry.fixture_adapters()
    adapter_impl = registry.resolve(adapter_ref=raw["adapter_ref"], adapter_version="1.0.0")
    adapter = SourceAdapterIdentityV1Alpha1(
        adapter_ref=adapter_impl.adapter_ref,
        adapter_version=adapter_impl.adapter_version,
        artifact_digest=adapter_impl.artifact_digest,
    )
    idempotency = IdempotencyIdentityV1Alpha1(
        product_id=_scope().product_id,
        actor_id=_scope().actor_id,
        external_key="import:fixture-001",
        immutable_input_digest=immutable_digest,
        adapter_id=adapter.adapter_id,
    )
    return SessionImportIntentV1Alpha1(
        scope=_scope(),
        adapter=adapter,
        input_source_ref="source:fixture-session-export",
        input_source_version_id="source_version:fixture-session-export-v1",
        input_acquisition_receipt_ref="receipt:fixture-session-export",
        source_knowledge_time=KnowledgeTimeV1Alpha1(
            kind=KnowledgeTimeKind.KNOWN,
            first_known_at=datetime(2026, 8, 11, 20, 0, tzinfo=UTC),
            basis_refs=("receipt:fixture-session-export",),
        ),
        immutable_input_digest=immutable_digest,
        native_session_coordinate="fixture-001",
        idempotency=idempotency,
        mode=IngestionMode.BATCH,
        requested_at=NOW,
    )


def test_two_adapters_derive_exact_frozen_canonical_material(am1_fixture: dict[str, Any]) -> None:
    registry = ExplicitSessionAdapterRegistry.fixture_adapters()
    normalized = []
    for raw in am1_fixture["adapter_inputs"]:
        intent = _intent(raw)
        adapter = registry.resolve_identity(intent)
        batch, receipt, turns = normalize_session_proposal(intent=intent, proposal=adapter.normalize(raw))
        expected = am1_fixture["expected_canonical_identities"]
        assert receipt.session_id == expected["session_id"]
        assert receipt.ordered_event_refs == tuple(expected["event_ids"][f"event-{index:03d}"] for index in range(1, 4))
        assert receipt.source_span_refs == tuple(sorted(expected["source_span_ids"].values()))
        assert tuple(turn.turn_id for turn in turns) == tuple(
            expected["turn_ids"][f"event-{index:03d}"] for index in range(1, 4)
        )
        adapter_expected = expected["adapter_specific_import_identities"][raw["adapter_ref"]]
        assert intent.adapter.adapter_id == adapter_expected["adapter_id"]
        assert intent.idempotency.idempotency_id == adapter_expected["idempotency_id"]
        assert intent.intent_id == adapter_expected["intent_id"]
        assert receipt.receipt_id == adapter_expected["normalization_receipt_id"]
        normalized.append(batch.events)
    assert normalized[0] == normalized[1]


@pytest.mark.asyncio
async def test_ingest_exact_replay_is_a_noop_and_survives_service_reopen(am1_fixture: dict[str, Any]) -> None:
    raw = am1_fixture["adapter_inputs"][0]
    intent = _intent(raw)
    store = InMemoryImmutableRecordStore()
    authorization = _Authorization()
    first_service = SessionIngestionService(
        store=store,
        authorization=authorization,
        adapters=ExplicitSessionAdapterRegistry.fixture_adapters(),
        clock=lambda: NOW,
    )
    first = await first_service.ingest(context=_context(), intent=intent, raw_input=raw)
    record_count = len(store.records)
    reopened_service = SessionIngestionService(
        store=store,
        authorization=authorization,
        adapters=ExplicitSessionAdapterRegistry.fixture_adapters(),
        clock=lambda: NOW,
    )
    replay = await reopened_service.ingest(context=_context(), intent=intent, raw_input=raw)

    assert first.replayed is False
    assert replay.replayed is True
    assert replay.ingestion_receipt == first.ingestion_receipt
    assert replay.transaction_receipt == first.transaction_receipt
    assert replay.ingestion_receipt.job_id.startswith("agent_memory_import_job:")
    assert replay.ingestion_receipt.ledger_coordinate.ledger_ref.startswith("agent_memory_import_job_ledger:")
    assert len(store.records) == record_count


@pytest.mark.asyncio
async def test_concurrent_exact_ingest_has_one_commit_and_one_exact_replay(am1_fixture: dict[str, Any]) -> None:
    raw = am1_fixture["adapter_inputs"][0]
    intent = _intent(raw)
    store = InMemoryImmutableRecordStore()
    service = SessionIngestionService(
        store=store,
        authorization=_Authorization(),
        adapters=ExplicitSessionAdapterRegistry.fixture_adapters(),
        clock=lambda: NOW,
    )

    outcomes = await asyncio.gather(
        service.ingest(context=_context(), intent=intent, raw_input=raw),
        service.ingest(context=_context(), intent=intent, raw_input=raw),
    )

    assert sorted(outcome.replayed for outcome in outcomes) == [False, True]
    assert outcomes[0].transaction_receipt == outcomes[1].transaction_receipt
    assert outcomes[0].ingestion_receipt == outcomes[1].ingestion_receipt


@pytest.mark.asyncio
async def test_retry_and_repair_states_append_against_exact_prior_job_coordinate(
    am1_fixture: dict[str, Any],
) -> None:
    raw = am1_fixture["adapter_inputs"][0]
    store = InMemoryImmutableRecordStore()
    service = SessionIngestionService(
        store=store,
        authorization=_Authorization(),
        adapters=ExplicitSessionAdapterRegistry.fixture_adapters(),
        clock=lambda: NOW,
    )
    admission = await service.ingest(context=_context(), intent=_intent(raw), raw_input=raw)
    prior = admission.ingestion_receipt.ledger_coordinate
    repair = SessionIngestionStatusV1Alpha1(
        job_id=admission.ingestion_receipt.job_id,
        state=ImportState.REPAIR_REQUIRED,
        attempt=2,
        previous_state=ImportState.READY,
        prior_coordinate=prior,
        repair_proposal_ref="repair_proposal:fixture",
        recorded_at=NOW,
    )
    repair_admission = await service.record_status(context=_context(), scope=_scope(), status=repair)
    retry = SessionIngestionStatusV1Alpha1(
        job_id=admission.ingestion_receipt.job_id,
        state=ImportState.RETRY_PENDING,
        attempt=2,
        previous_state=ImportState.REPAIR_REQUIRED,
        prior_coordinate=prior.model_copy(update={"sequence": prior.sequence + 1, "event_ref": repair.status_id}),
        retry_after=NOW + timedelta(minutes=1),
        recorded_at=NOW,
    )
    retry_admission = await service.record_status(context=_context(), scope=_scope(), status=retry)

    assert repair_admission.status.prior_coordinate == prior
    assert repair_admission.status.job_id == admission.ingestion_receipt.job_id
    assert retry_admission.transaction_receipt != repair_admission.transaction_receipt


@pytest.mark.asyncio
async def test_divergent_replay_conflicts_before_new_records(am1_fixture: dict[str, Any]) -> None:
    raw = am1_fixture["adapter_inputs"][0]
    store = InMemoryImmutableRecordStore()
    service = SessionIngestionService(
        store=store,
        authorization=_Authorization(),
        adapters=ExplicitSessionAdapterRegistry.fixture_adapters(),
        clock=lambda: NOW,
    )
    await service.ingest(context=_context(), intent=_intent(raw), raw_input=raw)
    record_count = len(store.records)
    divergent_raw = copy.deepcopy(raw)
    divergent_raw["events"][0]["body"] = "Divergent immutable source material."
    adapter = ExplicitSessionAdapterRegistry.fixture_adapters().resolve(
        adapter_ref=divergent_raw["adapter_ref"],
        adapter_version="1.0.0",
    )
    divergent = _intent(
        divergent_raw,
        immutable_digest=normalized_input_digest(adapter.normalize(divergent_raw)),
    )

    with pytest.raises(AgentMemoryReplayConflict, match="digest|exact import intent|divergent import intent"):
        await service.ingest(context=_context(), intent=divergent, raw_input=divergent_raw)
    assert len(store.records) == record_count


@pytest.mark.asyncio
async def test_injected_append_failure_is_atomic(am1_fixture: dict[str, Any]) -> None:
    raw = am1_fixture["adapter_inputs"][0]
    store = InMemoryImmutableRecordStore(fail_after_records=2)
    service = SessionIngestionService(
        store=store,
        authorization=_Authorization(),
        adapters=ExplicitSessionAdapterRegistry.fixture_adapters(),
        clock=lambda: NOW,
    )

    with pytest.raises(ImmutableRecordPersistenceError, match="simulated interruption"):
        await service.ingest(context=_context(), intent=_intent(raw), raw_input=raw)
    assert store.records == {}
    assert store.receipts == {}


@pytest.mark.asyncio
async def test_authorized_listing_and_span_read_keep_body_private(am1_fixture: dict[str, Any]) -> None:
    raw = am1_fixture["adapter_inputs"][0]
    store = InMemoryImmutableRecordStore()
    authorization = _Authorization()
    admission = await SessionIngestionService(
        store=store,
        authorization=authorization,
        adapters=ExplicitSessionAdapterRegistry.fixture_adapters(),
        clock=lambda: NOW,
    ).ingest(context=_context(), intent=_intent(raw), raw_input=raw)
    reader = SessionReadService(store=store, authorization=authorization, clock=lambda: NOW)
    listing = await reader.list_events(
        context=_context(),
        query=EventListQueryV1Alpha1(
            scope=_scope(),
            session_id=admission.normalization_receipt.session_id,
            authorization_receipt_ref="authority_receipt:request",
        ),
    )
    first = listing.events[0]
    span_read = await reader.read_span(
        context=_context(),
        query=SpanReadQueryV1Alpha1(
            scope=_scope(),
            event_ref=first.identity.event_id,
            span=first.provenance.span,
            authorization_receipt_ref="authority_receipt:request",
        ),
    )

    assert listing.receipt.ordered_event_refs == admission.normalization_receipt.ordered_event_refs
    assert listing.receipt.lifecycle_snapshot_ref == "lifecycle_snapshot:fixture-current"
    assert span_read.content == raw["events"][0]["body"]
    assert "body" not in span_read.receipt.model_dump(mode="json")
    assert span_read.receipt.returned_event_refs == (first.identity.event_id,)


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "context",
    [
        _context(product_id="product:foreign"),
        _context(actor_id="principal:foreign"),
    ],
)
async def test_cross_product_and_principal_fail_before_any_lookup(context: AuthenticatedRuntimeContextV1Alpha1) -> None:
    store = _ReadTrackingStore()
    reader = SessionReadService(store=store, authorization=_Authorization(), clock=lambda: NOW)
    query = EventListQueryV1Alpha1(
        scope=_scope(),
        session_id="agent_memory_session:nonexistent",
        authorization_receipt_ref="authority_receipt:request",
    )

    with pytest.raises(AgentMemoryAuthorizationDenied, match="operation is unavailable"):
        await reader.list_events(context=context, query=query)
    assert store.lookup_count == 0


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "authorization",
    [
        _Authorization(deny=True),
        _Authorization(stale=True),
        _Authorization(lifecycle_state=LifecycleState.RESTRICTED),
        _Authorization(lifecycle_state=LifecycleState.EXPIRED),
        _Authorization(lifecycle_state=LifecycleState.QUARANTINED),
    ],
)
async def test_denied_or_stale_authority_fails_before_nonexistent_resource_probe(
    authorization: _Authorization,
) -> None:
    store = _ReadTrackingStore()
    reader = SessionReadService(store=store, authorization=authorization, clock=lambda: NOW)
    query = EventListQueryV1Alpha1(
        scope=_scope(),
        session_id="agent_memory_session:nonexistent",
        authorization_receipt_ref="authority_receipt:request",
    )

    with pytest.raises(AgentMemoryAuthorizationDenied, match="operation is unavailable"):
        await reader.list_events(context=_context(), query=query)
    assert store.lookup_count == 0
