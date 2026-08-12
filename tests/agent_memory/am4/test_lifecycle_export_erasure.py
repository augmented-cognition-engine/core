from __future__ import annotations

import json
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest

from ace.application.agent_memory_ingestion import AuthorizedAgentMemoryUse
from ace.application.agent_memory_lifecycle import (
    AgentMemoryDependencyIncomplete,
    AgentMemoryImportRefused,
    AgentMemoryLifecycleDenied,
    AgentMemoryLifecycleService,
)
from ace.application.agent_memory_recall import (
    AgentMemoryContextBudgetError,
    ContextPlannerService,
    StaticRetrievalStateOwner,
)
from ace.core.agent_memory import (
    AgentMemoryScopeV1Alpha1,
    LedgerCoordinateV1Alpha1,
    LifecycleState,
    MemoryVisibility,
    RetentionClass,
)
from ace.core.agent_memory_lifecycle import (
    BodyAvailability,
    DependencyKind,
    ExportRequestV1Alpha1,
    ExportScopeKind,
    ImportDisposition,
    ImportRequestV1Alpha1,
    LifecycleMutationReceiptV1Alpha1,
    LifecycleRequestV1Alpha1,
    MemoryLifecycleMeaning,
)
from ace.core.contracts import canonical_hash, canonical_json, stable_id
from ace.core.records import AppendOnlyTransactionRequestV1, ImmutableRecordV1
from ace.core.runtime_use import AuthenticatedRuntimeContextV1Alpha1
from ace.core.state import GovernedStateHeadPreconditionV1Alpha1, GovernedStateHeadV1
from ace.testing.immutable_records import InMemoryImmutableRecordStore
from tests.agent_memory.am2.test_assertion_reconciliation import NOW as RECALL_NOW
from tests.agent_memory.am3.test_authorized_recall import (
    _Authority as _RecallAuthority,
)
from tests.agent_memory.am3.test_authorized_recall import (
    _Instructions,
    _planner_request,
    _policy,
    _recall,
    _snapshot,
)
from tests.agent_memory.am3.test_authorized_recall import (
    _scope as _recall_scope,
)
from tests.agent_memory.am3.test_authorized_recall import (
    _seed as _seed_recall,
)

pytestmark = pytest.mark.unit

NOW = datetime(2026, 8, 12, 21, 0, tzinfo=UTC)
ROOT_REF = "agent_memory_event:am4-root"
SHA_A = "sha256:" + "a" * 64
FIXTURE = Path(__file__).resolve().parents[3] / "evaluations/fixtures/agent_memory_am4_lifecycle_v1.json"


def _scope(*, actor: str = "principal:am4-user", session: str | None = "session:am4") -> AgentMemoryScopeV1Alpha1:
    return AgentMemoryScopeV1Alpha1(
        product_id="product:am4",
        actor_id=actor,
        session_id=session,
        source_id="source:am4" if session is not None else None,
        visibility=MemoryVisibility.PRIVATE,
        retention_class=RetentionClass.STANDARD,
        authority_receipt_ref="authority_receipt:am4",
    )


def _context(scope: AgentMemoryScopeV1Alpha1) -> AuthenticatedRuntimeContextV1Alpha1:
    return AuthenticatedRuntimeContextV1Alpha1(
        product_id=scope.product_id,
        actor_ref=scope.actor_id,
        authentication_receipt_ref="authentication_receipt:am4",
        authentication_receipt_digest=SHA_A,
        authenticated_at=NOW - timedelta(minutes=1),
        expires_at=NOW + timedelta(minutes=10),
    )


def _head(scope: AgentMemoryScopeV1Alpha1) -> GovernedStateHeadV1:
    return GovernedStateHeadV1(
        state_kind="agent_memory_lifecycle",
        product_id=scope.product_id,
        state_id=str(scope.scope_id),
        sequence=7,
        revision_id="revision:am4-head",
        commit_receipt_id="governed_state_commit:am4-head",
        updated_at=NOW - timedelta(minutes=1),
    )


