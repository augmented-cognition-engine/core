"""AM4 lifecycle, retention, canonical export/import, and hard-erasure services.

The services compose Core's existing authenticated scope and immutable-record
owner.  They neither infer authority from memory nor introduce another query,
identity, persistence, or receipt system.
"""

from __future__ import annotations

from collections import Counter, deque
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any, Mapping, Protocol, Sequence, runtime_checkable

from ace.application.agent_memory_ingestion import (
    AgentMemoryAuthorizationDenied,
    AgentMemoryAuthorizationResolver,
    AuthorizedAgentMemoryUse,
)
from ace.core.agent_memory import (
    AgentMemoryScopeV1Alpha1,
    LedgerCoordinateV1Alpha1,
    LifecycleEventV1Alpha1,
    LifecycleOperation,
    LifecycleState,
)
from ace.core.agent_memory_lifecycle import (
    DEPENDENCY_SNAPSHOT_RECORD_KIND,
    ERASURE_RECEIPT_RECORD_KIND,
    EXPORT_RECEIPT_RECORD_KIND,
    IMPORT_RECEIPT_RECORD_KIND,
    LIFECYCLE_EVENT_RECORD_KIND,
    LIFECYCLE_RECEIPT_RECORD_KIND,
    BodyAvailability,
    DependencyEntryV1Alpha1,
    DependencyKind,
    DependencySnapshotV1Alpha1,
    ErasureReceiptV1Alpha1,
    ExportArtifactV1Alpha1,
    ExportEntryV1Alpha1,
    ExportReceiptV1Alpha1,
    ExportRequestV1Alpha1,
    ExportScopeKind,
    ImportDisposition,
    ImportReceiptV1Alpha1,
    ImportRequestV1Alpha1,
    LifecycleImpactReceiptV1Alpha1,
    LifecycleMutationReceiptV1Alpha1,
    LifecycleRequestV1Alpha1,
    MemoryLifecycleMeaning,
    RetentionPolicyV1Alpha1,
    lifecycle_record_space,
)
from ace.core.agent_memory_ports import AgentMemoryLifecycleStore
from ace.core.contracts import canonical_hash, stable_id
from ace.core.records import (
    AppendOnlyTransactionRequestV1,
    ImmutableRecordPreconditionFailed,
    ImmutableRecordV1,
    append_only_receipt_id,
)
from ace.core.runtime_use import AuthenticatedRuntimeContextV1Alpha1


class AgentMemoryLifecycleError(RuntimeError):
    """A bounded AM4 operation failed closed."""


class AgentMemoryLifecycleDenied(AgentMemoryAuthorizationDenied):
    """Uniform lifecycle denial with no resource-existence disclosure."""


class AgentMemoryDependencyIncomplete(AgentMemoryLifecycleError):
    """Hard erasure stopped because dependency completeness was not proved."""


class AgentMemoryImportRefused(AgentMemoryLifecycleError):
    """Canonical import validation refused all mutation."""

    def __init__(self, receipt: ImportReceiptV1Alpha1) -> None:
        super().__init__("agent memory import was refused")
        self.receipt = receipt


@dataclass(frozen=True, slots=True)
class LifecyclePreview:
    snapshot: DependencySnapshotV1Alpha1
    impact: LifecycleImpactReceiptV1Alpha1


@dataclass(frozen=True, slots=True)
class LifecycleMutation:
    receipt: LifecycleMutationReceiptV1Alpha1 | ErasureReceiptV1Alpha1
    transaction_receipt_ref: str


@dataclass(frozen=True, slots=True)
class ExportResult:
    artifact: ExportArtifactV1Alpha1
    receipt: ExportReceiptV1Alpha1
    transaction_receipt_ref: str


@dataclass(frozen=True, slots=True)
class ImportResult:
    receipt: ImportReceiptV1Alpha1
    transaction_receipt_ref: str


@runtime_checkable
class ExternalMemoryBodyStore(Protocol):
    """Exact external-body seam; a prepared erasure must be rollback-capable."""

    async def enumerate_exact(
        self, *, scope: AgentMemoryScopeV1Alpha1, root_refs: tuple[str, ...]
    ) -> tuple[str, ...]: ...

    async def body_digest(self, *, scope: AgentMemoryScopeV1Alpha1, body_ref: str) -> str | None: ...

    async def prepare_erasure(
        self, *, scope: AgentMemoryScopeV1Alpha1, body_refs: tuple[str, ...], request_ref: str
    ) -> str: ...

    async def commit_erasure(self, *, preparation_ref: str) -> tuple[str, ...]: ...

    async def rollback_erasure(self, *, preparation_ref: str) -> None: ...


_AGENT_MEMORY_RECORD_KINDS = {
    "import_intent",
    "import_job",
    "event_metadata",
    "event_body_private",
    "normalization_receipt",
    "ingestion_receipt",
    "ingestion_status",
    "memory_assertion_decision",
    "memory_extraction_receipt",
    "memory_reconciliation_receipt",
    "memory_graph_projection",
    "memory_recall_receipt",
    "memory_instruction_resolution",
    "memory_context_manifest",
    "memory_context_planner_result",
    "memory_context_injection",
    "memory_context_reflection",
    "memory_decision_material",
    "memory_context_use",
    "memory_materiality_comparison",
    "memory_context_lineage",
    LIFECYCLE_EVENT_RECORD_KIND,
    LIFECYCLE_RECEIPT_RECORD_KIND,
    DEPENDENCY_SNAPSHOT_RECORD_KIND,
    ERASURE_RECEIPT_RECORD_KIND,
    EXPORT_RECEIPT_RECORD_KIND,
    IMPORT_RECEIPT_RECORD_KIND,
    "memory_embedding",
    "memory_vector_material",
    "memory_summary",
    "memory_cache",
}

