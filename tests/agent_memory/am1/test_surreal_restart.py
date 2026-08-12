from __future__ import annotations

import json
import os
import subprocess
import sys
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any
from uuid import uuid4

import pytest

from ace.application.agent_memory_ingestion import (
    EVENT_BODY_RECORD_KIND,
    EVENT_METADATA_RECORD_KIND,
    IMPORT_INTENT_RECORD_KIND,
    IMPORT_JOB_RECORD_KIND,
    INGESTION_RECEIPT_RECORD_KIND,
    INGESTION_STATUS_RECORD_KIND,
    NORMALIZATION_RECEIPT_RECORD_KIND,
    AgentMemoryReplayConflict,
    AuthorizedAgentMemoryUse,
    ExplicitSessionAdapterRegistry,
    SessionIngestionService,
    SessionReadService,
    _record_space,
    _transaction_key,
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
    IngestionMode,
    SessionImportIntentV1Alpha1,
    SourceAdapterIdentityV1Alpha1,
    SpanReadQueryV1Alpha1,
)
from ace.core.records import ImmutableRecordPersistenceError
from ace.core.runtime_use import AuthenticatedRuntimeContextV1Alpha1

pytestmark = [pytest.mark.integration, pytest.mark.asyncio]

NOW = datetime(2026, 8, 12, 20, 0, tzinfo=UTC)
REOPENED_AT = NOW + timedelta(seconds=1)
AUTH_DIGEST = f"sha256:{'a' * 64}"


class _CurrentAuthority:
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
        return AuthorizedAgentMemoryUse(
            product_id=scope.product_id,
            actor_id=scope.actor_id,
            operation=operation,
            subject_ref=subject_ref,
            authority_receipt_ref=scope.authority_receipt_ref,
            lifecycle_snapshot_ref="lifecycle_snapshot:am1-integration-current",
            lifecycle_state=LifecycleState.ACTIVE,
            evaluated_at=evaluated_at,
            expires_at=evaluated_at + timedelta(minutes=1),
        )


def _coordinates(
    raw_input: dict[str, Any],
    *,
    suffix: str,
) -> tuple[SessionImportIntentV1Alpha1, AuthenticatedRuntimeContextV1Alpha1]:
    scope = AgentMemoryScopeV1Alpha1(
        product_id=f"product:agent-memory-am1-{suffix}",
        actor_id="principal:am1-integration",
        session_id="native-session:fixture-001",
        source_id="source:fixture-session-export",
        visibility=MemoryVisibility.PRIVATE,
        retention_class=RetentionClass.STANDARD,
        authority_receipt_ref="authority_receipt:am1-integration",
    )
    registry = ExplicitSessionAdapterRegistry.fixture_adapters()
    adapter_impl = registry.resolve(
        adapter_ref=raw_input["adapter_ref"],
        adapter_version="1.0.0",
    )
    adapter = SourceAdapterIdentityV1Alpha1(
        adapter_ref=adapter_impl.adapter_ref,
        adapter_version=adapter_impl.adapter_version,
        artifact_digest=adapter_impl.artifact_digest,
    )
    immutable_digest = normalized_input_digest(adapter_impl.normalize(raw_input))
    intent = SessionImportIntentV1Alpha1(
        scope=scope,
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
        idempotency=IdempotencyIdentityV1Alpha1(
            product_id=scope.product_id,
            actor_id=scope.actor_id,
            external_key="import:fixture-001",
            immutable_input_digest=immutable_digest,
            adapter_id=str(adapter.adapter_id),
        ),
        mode=IngestionMode.BATCH,
        requested_at=NOW,
    )
    context = AuthenticatedRuntimeContextV1Alpha1(
        product_id=scope.product_id,
        actor_ref=scope.actor_id,
        authentication_receipt_ref="authentication_receipt:am1-integration",
        authentication_receipt_digest=AUTH_DIGEST,
        authenticated_at=NOW - timedelta(minutes=1),
        expires_at=NOW + timedelta(minutes=5),
    )
    return intent, context