class _Authorization:
    def __init__(self, head: GovernedStateHeadV1, *, deny: bool = False) -> None:
        self.head = head
        self.deny = deny
        self.calls: list[tuple[str, str]] = []

    async def authorize(self, *, context, scope, operation, subject_ref, evaluated_at):
        del context
        self.calls.append((operation, subject_ref))
        if self.deny:
            raise RuntimeError("uniform denial")
        return AuthorizedAgentMemoryUse(
            product_id=scope.product_id,
            actor_id=scope.actor_id,
            operation=operation,
            subject_ref=subject_ref,
            authority_receipt_ref=scope.authority_receipt_ref,
            evaluated_at=evaluated_at,
            lifecycle_snapshot_ref="lifecycle_snapshot:am4-current",
            lifecycle_state=LifecycleState.ACTIVE,
            expires_at=evaluated_at + timedelta(minutes=1),
            state_head_precondition=GovernedStateHeadPreconditionV1Alpha1.from_head(self.head),
        )


class _TrackingStore(InMemoryImmutableRecordStore):
    def __init__(self) -> None:
        super().__init__()
        self.scans = 0

    async def scan_product_records(self, *, product_id: str):
        self.scans += 1
        return await super().scan_product_records(product_id=product_id)


class _ExternalBodies:
    def __init__(self) -> None:
        self.bodies = {"external_body:am4": "exact external private body"}
        self.prepared: dict[str, dict[str, str]] = {}
        self.fail_commit = False

    async def enumerate_exact(self, *, scope, root_refs):
        del scope, root_refs
        return tuple(sorted(self.bodies))

    async def body_digest(self, *, scope, body_ref):
        del scope
        body = self.bodies.get(body_ref)
        return None if body is None else f"sha256:{canonical_hash(body)}"

    async def prepare_erasure(self, *, scope, body_refs, request_ref):
        del scope
        preparation = f"external_erasure:{request_ref}"
        self.prepared[preparation] = {ref: self.bodies[ref] for ref in body_refs}
        return preparation

    async def commit_erasure(self, *, preparation_ref):
        saved = self.prepared[preparation_ref]
        for ref in saved:
            self.bodies.pop(ref)
            if self.fail_commit:
                raise RuntimeError("injected external commit failure")
        return tuple(f"sha256:{canonical_hash({'ref': ref, 'prior': body})}" for ref, body in sorted(saved.items()))

    async def rollback_erasure(self, *, preparation_ref):
        self.bodies.update(self.prepared[preparation_ref])


def _coordinate() -> LedgerCoordinateV1Alpha1:
    return LedgerCoordinateV1Alpha1(
        ledger_ref="ledger:am4",
        sequence=40,
        event_ref="ledger_event:am4-40",
        committed_at=NOW,
    )


def _record(scope: AgentMemoryScopeV1Alpha1, kind: str, key: str, payload: dict, order: int) -> ImmutableRecordV1:
    return ImmutableRecordV1(
        product_id=scope.product_id,
        record_space=stable_id(
            "agent_memory",
            {
                "product_id": scope.product_id,
                "actor_id": scope.actor_id,
                "session_id": scope.session_id,
                "source_id": scope.source_id,
                "visibility": scope.visibility,
                "retention_class": scope.retention_class,
            },
        ),
        record_kind=kind,
        record_key=key,
        payload_contract="ace.evaluation.agent-memory-am4-private/v1alpha1",
        payload={**payload, "scope": scope.model_dump(mode="json")},
        as_of=NOW - timedelta(minutes=2),
        available_at=NOW - timedelta(minutes=2),
        processing_order=order,
    )


