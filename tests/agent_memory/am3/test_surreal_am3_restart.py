from __future__ import annotations

import asyncio
import json
import os
import shutil
import socket
import subprocess
import sys
from contextlib import asynccontextmanager
from datetime import UTC, datetime, timedelta
from pathlib import Path
from uuid import uuid4

import pytest
from surrealdb import AsyncSurreal

from ace.application.agent_memory_assertions import (
    DeterministicFixtureExtractionAdapter,
    MemoryAssertionReconciliationService,
    MemoryGraphProjectionService,
)
from ace.application.agent_memory_recall import (
    AgentMemoryRetrievalStateError,
    ContextPlannerService,
    InstructionResolutionOutcome,
    StaticRetrievalStateOwner,
)
from ace.core.agent_memory import LifecycleState, TemporalQueryV1Alpha1
from ace.intelligence.contracts.agent_memory_assertions import (
    ActivatedMemoryConstraintsV1Alpha1,
    AssertionFamilyV1Alpha1,
)
from ace.intelligence.contracts.agent_memory_recall import (
    AuthenticatedRecallRequestV1Alpha1,
    ContextPlannerBudgetV1Alpha1,
    ContextPlannerRequestV1Alpha1,
    InstructionPolicyResolutionReceiptV1Alpha1,
    InstructionPolicyResolutionRequestV1Alpha1,
    ReceivingCoordinatesV1Alpha1,
    RetrievalStateSnapshotV1Alpha1,
)
from core.engine.core.db import parse_record_id
from core.engine.core.immutable_records import SurrealImmutableRecordStore
from tests.agent_memory.am2.test_surreal_am2_restart import _Authority, _coordinates, _Reader
from tests.agent_memory.am3.test_authorized_recall import _policy

pytestmark = [pytest.mark.integration, pytest.mark.asyncio]

ROOT = Path(__file__).resolve().parents[3]
NOW = datetime(2026, 8, 12, 23, 0, tzinfo=UTC)


def _port() -> int:
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        return int(sock.getsockname()[1])


class _DisposableSurreal:
    def __init__(self, *, surreal: str, tmp_path: Path) -> None:
        self.surreal = surreal
        self.port = _port()
        self.url = f"ws://127.0.0.1:{self.port}"
        self.namespace = "ace_am3_restart"
        self.database = "ace_am3_restart"
        self.path = tmp_path / "surrealkv"
        self.log = (tmp_path / "surreal.log").open("wb")
        self.process: subprocess.Popen | None = None

    async def start(self) -> None:
        self.process = subprocess.Popen(
            [
                self.surreal,
                "start",
                "--no-banner",
                "--username",
                "root",
                "--password",
                "root",
                "--bind",
                f"127.0.0.1:{self.port}",
                f"surrealkv://{self.path}",
            ],
            cwd=ROOT,
            stdout=self.log,
            stderr=subprocess.STDOUT,
        )
        deadline = asyncio.get_running_loop().time() + 20
        while asyncio.get_running_loop().time() < deadline:
            if self.process.poll() is not None:
                raise RuntimeError("disposable AM3 SurrealDB exited before accepting connections")
            try:
                _, writer = await asyncio.open_connection("127.0.0.1", self.port)
                writer.close()
                await writer.wait_closed()
                return
            except OSError:
                await asyncio.sleep(0.1)
        raise RuntimeError("disposable AM3 SurrealDB did not accept connections")

    async def stop(self) -> None:
        if self.process is None or self.process.poll() is not None:
            return
        self.process.terminate()
        try:
            await asyncio.to_thread(self.process.wait, 10)
        except subprocess.TimeoutExpired:
            self.process.kill()
            await asyncio.to_thread(self.process.wait)

    async def restart(self) -> None:
        await self.stop()
        await self.start()

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


class _AM3Authority:
    async def authorize(self, *, context, scope, operation, subject_ref, evaluated_at):
        del context
        from ace.application.agent_memory_ingestion import AuthorizedAgentMemoryUse

        return AuthorizedAgentMemoryUse(
            product_id=scope.product_id,
            actor_id=scope.actor_id,
            operation=operation,
            subject_ref=subject_ref,
            authority_receipt_ref=scope.authority_receipt_ref,
            evaluated_at=evaluated_at,
            lifecycle_snapshot_ref="lifecycle_snapshot:am3-restart-current",
            lifecycle_state=LifecycleState.ACTIVE,
            expires_at=evaluated_at + timedelta(minutes=5),
        )