async def test_surreal_first_ingest_restart_replay_reads_conflict_and_atomic_failure(
    db_pool: Any,
    am1_fixture: dict[str, Any],
) -> None:
    from core.engine.core.immutable_records import SurrealImmutableRecordStore

    raw_input = am1_fixture["adapter_inputs"][0]
    intent, context = _coordinates(raw_input, suffix=uuid4().hex)
    authority = _CurrentAuthority()
    first_store = SurrealImmutableRecordStore(db_pool)
    first = await SessionIngestionService(
        store=first_store,
        authorization=authority,
        adapters=ExplicitSessionAdapterRegistry.fixture_adapters(),
        clock=lambda: NOW,
    ).ingest(context=context, intent=intent, raw_input=raw_input)
    assert first.replayed is False

    reopened_store = SurrealImmutableRecordStore(db_pool)
    replay = await SessionIngestionService(
        store=reopened_store,
        authorization=authority,
        adapters=ExplicitSessionAdapterRegistry.fixture_adapters(),
        clock=lambda: REOPENED_AT,
    ).ingest(context=context, intent=intent, raw_input=raw_input)
    assert replay.replayed is True
    assert replay.transaction_receipt == first.transaction_receipt
    assert replay.ingestion_receipt == first.ingestion_receipt

    reader = SessionReadService(
        store=reopened_store,
        authorization=authority,
        clock=lambda: REOPENED_AT,
    )
    listing = await reader.list_events(
        context=context,
        query=EventListQueryV1Alpha1(
            scope=intent.scope,
            session_id=first.normalization_receipt.session_id,
            authorization_receipt_ref=intent.scope.authority_receipt_ref,
        ),
    )
    expected_order = tuple(str(event.identity.event_id) for event in first.proposal.events)
    assert listing.receipt.ordered_event_refs == expected_order
    assert tuple(str(event.identity.event_id) for event in listing.events) == expected_order

    first_event = first.proposal.events[0]
    span = await reader.read_span(
        context=context,
        query=SpanReadQueryV1Alpha1(
            scope=intent.scope,
            event_ref=str(first_event.identity.event_id),
            span=first_event.provenance.span,
            authorization_receipt_ref=intent.scope.authority_receipt_ref,
        ),
    )
    assert span.content == raw_input["events"][0]["body"]
    assert span.content not in span.receipt.model_dump_json()

    divergent = SessionImportIntentV1Alpha1.model_validate(
        {
            **intent.model_dump(mode="python", exclude={"intent_id"}),
            "task_ref": "task:divergent-replay",
        }
    )
    with pytest.raises(AgentMemoryReplayConflict, match="idempotency identity"):
        await SessionIngestionService(
            store=SurrealImmutableRecordStore(db_pool),
            authorization=authority,
            adapters=ExplicitSessionAdapterRegistry.fixture_adapters(),
            clock=lambda: NOW,
        ).ingest(context=context, intent=divergent, raw_input=raw_input)

    script = Path(__file__).with_name("surreal_restart_process.py")
    process = subprocess.run(
        [sys.executable, "-B", str(script)],
        cwd=Path(__file__).resolve().parents[3],
        env={**os.environ, "PYTHONDONTWRITEBYTECODE": "1"},
        input=json.dumps(
            {
                "intent": intent.model_dump(mode="json"),
                "context": context.model_dump(mode="json"),
                "raw_input": raw_input,
                "now": REOPENED_AT.isoformat(),
            }
        ),
        capture_output=True,
        text=True,
        timeout=60,
        check=False,
    )
    assert process.returncode == 0, process.stderr or process.stdout
    fresh_process = json.loads(process.stdout.strip().splitlines()[-1])
    assert fresh_process["replayed"] is True
    assert fresh_process["transaction"] == first.transaction_receipt.model_dump(mode="json")
    assert fresh_process["ingestion"] == first.ingestion_receipt.model_dump(mode="json")
    assert fresh_process["ordered_event_refs"] == list(expected_order)
    assert fresh_process["span_content"] == raw_input["events"][0]["body"]
    assert fresh_process["span_content"] not in json.dumps(fresh_process["span_receipt"])

    interrupted_intent, interrupted_context = _coordinates(raw_input, suffix=uuid4().hex)
    interrupted_store = SurrealImmutableRecordStore(
        db_pool,
        simulate_failure_after_records=3,
    )
    with pytest.raises(ImmutableRecordPersistenceError, match="immutable-record transaction failed"):
        await SessionIngestionService(
            store=interrupted_store,
            authorization=authority,
            adapters=ExplicitSessionAdapterRegistry.fixture_adapters(),
            clock=lambda: NOW,
        ).ingest(
            context=interrupted_context,
            intent=interrupted_intent,
            raw_input=raw_input,
        )
    for record_kind in (
        IMPORT_INTENT_RECORD_KIND,
        IMPORT_JOB_RECORD_KIND,
        EVENT_METADATA_RECORD_KIND,
        EVENT_BODY_RECORD_KIND,
        NORMALIZATION_RECEIPT_RECORD_KIND,
        INGESTION_STATUS_RECORD_KIND,
        INGESTION_RECEIPT_RECORD_KIND,
    ):
        assert (
            await interrupted_store.count_as_of(
                product_id=interrupted_intent.scope.product_id,
                record_space=_record_space(interrupted_intent.scope),
                record_kind=record_kind,
                available_at=REOPENED_AT,
            )
            == 0
        )
    assert (
        await interrupted_store.load_transaction_receipt(
            product_id=interrupted_intent.scope.product_id,
            record_space=_record_space(interrupted_intent.scope),
            transaction_key=_transaction_key(interrupted_intent),
        )
        is None
    )
