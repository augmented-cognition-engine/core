from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
from contextlib import asynccontextmanager
from datetime import timedelta
from pathlib import Path
from uuid import uuid4

import pytest
from surrealdb import AsyncSurreal

from ace.application.agent_memory_assertions import (
    DeterministicFixtureExtractionAdapter,
    MemoryAssertionReconciliationService,
    MemoryGraphProjectionService,
)
from ace.application.agent_memory_ingestion import AuthorizedAgentMemoryUse
from ace.application.agent_memory_lifecycle import (
    AgentMemoryImportRefused,
    AgentMemoryLifecycleService,
)
from ace.core.agent_memory import (
    AgentMemoryScopeV1Alpha1,
    LedgerCoordinateV1Alpha1,
    LifecycleState,
    MemoryVisibility,
    RetentionClass,
)
from ace.core.agent_memory_lifecycle import (
    ExportArtifactV1Alpha1,
    ExportEntryV1Alpha1,
    ExportRequestV1Alpha1,
    ExportScopeKind,
    ImportDisposition,
    ImportRequestV1Alpha1,
    LifecycleRequestV1Alpha1,
    MemoryLifecycleMeaning,
)
from ace.core.contracts import stable_id
from ace.core.records import (
    AppendOnlyTransactionRequestV1,
    ImmutableRecordPersistenceError,
    ImmutableRecordV1,
)
from ace.core.state import GovernedStateHeadPreconditionV1Alpha1, GovernedStateHeadV1
from core.engine.core.db import parse_record_id
from core.engine.core.immutable_records import SurrealImmutableRecordStore
from tests.agent_memory.am2.test_surreal_am2_restart import NOW, _Authority, _coordinates, _Reader
from tests.agent_memory.am3.test_surreal_am3_restart import ROOT, _DisposableSurreal

pytestmark = [pytest.mark.integration, pytest.mark.asyncio]


class _LifecycleAuthority:
    def __init__(self, head: GovernedStateHeadV1) -> None:
        self.head = head

    async def authorize(self, *, context, scope, operation, subject_ref, evaluated_at):
        del context
        return AuthorizedAgentMemoryUse(
            product_id=scope.product_id,
            actor_id=scope.actor_id,
            operation=operation,
            subject_ref=subject_ref,
            authority_receipt_ref=scope.authority_receipt_ref,
            evaluated_at=evaluated_at,
            lifecycle_snapshot_ref="lifecycle_snapshot:am4-surreal-current",
            lifecycle_state=LifecycleState.ACTIVE,
            expires_at=evaluated_at + timedelta(minutes=5),
            state_head_precondition=GovernedStateHeadPreconditionV1Alpha1.from_head(self.head),
        )


class _DatabasePool:
    def __init__(self, controller: _DisposableSurreal, database: str) -> None:
        self.url = controller.url
        self.namespace = controller.namespace
        self.database = database

    @asynccontextmanager
    async def connection(self):
        db = AsyncSurreal(self.url)
        await db.connect()
        await db.signin({"username": "root", "password": "root"})
        await db.use(self.namespace, self.database)
        try:
            yield db
        finally:
            await db.close()


async def _initialize_import_target(
    pool: _DatabasePool,
    *,
    scope: AgentMemoryScopeV1Alpha1,
    head: GovernedStateHeadV1,
) -> None:
    async with pool.connection() as db:
        await db.query("DEFINE TABLE IF NOT EXISTS product SCHEMALESS")
        await db.query((ROOT / "core/schema/v174_immutable_record_ledger.surql").read_text())
        await db.query((ROOT / "core/schema/v175_immutable_record_canonical_payload.surql").read_text())
        await db.query(
            "CREATE ONLY $product SET name = 'AM4 import target'",
            {"product": parse_record_id(scope.product_id)},
        )
        await db.query(
            "CREATE ONLY $head CONTENT $content",
            {
                "head": parse_record_id(str(head.head_id)),
                "content": {
                    "product": parse_record_id(scope.product_id),
                    "state_kind": head.state_kind,
                    "state_id": head.state_id,
                    "sequence": head.sequence,
                    "revision_id": head.revision_id,
                    "commit_receipt_id": head.commit_receipt_id,
                    "updated_at": head.updated_at,
                },
            },
        )