_CONTENT_FREE_ADMIN_RECORD_KINDS = {
    LIFECYCLE_EVENT_RECORD_KIND,
    LIFECYCLE_RECEIPT_RECORD_KIND,
    DEPENDENCY_SNAPSHOT_RECORD_KIND,
    ERASURE_RECEIPT_RECORD_KIND,
    EXPORT_RECEIPT_RECORD_KIND,
    IMPORT_RECEIPT_RECORD_KIND,
}

_IDENTITY_KEY_SUFFIXES = ("_id", "_ref", "_refs")
_NON_DEPENDENCY_KEYS = {
    "actor_id",
    "authority_receipt_ref",
    "policy_ref",
    "policy_version",
    "product_id",
    "session_id",
    "source_id",
    "scope_id",
}


def _now() -> datetime:
    return datetime.now(UTC)


def _record(
    *,
    scope: AgentMemoryScopeV1Alpha1,
    kind: str,
    key: str,
    contract: str,
    payload: Mapping[str, Any],
    now: datetime,
    order: int,
) -> ImmutableRecordV1:
    return ImmutableRecordV1(
        product_id=scope.product_id,
        record_space=lifecycle_record_space(scope),
        record_kind=kind,
        record_key=key,
        payload_contract=contract,
        payload=dict(payload),
        as_of=now,
        available_at=now,
        processing_order=order,
    )


def _all_strings(value: Any) -> tuple[str, ...]:
    found: list[str] = []
    if isinstance(value, str):
        found.append(value)
    elif isinstance(value, Mapping):
        for item in value.values():
            found.extend(_all_strings(item))
    elif isinstance(value, (list, tuple)):
        for item in value:
            found.extend(_all_strings(item))
    return tuple(found)


def _identity_refs(value: Any, key: str | None = None) -> tuple[str, ...]:
    found: list[str] = []
    if isinstance(value, Mapping):
        for child_key, child in value.items():
            if child_key in _NON_DEPENDENCY_KEYS:
                continue
            if child_key.endswith(_IDENTITY_KEY_SUFFIXES):
                found.extend(_all_strings(child))
            found.extend(_identity_refs(child, child_key))
    elif isinstance(value, (list, tuple)):
        for child in value:
            found.extend(_identity_refs(child, key))
    return tuple(item for item in found if 0 < len(item) <= 240)


def _contains_any(record: ImmutableRecordV1, refs: set[str]) -> bool:
    if str(record.storage_id) in refs or record.record_key in refs:
        return True
    return bool(refs.intersection(_all_strings(record.payload)))


def _dependency_kind(record: ImmutableRecordV1) -> DependencyKind:
    kind = record.record_kind
    if kind == "event_body_private":
        return DependencyKind.SOURCE_BODY
    if kind == "memory_assertion_decision":
        return DependencyKind.ASSERTION
    if kind in {"memory_recall_receipt", "memory_context_planner_result"}:
        return DependencyKind.RANK_CANDIDATE
    if kind == "memory_context_manifest":
        return DependencyKind.CONTEXT_MANIFEST
    if kind in {
        "memory_context_injection",
        "memory_context_reflection",
        "memory_decision_material",
        "memory_context_use",
        "memory_context_lineage",
        "memory_materiality_comparison",
    }:
        return DependencyKind.USE_LINEAGE
    if kind == "memory_graph_projection":
        return DependencyKind.GRAPH_PROJECTION
    if kind == "memory_embedding":
        return DependencyKind.EMBEDDING
    if kind == "memory_vector_material":
        return DependencyKind.VECTOR_MATERIAL
    if kind == "memory_summary":
        return DependencyKind.SUMMARY
    if kind == "memory_cache":
        return DependencyKind.CACHE
    return DependencyKind.PRIMARY_RECORD


def _lifecycle_operation(meaning: MemoryLifecycleMeaning) -> tuple[LifecycleOperation, LifecycleState]:
    return {
        MemoryLifecycleMeaning.SUPERSESSION: (LifecycleOperation.SUPERSEDE, LifecycleState.SUPERSEDED),
        MemoryLifecycleMeaning.EXPIRY: (LifecycleOperation.EXPIRE, LifecycleState.EXPIRED),
        MemoryLifecycleMeaning.ARCHIVAL: (LifecycleOperation.ARCHIVE, LifecycleState.ARCHIVED),
        MemoryLifecycleMeaning.REDACTION: (LifecycleOperation.REDACT, LifecycleState.REDACTED),
        MemoryLifecycleMeaning.SOFT_FORGET: (LifecycleOperation.SOFT_FORGET, LifecycleState.FORGOTTEN),
        MemoryLifecycleMeaning.HARD_ERASURE: (LifecycleOperation.CONFIRM_ERASURE, LifecycleState.ERASED),
    }[meaning]


def _is_agent_memory_record(record: ImmutableRecordV1) -> bool:
    return record.record_kind in _AGENT_MEMORY_RECORD_KINDS or "agent-memory" in record.payload_contract


def _scope_record_spaces(scope: AgentMemoryScopeV1Alpha1) -> frozenset[str]:
    episodic_and_assertion = stable_id(
        "agent_memory",
        {
            "product_id": scope.product_id,
            "actor_id": scope.actor_id,
            "session_id": scope.session_id,
            "source_id": scope.source_id,
            "visibility": scope.visibility,
            "retention_class": scope.retention_class,
        },
    )
    recall = stable_id("agent_memory_recall_v1alpha1", {"scope_id": scope.scope_id})
    return frozenset((episodic_and_assertion, recall, lifecycle_record_space(scope)))


def _record_matches_export(record: ImmutableRecordV1, request: ExportRequestV1Alpha1) -> bool:
    if not _is_agent_memory_record(record):
        return False
    if request.export_scope is ExportScopeKind.PRODUCT:
        return True
    if record.record_space in _scope_record_spaces(request.scope):
        return True
    strings = set(_all_strings(record.payload))
    return request.selector_ref in strings


