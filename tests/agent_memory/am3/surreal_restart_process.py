from __future__ import annotations

import asyncio
import json
import sys
from contextlib import asynccontextmanager
from datetime import timedelta

from surrealdb import AsyncSurreal

from ace.application.agent_memory_ingestion import AuthorizedAgentMemoryUse
from ace.application.agent_memory_recall import (
    ContextPlannerService,
    InstructionResolutionOutcome,
    StaticRetrievalStateOwner,
    compare_matched_conditions,
)
from ace.core.agent_memory import LifecycleState
from ace.core.contracts import canonical_json
from ace.intelligence.contracts.agent_memory_recall import (
    AuthenticatedRecallRequestV1Alpha1,
    ConditionKind,
    ContextPlannerRequestV1Alpha1,
    InstructionPolicyResolutionReceiptV1Alpha1,
    MatchedConditionAssignmentV1Alpha1,
    RetrievalStateSnapshotV1Alpha1,
)
from core.engine.core.immutable_records import SurrealImmutableRecordStore


class _Pool:
    def __init__(self, url: str, namespace: str, database: str) -> None:
        self.url = url
        self.namespace = namespace
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
            lifecycle_snapshot_ref="lifecycle_snapshot:am3-fresh-process",
            lifecycle_state=LifecycleState.ACTIVE,
            expires_at=evaluated_at + timedelta(minutes=5),
        )


class _Instructions:
    async def resolve(self, *, request):
        return InstructionResolutionOutcome(
            InstructionPolicyResolutionReceiptV1Alpha1(
                request_ref=str(request.artifact_id),
                instruction_channel_ref=request.instruction_channel_ref,
                authorization_receipt_ref="authority_receipt:am3-fresh-instruction",
                resolved_policy_refs=(),
                current_head_refs=("governed_head:am3-instruction-current",),
                blocked=False,
                resolved_at=request.requested_at,
            ),
            (),
        )


async def main() -> None:
    raw = json.loads(sys.stdin.read())
    prior_recall = AuthenticatedRecallRequestV1Alpha1.model_validate(raw["prior_recall"], strict=False)
    later = ContextPlannerRequestV1Alpha1.model_validate(raw["later_request"], strict=False)
    snapshot = RetrievalStateSnapshotV1Alpha1.model_validate(raw["snapshot"], strict=False)
    now = later.recall_request.requested_at
    store = SurrealImmutableRecordStore(_Pool(raw["url"], raw["namespace"], raw["database"]))
    service = ContextPlannerService(
        store=store,
        authorization=_Authority(),
        state_owner=StaticRetrievalStateOwner(snapshot),
        instruction_resolver=_Instructions(),
        clock=lambda: now,
    )
    reopened = await service.reopen_manifest(
        request=prior_recall,
        manifest_ref=raw["prior_manifest_ref"],
        expected_snapshot=snapshot,
    )
    planned = await service.plan(later)
    selected = planned.manifest.selected_candidate_refs
    held = {
        "comparison_group_ref": "comparison_group:am3-restart",
        "task_digest": "sha256:" + "1" * 64,
        "prompt_contract_digest": "sha256:" + "2" * 64,
        "provider_ref": "provider:deterministic-provider-free",
        "model_ref": "model:none",
        "configuration_digest": "sha256:" + "3" * 64,
        "decision_schema_ref": "decision_schema:i1-v1",
        "toolset_digest": "sha256:" + "4" * 64,
        "assigned_at": now,
    }
    memory = MatchedConditionAssignmentV1Alpha1(
        **held,
        condition=ConditionKind.MEMORY,
        invocation_ref="invocation:am3-restart-memory",
        manifest_ref=str(planned.manifest.artifact_id),
    )
    control = MatchedConditionAssignmentV1Alpha1(
        **held,
        condition=ConditionKind.NO_MEMORY,
        invocation_ref="invocation:am3-restart-no-memory",
    )
    comparison = compare_matched_conditions(
        memory=memory,
        no_memory=control,
        target_candidate_refs=selected,
        memory_output={"selected_option": "eligible_memory_applied", "scope": "held"},
        no_memory_output={"selected_option": "no_memory_default", "scope": "held"},
        compared_at=now,
    )
    use = await service.record_use(
        request=later.recall_request,
        manifest=planned.manifest,
        injected_candidate_refs=selected,
        reflected_candidate_refs=selected,
        decision_material_candidate_refs=selected,
        comparison=comparison,
        intelligence_use_receipt_ref="intelligence_use_receipt:am3-restart-matched",
        evidence_refs=("bounded_attribution:am3-restart",),
    )
    print(
        canonical_json(
            {
                "reopened_manifest_ref": reopened.artifact_id,
                "later_manifest": planned.manifest.model_dump(mode="json"),
                "later_recall": planned.recall.model_dump(mode="json"),
                "use": use.use.model_dump(mode="json"),
                "comparison": comparison.model_dump(mode="json"),
            }
        )
    )


if __name__ == "__main__":
    asyncio.run(main())
