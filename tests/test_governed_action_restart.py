from __future__ import annotations

import json
import os
import subprocess
import sys
from datetime import UTC, datetime, timedelta
from pathlib import Path
from uuid import uuid4

import pytest

from ace.core import (
    ActionDisposition,
    ActionEffectState,
    ActionIntentV1Alpha1,
    ActionResultV1Alpha1,
    ActionReversibility,
    AppendOnlyTransactionRequestV1,
    AuthenticatedRuntimeContextV1Alpha1,
    CapabilityArtifactIdentityV1Alpha1,
    DecisionActionDisposition,
    DecisionDisposition,
    DecisionIntentV1Alpha1,
    DecisionV1Alpha1,
    GovernedActionAuthorizationProjection,
    GovernedOperationBindingV1Alpha1,
    GovernedStateCommitRequestV1,
    GovernedStateHeadPreconditionV1Alpha1,
    GovernedStateRevisionV1,
    ImmutableRecordPersistenceError,
    ImmutableRecordV1,
    PreparedActionV1Alpha1,
    ReceiptReferenceV1Alpha1,
    ResolvedApprovalReceiptV1,
    canonical_hash,
)
from core.engine.core.action_execution import (
    BoundedActionAdapterRegistry,
    build_governed_action_execution_service,
    build_surreal_governed_action_execution_service,
)

pytestmark = pytest.mark.integration


class _Authorizer:
    def __init__(self, projection: GovernedActionAuthorizationProjection) -> None:
        self.projection = projection

    async def authorize_action(self, request):
        return self.projection


class _Adapter:
    def __init__(
        self,
        *,
        artifact: CapabilityArtifactIdentityV1Alpha1,
        prepared_at: datetime,
        completed_at: datetime,
    ) -> None:
        self.artifact_identity = artifact
        self.prepared_at = prepared_at
        self.completed_at = completed_at
        self.prepare_calls = 0
        self.execute_calls = 0

    async def prepare(self, intent):
        self.prepare_calls += 1
        return PreparedActionV1Alpha1(
            product_id=intent.product_id,
            intent_id=intent.intent_id,
            intent_digest=intent.intent_digest,
            artifact=self.artifact_identity,
            action_type=intent.action_type,
            target_ref="workspace:file:restart-proof.md",
            target_digest="sha256:" + canonical_hash("before"),
            required_permissions=("workspace.write",),
            declared_side_effects=("modify_file",),
            reversibility=ActionReversibility.REVERSIBLE,
            prepared_at=self.prepared_at,
        )

    async def execute(self, plan, authorization):
        self.execute_calls += 1
        return ActionResultV1Alpha1(
            disposition=ActionDisposition.SUCCEEDED,
            effect_state=ActionEffectState.CONFIRMED,
            result_json='{"files_changed":1}',
            completed_at=self.completed_at,
        )


class _UnusedAuthorizer:
    async def authorize_action(self, request):
        raise AssertionError(f"durable replay unexpectedly reauthorized: {request}")


class _UnusedAdapter(_Adapter):
    async def prepare(self, intent):
        self.prepare_calls += 1
        raise AssertionError(f"durable replay unexpectedly prepared: {intent}")

    async def execute(self, plan, authorization):
        self.execute_calls += 1
        raise AssertionError(f"durable replay unexpectedly executed: {(plan, authorization)}")