def _records_for_export(
    records: tuple[ImmutableRecordV1, ...], request: ExportRequestV1Alpha1
) -> tuple[ImmutableRecordV1, ...]:
    """Select an exact scope and its linked memory records without crossing product."""
    eligible = tuple(
        record
        for record in records
        if record.available_at <= request.ledger_through.committed_at and _is_agent_memory_record(record)
    )
    if request.export_scope is ExportScopeKind.PRODUCT:
        return eligible
    selected = {str(record.storage_id): record for record in eligible if _record_matches_export(record, request)}
    observed = {request.selector_ref}
    for record in selected.values():
        observed.update((str(record.storage_id), record.record_key))
        observed.update(_identity_refs(record.payload))
    changed = True
    while changed:
        changed = False
        for record in eligible:
            storage_id = str(record.storage_id)
            if storage_id in selected or not _contains_any(record, observed):
                continue
            selected[storage_id] = record
            observed.update((storage_id, record.record_key))
            observed.update(_identity_refs(record.payload))
            changed = True
    return tuple(selected.values())


def _provenance_refs(payload: Mapping[str, Any]) -> tuple[str, ...]:
    prefixes = ("source:", "source_version:", "agent_memory_span:", "agent_memory_event:")
    return tuple(sorted({item for item in _all_strings(payload) if item.startswith(prefixes)}))


def _payload_lifecycle(payload: Mapping[str, Any]) -> LifecycleState:
    values = set(_all_strings(payload))
    for state in LifecycleState:
        if state.value in values:
            return state
    return LifecycleState.ACTIVE


def _export_lifecycle_overlays(
    records: tuple[ImmutableRecordV1, ...], *, through: datetime
) -> dict[str, LifecycleState]:
    eligible = tuple(record for record in records if record.available_at <= through)
    snapshots: dict[str, DependencySnapshotV1Alpha1] = {}
    events: dict[str, LifecycleEventV1Alpha1] = {}
    receipts: list[LifecycleMutationReceiptV1Alpha1] = []
    for record in eligible:
        if record.record_kind == DEPENDENCY_SNAPSHOT_RECORD_KIND:
            snapshot = DependencySnapshotV1Alpha1.model_validate(record.payload, strict=False)
            snapshots[str(snapshot.snapshot_id)] = snapshot
        elif record.record_kind == LIFECYCLE_EVENT_RECORD_KIND:
            event = LifecycleEventV1Alpha1.model_validate(record.payload, strict=False)
            events[str(event.event_id)] = event
        elif record.record_kind == LIFECYCLE_RECEIPT_RECORD_KIND:
            receipts.append(LifecycleMutationReceiptV1Alpha1.model_validate(record.payload, strict=False))
    overlays: dict[str, tuple[datetime, str, LifecycleState]] = {}

    def apply(storage_id: str, at: datetime, tie_breaker: str, state: LifecycleState) -> None:
        prior = overlays.get(storage_id)
        candidate = (at, tie_breaker, state)
        if prior is None or candidate[:2] > prior[:2]:
            overlays[storage_id] = candidate

    for receipt in receipts:
        snapshot = snapshots.get(receipt.dependency_snapshot_ref)
        if snapshot is not None:
            for entry in snapshot.entries:
                if entry.storage_id is not None:
                    apply(entry.storage_id, receipt.applied_at, str(receipt.receipt_id), receipt.resulting_state)
    for event_id, event in events.items():
        for record in eligible:
            if record.record_kind in _CONTENT_FREE_ADMIN_RECORD_KINDS:
                continue
            if _contains_any(record, {event.target_ref}):
                apply(str(record.storage_id), event.occurred_at, event_id, event.next_state)
    return {storage_id: value[2] for storage_id, value in overlays.items()}