async def _seed(
    store: InMemoryImmutableRecordStore,
    scope: AgentMemoryScopeV1Alpha1,
    *,
    root_ref: str = ROOT_REF,
) -> tuple[ImmutableRecordV1, ...]:
    records = (
        _record(
            scope,
            "event_body_private",
            f"body:{root_ref}",
            {"event_id": root_ref, "body": "erase this exact private body", "session_id": scope.session_id},
            0,
        ),
        _record(
            scope,
            "memory_assertion_decision",
            f"assertion:{root_ref}",
            {
                "source_event_ref": root_ref,
                "candidate_id": f"candidate:{root_ref}",
                "statement": "derived private text",
            },
            1,
        ),
        _record(
            scope,
            "memory_graph_projection",
            f"graph:{root_ref}",
            {"candidate_refs": [f"candidate:{root_ref}"], "edge_refs": [f"edge:{root_ref}"]},
            2,
        ),
        _record(
            scope,
            "memory_context_manifest",
            f"manifest:{root_ref}",
            {
                "selected_candidate_refs": [f"candidate:{root_ref}"],
                "manifest_id": f"manifest:{root_ref}",
            },
            3,
        ),
        _record(
            scope,
            "memory_context_use",
            f"use:{root_ref}",
            {"manifest_ref": f"manifest:{root_ref}", "use_receipt_id": f"use:{root_ref}"},
            4,
        ),
        _record(
            scope,
            "memory_embedding",
            f"embedding:{root_ref}",
            {"source_ref": root_ref, "embedding_ref": f"embedding:{root_ref}", "vector": [0.1, 0.2]},
            5,
        ),
        _record(
            scope,
            "memory_summary",
            f"summary:{root_ref}",
            {"source_refs": [root_ref], "summary": "derived private summary"},
            6,
        ),
        _record(
            scope,
            "memory_cache",
            f"cache:{root_ref}",
            {"dependency_refs": [f"candidate:{root_ref}"], "response": "derived private response"},
            7,
        ),
    )
    await store.append(
        AppendOnlyTransactionRequestV1(
            product_id=scope.product_id,
            record_space=records[0].record_space,
            transaction_key="seed:am4",
            records=records,
            submitted_at=NOW - timedelta(minutes=1),
        )
    )
    return records


def _request(scope: AgentMemoryScopeV1Alpha1, meaning: MemoryLifecycleMeaning, *, dry_run: bool):
    return LifecycleRequestV1Alpha1(
        scope=scope,
        target_refs=(ROOT_REF,),
        meaning=meaning,
        authority_receipt_ref=scope.authority_receipt_ref,
        requested_by_ref=scope.actor_id,
        requested_at=NOW,
        exact_prior_coordinate=_coordinate(),
        policy_ref="retention_policy:am4",
        policy_version="1.0.0",
        dry_run=dry_run,
        successor_ref="agent_memory_event:am4-successor" if meaning is MemoryLifecycleMeaning.SUPERSESSION else None,
    )


def _service(store: InMemoryImmutableRecordStore, scope: AgentMemoryScopeV1Alpha1, *, deny: bool = False):
    head = _head(scope)
    store.set_governed_state_head(head)
    return AgentMemoryLifecycleService(
        store=store,
        authorization=_Authorization(head, deny=deny),
        clock=lambda: NOW,
    )


def test_frozen_fixture_covers_positive_and_fail_closed_matrix() -> None:
    fixture = json.loads(FIXTURE.read_text())
    assert fixture["provider_required"] is False
    assert set(fixture["lifecycle_meanings"]) == {item.value for item in MemoryLifecycleMeaning}
    assert "dependency_incomplete" in fixture["fail_closed_cases"]
    assert "export_import_round_trip" in fixture["positive_cases"]


@pytest.mark.asyncio
async def test_preview_enumerates_primary_and_every_supported_derivative_without_bodies() -> None:
    scope = _scope()
    store = InMemoryImmutableRecordStore()
    await _seed(store, scope)
    service = _service(store, scope)

    preview = await service.preview(
        context=_context(scope), request=_request(scope, MemoryLifecycleMeaning.EXPIRY, dry_run=True)
    )

    assert preview.snapshot.complete is True
    kinds = {entry.kind for entry in preview.snapshot.entries}
    assert {
        DependencyKind.SOURCE_BODY,
        DependencyKind.ASSERTION,
        DependencyKind.GRAPH_PROJECTION,
        DependencyKind.CONTEXT_MANIFEST,
        DependencyKind.USE_LINEAGE,
        DependencyKind.EMBEDDING,
        DependencyKind.SUMMARY,
        DependencyKind.CACHE,
    } <= kinds
    serialized = canonical_json(preview.impact)
    assert "erase this exact private body" not in serialized
    assert "derived private" not in serialized