class _Instructions:
    async def resolve(self, *, request):
        return InstructionResolutionOutcome(
            InstructionPolicyResolutionReceiptV1Alpha1(
                request_ref=str(request.artifact_id),
                instruction_channel_ref=request.instruction_channel_ref,
                authorization_receipt_ref="authority_receipt:am3-restart-instruction",
                resolved_policy_refs=(),
                current_head_refs=("governed_head:am3-restart-instruction",),
                blocked=False,
                resolved_at=request.requested_at,
            ),
            (),
        )


def _receiver(product_id: str, task_ref: str) -> ReceivingCoordinatesV1Alpha1:
    return ReceivingCoordinatesV1Alpha1(
        product_id=product_id,
        task_ref=task_ref,
        composition_plan_ref=f"composition_plan:{task_ref.split(':')[-1]}",
        composition_plan_digest="sha256:" + "1" * 64,
        stage_ref="stage:am3-restart-reasoning",
        participant_ref="composition_participant:am3-restart",
        run_manifest_ref=f"stage_run_manifest:{task_ref.split(':')[-1]}",
        run_manifest_digest="sha256:" + "2" * 64,
    )


def _planner_request(*, scope, context, snapshot, policy, task_ref, when):
    recall = AuthenticatedRecallRequestV1Alpha1(
        authenticated_context=context,
        scope=scope,
        receiver=_receiver(scope.product_id, task_ref),
        query_text="Recall the exact eligible durable bounded state.",
        semantic_target_ref="entity:am2-surreal",
        eligible_families=(AssertionFamilyV1Alpha1.LEARNED_FACT,),
        temporal=TemporalQueryV1Alpha1(),
        requested_at=when,
    )
    instruction = InstructionPolicyResolutionRequestV1Alpha1(
        authenticated_context=context,
        scope=scope,
        receiver=recall.receiver,
        admitted_policy_refs=(),
        instruction_channel_ref="instruction_channel:am3-restart",
        requested_at=when,
    )
    return ContextPlannerRequestV1Alpha1(
        recall_request=recall,
        instruction_request=instruction,
        expected_snapshot=snapshot,
        policy=policy,
        budget=ContextPlannerBudgetV1Alpha1(
            max_candidates=16,
            max_blocks=8,
            max_tokens=1_024,
            max_bytes=8_192,
            max_latency_ms=2_000,
            max_calls=16,
        ),
        activated_constraints=ActivatedMemoryConstraintsV1Alpha1(activation_ref="activation:am3-restart-inert"),
    )


