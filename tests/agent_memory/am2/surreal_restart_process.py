from __future__ import annotations

import asyncio
import json
import sys
from datetime import UTC, datetime, timedelta

from ace.application.agent_memory_assertions import (
    DeterministicFixtureExtractionAdapter,
    InertAssertionCandidate,
    MemoryAssertionReconciliationService,
    MemoryGraphProjectionService,
)
from ace.application.agent_memory_ingestion import AuthorizedAgentMemoryUse
from ace.core.agent_memory import AgentMemoryScopeV1Alpha1, LifecycleState
from ace.core.contracts import canonical_json
from ace.core.runtime_use import AuthenticatedRuntimeContextV1Alpha1
from ace.intelligence.contracts.agent_memory_assertions import (
    AssertionFamilyV1Alpha1,
    MemoryExtractionRequestV1Alpha1,
    MemoryReconciliationPolicyV1Alpha1,
)
from core.engine.core.db import pool
from core.engine.core.immutable_records import SurrealImmutableRecordStore


class _Authority:
    async def authorize(self, *, context, scope, operation, subject_ref, evaluated_at):
        del context
        return AuthorizedAgentMemoryUse(
            product_id=scope.product_id,
            actor_id=scope.actor_id,
            operation=operation,
            subject_ref=subject_ref,
            authority_receipt_ref=scope.authority_receipt_ref,
            evaluated_at=evaluated_at,
            lifecycle_snapshot_ref="lifecycle_snapshot:am2-fresh-process",
            lifecycle_state=LifecycleState.ACTIVE,
            expires_at=evaluated_at + timedelta(minutes=2),
        )


class _Reader:
    async def read(self, *, source):
        del source
        raise AssertionError("exact durable replay must not reread a private source body")


async def main() -> None:
    raw = json.loads(sys.stdin.read())
    request = MemoryExtractionRequestV1Alpha1.model_validate(raw["request"], strict=False)
    context = AuthenticatedRuntimeContextV1Alpha1.model_validate(raw["context"], strict=False)
    policy = MemoryReconciliationPolicyV1Alpha1.model_validate(raw["policy"], strict=False)
    candidate_raw = raw["candidate"]
    candidate = InertAssertionCandidate(
        source_index=candidate_raw["source_index"],
        family=AssertionFamilyV1Alpha1(candidate_raw["family"]),
        predicate_ref=candidate_raw["predicate_ref"],
        statement=candidate_raw["statement"],
        entity_ref=candidate_raw.get("entity_ref"),
        unresolved_entity_ref=candidate_raw.get("unresolved_entity_ref"),
        target_ref=candidate_raw.get("target_ref"),
        correction_target_ref=candidate_raw.get("correction_target_ref"),
        proposed_confidence=candidate_raw.get("proposed_confidence"),
    )
    now = datetime.fromisoformat(raw["now"]).astimezone(UTC)
    await pool.init()
    try:
        store = SurrealImmutableRecordStore(pool)
        adapter = DeterministicFixtureExtractionAdapter((candidate,))
        authority = _Authority()
        replay = await MemoryAssertionReconciliationService(
            store=store,
            authorization=authority,
            source_reader=_Reader(),
            adapters=(adapter,),
            clock=lambda: now,
        ).extract_and_reconcile(context=context, request=request, policy=policy)
        graph = await MemoryGraphProjectionService(
            store=store,
            authorization=authority,
            clock=lambda: now,
        ).query(context=context, scope=AgentMemoryScopeV1Alpha1.model_validate(request.scope.model_dump(mode="python")))
        print(
            canonical_json(
                {
                    "replayed": replay.replayed,
                    "transaction": replay.transaction_receipt.model_dump(mode="json"),
                    "reconciliation": replay.receipt.model_dump(mode="json"),
                    "projection": graph.projection.model_dump(mode="json"),
                    "graph_receipt": graph.receipt.model_dump(mode="json"),
                }
            )
        )
    finally:
        await pool.close()


if __name__ == "__main__":
    asyncio.run(main())