@pytest.mark.asyncio
async def test_stale_ledger_coordinate_refuses_mutation_without_partial_change() -> None:
    scope = _scope()
    store = InMemoryImmutableRecordStore()
    seeded = await _seed(store, scope)
    service = _service(store, scope)
    stale_coordinate = _coordinate().model_copy(
        update={"sequence": 39, "event_ref": "ledger_event:am4-39", "committed_at": NOW - timedelta(minutes=3)}
    )
    request = _request(scope, MemoryLifecycleMeaning.HARD_ERASURE, dry_run=True).model_copy(
        update={"exact_prior_coordinate": stale_coordinate, "request_id": None}
    )

    preview = await service.preview(context=_context(scope), request=request)

    assert preview.snapshot.complete is False
    assert all(item.startswith("dependency:stale:") for item in preview.snapshot.omissions)
    with pytest.raises(AgentMemoryDependencyIncomplete):
        await service.apply(
            context=_context(scope),
            request=request.model_copy(update={"dry_run": False}),
            dependency_snapshot=preview.snapshot,
        )
    assert all(str(record.storage_id) in store.records for record in seeded)


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "meaning,state",
    [
        (MemoryLifecycleMeaning.SUPERSESSION, LifecycleState.SUPERSEDED),
        (MemoryLifecycleMeaning.EXPIRY, LifecycleState.EXPIRED),
        (MemoryLifecycleMeaning.ARCHIVAL, LifecycleState.ARCHIVED),
        (MemoryLifecycleMeaning.REDACTION, LifecycleState.REDACTED),
        (MemoryLifecycleMeaning.SOFT_FORGET, LifecycleState.FORGOTTEN),
    ],
)
async def test_history_preserving_lifecycle_meanings_append_distinct_current_state(meaning, state) -> None:
    scope = _scope()
    store = InMemoryImmutableRecordStore()
    seeded = await _seed(store, scope)
    service = _service(store, scope)
    preview_request = _request(scope, meaning, dry_run=True)
    preview = await service.preview(context=_context(scope), request=preview_request)
    apply_request = _request(scope, meaning, dry_run=False)

    result = await service.apply(context=_context(scope), request=apply_request, dependency_snapshot=preview.snapshot)

    assert isinstance(result.receipt, LifecycleMutationReceiptV1Alpha1)
    assert result.receipt.resulting_state is state
    for record in seeded:
        if meaning is MemoryLifecycleMeaning.REDACTION and record.record_kind == "event_body_private":
            assert str(record.storage_id) not in store.records
        else:
            assert str(record.storage_id) in store.records
    replay = await service.apply(context=_context(scope), request=apply_request, dependency_snapshot=preview.snapshot)
    assert replay == result


@pytest.mark.asyncio
async def test_export_reports_current_lifecycle_overlay_for_canonical_records() -> None:
    scope = _scope()
    store = InMemoryImmutableRecordStore()
    seeded = await _seed(store, scope)
    service = _service(store, scope)
    preview = await service.preview(
        context=_context(scope),
        request=_request(scope, MemoryLifecycleMeaning.EXPIRY, dry_run=True),
    )
    await service.apply(
        context=_context(scope),
        request=_request(scope, MemoryLifecycleMeaning.EXPIRY, dry_run=False),
        dependency_snapshot=preview.snapshot,
    )
    exported = await service.export(
        context=_context(scope),
        request=ExportRequestV1Alpha1(
            scope=scope,
            export_scope=ExportScopeKind.PRODUCT,
            selector_ref=scope.product_id,
            ledger_through=_coordinate(),
            authority_receipt_ref=scope.authority_receipt_ref,
            policy_ref="export_policy:am4-lifecycle",
            policy_version="1.0.0",
            include_bodies=True,
            requested_at=NOW,
        ),
    )
    by_storage = {entry.storage_id: entry for entry in exported.artifact.entries}
    assert all(by_storage[str(record.storage_id)].lifecycle_state is LifecycleState.EXPIRED for record in seeded)