async def test_real_surreal_erasure_restart_fresh_process_rebuild_non_reappearance(tmp_path) -> None:
    surreal = os.environ.get("ACE_AM4_SURREAL_BIN") or os.environ.get("ACE_AM3_SURREAL_BIN") or shutil.which("surreal")
    if not surreal:
        pytest.skip("surreal binary is unavailable")
    controller = _DisposableSurreal(surreal=surreal, tmp_path=tmp_path)
    await controller.start()
    try:
        scope, _, inert_candidate, adapter, extraction, policy, context = _coordinates(uuid4().hex)
        async with controller.connection() as db:
            await db.query("DEFINE TABLE IF NOT EXISTS product SCHEMALESS")
            await db.query((ROOT / "core/schema/v174_immutable_record_ledger.surql").read_text())
            await db.query((ROOT / "core/schema/v175_immutable_record_canonical_payload.surql").read_text())
            await db.query(
                "CREATE ONLY $product SET name = 'AM4 restart product'",
                {"product": parse_record_id(scope.product_id)},
            )
        store = SurrealImmutableRecordStore(controller)
        admission = await MemoryAssertionReconciliationService(
            store=store,
            authorization=_Authority(),
            source_reader=_Reader("Synthetic private AM4 body."),
            adapters=(DeterministicFixtureExtractionAdapter((inert_candidate,)),),
            clock=lambda: NOW,
        ).extract_and_reconcile(context=context, request=extraction, policy=policy)
        candidate_ref = str(admission.candidates[0].candidate_id)
        await MemoryGraphProjectionService(
            store=store,
            authorization=_Authority(),
            clock=lambda: NOW + timedelta(seconds=1),
        ).rebuild(context=context, scope=scope)
        head = GovernedStateHeadV1(
            state_kind="agent_memory_lifecycle",
            product_id=scope.product_id,
            state_id=str(scope.scope_id),
            sequence=3,
            revision_id="revision:am4-surreal-head",
            commit_receipt_id="governed_state_commit:am4-surreal-head",
            updated_at=NOW + timedelta(seconds=2),
        )
        async with controller.connection() as db:
            await db.query(
                "CREATE ONLY $head CONTENT $content",
                {
                    "head": parse_record_id(str(head.head_id)),
                    "content": {
                        "product": parse_record_id(scope.product_id),
                        "state_kind": head.state_kind,
                        "state_id": head.state_id,
                        "sequence": head.sequence,
                        "revision_id": head.revision_id,
                        "commit_receipt_id": head.commit_receipt_id,
                        "updated_at": head.updated_at,
                    },
                },
            )
        service = AgentMemoryLifecycleService(
            store=store,
            authorization=_LifecycleAuthority(head),
            clock=lambda: NOW + timedelta(seconds=3),
        )
        coordinate = LedgerCoordinateV1Alpha1(
            ledger_ref="ledger:am4-surreal",
            sequence=20,
            event_ref="ledger_event:am4-surreal-20",
            committed_at=NOW + timedelta(seconds=2),
        )
        foreign_scope = AgentMemoryScopeV1Alpha1(
            product_id=scope.product_id,
            actor_id="principal:am4-surreal-foreign",
            session_id="session:am4-surreal-foreign",
            source_id="source:am4-surreal-foreign",
            visibility=MemoryVisibility.PRIVATE,
            retention_class=RetentionClass.STANDARD,
            authority_receipt_ref="authority_receipt:am4-surreal-foreign",
        )
        foreign_record = ImmutableRecordV1(
            product_id=scope.product_id,
            record_space=stable_id(
                "agent_memory",
                {
                    "product_id": foreign_scope.product_id,
                    "actor_id": foreign_scope.actor_id,
                    "session_id": foreign_scope.session_id,
                    "source_id": foreign_scope.source_id,
                    "visibility": foreign_scope.visibility,
                    "retention_class": foreign_scope.retention_class,
                },
            ),
            record_kind="event_body_private",
            record_key="body:am4-surreal-foreign",
            payload_contract="ace.evaluation.agent-memory-am4-private/v1alpha1",
            payload={
                "event_id": "agent_memory_event:am4-surreal-foreign",
                "body": "foreign principal body",
                "scope": foreign_scope.model_dump(mode="json"),
            },
            as_of=NOW,
            available_at=NOW,
            processing_order=0,
        )
        await store.append(
            AppendOnlyTransactionRequestV1(
                product_id=scope.product_id,
                record_space=foreign_record.record_space,
                transaction_key="seed:am4-surreal-foreign",
                records=(foreign_record,),
                submitted_at=NOW,
            )
        )
        export_request = ExportRequestV1Alpha1(
            scope=scope,
            export_scope=ExportScopeKind.PRINCIPAL,
            selector_ref=scope.actor_id,
            ledger_through=coordinate,
            authority_receipt_ref=scope.authority_receipt_ref,
            policy_ref="export_policy:am4-surreal",
            policy_version="1.0.0",
            include_bodies=True,
            requested_at=NOW + timedelta(seconds=3),
        )
        exported = await service.export(context=context, request=export_request)
        assert exported.artifact.entries
        assert str(foreign_record.storage_id) not in {entry.storage_id for entry in exported.artifact.entries}
        preview_request = LifecycleRequestV1Alpha1(
            scope=scope,
            target_refs=(candidate_ref,),
            meaning=MemoryLifecycleMeaning.HARD_ERASURE,
            authority_receipt_ref=scope.authority_receipt_ref,
            requested_by_ref=scope.actor_id,
            requested_at=NOW + timedelta(seconds=3),
            exact_prior_coordinate=coordinate,
            policy_ref="retention_policy:am4-surreal",
            policy_version="1.0.0",
            dry_run=True,
        )
        preview = await service.preview(context=context, request=preview_request)
        assert preview.snapshot.complete
        mutation_request = preview_request.model_copy(update={"dry_run": False, "request_id": None})
        failing_service = AgentMemoryLifecycleService(
            store=SurrealImmutableRecordStore(controller, simulate_failure_after_records=1),
            authorization=_LifecycleAuthority(head),
            clock=lambda: NOW + timedelta(seconds=3),
        )
        with pytest.raises(ImmutableRecordPersistenceError):
            await failing_service.apply(
                context=context,
                request=mutation_request,
                dependency_snapshot=preview.snapshot,
            )
        after_failure = await store.scan_product_records(product_id=scope.product_id)
        assert any(candidate_ref in json.dumps(record.payload) for record in after_failure)

        result = await service.apply(
            context=context,
            request=mutation_request,
            dependency_snapshot=preview.snapshot,
        )
        assert result.receipt.removed_dependency_refs

        refused_request = ImportRequestV1Alpha1(
            scope=scope,
            artifact_digest=str(exported.artifact.artifact_digest),
            authority_receipt_ref=scope.authority_receipt_ref,
            accepted_policy_refs=(exported.artifact.policy_ref,),
            required_policy_version=exported.artifact.policy_version,
            idempotency_ref="import:am4-surreal-erased-refusal",
            requested_at=NOW + timedelta(seconds=4),
        )
        with pytest.raises(AgentMemoryImportRefused) as erased_refusal:
            await AgentMemoryLifecycleService(
                store=store,
                authorization=_LifecycleAuthority(head),
                clock=lambda: NOW + timedelta(seconds=4),
            ).import_artifact(context=context, request=refused_request, artifact=exported.artifact)
        assert erased_refusal.value.receipt.disposition is ImportDisposition.REFUSED_STALE

        target_pool = _DatabasePool(controller, "ace_am4_import_target")
        await _initialize_import_target(target_pool, scope=scope, head=head)
        target_service = AgentMemoryLifecycleService(
            store=SurrealImmutableRecordStore(target_pool),
            authorization=_LifecycleAuthority(head),
            clock=lambda: NOW + timedelta(seconds=4),
        )
        import_request = ImportRequestV1Alpha1(
            scope=scope,
            artifact_digest=str(exported.artifact.artifact_digest),
            authority_receipt_ref=scope.authority_receipt_ref,
            accepted_policy_refs=(exported.artifact.policy_ref,),
            required_policy_version=exported.artifact.policy_version,
            idempotency_ref="import:am4-surreal-round-trip",
            requested_at=NOW + timedelta(seconds=4),
        )
        imported = await target_service.import_artifact(
            context=context, request=import_request, artifact=exported.artifact
        )
        assert imported.receipt.disposition is ImportDisposition.IMPORTED
        assert set(imported.receipt.imported_storage_refs) == {entry.storage_id for entry in exported.artifact.entries}

        await controller.restart()
        script = Path(__file__).with_name("surreal_restart_process.py")
        process = subprocess.run(
            [sys.executable, "-B", str(script)],
            cwd=ROOT,
            env={**os.environ, "PYTHONDONTWRITEBYTECODE": "1"},
            input=json.dumps(
                {
                    "url": controller.url,
                    "namespace": controller.namespace,
                    "database": controller.database,
                    "scope": scope.model_dump(mode="json"),
                    "context": context.model_dump(mode="json"),
                    "target_ref": candidate_ref,
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
        assert fresh["target_in_supported_records"] is False
        assert fresh["target_in_rebuilt_graph"] is False
        assert fresh["erasure_receipts"] == 1

        reopened_target = AgentMemoryLifecycleService(
            store=SurrealImmutableRecordStore(target_pool),
            authorization=_LifecycleAuthority(head),
            clock=lambda: NOW + timedelta(seconds=5),
        )
        replay = await reopened_target.import_artifact(
            context=context, request=import_request, artifact=exported.artifact
        )
        assert replay == imported

        first = exported.artifact.entries[0]
        divergent_payload = {**(first.payload or {}), "collision_marker": "different material"}
        divergent_record = ImmutableRecordV1(
            product_id=scope.product_id,
            record_space=first.record_space,
            record_kind=first.record_kind,
            record_key=first.record_key,
            payload_contract=first.payload_contract,
            payload=divergent_payload,
            as_of=first.as_of,
            available_at=first.available_at,
            processing_order=first.processing_order,
        )
        divergent_entry_data = first.model_dump(mode="python")
        divergent_entry_data.update(
            payload=divergent_payload,
            artifact_digest=str(divergent_record.material_hash),
        )
        divergent_entry = ExportEntryV1Alpha1.model_validate(divergent_entry_data)
        collision_entries = tuple(
            divergent_entry if entry.storage_id == first.storage_id else entry for entry in exported.artifact.entries
        )
        collision_artifact_data = exported.artifact.model_dump(mode="python", exclude={"artifact_digest"})
        collision_artifact_data["entries"] = collision_entries
        collision_artifact = ExportArtifactV1Alpha1.model_validate(collision_artifact_data)
        collision_request = ImportRequestV1Alpha1(
            scope=scope,
            artifact_digest=str(collision_artifact.artifact_digest),
            authority_receipt_ref=scope.authority_receipt_ref,
            accepted_policy_refs=(collision_artifact.policy_ref,),
            required_policy_version=collision_artifact.policy_version,
            idempotency_ref="import:am4-surreal-collision",
            requested_at=NOW + timedelta(seconds=5),
        )
        with pytest.raises(AgentMemoryImportRefused) as collision:
            await reopened_target.import_artifact(
                context=context,
                request=collision_request,
                artifact=collision_artifact,
            )
        assert collision.value.receipt.disposition is ImportDisposition.REFUSED_COLLISION
    finally:
        await controller.stop()