async def _commit_head(db_pool, *, product_id: str, state_kind: str, state_id: str, now: datetime):
    from core.engine.core.governed_state import SurrealGovernedStateStore

    revision = GovernedStateRevisionV1(
        state_kind=state_kind,
        product_id=product_id,
        state_id=state_id,
        sequence=1,
        revision_id=f"{state_kind}_revision:{uuid4().hex}",
        material_hash=canonical_hash({"state_kind": state_kind, "state_id": state_id}),
        approval_subject_ref=f"approval_subject:{state_kind}",
        payload_contract=f"fixture.{state_kind}/v1",
        payload={"status": "active"},
    )
    request = GovernedStateCommitRequestV1(
        revision=revision,
        actor_ref="principal:operator",
        approval=ResolvedApprovalReceiptV1(
            receipt_ref=f"approval:{state_kind}:{uuid4().hex}",
            product_id=product_id,
            subject_ref=revision.approval_subject_ref,
            actor_ref="principal:operator",
            receipt_hash=canonical_hash({"approval": state_kind, "product_id": product_id}),
            approved_at=now - timedelta(minutes=2),
        ),
        committed_at=now - timedelta(minutes=1),
    )
    store = SurrealGovernedStateStore(db_pool)
    await store.commit(request)
    head = await store.load_head(state_kind=state_kind, product_id=product_id, state_id=state_id)
    assert head is not None
    return head