@pytest.mark.asyncio
async def test_hard_erasure_removes_complete_closure_and_cannot_reappear_after_reopen() -> None:
    scope = _scope()
    store = InMemoryImmutableRecordStore()
    seeded = await _seed(store, scope)
    service = _service(store, scope)
    export_request = ExportRequestV1Alpha1(
        scope=scope,
        export_scope=ExportScopeKind.PRODUCT,
        selector_ref=scope.product_id,
        ledger_through=_coordinate(),
        authority_receipt_ref=scope.authority_receipt_ref,
        policy_ref="export_policy:am4-before-erasure",
        policy_version="1.0.0",
        include_bodies=True,
        requested_at=NOW,
    )
    exported = await service.export(context=_context(scope), request=export_request)
    preview = await service.preview(
        context=_context(scope), request=_request(scope, MemoryLifecycleMeaning.HARD_ERASURE, dry_run=True)
    )
    request = _request(scope, MemoryLifecycleMeaning.HARD_ERASURE, dry_run=False)

    result = await service.apply(context=_context(scope), request=request, dependency_snapshot=preview.snapshot)

    assert all(str(record.storage_id) not in store.records for record in seeded)
    receipt_json = canonical_json(result.receipt)
    assert "erase this exact private body" not in receipt_json
    assert "derived private" not in receipt_json
    reopened = _service(store, scope)
    replay = await reopened.apply(context=_context(scope), request=request, dependency_snapshot=preview.snapshot)
    assert replay == result
    assert all(str(record.storage_id) not in store.records for record in seeded)
    import_request = ImportRequestV1Alpha1(
        scope=scope,
        artifact_digest=str(exported.artifact.artifact_digest),
        authority_receipt_ref=scope.authority_receipt_ref,
        accepted_policy_refs=("export_policy:am4-before-erasure",),
        required_policy_version="1.0.0",
        idempotency_ref="import:am4-erased-refusal",
        requested_at=NOW,
    )
    with pytest.raises(AgentMemoryImportRefused) as refused:
        await reopened.import_artifact(context=_context(scope), request=import_request, artifact=exported.artifact)
    assert refused.value.receipt.disposition is ImportDisposition.REFUSED_STALE
    assert all(str(record.storage_id) not in store.records for record in seeded)


@pytest.mark.asyncio
async def test_hard_erasure_removes_exact_external_body_and_uses_owner_evidence() -> None:
    scope = _scope()
    store = InMemoryImmutableRecordStore()
    external_record = _record(
        scope,
        "event_metadata",
        "external:am4-root",
        {"event_id": ROOT_REF, "external_body_ref": "external_body:am4"},
        0,
    )
    await store.append(
        AppendOnlyTransactionRequestV1(
            product_id=scope.product_id,
            record_space=external_record.record_space,
            transaction_key="seed:am4-external",
            records=(external_record,),
            submitted_at=NOW - timedelta(minutes=1),
        )
    )
    head = _head(scope)
    store.set_governed_state_head(head)
    bodies = _ExternalBodies()
    service = AgentMemoryLifecycleService(
        store=store,
        authorization=_Authorization(head),
        external_bodies=bodies,
        clock=lambda: NOW,
    )
    preview = await service.preview(
        context=_context(scope), request=_request(scope, MemoryLifecycleMeaning.HARD_ERASURE, dry_run=True)
    )
    assert any(entry.kind is DependencyKind.EXTERNAL_BODY for entry in preview.snapshot.entries)
    result = await service.apply(
        context=_context(scope),
        request=_request(scope, MemoryLifecycleMeaning.HARD_ERASURE, dry_run=False),
        dependency_snapshot=preview.snapshot,
    )
    assert bodies.bodies == {}
    assert "exact external private body" not in canonical_json(result.receipt)


