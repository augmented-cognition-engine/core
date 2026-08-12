from __future__ import annotations

import asyncio
import json
import sys
from datetime import UTC, datetime, timedelta

from ace.application.agent_memory_ingestion import (
    AuthorizedAgentMemoryUse,
    ExplicitSessionAdapterRegistry,
    SessionIngestionService,
    SessionReadService,
)
from ace.core.agent_memory import AgentMemoryScopeV1Alpha1, LifecycleState
from ace.core.agent_memory_ingestion import (
    EventListQueryV1Alpha1,
    SessionImportIntentV1Alpha1,
    SpanReadQueryV1Alpha1,
)
from ace.core.contracts import canonical_json
from ace.core.runtime_use import AuthenticatedRuntimeContextV1Alpha1
from core.engine.core.db import pool
from core.engine.core.immutable_records import SurrealImmutableRecordStore


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
            lifecycle_snapshot_ref="lifecycle_snapshot:am1-restart-current",
            lifecycle_state=LifecycleState.ACTIVE,
            evaluated_at=evaluated_at,
            expires_at=evaluated_at + timedelta(minutes=1),
        )


async def main() -> None:
    request = json.loads(sys.stdin.read())
    intent = SessionImportIntentV1Alpha1.model_validate(request["intent"], strict=False)
    context = AuthenticatedRuntimeContextV1Alpha1.model_validate(request["context"], strict=False)
    now = datetime.fromisoformat(request["now"]).astimezone(UTC)
    await pool.init()
    try:
        store = SurrealImmutableRecordStore(pool)
        authority = _CurrentAuthority()
        replay = await SessionIngestionService(
            store=store,
            authorization=authority,
            adapters=ExplicitSessionAdapterRegistry.fixture_adapters(),
            clock=lambda: now,
        ).ingest(
            context=context,
            intent=intent,
            raw_input=request["raw_input"],
        )
        reader = SessionReadService(
            store=store,
            authorization=authority,
            clock=lambda: now,
        )
        listing = await reader.list_events(
            context=context,
            query=EventListQueryV1Alpha1(
                scope=intent.scope,
                session_id=replay.normalization_receipt.session_id,
                authorization_receipt_ref=intent.scope.authority_receipt_ref,
            ),
        )
        first_event = replay.proposal.events[0]
        span = await reader.read_span(
            context=context,
            query=SpanReadQueryV1Alpha1(
                scope=intent.scope,
                event_ref=str(first_event.identity.event_id),
                span=first_event.provenance.span,
                authorization_receipt_ref=intent.scope.authority_receipt_ref,
            ),
        )
        print(
            canonical_json(
                {
                    "replayed": replay.replayed,
                    "transaction": replay.transaction_receipt.model_dump(mode="json"),
                    "ingestion": replay.ingestion_receipt.model_dump(mode="json"),
                    "ordered_event_refs": list(listing.receipt.ordered_event_refs),
                    "span_content": span.content,
                    "span_receipt": span.receipt.model_dump(mode="json"),
                }
            )
        )
    finally:
        await pool.close()


if __name__ == "__main__":
    asyncio.run(main())