class AgentMemoryLifecycleService:
    """Authorization-first AM4 service over the existing Core store."""

    def __init__(
        self,
        *,
        store: AgentMemoryLifecycleStore,
        authorization: AgentMemoryAuthorizationResolver,
        external_bodies: ExternalMemoryBodyStore | None = None,
        clock=_now,
    ) -> None:
        self.store = store
        self.authorization = authorization
        self.external_bodies = external_bodies
        self.clock = clock

    async def _authorize(
        self,
        *,
        context: AuthenticatedRuntimeContextV1Alpha1,
        scope: AgentMemoryScopeV1Alpha1,
        operation: str,
        subject_ref: str,
        now: datetime,
        mutation: bool,
    ) -> AuthorizedAgentMemoryUse:
        try:
            use = await self.authorization.authorize(
                context=context,
                scope=scope,
                operation=operation,
                subject_ref=subject_ref,
                evaluated_at=now,
            )
        except Exception as exc:
            raise AgentMemoryLifecycleDenied() from exc
        if (
            use.product_id != scope.product_id
            or use.actor_id != scope.actor_id
            or use.operation != operation
            or use.subject_ref != subject_ref
            or use.authority_receipt_ref != scope.authority_receipt_ref
            or use.lifecycle_snapshot_ref == "lifecycle_snapshot:unspecified"
            or use.lifecycle_state is not LifecycleState.ACTIVE
            or use.evaluated_at != now
            or context.product_id != scope.product_id
            or context.actor_ref != scope.actor_id
            or not context.authenticated_at <= now < context.expires_at
            or (use.expires_at is not None and use.expires_at <= now)
            or (mutation and use.state_head_precondition is None)
        ):
            raise AgentMemoryLifecycleDenied()
        return use

    async def _enumerate(
        self,
        *,
        request: LifecycleRequestV1Alpha1,
        created_at: datetime,
    ) -> tuple[DependencySnapshotV1Alpha1, tuple[ImmutableRecordV1, ...]]:
        records = tuple(
            record
            for record in await self.store.scan_product_records(product_id=request.scope.product_id)
            if _is_agent_memory_record(record) and record.record_kind not in _CONTENT_FREE_ADMIN_RECORD_KINDS
        )
        roots = set(request.target_refs)
        included: dict[str, ImmutableRecordV1] = {}
        frontier = deque(request.target_refs)
        observed = set(request.target_refs)
        while frontier:
            frontier.popleft()
            for record in records:
                storage_id = str(record.storage_id)
                if storage_id in included or not _contains_any(record, observed):
                    continue
                included[storage_id] = record
                for identity in (storage_id, record.record_key, *_identity_refs(record.payload)):
                    if identity not in observed:
                        observed.add(identity)
                        frontier.append(identity)
        missing_roots = tuple(
            sorted(root for root in roots if not any(_contains_any(item, {root}) for item in records))
        )
        stale_dependencies = tuple(
            sorted(
                str(record.storage_id)
                for record in included.values()
                if record.available_at > request.exact_prior_coordinate.committed_at
            )
        )
        if stale_dependencies:
            missing_roots += tuple(f"dependency:stale:{item}" for item in stale_dependencies)
        entries = [
            DependencyEntryV1Alpha1(
                dependency_ref=str(record.storage_id),
                kind=_dependency_kind(record),
                root_refs=tuple(sorted(root for root in roots if _contains_any(record, {root}))) or request.target_refs,
                storage_id=str(record.storage_id),
                record_space=record.record_space,
                record_kind=record.record_kind,
                material_digest=str(record.material_hash),
            )
            for record in included.values()
        ]
        external_refs: tuple[str, ...] = ()
        if self.external_bodies is not None:
            external_refs = await self.external_bodies.enumerate_exact(
                scope=request.scope, root_refs=request.target_refs
            )
            for external_ref in external_refs:
                digest = await self.external_bodies.body_digest(scope=request.scope, body_ref=external_ref)
                if digest is None:
                    missing_roots += (external_ref,)
                    continue
                entries.append(
                    DependencyEntryV1Alpha1(
                        dependency_ref=external_ref,
                        kind=DependencyKind.EXTERNAL_BODY,
                        root_refs=request.target_refs,
                        material_digest=digest,
                        external_body_ref=external_ref,
                    )
                )
        elif any("external_body_ref" in record.payload for record in included.values()):
            missing_roots += ("dependency:external-body-store-unavailable",)
        if not entries:
            missing_roots += request.target_refs
        entries.sort(key=lambda item: item.dependency_ref)
        omissions = tuple(sorted(set(missing_roots)))
        snapshot = DependencySnapshotV1Alpha1(
            scope=request.scope,
            request_ref=str(request.request_id),
            ledger_through=request.exact_prior_coordinate,
            entries=tuple(entries),
            complete=not omissions,
            completeness_policy_ref=f"{request.policy_ref}/{request.policy_version}",
            omissions=omissions,
            created_at=created_at,
        )
        stored = tuple(included[key] for key in sorted(included))
        return snapshot, stored

    async def preview(
        self,
        *,
        context: AuthenticatedRuntimeContextV1Alpha1,
        request: LifecycleRequestV1Alpha1,
    ) -> LifecyclePreview:
        request = LifecycleRequestV1Alpha1.model_validate(request.model_dump(mode="python"))
        if not request.dry_run:
            raise AgentMemoryLifecycleError("preview requires dry_run=true")
        now = self.clock()
        await self._authorize(
            context=context,
            scope=request.scope,
            operation="preview_memory_lifecycle",
            subject_ref=str(request.request_id),
            now=now,
            mutation=False,
        )
        snapshot, _ = await self._enumerate(request=request, created_at=now)
        counts = Counter(entry.kind.value for entry in snapshot.entries)
        impact = LifecycleImpactReceiptV1Alpha1(
            request_ref=str(request.request_id),
            scope=request.scope,
            dependency_snapshot_ref=str(snapshot.snapshot_id),
            affected_by_kind=dict(sorted(counts.items())),
            current_recall_removed_refs=request.target_refs,
            history_preserved=request.meaning is not MemoryLifecycleMeaning.HARD_ERASURE,
            external_action_refs=tuple(
                entry.dependency_ref for entry in snapshot.entries if entry.kind is DependencyKind.EXTERNAL_BODY
            ),
        )
        return LifecyclePreview(snapshot=snapshot, impact=impact)

    async def apply(
        self,
        *,
        context: AuthenticatedRuntimeContextV1Alpha1,
        request: LifecycleRequestV1Alpha1,
        dependency_snapshot: DependencySnapshotV1Alpha1,
    ) -> LifecycleMutation:
        request = LifecycleRequestV1Alpha1.model_validate(request.model_dump(mode="python"))
        dependency_snapshot = DependencySnapshotV1Alpha1.model_validate(dependency_snapshot.model_dump(mode="python"))
        if request.dry_run:
            raise AgentMemoryLifecycleError("mutation requires dry_run=false")
        now = self.clock()
        use = await self._authorize(
            context=context,
            scope=request.scope,
            operation="apply_memory_lifecycle",
            subject_ref=str(request.request_id),
            now=now,
            mutation=True,
        )
        prior = await self._prior_lifecycle_mutation(request)
        if prior is not None:
            return prior
        if (
            dependency_snapshot.scope != request.scope
            or dependency_snapshot.request_ref != request.request_id
            or dependency_snapshot.ledger_through != request.exact_prior_coordinate
            or not dependency_snapshot.complete
        ):
            raise AgentMemoryDependencyIncomplete("dependency snapshot is incomplete or does not bind the request")
        current, stored = await self._enumerate(request=request, created_at=dependency_snapshot.created_at)
        if current != dependency_snapshot:
            raise ImmutableRecordPreconditionFailed("dependency snapshot changed before lifecycle mutation")
        if request.meaning is MemoryLifecycleMeaning.HARD_ERASURE:
            return await self._hard_erase(request=request, snapshot=current, stored=stored, use=use, now=now)
        return await self._apply_history_preserving(request=request, snapshot=current, stored=stored, use=use, now=now)

    async def _apply_history_preserving(
        self,
        *,
        request: LifecycleRequestV1Alpha1,
        snapshot: DependencySnapshotV1Alpha1,
        stored: tuple[ImmutableRecordV1, ...],
        use: AuthorizedAgentMemoryUse,
        now: datetime,
    ) -> LifecycleMutation:
        operation, state = _lifecycle_operation(request.meaning)
        events: list[LifecycleEventV1Alpha1] = []
        for index, target_ref in enumerate(request.target_refs, start=1):
            events.append(
                LifecycleEventV1Alpha1(
                    scope=request.scope,
                    target_ref=target_ref,
                    operation=operation,
                    prior_state=LifecycleState.ACTIVE,
                    next_state=state,
                    actor_ref=request.requested_by_ref,
                    authority_receipt_ref=request.authority_receipt_ref,
                    reason=f"AM4 {request.meaning.value} under {request.policy_ref}/{request.policy_version}",
                    occurred_at=now,
                    prior_coordinate=request.exact_prior_coordinate,
                    successor_ref=request.successor_ref,
                )
            )
        receipt = LifecycleMutationReceiptV1Alpha1(
            request_ref=str(request.request_id),
            scope=request.scope,
            meaning=request.meaning,
            target_refs=request.target_refs,
            lifecycle_event_refs=tuple(str(event.event_id) for event in events),
            resulting_state=state,
            dependency_snapshot_ref=str(snapshot.snapshot_id),
            authority_receipt_ref=request.authority_receipt_ref,
            applied_at=now,
        )
        records = [
            _record(
                scope=request.scope,
                kind=DEPENDENCY_SNAPSHOT_RECORD_KIND,
                key=str(snapshot.snapshot_id),
                contract=snapshot.contract,
                payload=snapshot.model_dump(mode="json"),
                now=now,
                order=0,
            )
        ]
        records.extend(
            _record(
                scope=request.scope,
                kind=LIFECYCLE_EVENT_RECORD_KIND,
                key=str(event.event_id),
                contract=event.contract,
                payload=event.model_dump(mode="json"),
                now=now,
                order=index,
            )
            for index, event in enumerate(events, start=1)
        )
        records.append(
            _record(
                scope=request.scope,
                kind=LIFECYCLE_RECEIPT_RECORD_KIND,
                key=str(receipt.receipt_id),
                contract=receipt.contract,
                payload=receipt.model_dump(mode="json"),
                now=now,
                order=len(records),
            )
        )
        append_request = AppendOnlyTransactionRequestV1(
            product_id=request.scope.product_id,
            record_space=lifecycle_record_space(request.scope),
            transaction_key=str(request.request_id),
            records=tuple(records),
            submitted_at=now,
            governed_state_preconditions=(use.state_head_precondition,),
        )
        if request.meaning is MemoryLifecycleMeaning.REDACTION:
            body_storage_ids = {
                entry.storage_id
                for entry in snapshot.entries
                if entry.kind is DependencyKind.SOURCE_BODY and entry.storage_id is not None
            }
            external_refs = tuple(
                entry.external_body_ref
                for entry in snapshot.entries
                if entry.kind is DependencyKind.EXTERNAL_BODY and entry.external_body_ref is not None
            )
            preparation_ref: str | None = None
            if external_refs:
                if self.external_bodies is None:
                    raise AgentMemoryDependencyIncomplete("redaction cannot reach an exact external body owner")
                preparation_ref = await self.external_bodies.prepare_erasure(
                    scope=request.scope,
                    body_refs=external_refs,
                    request_ref=str(request.request_id),
                )
            try:
                if preparation_ref is not None:
                    evidence = await self.external_bodies.commit_erasure(  # type: ignore[union-attr]
                        preparation_ref=preparation_ref
                    )
                    if len(evidence) != len(external_refs):
                        raise AgentMemoryLifecycleError("external redaction evidence is incomplete")
                transaction = await self.store.erase_records_atomically(
                    product_id=request.scope.product_id,
                    expected_records=tuple(
                        item.reference() for item in stored if str(item.storage_id) in body_storage_ids
                    ),
                    receipt_request=append_request,
                )
            except Exception:
                if preparation_ref is not None:
                    await self.external_bodies.rollback_erasure(  # type: ignore[union-attr]
                        preparation_ref=preparation_ref
                    )
                raise
        else:
            transaction = await self.store.append(append_request)
        return LifecycleMutation(receipt=receipt, transaction_receipt_ref=str(transaction.receipt_id))

    async def _hard_erase(
        self,
        *,
        request: LifecycleRequestV1Alpha1,
        snapshot: DependencySnapshotV1Alpha1,
        stored: tuple[ImmutableRecordV1, ...],
        use: AuthorizedAgentMemoryUse,
        now: datetime,
    ) -> LifecycleMutation:
        external_refs = tuple(
            entry.external_body_ref
            for entry in snapshot.entries
            if entry.kind is DependencyKind.EXTERNAL_BODY and entry.external_body_ref is not None
        )
        preparation_ref: str | None = None
        external_evidence: dict[str, str] = {}
        if external_refs:
            if self.external_bodies is None:
                raise AgentMemoryDependencyIncomplete("external bodies cannot be erased by the configured owner")
            preparation_ref = await self.external_bodies.prepare_erasure(
                scope=request.scope, body_refs=external_refs, request_ref=str(request.request_id)
            )
        removal_refs = tuple(entry.dependency_ref for entry in snapshot.entries)
        if preparation_ref is not None:
            try:
                evidence = await self.external_bodies.commit_erasure(  # type: ignore[union-attr]
                    preparation_ref=preparation_ref
                )
                if len(evidence) != len(external_refs) or any(not item.startswith("sha256:") for item in evidence):
                    raise AgentMemoryLifecycleError("external erasure evidence is incomplete")
            except Exception:
                await self.external_bodies.rollback_erasure(preparation_ref=preparation_ref)  # type: ignore[union-attr]
                raise
            external_evidence = dict(zip(external_refs, evidence, strict=True))
        removal_digests = tuple(
            external_evidence.get(
                entry.dependency_ref,
                f"sha256:{canonical_hash({'request': request.request_id, 'ref': entry.dependency_ref, 'prior': entry.material_digest})}",
            )
            for entry in snapshot.entries
        )
        probe_digest = f"sha256:{canonical_hash({'request': request.request_id, 'remaining': (), 'external': ()})}"
        receipt = ErasureReceiptV1Alpha1(
            request_ref=str(request.request_id),
            scope=request.scope,
            exact_prior_coordinate=request.exact_prior_coordinate,
            dependency_snapshot_ref=str(snapshot.snapshot_id),
            dependency_snapshot_digest=str(snapshot.snapshot_digest),
            removed_dependency_refs=removal_refs,
            removal_evidence_digests=removal_digests,
            authority_receipt_ref=request.authority_receipt_ref,
            completed_at=now,
            post_removal_probe_digest=probe_digest,
        )
        request_event = LifecycleEventV1Alpha1(
            scope=request.scope,
            target_ref=request.target_refs[0],
            operation=LifecycleOperation.REQUEST_ERASURE,
            prior_state=LifecycleState.ACTIVE,
            next_state=LifecycleState.ERASE_PENDING,
            actor_ref=request.requested_by_ref,
            authority_receipt_ref=request.authority_receipt_ref,
            reason=f"AM4 hard erasure request under {request.policy_ref}/{request.policy_version}",
            occurred_at=now,
            prior_coordinate=request.exact_prior_coordinate,
        )
        erase_pending_coordinate = LedgerCoordinateV1Alpha1(
            ledger_ref=request.exact_prior_coordinate.ledger_ref,
            sequence=request.exact_prior_coordinate.sequence + 1,
            event_ref=str(request_event.event_id),
            committed_at=now,
        )
        confirm_event = LifecycleEventV1Alpha1(
            scope=request.scope,
            target_ref=request.target_refs[0],
            operation=LifecycleOperation.CONFIRM_ERASURE,
            prior_state=LifecycleState.ERASE_PENDING,
            next_state=LifecycleState.ERASED,
            actor_ref=request.requested_by_ref,
            authority_receipt_ref=request.authority_receipt_ref,
            reason=f"AM4 dependency-complete hard erasure under {request.policy_ref}/{request.policy_version}",
            occurred_at=now,
            prior_coordinate=erase_pending_coordinate,
            erasure_dependency_proof_ref=str(receipt.receipt_id),
        )
        proof_records = (
            _record(
                scope=request.scope,
                kind=DEPENDENCY_SNAPSHOT_RECORD_KIND,
                key=str(snapshot.snapshot_id),
                contract=snapshot.contract,
                payload=snapshot.model_dump(mode="json"),
                now=now,
                order=0,
            ),
            _record(
                scope=request.scope,
                kind=LIFECYCLE_EVENT_RECORD_KIND,
                key=str(request_event.event_id),
                contract=request_event.contract,
                payload=request_event.model_dump(mode="json"),
                now=now,
                order=1,
            ),
            _record(
                scope=request.scope,
                kind=LIFECYCLE_EVENT_RECORD_KIND,
                key=str(confirm_event.event_id),
                contract=confirm_event.contract,
                payload=confirm_event.model_dump(mode="json"),
                now=now,
                order=2,
            ),
            _record(
                scope=request.scope,
                kind=ERASURE_RECEIPT_RECORD_KIND,
                key=str(receipt.receipt_id),
                contract=receipt.contract,
                payload=receipt.model_dump(mode="json"),
                now=now,
                order=3,
            ),
        )
        try:
            transaction = await self.store.erase_records_atomically(
                product_id=request.scope.product_id,
                expected_records=tuple(record.reference() for record in stored),
                receipt_request=AppendOnlyTransactionRequestV1(
                    product_id=request.scope.product_id,
                    record_space=lifecycle_record_space(request.scope),
                    transaction_key=str(request.request_id),
                    records=proof_records,
                    submitted_at=now,
                    governed_state_preconditions=(use.state_head_precondition,),
                ),
            )
        except Exception:
            if preparation_ref is not None:
                await self.external_bodies.rollback_erasure(preparation_ref=preparation_ref)  # type: ignore[union-attr]
            raise
        remaining = await self.store.scan_product_records(product_id=request.scope.product_id)
        content_free_kinds = {
            DEPENDENCY_SNAPSHOT_RECORD_KIND,
            ERASURE_RECEIPT_RECORD_KIND,
            LIFECYCLE_EVENT_RECORD_KIND,
            LIFECYCLE_RECEIPT_RECORD_KIND,
        }
        leaked = [
            record
            for record in remaining
            if record.record_kind not in content_free_kinds and _contains_any(record, set(request.target_refs))
        ]
        if leaked:
            raise AgentMemoryLifecycleError("post-erasure verification found a supported derivative")
        return LifecycleMutation(receipt=receipt, transaction_receipt_ref=str(transaction.receipt_id))

    async def export(
        self,
        *,
        context: AuthenticatedRuntimeContextV1Alpha1,
        request: ExportRequestV1Alpha1,
    ) -> ExportResult:
        request = ExportRequestV1Alpha1.model_validate(request.model_dump(mode="python"))
        now = self.clock()
        use = await self._authorize(
            context=context,
            scope=request.scope,
            operation="export_agent_memory",
            subject_ref=str(request.request_id),
            now=now,
            mutation=True,
        )
        product_records = await self.store.scan_product_records(product_id=request.scope.product_id)
        records = _records_for_export(product_records, request)
        lifecycle_overlays = _export_lifecycle_overlays(product_records, through=request.ledger_through.committed_at)
        entries: list[ExportEntryV1Alpha1] = []
        for item in sorted(records, key=lambda value: str(value.storage_id)):
            availability = BodyAvailability.INCLUDED if request.include_bodies else BodyAvailability.OMITTED_BY_POLICY
            entries.append(
                ExportEntryV1Alpha1(
                    storage_id=str(item.storage_id),
                    record_space=item.record_space,
                    record_kind=item.record_kind,
                    record_key=item.record_key,
                    payload_contract=item.payload_contract,
                    canonical_identity_ref=item.record_key,
                    as_of=item.as_of,
                    available_at=item.available_at,
                    processing_order=item.processing_order,
                    lifecycle_state=lifecycle_overlays.get(str(item.storage_id), _payload_lifecycle(item.payload)),
                    provenance_refs=_provenance_refs(item.payload),
                    source_body_availability=availability,
                    artifact_digest=str(item.material_hash),
                    payload=item.payload if request.include_bodies else None,
                    omission_reason=None if request.include_bodies else "policy:body-omitted",
                )
            )
        artifact = ExportArtifactV1Alpha1(
            request_ref=str(request.request_id),
            scope=request.scope,
            export_scope=request.export_scope,
            selector_ref=request.selector_ref,
            ledger_through=request.ledger_through,
            policy_ref=request.policy_ref,
            policy_version=request.policy_version,
            entries=tuple(entries),
            omissions=() if request.include_bodies else tuple(entry.storage_id for entry in entries),
            created_at=request.requested_at,
        )
        receipt = ExportReceiptV1Alpha1(
            request_ref=str(request.request_id),
            authority_receipt_ref=request.authority_receipt_ref,
            ledger_through=request.ledger_through,
            artifact_digest=str(artifact.artifact_digest),
            exported_entry_digests=tuple(entry.artifact_digest for entry in entries),
            omission_refs=artifact.omissions,
            completed_at=request.requested_at,
        )
        transaction = await self.store.append(
            AppendOnlyTransactionRequestV1(
                product_id=request.scope.product_id,
                record_space=lifecycle_record_space(request.scope),
                transaction_key=str(request.request_id),
                records=(
                    _record(
                        scope=request.scope,
                        kind=EXPORT_RECEIPT_RECORD_KIND,
                        key=str(receipt.receipt_id),
                        contract=receipt.contract,
                        payload=receipt.model_dump(mode="json"),
                        now=request.requested_at,
                        order=0,
                    ),
                ),
                submitted_at=request.requested_at,
                governed_state_preconditions=(use.state_head_precondition,),
            )
        )
        return ExportResult(artifact=artifact, receipt=receipt, transaction_receipt_ref=str(transaction.receipt_id))

    async def import_artifact(
        self,
        *,
        context: AuthenticatedRuntimeContextV1Alpha1,
        request: ImportRequestV1Alpha1,
        artifact: ExportArtifactV1Alpha1,
    ) -> ImportResult:
        request = ImportRequestV1Alpha1.model_validate(request.model_dump(mode="python"))
        artifact = ExportArtifactV1Alpha1.model_validate(artifact.model_dump(mode="python"))
        now = self.clock()
        use = await self._authorize(
            context=context,
            scope=request.scope,
            operation="import_agent_memory",
            subject_ref=str(request.request_id),
            now=now,
            mutation=True,
        )
        product_records = await self.store.scan_product_records(product_id=request.scope.product_id)
        erased_storage_refs: set[str] = set()
        for record in product_records:
            if record.record_kind != ERASURE_RECEIPT_RECORD_KIND:
                continue
            erasure = ErasureReceiptV1Alpha1.model_validate(record.payload, strict=False)
            erased_storage_refs.update(erasure.removed_dependency_refs)
        if erased_storage_refs.intersection(entry.storage_id for entry in artifact.entries):
            refusal = ImportReceiptV1Alpha1(
                request_ref=str(request.request_id),
                artifact_digest=str(artifact.artifact_digest),
                disposition=ImportDisposition.REFUSED_STALE,
                policy_ref=artifact.policy_ref,
                policy_version=artifact.policy_version,
                completed_at=now,
            )
            raise AgentMemoryImportRefused(refusal)
        prior = await self._prior_import(request)
        if prior is not None:
            return prior
        refusal = self._validate_import(request=request, artifact=artifact, now=now)
        if refusal is not None:
            raise AgentMemoryImportRefused(refusal)
        existing = {str(item.storage_id): item for item in product_records}
        records: list[ImmutableRecordV1] = []
        collisions: list[str] = []
        for entry in artifact.entries:
            rebuilt = ImmutableRecordV1(
                product_id=request.scope.product_id,
                record_space=entry.record_space,
                record_kind=entry.record_kind,
                record_key=entry.record_key,
                payload_contract=entry.payload_contract,
                payload=dict(entry.payload or {}),
                as_of=entry.as_of,
                available_at=entry.available_at,
                processing_order=entry.processing_order,
                storage_id=entry.storage_id,
                material_hash=entry.artifact_digest,
            )
            prior = existing.get(entry.storage_id)
            if prior is not None and prior != rebuilt:
                collisions.append(entry.storage_id)
            elif prior is None:
                records.append(rebuilt)
        if collisions:
            receipt = ImportReceiptV1Alpha1(
                request_ref=str(request.request_id),
                artifact_digest=str(artifact.artifact_digest),
                disposition=ImportDisposition.REFUSED_COLLISION,
                collision_refs=tuple(collisions),
                policy_ref=artifact.policy_ref,
                policy_version=artifact.policy_version,
                completed_at=now,
            )
            raise AgentMemoryImportRefused(receipt)
        disposition = ImportDisposition.IMPORTED if records else ImportDisposition.EXACT_REPLAY
        receipt = ImportReceiptV1Alpha1(
            request_ref=str(request.request_id),
            artifact_digest=str(artifact.artifact_digest),
            disposition=disposition,
            imported_storage_refs=tuple(str(record.storage_id) for record in records),
            policy_ref=artifact.policy_ref,
            policy_version=artifact.policy_version,
            completed_at=now,
        )
        receipt_record = _record(
            scope=request.scope,
            kind=IMPORT_RECEIPT_RECORD_KIND,
            key=str(receipt.receipt_id),
            contract=receipt.contract,
            payload=receipt.model_dump(mode="json"),
            now=now,
            order=len(records),
        )
        transaction_receipt_ref = await self.store.import_records_atomically(
            product_id=request.scope.product_id,
            transaction_key=request.idempotency_ref,
            records=tuple(records) + (receipt_record,),
            submitted_at=now,
            governed_state_preconditions=(use.state_head_precondition,),
        )
        return ImportResult(receipt=receipt, transaction_receipt_ref=transaction_receipt_ref)

    async def _prior_lifecycle_mutation(self, request: LifecycleRequestV1Alpha1) -> LifecycleMutation | None:
        records = await self.store.scan_product_records(product_id=request.scope.product_id)
        for record in records:
            if record.record_space != lifecycle_record_space(request.scope):
                continue
            if record.record_kind == LIFECYCLE_RECEIPT_RECORD_KIND:
                receipt = LifecycleMutationReceiptV1Alpha1.model_validate(record.payload, strict=False)
                if receipt.request_ref == request.request_id:
                    return LifecycleMutation(
                        receipt=receipt,
                        transaction_receipt_ref=append_only_receipt_id(
                            product_id=request.scope.product_id,
                            record_space=lifecycle_record_space(request.scope),
                            transaction_key=str(request.request_id),
                        ),
                    )
            if record.record_kind == ERASURE_RECEIPT_RECORD_KIND:
                receipt = ErasureReceiptV1Alpha1.model_validate(record.payload, strict=False)
                if receipt.request_ref == request.request_id:
                    return LifecycleMutation(
                        receipt=receipt,
                        transaction_receipt_ref=append_only_receipt_id(
                            product_id=request.scope.product_id,
                            record_space=lifecycle_record_space(request.scope),
                            transaction_key=str(request.request_id),
                        ),
                    )
        return None

    async def _prior_import(self, request: ImportRequestV1Alpha1) -> ImportResult | None:
        records = await self.store.scan_product_records(product_id=request.scope.product_id)
        by_storage_id = {str(item.storage_id): item for item in records}
        for record in records:
            if (
                record.record_space != lifecycle_record_space(request.scope)
                or record.record_kind != IMPORT_RECEIPT_RECORD_KIND
            ):
                continue
            receipt = ImportReceiptV1Alpha1.model_validate(record.payload, strict=False)
            if receipt.request_ref == request.request_id and receipt.artifact_digest == request.artifact_digest:
                transaction_records = [by_storage_id[item] for item in receipt.imported_storage_refs]
                transaction_records.append(record)
                request_hash = f"sha256:{canonical_hash(tuple((item.storage_id, item.material_hash) for item in transaction_records))}"
                return ImportResult(
                    receipt=receipt,
                    transaction_receipt_ref=stable_id(
                        "agent_memory_admin_import_receipt",
                        {
                            "transaction_id": stable_id(
                                "agent_memory_admin_import",
                                {
                                    "product_id": request.scope.product_id,
                                    "transaction_key": request.idempotency_ref,
                                },
                            ),
                            "request_hash": request_hash,
                        },
                    ),
                )
        return None

    @staticmethod
    def _validate_import(
        *, request: ImportRequestV1Alpha1, artifact: ExportArtifactV1Alpha1, now: datetime
    ) -> ImportReceiptV1Alpha1 | None:
        base = {
            "request_ref": str(request.request_id),
            "artifact_digest": str(artifact.artifact_digest),
            "policy_ref": artifact.policy_ref,
            "policy_version": artifact.policy_version,
            "completed_at": now,
        }
        if artifact.artifact_digest != request.artifact_digest:
            return ImportReceiptV1Alpha1(
                disposition=ImportDisposition.REFUSED_COLLISION, collision_refs=("artifact:digest",), **base
            )
        if artifact.scope != request.scope:
            return ImportReceiptV1Alpha1(disposition=ImportDisposition.REFUSED_SCOPE, **base)
        if (
            artifact.policy_ref not in request.accepted_policy_refs
            or artifact.policy_version != request.required_policy_version
        ):
            return ImportReceiptV1Alpha1(disposition=ImportDisposition.REFUSED_POLICY, **base)
        missing = tuple(
            entry.storage_id
            for entry in artifact.entries
            if entry.source_body_availability is not BodyAvailability.INCLUDED
        )
        if missing:
            return ImportReceiptV1Alpha1(
                disposition=ImportDisposition.REFUSED_MISSING_BODY, missing_body_refs=missing, **base
            )
        if artifact.ledger_through.committed_at > now:
            return ImportReceiptV1Alpha1(disposition=ImportDisposition.REFUSED_STALE, **base)
        return None