@pytest.mark.asyncio
async def test_external_commit_failure_rolls_back_body_and_leaves_core_unchanged() -> None:
    scope = _scope()
    store = InMemoryImmutableRecordStore()
    external_record = _record(
        scope,
        "event_metadata",
        "external:am4-failure",
        {"event_id": ROOT_REF, "external_body_ref": "external_body:am4"},
        0,
    )
    await store.append(
        AppendOnlyTransactionRequestV1(
            product_id=scope.product_id,
            record_space=external_record.record_space,
            transaction_key="seed:am4-external-failure",
            records=(external_record,),
            submitted_at=NOW - timedelta(minutes=1),
        )
    )
    head = _head(scope)
    store.set_governed_state_head(head)
    bodies = _ExternalBodies()
    service = AgentMemoryLifecycleService(
        store=store,
        authorization=_Authorization(head),
        external_bodies=bodies,
        clock=lambda: NOW,
    )
    request = _request(scope, MemoryLifecycleMeaning.HARD_ERASURE, dry_run=False)
    preview = await service.preview(
        context=_context(scope),
        request=request.model_copy(update={"dry_run": True}),
    )
    bodies.fail_commit = True

    with pytest.raises(RuntimeError, match="injected external commit failure"):
        await service.apply(context=_context(scope), request=request, dependency_snapshot=preview.snapshot)

    assert bodies.bodies == {"external_body:am4": "exact external private body"}
    assert str(external_record.storage_id) in store.records
    assert all(record.record_kind != "memory_erasure_receipt" for record in store.records.values())


@pytest.mark.asyncio
async def test_expiry_removes_current_am3_recall_eligibility_without_rewriting_am2_history() -> None:
    store, admission, _, projection = await _seed_recall(second=False)
    scope = _recall_scope()
    head = GovernedStateHeadV1(
        state_kind="agent_memory_lifecycle",
        product_id=scope.product_id,
        state_id=str(scope.scope_id),
        sequence=7,
        revision_id="revision:am4-recall-head",
        commit_receipt_id="governed_state_commit:am4-recall-head",
        updated_at=RECALL_NOW + timedelta(minutes=1),
    )
    store.set_governed_state_head(head)
    context = AuthenticatedRuntimeContextV1Alpha1(
        product_id=scope.product_id,
        actor_ref=scope.actor_id,
        authentication_receipt_ref="authentication_receipt:am4-recall",
        authentication_receipt_digest=SHA_A,
        authenticated_at=RECALL_NOW - timedelta(minutes=1),
        expires_at=RECALL_NOW + timedelta(minutes=10),
    )
    service = AgentMemoryLifecycleService(
        store=store,
        authorization=_Authorization(head),
        clock=lambda: RECALL_NOW + timedelta(minutes=2),
    )
    candidate_ref = str(admission.candidates[0].candidate_id)
    coordinate = LedgerCoordinateV1Alpha1(
        ledger_ref="ledger:am4-recall",
        sequence=50,
        event_ref="ledger_event:am4-recall-50",
        committed_at=RECALL_NOW + timedelta(minutes=1),
    )
    preview_request = LifecycleRequestV1Alpha1(
        scope=scope,
        target_refs=(candidate_ref,),
        meaning=MemoryLifecycleMeaning.EXPIRY,
        authority_receipt_ref=scope.authority_receipt_ref,
        requested_by_ref=scope.actor_id,
        requested_at=RECALL_NOW + timedelta(minutes=2),
        exact_prior_coordinate=coordinate,
        policy_ref="retention_policy:am4-recall",
        policy_version="1.0.0",
        dry_run=True,
    )
    preview = await service.preview(context=context, request=preview_request)
    await service.apply(
        context=context,
        request=preview_request.model_copy(update={"dry_run": False, "request_id": None}),
        dependency_snapshot=preview.snapshot,
    )
    policy = _policy()
    snapshot = _snapshot(policy, projection)
    with pytest.raises(AgentMemoryContextBudgetError, match="no authorized context block"):
        await ContextPlannerService(
            store=store,
            authorization=_RecallAuthority(),
            state_owner=StaticRetrievalStateOwner(snapshot),
            instruction_resolver=_Instructions(),
            clock=lambda: RECALL_NOW + timedelta(minutes=2),
        ).plan(_planner_request(_recall(), policy, snapshot))
    assert str(admission.transaction_receipt.receipt_id) in store.receipts
    assertion_records = [item for item in store.records.values() if item.record_kind == "memory_assertion_decision"]
    assert len(assertion_records) == 1


