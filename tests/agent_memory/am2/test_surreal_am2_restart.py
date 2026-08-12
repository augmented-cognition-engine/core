from __future__ import annotations

# The AM2-specific basename avoids pytest collisions with the frozen AM1 restart module.
import json
import os
import subprocess
import sys
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any
from uuid import uuid4

import pytest

from ace.application.agent_memory_assertions import (
    ASSERTION_DECISION_RECORD_KIND,
    EXTRACTION_RECEIPT_RECORD_KIND,
    GRAPH_PROJECTION_RECORD_KIND,
    RECONCILIATION_RECEIPT_RECORD_KIND,
    DeterministicFixtureExtractionAdapter,
    InertAssertionCandidate,
    MemoryAssertionReconciliationService,
    MemoryGraphProjectionService,
    _record_space,
)
from ace.application.agent_memory_ingestion import AuthorizedAgentMemoryUse
from ace.core.agent_memory import (
    AgentMemoryScopeV1Alpha1,
    KnowledgeTimeKind,
    KnowledgeTimeV1Alpha1,
    LifecycleState,
    MemoryVisibility,
    RetentionClass,
    WholeSourceSpanV1Alpha1,
    WorldTimeKind,
    WorldTimeV1Alpha1,
)
from ace.core.records import ImmutableRecordPersistenceError
from ace.core.runtime_use import AuthenticatedRuntimeContextV1Alpha1
from ace.intelligence.contracts.agent_memory_assertions import (
    ActivatedMemoryConstraintsV1Alpha1,
    AssertionFamilyV1Alpha1,
    AssertionSourceEnvelopeV1Alpha1,
    AssertionSourceKind,
    EvidenceStatus,
    GovernedEvidenceV1Alpha1,
    MemoryExtractionRequestV1Alpha1,
    MemoryReconciliationPolicyV1Alpha1,
    SourceAuthorityKind,
    SourceIndependence,
)

pytestmark = [pytest.mark.integration, pytest.mark.asyncio]

NOW = datetime(2026, 8, 12, 23, 0, tzinfo=UTC)


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
            lifecycle_snapshot_ref="lifecycle_snapshot:am2-surreal-current",
            lifecycle_state=LifecycleState.ACTIVE,
            expires_at=evaluated_at + timedelta(minutes=2),
        )


class _Reader:
    def __init__(self, body: str) -> None:
        self.body = body
        self.calls = 0

    async def read(self, *, source):
        del source
        self.calls += 1
        return self.body


def _coordinates(suffix: str):
    scope = AgentMemoryScopeV1Alpha1(
        product_id=f"product:am2-surreal-{suffix}",
        actor_id="principal:am2-surreal",
        visibility=MemoryVisibility.PRIVATE,
        retention_class=RetentionClass.STANDARD,
        authority_receipt_ref="authority_receipt:am2-surreal",
    )
    source_version = "source_version:am2-surreal-v1"
    envelope = AssertionSourceEnvelopeV1Alpha1(
        source_kind=AssertionSourceKind.DOCUMENT,
        source_id="source:am2-surreal",
        source_version_id=source_version,
        span=WholeSourceSpanV1Alpha1(source_version_id=source_version),
        source_authority=SourceAuthorityKind.EXTERNAL_CONTENT,
        reliability=GovernedEvidenceV1Alpha1(
            status=EvidenceStatus.KNOWN,
            value=0.8,
            policy_ref="policy:am2-surreal-reliability",
            evidence_receipt_ref="evidence_receipt:am2-surreal-reliability",
        ),
        freshness=GovernedEvidenceV1Alpha1(
            status=EvidenceStatus.KNOWN,
            value=0.8,
            policy_ref="policy:am2-surreal-freshness",
            evidence_receipt_ref="evidence_receipt:am2-surreal-freshness",
        ),
        independence=SourceIndependence.INDEPENDENT,
        acquisition_receipt_ref="acquisition_receipt:am2-surreal",
        knowledge_time=KnowledgeTimeV1Alpha1(
            kind=KnowledgeTimeKind.KNOWN,
            first_known_at=NOW - timedelta(hours=2),
            basis_refs=("acquisition_receipt:am2-surreal",),
        ),
        knowledge_revision_at=NOW - timedelta(hours=1),
        world_time=WorldTimeV1Alpha1(
            kind=WorldTimeKind.INTERVAL,
            valid_from=NOW - timedelta(days=1),
            valid_to=NOW + timedelta(days=1),
        ),
    )
    candidate = InertAssertionCandidate(
        source_index=0,
        family=AssertionFamilyV1Alpha1.LEARNED_FACT,
        predicate_ref="predicate:am2-surreal-state",
        statement="Synthetic durable assertion body.",
        entity_ref="entity:am2-surreal",
        proposed_confidence=0.8,
    )
    adapter = DeterministicFixtureExtractionAdapter((candidate,))
    request = MemoryExtractionRequestV1Alpha1(
        scope=scope,
        source_envelopes=(envelope,),
        adapter_ref=adapter.adapter_ref,
        adapter_version=adapter.adapter_version,
        adapter_digest=adapter.adapter_digest,
        constraints=ActivatedMemoryConstraintsV1Alpha1(activation_ref="activation:am2-surreal-inert"),
        idempotency_ref=f"idempotency:am2-surreal-{suffix}",
        requested_at=NOW,
    )
    policy = MemoryReconciliationPolicyV1Alpha1(
        policy_ref="policy:am2-surreal-reconciliation",
        policy_version="1.0.0",
        policy_digest="sha256:" + "7" * 64,
        minimum_confidence=0.5,
    )
    context = AuthenticatedRuntimeContextV1Alpha1(
        product_id=scope.product_id,
        actor_ref=scope.actor_id,
        authentication_receipt_ref="authentication_receipt:am2-surreal",
        authentication_receipt_digest="sha256:" + "6" * 64,
        authenticated_at=NOW - timedelta(minutes=1),
        expires_at=NOW + timedelta(hours=1),
    )
    return scope, envelope, candidate, adapter, request, policy, context