def retention_request(
    *,
    scope: AgentMemoryScopeV1Alpha1,
    policy: RetentionPolicyV1Alpha1,
    targets: Sequence[str],
    prior_coordinate: LedgerCoordinateV1Alpha1,
    requested_by_ref: str,
    requested_at: datetime,
    dry_run: bool,
) -> LifecycleRequestV1Alpha1:
    """Bind category/scope/source/policy retention to one exact lifecycle request."""

    if not set(targets).intersection(policy.selector_refs):
        raise AgentMemoryLifecycleError("retention targets do not satisfy the frozen selector")
    return LifecycleRequestV1Alpha1(
        scope=scope,
        target_refs=tuple(targets),
        meaning=policy.lifecycle_meaning,
        authority_receipt_ref=scope.authority_receipt_ref,
        requested_by_ref=requested_by_ref,
        requested_at=requested_at,
        exact_prior_coordinate=prior_coordinate,
        policy_ref=policy.policy_ref,
        policy_version=policy.policy_version,
        dry_run=dry_run,
    )


__all__ = [
    "AgentMemoryDependencyIncomplete",
    "AgentMemoryImportRefused",
    "AgentMemoryLifecycleDenied",
    "AgentMemoryLifecycleError",
    "AgentMemoryLifecycleService",
    "ExportResult",
    "ExternalMemoryBodyStore",
    "ImportResult",
    "LifecycleMutation",
    "LifecyclePreview",
    "retention_request",
]