@pytest.mark.asyncio
async def test_real_database_fresh_process_orphans_admission_without_reexecuting(db_pool) -> None:
    from core.engine.core.immutable_records import SurrealImmutableRecordStore

    suffix = uuid4().hex
    product_id = f"product:action-restart-{suffix}"
    now = datetime.now(UTC).replace(microsecond=0)
    configuration_id = f"governed_operation_configuration:action-{suffix}"
    heads = (
        await _commit_head(
            db_pool,
            product_id=product_id,
            state_kind="governed_operation_configuration",
            state_id=configuration_id,
            now=now,
        ),
        await _commit_head(
            db_pool,
            product_id=product_id,
            state_kind="capability_state",
            state_id=f"capability_state:action-{suffix}",
            now=now,
        ),
        await _commit_head(
            db_pool,
            product_id=product_id,
            state_kind="authority_grant",
            state_id=f"authority_grant:action-{suffix}",
            now=now,
        ),
    )
    preconditions = tuple(GovernedStateHeadPreconditionV1Alpha1.from_head(head) for head in heads)
    artifact = CapabilityArtifactIdentityV1Alpha1(
        capability="bounded_action_execution",
        contract="ace.core.action-adapter/v1alpha1",
        implementation_id="restart_fixture_adapter",
        implementation_version="1.0.0",
        artifact_digest="sha256:" + canonical_hash({"adapter": suffix}),
    )
    binding = GovernedOperationBindingV1Alpha1(
        product_id=product_id,
        artifact=artifact,
        configuration_ref=configuration_id,
        authority="execute_action",
        grant_ref=heads[2].state_id,
        state_head_precondition=GovernedStateHeadPreconditionV1Alpha1.from_head(heads[0]),
    )
    assert binding.state_head_precondition.state_kind == "governed_operation_configuration"
    context = AuthenticatedRuntimeContextV1Alpha1(
        product_id=product_id,
        actor_ref="principal:operator",
        authentication_receipt_ref=f"authentication:{suffix}",
        authentication_receipt_digest="sha256:" + canonical_hash({"authentication": suffix}),
        authenticated_at=now - timedelta(minutes=5),
        expires_at=now + timedelta(minutes=30),
    )
    authorization = GovernedActionAuthorizationProjection(
        authorization_ref=ReceiptReferenceV1Alpha1(
            receipt_id=f"authorization:{suffix}",
            receipt_digest="sha256:" + canonical_hash({"authorization": suffix}),
        ),
        authorized_at=now + timedelta(seconds=2),
        state_preconditions=preconditions,
    )
    subject = ImmutableRecordV1(
        product_id=product_id,
        record_space="prepared",
        record_kind="brief",
        record_key=f"brief:{suffix}",
        payload_contract="fixture.brief/v1",
        payload={"title": "Restart proof"},
        as_of=now - timedelta(minutes=2),
        available_at=now - timedelta(minutes=2),
        processing_order=0,
    )
    decision = DecisionV1Alpha1(
        intent=DecisionIntentV1Alpha1(
            product_id=product_id,
            authenticated_context=context,
            subject=subject.reference(),
            actor_role_ref="persona:operator",
            decision_type="direction",
            disposition=DecisionDisposition.ACCEPT,
            action_disposition=DecisionActionDisposition.AUTHORIZE_ACTION,
            action_type="write_report",
            rationale="Approve the bounded restart proof.",
            decided_at=now - timedelta(minutes=1),
        ),
        authorization=authorization,
    )
    decision_record = ImmutableRecordV1(
        product_id=product_id,
        record_space="prepared",
        record_kind="decision",
        record_key=str(decision.decision_id),
        payload_contract=decision.contract,
        payload=decision.model_dump(mode="python"),
        as_of=decision.intent.decided_at,
        available_at=now,
        processing_order=0,
    )
    durable_store = SurrealImmutableRecordStore(db_pool)
    await durable_store.append(
        AppendOnlyTransactionRequestV1(
            product_id=product_id,
            record_space="prepared",
            transaction_key=f"seed:{decision.decision_id}",
            records=(decision_record,),
            submitted_at=now,
            governed_state_preconditions=preconditions,
        )
    )
    intent = ActionIntentV1Alpha1(
        action_key=f"action:restart:{suffix}",
        product_id=product_id,
        authenticated_context=context,
        decision=decision_record.reference(),
        action_type="write_report",
        parameters_json='{"format":"markdown"}',
        requested_at=now,
    )

    class _InterruptTerminalStore(SurrealImmutableRecordStore):
        async def append(self, request):
            if request.records[0].record_kind == "action_terminal":
                raise ImmutableRecordPersistenceError("simulated process loss before terminal commit")
            return await super().append(request)

    adapter = _Adapter(
        artifact=artifact,
        prepared_at=now + timedelta(seconds=1),
        completed_at=now + timedelta(seconds=4),
    )
    interrupted = build_governed_action_execution_service(
        store=_InterruptTerminalStore(db_pool),
        authorizer=_Authorizer(authorization),
        operation_binding=binding,
        adapters=BoundedActionAdapterRegistry((adapter,)),
        clock=lambda: now + timedelta(seconds=3),
    )
    with pytest.raises(ImmutableRecordPersistenceError, match="process loss"):
        await interrupted.execute(intent)
    assert adapter.prepare_calls == 1
    assert adapter.execute_calls == 1

    script = Path(__file__).with_name("action_restart_process.py")
    process = subprocess.run(
        [sys.executable, "-B", str(script)],
        cwd=Path(__file__).resolve().parents[1],
        env={**os.environ, "PYTHONDONTWRITEBYTECODE": "1"},
        input=json.dumps(
            {
                "intent": intent.model_dump(mode="json"),
                "binding": binding.model_dump(mode="json"),
                "restarted_at": (now + timedelta(seconds=5)).isoformat(),
            }
        ),
        capture_output=True,
        text=True,
        timeout=60,
        check=False,
    )
    assert process.returncode == 0, process.stderr or process.stdout
    reopened = json.loads(process.stdout.strip().splitlines()[-1])
    assert reopened["replayed"] is True
    assert reopened["disposition"] == "degraded"
    assert reopened["effect_state"] == "unknown"
    assert reopened["failure_code"] == "runtime_restarted"
    assert reopened["prepare_calls"] == 0
    assert reopened["execute_calls"] == 0

    replay_adapter = _UnusedAdapter(
        artifact=artifact,
        prepared_at=now + timedelta(seconds=1),
        completed_at=now + timedelta(seconds=4),
    )
    replay = await build_surreal_governed_action_execution_service(
        db=db_pool,
        authorizer=_UnusedAuthorizer(),
        operation_binding=binding,
        adapters=BoundedActionAdapterRegistry((replay_adapter,)),
        clock=lambda: now + timedelta(seconds=6),
    ).execute(intent)
    assert replay.replayed is True
    assert replay.terminal.model_dump(mode="json") == reopened["terminal"]
    assert replay_adapter.prepare_calls == 0
    assert replay_adapter.execute_calls == 0