async def test_surreal_reopen_fresh_process_projection_rebuild_and_atomic_failure(db_pool: Any) -> None:
    from core.engine.core.immutable_records import SurrealImmutableRecordStore

    scope, _, candidate, adapter, request, policy, context = _coordinates(uuid4().hex)
    reader = _Reader("Synthetic durable source body.")
    first = await MemoryAssertionReconciliationService(
        store=SurrealImmutableRecordStore(db_pool),
        authorization=_Authority(),
        source_reader=reader,
        adapters=(adapter,),
        clock=lambda: NOW,
    ).extract_and_reconcile(context=context, request=request, policy=policy)
    assert first.replayed is False
    assert reader.calls == 1

    reopened_reader = _Reader("Must not be reread on exact replay.")
    reopened_store = SurrealImmutableRecordStore(db_pool)
    replay = await MemoryAssertionReconciliationService(
        store=reopened_store,
        authorization=_Authority(),
        source_reader=reopened_reader,
        adapters=(adapter,),
        clock=lambda: NOW + timedelta(seconds=1),
    ).extract_and_reconcile(context=context, request=request, policy=policy)
    assert replay.replayed is True
    assert reopened_reader.calls == 0
    assert replay.transaction_receipt == first.transaction_receipt

    graph_service = MemoryGraphProjectionService(
        store=SurrealImmutableRecordStore(db_pool),
        authorization=_Authority(),
        clock=lambda: NOW + timedelta(seconds=2),
    )
    projection = await graph_service.rebuild(context=context, scope=scope)
    assert (
        await reopened_store.count_as_of(
            product_id=scope.product_id,
            record_space=_record_space(scope),
            record_kind=GRAPH_PROJECTION_RECORD_KIND,
            available_at=NOW + timedelta(seconds=3),
        )
        == 1
    )
    view = await MemoryGraphProjectionService(
        store=SurrealImmutableRecordStore(db_pool),
        authorization=_Authority(),
        clock=lambda: NOW + timedelta(seconds=3),
    ).query(context=context, scope=scope)
    assert view.projection == projection
    assert candidate.statement not in projection.model_dump_json()

    script = Path(__file__).with_name("surreal_restart_process.py")
    process = subprocess.run(
        [sys.executable, "-B", str(script)],
        cwd=Path(__file__).resolve().parents[3],
        env={**os.environ, "PYTHONDONTWRITEBYTECODE": "1"},
        input=json.dumps(
            {
                "request": request.model_dump(mode="json"),
                "context": context.model_dump(mode="json"),
                "policy": policy.model_dump(mode="json"),
                "candidate": {
                    "source_index": candidate.source_index,
                    "family": candidate.family.value,
                    "predicate_ref": candidate.predicate_ref,
                    "statement": candidate.statement,
                    "entity_ref": candidate.entity_ref,
                    "unresolved_entity_ref": candidate.unresolved_entity_ref,
                    "target_ref": candidate.target_ref,
                    "correction_target_ref": candidate.correction_target_ref,
                    "proposed_confidence": candidate.proposed_confidence,
                },
                "now": (NOW + timedelta(seconds=4)).isoformat(),
            }
        ),
        capture_output=True,
        text=True,
        timeout=60,
        check=False,
    )
    assert process.returncode == 0, process.stderr or process.stdout
    fresh = json.loads(process.stdout.strip().splitlines()[-1])
    assert fresh["replayed"] is True
    assert fresh["transaction"] == first.transaction_receipt.model_dump(mode="json")
    assert fresh["projection"] == projection.model_dump(mode="json")
    assert candidate.statement not in json.dumps(fresh["graph_receipt"])

    interrupted_scope, _, _, interrupted_adapter, interrupted_request, interrupted_policy, interrupted_context = (
        _coordinates(uuid4().hex)
    )
    interrupted = SurrealImmutableRecordStore(db_pool, simulate_failure_after_records=2)
    with pytest.raises(ImmutableRecordPersistenceError):
        await MemoryAssertionReconciliationService(
            store=interrupted,
            authorization=_Authority(),
            source_reader=_Reader("Synthetic interrupted source."),
            adapters=(interrupted_adapter,),
            clock=lambda: NOW,
        ).extract_and_reconcile(
            context=interrupted_context,
            request=interrupted_request,
            policy=interrupted_policy,
        )
    for kind in (
        EXTRACTION_RECEIPT_RECORD_KIND,
        ASSERTION_DECISION_RECORD_KIND,
        RECONCILIATION_RECEIPT_RECORD_KIND,
        GRAPH_PROJECTION_RECORD_KIND,
    ):
        assert (
            await interrupted.count_as_of(
                product_id=interrupted_scope.product_id,
                record_space=_record_space(interrupted_scope),
                record_kind=kind,
                available_at=NOW + timedelta(minutes=1),
            )
            == 0
        )