@pytest.mark.asyncio
async def test_erasure_atomic_failure_leaves_every_dependency_intact() -> None:
    scope = _scope()
    store = InMemoryImmutableRecordStore(fail_after_records=1)
    seeded = await _seed(InMemoryImmutableRecordStore(), scope)
    store.fail_after_records = None
    await store.append(
        AppendOnlyTransactionRequestV1(
            product_id=scope.product_id,
            record_space=seeded[0].record_space,
            transaction_key="seed:am4",
            records=seeded,
            submitted_at=NOW - timedelta(minutes=1),
        )
    )
    service = _service(store, scope)
    preview = await service.preview(
        context=_context(scope), request=_request(scope, MemoryLifecycleMeaning.HARD_ERASURE, dry_run=True)
    )
    store.fail_after_records = 1

    with pytest.raises(Exception):
        await service.apply(
            context=_context(scope),
            request=_request(scope, MemoryLifecycleMeaning.HARD_ERASURE, dry_run=False),
            dependency_snapshot=preview.snapshot,
        )
    assert all(str(record.storage_id) in store.records for record in seeded)


@pytest.mark.asyncio
@pytest.mark.parametrize("export_scope", [ExportScopeKind.SESSION, ExportScopeKind.PRINCIPAL])
async def test_export_scope_excludes_same_product_foreign_principal(export_scope: ExportScopeKind) -> None:
    selected_scope = _scope(session="session:am4-selected")
    same_principal_scope = _scope(session="session:am4-sibling")
    foreign_scope = _scope(actor="principal:am4-foreign", session="session:am4-foreign")
    store = InMemoryImmutableRecordStore()
    selected = await _seed(store, selected_scope, root_ref="agent_memory_event:am4-selected")
    sibling = await _seed(store, same_principal_scope, root_ref="agent_memory_event:am4-sibling")
    foreign = await _seed(store, foreign_scope, root_ref="agent_memory_event:am4-foreign")
    request_scope = selected_scope if export_scope is ExportScopeKind.SESSION else _scope(session=None)
    selector_ref = selected_scope.session_id if export_scope is ExportScopeKind.SESSION else selected_scope.actor_id
    exported = await _service(store, request_scope).export(
        context=_context(request_scope),
        request=ExportRequestV1Alpha1(
            scope=request_scope,
            export_scope=export_scope,
            selector_ref=selector_ref,
            ledger_through=_coordinate(),
            authority_receipt_ref=request_scope.authority_receipt_ref,
            policy_ref="export_policy:am4",
            policy_version="1.0.0",
            include_bodies=True,
            requested_at=NOW,
        ),
    )
    expected = selected if export_scope is ExportScopeKind.SESSION else selected + sibling
    exported_ids = {entry.storage_id for entry in exported.artifact.entries}
    assert exported_ids == {str(record.storage_id) for record in expected}
    assert exported_ids.isdisjoint(str(record.storage_id) for record in foreign)