async def test_real_surreal_restart_fresh_process_rebuild_and_later_material_use(tmp_path) -> None:
    surreal = os.environ.get("ACE_AM3_SURREAL_BIN") or shutil.which("surreal")
    if not surreal:
        pytest.skip("surreal binary is unavailable")
    controller = _DisposableSurreal(surreal=surreal, tmp_path=tmp_path)
    await controller.start()
    try:
        scope, _, candidate, adapter, extraction, reconciliation, context = _coordinates(uuid4().hex)
        async with controller.connection() as db:
            await db.query("DEFINE TABLE IF NOT EXISTS product SCHEMALESS")
            await db.query((ROOT / "core/schema/v174_immutable_record_ledger.surql").read_text())
            await db.query((ROOT / "core/schema/v175_immutable_record_canonical_payload.surql").read_text())
            await db.query(
                "CREATE ONLY $product SET name = 'AM3 restart product'",
                {"product": parse_record_id(scope.product_id)},
            )
        store = SurrealImmutableRecordStore(controller)
        await MemoryAssertionReconciliationService(
            store=store,
            authorization=_Authority(),
            source_reader=_Reader("Synthetic durable AM3 source body."),
            adapters=(DeterministicFixtureExtractionAdapter((candidate,)),),
            clock=lambda: NOW,
        ).extract_and_reconcile(context=context, request=extraction, policy=reconciliation)
        projection = await MemoryGraphProjectionService(
            store=store,
            authorization=_Authority(),
            clock=lambda: NOW + timedelta(seconds=1),
        ).rebuild(context=context, scope=scope)
        policy = _policy()
        snapshot = RetrievalStateSnapshotV1Alpha1(
            policy_ref=policy.policy_ref,
            policy_digest=str(policy.artifact_digest),
            index_refs=("index:am3-restart-lexical", "index:am3-restart-vector"),
            projection_ref=str(projection.projection_id),
            projection_digest=str(projection.projection_digest),
            canonical_head_refs=("governed_head:am3-restart-assertions",),
            cache_dependency_refs=("dependency:am3-restart-head",),
            captured_at=NOW + timedelta(seconds=2),
        )
        first_request = _planner_request(
            scope=scope,
            context=context,
            snapshot=snapshot,
            policy=policy,
            task_ref="task:am3-before-restart",
            when=NOW + timedelta(seconds=2),
        )
        first = await ContextPlannerService(
            store=store,
            authorization=_AM3Authority(),
            state_owner=StaticRetrievalStateOwner(snapshot),
            instruction_resolver=_Instructions(),
            clock=lambda: NOW + timedelta(seconds=2),
        ).plan(first_request)
        assert first.manifest.selected_candidate_refs == (str(first.recall.selected_refs[0]),)
        assert candidate.statement not in first.manifest.model_dump_json()

        await controller.restart()
        later_request = _planner_request(
            scope=scope,
            context=context,
            snapshot=snapshot,
            policy=policy,
            task_ref="task:am3-after-restart",
            when=NOW + timedelta(seconds=3),
        )
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
                    "prior_recall": first_request.recall_request.model_dump(mode="json"),
                    "prior_manifest_ref": first.manifest.artifact_id,
                    "later_request": later_request.model_dump(mode="json"),
                    "snapshot": snapshot.model_dump(mode="json"),
                }
            ),
            capture_output=True,
            text=True,
            timeout=60,
            check=False,
        )
        assert process.returncode == 0, process.stderr or process.stdout
        fresh = json.loads(process.stdout.strip().splitlines()[-1])
        assert fresh["reopened_manifest_ref"] == first.manifest.artifact_id
        assert fresh["later_manifest"]["receiver"]["task_ref"] == "task:am3-after-restart"
        assert fresh["use"]["decision_material_candidate_refs"] == list(first.manifest.selected_candidate_refs)
        assert fresh["comparison"]["material_influence"] is True
        assert fresh["comparison"]["benefit"] == "unknown"
        assert candidate.statement not in json.dumps(fresh)

        rebuilt = await MemoryGraphProjectionService(
            store=SurrealImmutableRecordStore(controller),
            authorization=_Authority(),
            clock=lambda: NOW + timedelta(seconds=4),
        ).rebuild(context=context, scope=scope)
        assert rebuilt.source_snapshot_digest == projection.source_snapshot_digest
        assert rebuilt.projection_id != projection.projection_id
        rebuilt_snapshot = RetrievalStateSnapshotV1Alpha1(
            policy_ref=snapshot.policy_ref,
            policy_digest=snapshot.policy_digest,
            index_refs=snapshot.index_refs,
            projection_ref=str(rebuilt.projection_id),
            projection_digest=str(rebuilt.projection_digest),
            canonical_head_refs=snapshot.canonical_head_refs,
            cache_dependency_refs=snapshot.cache_dependency_refs,
            captured_at=NOW + timedelta(seconds=4),
        )
        with pytest.raises(AgentMemoryRetrievalStateError, match="stale"):
            await ContextPlannerService(
                store=SurrealImmutableRecordStore(controller),
                authorization=_AM3Authority(),
                state_owner=StaticRetrievalStateOwner(rebuilt_snapshot),
                instruction_resolver=_Instructions(),
                clock=lambda: NOW + timedelta(seconds=4),
            ).reopen_manifest(
                request=first_request.recall_request,
                manifest_ref=str(first.manifest.artifact_id),
                expected_snapshot=rebuilt_snapshot,
            )
    finally:
        await controller.stop()