@pytest.mark.asyncio
async def test_export_import_round_trip_replay_collision_missing_body_and_policy_refusal() -> None:
    scope = _scope()
    source = InMemoryImmutableRecordStore()
    seeded = await _seed(source, scope)
    export_service = _service(source, scope)
    export_request = ExportRequestV1Alpha1(
        scope=scope,
        export_scope=ExportScopeKind.PRODUCT,
        selector_ref=scope.product_id,
        ledger_through=_coordinate(),
        authority_receipt_ref=scope.authority_receipt_ref,
        policy_ref="export_policy:am4",
        policy_version="1.0.0",
        include_bodies=True,
        requested_at=NOW,
    )
    exported = await export_service.export(context=_context(scope), request=export_request)
    assert len(exported.artifact.entries) == len(seeded)
    assert all(entry.source_body_availability is BodyAvailability.INCLUDED for entry in exported.artifact.entries)

    target = InMemoryImmutableRecordStore()
    import_service = _service(target, scope)
    import_request = ImportRequestV1Alpha1(
        scope=scope,
        artifact_digest=str(exported.artifact.artifact_digest),
        authority_receipt_ref=scope.authority_receipt_ref,
        accepted_policy_refs=("export_policy:am4",),
        required_policy_version="1.0.0",
        idempotency_ref="import:am4-round-trip",
        requested_at=NOW,
    )
    imported = await import_service.import_artifact(
        context=_context(scope), request=import_request, artifact=exported.artifact
    )
    assert imported.receipt.disposition is ImportDisposition.IMPORTED
    assert {str(record.storage_id) for record in seeded} <= set(target.records)
    assert (
        await import_service.import_artifact(
            context=_context(scope), request=import_request, artifact=exported.artifact
        )
        == imported
    )

    missing_export = await export_service.export(
        context=_context(scope),
        request=export_request.model_copy(update={"include_bodies": False, "request_id": None}),
    )
    missing_request = import_request.model_copy(
        update={
            "artifact_digest": missing_export.artifact.artifact_digest,
            "idempotency_ref": "import:missing",
            "request_id": None,
        }
    )
    with pytest.raises(AgentMemoryImportRefused) as missing:
        await import_service.import_artifact(
            context=_context(scope), request=missing_request, artifact=missing_export.artifact
        )
    assert missing.value.receipt.disposition is ImportDisposition.REFUSED_MISSING_BODY

    incompatible = import_request.model_copy(
        update={
            "accepted_policy_refs": ("export_policy:different",),
            "idempotency_ref": "import:policy",
            "request_id": None,
        }
    )
    with pytest.raises(AgentMemoryImportRefused) as policy:
        await import_service.import_artifact(context=_context(scope), request=incompatible, artifact=exported.artifact)
    assert policy.value.receipt.disposition is ImportDisposition.REFUSED_POLICY

    collision_store = InMemoryImmutableRecordStore()
    first = exported.artifact.entries[0]
    collision = ImmutableRecordV1(
        product_id=scope.product_id,
        record_space=first.record_space,
        record_kind=first.record_kind,
        record_key=first.record_key,
        payload_contract=first.payload_contract,
        payload={"event_id": ROOT_REF, "body": "different collision material"},
        as_of=first.as_of,
        available_at=first.available_at,
        processing_order=0,
    )
    await collision_store.append(
        AppendOnlyTransactionRequestV1(
            product_id=scope.product_id,
            record_space=collision.record_space,
            transaction_key="seed:collision",
            records=(collision,),
            submitted_at=NOW,
        )
    )
    collision_service = _service(collision_store, scope)
    collision_request = import_request.model_copy(update={"idempotency_ref": "import:collision", "request_id": None})
    with pytest.raises(AgentMemoryImportRefused) as collision_error:
        await collision_service.import_artifact(
            context=_context(scope), request=collision_request, artifact=exported.artifact
        )
    assert collision_error.value.receipt.disposition is ImportDisposition.REFUSED_COLLISION

    atomic_store = InMemoryImmutableRecordStore(fail_after_records=1)
    atomic_service = _service(atomic_store, scope)
    atomic_request = import_request.model_copy(update={"idempotency_ref": "import:atomic-failure", "request_id": None})
    with pytest.raises(Exception):
        await atomic_service.import_artifact(
            context=_context(scope), request=atomic_request, artifact=exported.artifact
        )
    assert not set(entry.storage_id for entry in exported.artifact.entries).intersection(atomic_store.records)
    assert all(record.record_kind != "memory_import_receipt" for record in atomic_store.records.values())


@pytest.mark.asyncio
async def test_cross_scope_denial_happens_before_product_scan() -> None:
    scope = _scope()
    store = _TrackingStore()
    service = _service(store, scope, deny=True)
    with pytest.raises(AgentMemoryLifecycleDenied, match="unavailable"):
        await service.preview(
            context=_context(scope), request=_request(scope, MemoryLifecycleMeaning.EXPIRY, dry_run=True)
        )
    assert store.scans == 0
