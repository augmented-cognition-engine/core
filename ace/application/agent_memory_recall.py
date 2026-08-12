"""AM3 authorized recall and provider-neutral Context Planner.

The planner reads canonical AM2 records through existing immutable-record
ports.  Every candidate, signal, body, graph, assembly, and receipt operation
is authorized independently.  Derived indexes and optional providers remain
ports; this module creates no search engine, vector store, graph truth, cache,
schema, or public task/MCP surface.
"""

from __future__ import annotations

from collections import defaultdict, deque
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any, Callable, Mapping, Protocol, Sequence

from ace.application.agent_composition import ContextResolutionOutcome
from ace.application.agent_composition_runtime import ReasoningCompositionRuntimeAuthorityPort
from ace.application.agent_memory_assertions import ASSERTION_DECISION_RECORD_KIND, GRAPH_PROJECTION_RECORD_KIND
from ace.application.agent_memory_ingestion import (
    AgentMemoryAuthorizationResolver,
    AuthorizedAgentMemoryUse,
)
from ace.core.agent_composition import ExactArtifactReferenceV1Alpha1
from ace.core.agent_memory import (
    AgentMemoryScopeV1Alpha1,
    KnowledgeTimeKind,
    TemporalQueryV1Alpha1,
    WorldTimeKind,
)
from ace.core.contracts import canonical_hash, stable_id
from ace.core.records import AppendOnlyTransactionRequestV1, ImmutableRecordStore, ImmutableRecordV1
from ace.intelligence.contracts.agent_memory import MemoryContextLineageV1Alpha1
from ace.intelligence.contracts.agent_memory_assertions import (
    AssertionFamilyV1Alpha1,
    AssertionLifecycle,
    EvidenceStatus,
    MemoryAssertionCandidateV1Alpha1,
    MemoryGraphProjectionV1Alpha1,
    MemoryReconciliationDecisionV1Alpha1,
    SourceIndependence,
)
from ace.intelligence.contracts.agent_memory_recall import (
    AuthenticatedRecallRequestV1Alpha1,
    AuthorizedCandidateEvidenceV1Alpha1,
    CandidateSignalScoreV1Alpha1,
    CanonicalContextManifestV1,
    ConditionKind,
    ContextBlockEvidenceV1Alpha1,
    ContextBlockKind,
    ContextInjectionReceiptV1Alpha1,
    ContextPlannerRequestV1Alpha1,
    ContextPlannerResultV1Alpha1,
    ContextReflectionReceiptV1Alpha1,
    ContextUseReceiptV1Alpha1,
    DecisionMaterialReceiptV1Alpha1,
    FusedRankPolicyV1Alpha1,
    InstructionPolicyResolutionReceiptV1Alpha1,
    InstructionPolicyResolutionRequestV1Alpha1,
    MatchedConditionAssignmentV1Alpha1,
    MaterialityComparisonV1Alpha1,
    RecallReceiptV1Alpha1,
    RetrievalSignal,
    RetrievalStateSnapshotV1Alpha1,
    RetrievalTelemetryV1Alpha1,
    RetrievalTier,
    StructuredQuestionKind,
)

AM3_RECORD_SPACE = "agent_memory_recall_v1alpha1"
RECALL_RECEIPT_RECORD_KIND = "memory_recall_receipt"
INSTRUCTION_RECEIPT_RECORD_KIND = "memory_instruction_resolution"
CONTEXT_MANIFEST_RECORD_KIND = "memory_context_manifest"
CONTEXT_PLANNER_RESULT_RECORD_KIND = "memory_context_planner_result"
CONTEXT_INJECTION_RECORD_KIND = "memory_context_injection"
CONTEXT_REFLECTION_RECORD_KIND = "memory_context_reflection"
DECISION_MATERIAL_RECORD_KIND = "memory_decision_material"
CONTEXT_USE_RECORD_KIND = "memory_context_use"
MATERIALITY_COMPARISON_RECORD_KIND = "memory_materiality_comparison"
MEMORY_CONTEXT_LINEAGE_RECORD_KIND = "memory_context_lineage"

MANDATORY_SIGNALS = (
    RetrievalSignal.LEXICAL,
    RetrievalSignal.VECTOR,
    RetrievalSignal.EXACT_ENTITY,
    RetrievalSignal.TEMPORAL,
    RetrievalSignal.GRAPH,
    RetrievalSignal.SOURCE_DIVERSITY,
    RetrievalSignal.GOVERNED_RELIABILITY,
    RetrievalSignal.LIFECYCLE_PRIORITY,
)


class AgentMemoryRecallError(RuntimeError):
    """AM3 failed closed without disclosing candidate existence."""


class AgentMemoryRecallDenied(AgentMemoryRecallError):
    """Authorization failed; message deliberately reveals no resource state."""

    def __init__(self) -> None:
        super().__init__("memory recall is not authorized")


class AgentMemoryRetrievalStateError(AgentMemoryRecallError):
    """A policy, index, projection, canonical head, or cache dependency is stale."""


class AgentMemoryInstructionIsolationError(AgentMemoryRecallError):
    """The authenticated instruction-policy channel failed closed."""


class AgentMemoryContextBudgetError(AgentMemoryRecallError):
    """No authorized context block fits the declared safe budget."""


def _now() -> datetime:
    return datetime.now(UTC)


def _aware(value: datetime, name: str) -> datetime:
    if value.tzinfo is None or value.utcoffset() is None:
        raise AgentMemoryRecallError(f"{name} must include a timezone")
    return value.astimezone(UTC)


def _am2_record_space(scope: AgentMemoryScopeV1Alpha1) -> str:
    return stable_id(
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


def _am3_record_space(scope: AgentMemoryScopeV1Alpha1) -> str:
    return stable_id(AM3_RECORD_SPACE, {"scope_id": scope.scope_id})


def _reopen(model: Any, payload: Mapping[str, Any]) -> Any:
    try:
        return model.model_validate(payload, strict=False)
    except (TypeError, ValueError) as exc:
        raise AgentMemoryRecallError("durable memory material failed exact revalidation") from exc


def _telemetry_local() -> RetrievalTelemetryV1Alpha1:
    return RetrievalTelemetryV1Alpha1(
        latency_ms=0,
        calls=0,
        input_tokens=0,
        output_tokens=0,
        cost_microunits=0,
    )


def _telemetry_unknown() -> RetrievalTelemetryV1Alpha1:
    return RetrievalTelemetryV1Alpha1(
        unknown_fields=("calls", "cost_microunits", "input_tokens", "latency_ms", "output_tokens"),
    )


@dataclass(frozen=True, slots=True)
class SignalObservation:
    score: float
    snapshot_ref: str
    telemetry: RetrievalTelemetryV1Alpha1


@dataclass(frozen=True, slots=True)
class InstructionMaterial:
    policy_ref: str
    source_id: str
    source_version_id: str
    source_span_ref: str
    body: str
    body_digest: str
    lifecycle: str


@dataclass(frozen=True, slots=True)
class InstructionResolutionOutcome:
    receipt: InstructionPolicyResolutionReceiptV1Alpha1
    materials: tuple[InstructionMaterial, ...]


@dataclass(frozen=True, slots=True)
class AssembledContextBlock:
    evidence: ContextBlockEvidenceV1Alpha1
    body: str


@dataclass(frozen=True, slots=True)
class PlannedContext:
    recall: RecallReceiptV1Alpha1
    instructions: InstructionPolicyResolutionReceiptV1Alpha1
    manifest: CanonicalContextManifestV1
    result: ContextPlannerResultV1Alpha1
    blocks: tuple[AssembledContextBlock, ...]


@dataclass(frozen=True, slots=True)
class RecordedContextUse:
    injection: ContextInjectionReceiptV1Alpha1 | None
    reflection: ContextReflectionReceiptV1Alpha1 | None
    decision_material: DecisionMaterialReceiptV1Alpha1 | None
    use: ContextUseReceiptV1Alpha1
    lineages: tuple[MemoryContextLineageV1Alpha1, ...]


class RetrievalStateOwner(Protocol):
    async def current_snapshot(
        self, *, request: AuthenticatedRecallRequestV1Alpha1
    ) -> RetrievalStateSnapshotV1Alpha1: ...

    async def current_assertion_ref(
        self,
        *,
        request: AuthenticatedRecallRequestV1Alpha1,
        semantic_target_ref: str,
        promotion_kind: str,
    ) -> str | None: ...


class RetrievalSignalPort(Protocol):
    signal: RetrievalSignal

    async def score(
        self,
        *,
        request: AuthenticatedRecallRequestV1Alpha1,
        candidate: MemoryAssertionCandidateV1Alpha1,
        expected_snapshot: RetrievalStateSnapshotV1Alpha1,
    ) -> SignalObservation: ...


class AuthorizedCandidateBodyReader(Protocol):
    async def read(self, *, candidate: MemoryAssertionCandidateV1Alpha1) -> str: ...


class InstructionPolicyResolutionPort(Protocol):
    async def resolve(self, *, request: InstructionPolicyResolutionRequestV1Alpha1) -> InstructionResolutionOutcome: ...


class CanonicalCandidateBodyReader:
    """AM2 canonical statement body adapter; caller must authorize first."""

    async def read(self, *, candidate: MemoryAssertionCandidateV1Alpha1) -> str:
        if f"sha256:{canonical_hash(candidate.statement)}" != candidate.statement_digest:
            raise AgentMemoryRecallError("canonical candidate body digest changed")
        return candidate.statement


class StaticRetrievalStateOwner:
    """Exact state-owner adapter for hosts with already-resolved current heads."""

    def __init__(
        self,
        snapshot: RetrievalStateSnapshotV1Alpha1,
        *,
        current_assertion_refs: Mapping[tuple[str, str], str] | None = None,
    ) -> None:
        self.snapshot = snapshot
        self.current_assertion_refs = dict(current_assertion_refs or {})

    async def current_snapshot(self, *, request: AuthenticatedRecallRequestV1Alpha1) -> RetrievalStateSnapshotV1Alpha1:
        del request
        return self.snapshot

    async def current_assertion_ref(
        self,
        *,
        request: AuthenticatedRecallRequestV1Alpha1,
        semantic_target_ref: str,
        promotion_kind: str,
    ) -> str | None:
        del request
        return self.current_assertion_refs.get((promotion_kind, semantic_target_ref))


class CompositionContextManifestBridge:
    """Bind AM3 evidence to AC1–AC7 only after fresh composition authority."""

    def __init__(
        self,
        *,
        runtime_authority: ReasoningCompositionRuntimeAuthorityPort,
        clock: Callable[[], datetime] = _now,
    ) -> None:
        self.runtime_authority = runtime_authority
        self.clock = clock

    async def resolve(
        self,
        *,
        planned: PlannedContext,
        authenticated_context: Any,
        authority_class: str,
        grant_ref: str,
        scope_ref: str,
        policy_ref: str,
    ) -> ContextResolutionOutcome:
        now = _aware(self.clock(), "composition context validation clock")
        manifest = planned.manifest
        receiver = manifest.receiver
        manifest_ref = ExactArtifactReferenceV1Alpha1(
            artifact_id=str(manifest.artifact_id),
            artifact_digest=str(manifest.artifact_digest),
            artifact_contract=manifest.contract,
        )
        if authenticated_context.product_id != receiver.product_id or not (
            authenticated_context.authenticated_at <= now < authenticated_context.expires_at
        ):
            raise AgentMemoryRecallDenied()
        try:
            bundle = await self.runtime_authority.resolve_planning(
                authenticated_context=authenticated_context,
                use_subject=manifest_ref,
                participant_principal_ref=receiver.participant_ref,
                authority_class=authority_class,
                operation="consume_context_manifest",
                grant_ref=grant_ref,
                scope_ref=scope_ref,
                policy_ref=policy_ref,
                evaluated_at=now,
            )
        except Exception as exc:
            raise AgentMemoryRecallDenied() from exc
        receipt = bundle.resolution_receipt
        if (
            receipt.phase != "planning"
            or receipt.product_id != receiver.product_id
            or receipt.participant_principal_ref != receiver.participant_ref
            or receipt.use_subject != manifest_ref
            or receipt.evaluated_at != now
            or not receipt.current_heads
        ):
            raise AgentMemoryRecallDenied()
        selection = ExactArtifactReferenceV1Alpha1(
            artifact_id=str(planned.recall.artifact_id),
            artifact_digest=str(planned.recall.artifact_digest),
            artifact_contract=planned.recall.contract,
        )
        return ContextResolutionOutcome(
            context_manifest=manifest_ref,
            context_selection_receipt=selection,
        )


class ContextPlannerService:
    """Smallest-safe authorized recall and context assembly over AM2 records."""

    def __init__(
        self,
        *,
        store: ImmutableRecordStore,
        authorization: AgentMemoryAuthorizationResolver,
        state_owner: RetrievalStateOwner,
        instruction_resolver: InstructionPolicyResolutionPort,
        body_reader: AuthorizedCandidateBodyReader | None = None,
        signal_ports: Sequence[RetrievalSignalPort] = (),
        clock: Callable[[], datetime] = _now,
    ) -> None:
        self.store = store
        self.authorization = authorization
        self.state_owner = state_owner
        self.instruction_resolver = instruction_resolver
        self.body_reader = body_reader or CanonicalCandidateBodyReader()
        self.signal_ports = {item.signal: item for item in signal_ports}
        if len(self.signal_ports) != len(tuple(signal_ports)):
            raise ValueError("retrieval signal provider identities must be unique")
        if set(self.signal_ports) - {
            RetrievalSignal.LEXICAL,
            RetrievalSignal.VECTOR,
            RetrievalSignal.PERSONALIZED,
            RetrievalSignal.SPATIAL,
            RetrievalSignal.PRIOR_USE,
        }:
            raise ValueError("ports may supply only existing provider-backed optional signals")
        self.clock = clock

    async def plan(self, request: ContextPlannerRequestV1Alpha1) -> PlannedContext:
        request = ContextPlannerRequestV1Alpha1.model_validate(request.model_dump(mode="python"), strict=False)
        now = _aware(self.clock(), "planner clock")
        recall_request = request.recall_request
        await self._authorize(recall_request, "recall_request", str(recall_request.artifact_id), now)
        current = await self._current_snapshot(recall_request, now)
        if current != request.expected_snapshot:
            raise AgentMemoryRetrievalStateError("retrieval state differs from the exact expected snapshot")
        if request.policy.artifact_digest != current.policy_digest:
            raise AgentMemoryRetrievalStateError("fused-rank policy head is stale")

        instructions = await self._resolve_instructions(request.instruction_request, now)
        decisions = await self._load_decisions(recall_request, now)
        projection = (
            None
            if recall_request.structured_question is not StructuredQuestionKind.NONE
            else await self._load_projection(recall_request, decisions, current, now)
        )
        ranked, route, degraded = await self._rank(
            request=recall_request,
            policy=request.policy,
            snapshot=current,
            decisions=decisions,
            projection=projection,
            candidate_limit=min(request.policy.max_candidates, request.budget.max_candidates),
            now=now,
        )
        recall = RecallReceiptV1Alpha1(
            request_ref=str(recall_request.artifact_id),
            request_digest=str(recall_request.artifact_digest),
            receiver_ref=str(recall_request.receiver.artifact_id),
            policy_ref=request.policy.policy_ref,
            policy_digest=str(request.policy.artifact_digest),
            snapshot=current,
            route=route,
            candidates=ranked,
            selected_refs=tuple(item.candidate_ref for item in ranked if item.selected),
            omitted_refs=tuple(item.candidate_ref for item in ranked if not item.selected),
            degraded_reasons=tuple(sorted(degraded)),
            budget_exhausted=any(item.omission_reason == "selection_budget_exhausted" for item in ranked),
            generated_at=now,
        )
        blocks, manifest_omissions = await self._assemble(
            request=request,
            recall=recall,
            instructions=instructions,
            decisions=decisions,
            now=now,
        )
        manifest = CanonicalContextManifestV1(
            planner_request_ref=str(request.artifact_id),
            receiver=recall_request.receiver,
            recall_receipt_ref=str(recall.artifact_id),
            instruction_resolution_ref=str(instructions.receipt.artifact_id),
            snapshot_ref=str(current.artifact_id),
            selected_candidate_refs=tuple(
                block.evidence.candidate_ref for block in blocks if block.evidence.candidate_ref is not None
            ),
            omitted_candidate_refs=tuple(
                sorted(set(recall.omitted_refs) | {item.split("|", 1)[0] for item in manifest_omissions})
            ),
            blocks=tuple(block.evidence for block in blocks),
            total_tokens=sum(block.evidence.token_count for block in blocks),
            total_bytes=sum(block.evidence.byte_count for block in blocks),
            omissions=manifest_omissions,
            degraded_reasons=tuple(sorted(set(recall.degraded_reasons) | set(instructions.receipt.degraded_reasons))),
            generated_at=now,
        )
        stopped = route[-1]
        result = ContextPlannerResultV1Alpha1(
            planner_request_ref=str(request.artifact_id),
            recall_receipt_ref=str(recall.artifact_id),
            instruction_resolution_ref=str(instructions.receipt.artifact_id),
            manifest_ref=str(manifest.artifact_id),
            manifest_digest=str(manifest.artifact_digest),
            stopped_at_tier=stopped,
            degraded_reasons=manifest.degraded_reasons,
            generated_at=now,
        )
        await self._persist_plan(request, recall, instructions.receipt, manifest, result, now)
        return PlannedContext(recall, instructions.receipt, manifest, result, blocks)

    async def reopen_manifest(
        self,
        *,
        request: AuthenticatedRecallRequestV1Alpha1,
        manifest_ref: str,
        expected_snapshot: RetrievalStateSnapshotV1Alpha1,
    ) -> CanonicalContextManifestV1:
        request = AuthenticatedRecallRequestV1Alpha1.model_validate(request.model_dump(mode="python"), strict=False)
        expected_snapshot = RetrievalStateSnapshotV1Alpha1.model_validate(
            expected_snapshot.model_dump(mode="python"), strict=False
        )
        now = _aware(self.clock(), "manifest inspection clock")
        await self._authorize(request, "inspect_context_manifest", manifest_ref, now)
        current = await self._current_snapshot(request, now)
        if current != expected_snapshot:
            raise AgentMemoryRetrievalStateError("context manifest dependencies are stale")
        record = await self.store.load_record(
            stable_id(
                "immutable_record",
                {
                    "product_id": request.scope.product_id,
                    "record_space": _am3_record_space(request.scope),
                    "record_kind": CONTEXT_MANIFEST_RECORD_KIND,
                    "record_key": manifest_ref,
                },
            ),
            product_id=request.scope.product_id,
            record_space=_am3_record_space(request.scope),
            record_kind=CONTEXT_MANIFEST_RECORD_KIND,
        )
        if record is None:
            raise AgentMemoryRecallDenied()
        await self._authorize(request, "inspect_context_manifest", manifest_ref, now)
        manifest = _reopen(CanonicalContextManifestV1, record.payload)
        if manifest.snapshot_ref != expected_snapshot.artifact_id:
            raise AgentMemoryRetrievalStateError("context manifest names a stale retrieval snapshot")
        return manifest

    async def record_use(
        self,
        *,
        request: AuthenticatedRecallRequestV1Alpha1,
        manifest: CanonicalContextManifestV1,
        injected_candidate_refs: tuple[str, ...] = (),
        reflected_candidate_refs: tuple[str, ...] = (),
        decision_material_candidate_refs: tuple[str, ...] = (),
        comparison: MaterialityComparisonV1Alpha1 | None = None,
        intelligence_use_receipt_ref: str | None = None,
        evidence_refs: tuple[str, ...] = (),
        reflection_method: str = "bounded_attribution",
    ) -> RecordedContextUse:
        now = _aware(self.clock(), "context-use clock")
        await self._authorize(request, "record_context_use", str(manifest.artifact_id), now)
        selected = set(manifest.selected_candidate_refs)
        injected = set(injected_candidate_refs)
        reflected = set(reflected_candidate_refs)
        material = set(decision_material_candidate_refs)
        if not material <= reflected <= injected <= selected:
            raise AgentMemoryRecallError("context-use evidence crossed the manifest selection chain")
        if material and (
            comparison is None
            or not comparison.material_influence
            or intelligence_use_receipt_ref is None
            or material != set(comparison.target_candidate_refs)
        ):
            raise AgentMemoryRecallError("decision-material use requires an exact matched comparison and I3 receipt")
        evidence = evidence_refs or (f"context_manifest:{manifest.artifact_id}",)
        receiver_ref = str(request.receiver.artifact_id)
        injection = (
            ContextInjectionReceiptV1Alpha1(
                manifest_ref=str(manifest.artifact_id),
                receiver_ref=receiver_ref,
                candidate_refs=tuple(sorted(injected)),
                evidence_refs=evidence,
                observed_at=now,
            )
            if injected
            else None
        )
        reflection = (
            ContextReflectionReceiptV1Alpha1(
                manifest_ref=str(manifest.artifact_id),
                receiver_ref=receiver_ref,
                candidate_refs=tuple(sorted(reflected)),
                evidence_refs=evidence,
                observed_at=now,
                reflection_method=reflection_method,
            )
            if reflected
            else None
        )
        decision_material = (
            DecisionMaterialReceiptV1Alpha1(
                manifest_ref=str(manifest.artifact_id),
                receiver_ref=receiver_ref,
                candidate_refs=tuple(sorted(material)),
                evidence_refs=evidence,
                observed_at=now,
                comparison_ref=str(comparison.artifact_id),
                changed_fields=comparison.changed_fields,
            )
            if material and comparison is not None
            else None
        )
        use = ContextUseReceiptV1Alpha1(
            manifest_ref=str(manifest.artifact_id),
            receiver_ref=receiver_ref,
            selected_candidate_refs=manifest.selected_candidate_refs,
            injected_candidate_refs=tuple(sorted(injected)),
            reflected_candidate_refs=tuple(sorted(reflected)),
            decision_material_candidate_refs=tuple(sorted(material)),
            injection_receipt_ref=str(injection.artifact_id) if injection else None,
            reflection_receipt_ref=str(reflection.artifact_id) if reflection else None,
            decision_material_receipt_ref=str(decision_material.artifact_id) if decision_material else None,
            intelligence_use_receipt_ref=intelligence_use_receipt_ref,
            recorded_at=now,
        )
        blocks_by_candidate = {
            block.candidate_ref: block for block in manifest.blocks if block.candidate_ref is not None
        }
        lineages = tuple(
            MemoryContextLineageV1Alpha1(
                scope=request.scope,
                candidate_receipt_id=str(manifest.recall_receipt_ref),
                assertion_ref=candidate_ref,
                context_manifest_id=str(manifest.artifact_id),
                context_item_ref=str(blocks_by_candidate[candidate_ref].artifact_id),
                context_item_source_receipt_ref=blocks_by_candidate[candidate_ref].authorization_receipt_ref,
                intelligence_use_receipt_ref=intelligence_use_receipt_ref if candidate_ref in material else None,
                decision_ref=(
                    f"decision_material:{decision_material.artifact_id}" if candidate_ref in material else None
                ),
                recorded_at=now,
            )
            for candidate_ref in manifest.selected_candidate_refs
        )
        await self._persist_use(request.scope, injection, reflection, decision_material, use, comparison, lineages, now)
        return RecordedContextUse(injection, reflection, decision_material, use, lineages)

    async def _authorize(
        self,
        request: AuthenticatedRecallRequestV1Alpha1,
        operation: str,
        subject_ref: str,
        evaluated_at: datetime,
    ) -> AuthorizedAgentMemoryUse:
        try:
            use = await self.authorization.authorize(
                context=request.authenticated_context,
                scope=request.scope,
                operation=operation,
                subject_ref=subject_ref,
                evaluated_at=evaluated_at,
            )
        except Exception as exc:
            raise AgentMemoryRecallDenied() from exc
        if (
            use.product_id != request.scope.product_id
            or use.actor_id != request.scope.actor_id
            or use.operation != operation
            or use.subject_ref != subject_ref
            or use.authority_receipt_ref != request.scope.authority_receipt_ref
            or use.lifecycle_snapshot_ref == "lifecycle_snapshot:unspecified"
            or use.lifecycle_state.value != "active"
            or use.evaluated_at != evaluated_at
            or request.authenticated_context.product_id != request.scope.product_id
            or request.authenticated_context.actor_ref != request.scope.actor_id
            or not (
                request.authenticated_context.authenticated_at
                <= evaluated_at
                < request.authenticated_context.expires_at
            )
            or (use.expires_at is not None and use.expires_at <= evaluated_at)
        ):
            raise AgentMemoryRecallDenied()
        return use

    async def _current_snapshot(
        self, request: AuthenticatedRecallRequestV1Alpha1, now: datetime
    ) -> RetrievalStateSnapshotV1Alpha1:
        await self._authorize(request, "resolve_retrieval_state", str(request.artifact_id), now)
        try:
            snapshot = await self.state_owner.current_snapshot(request=request)
        except Exception as exc:
            raise AgentMemoryRetrievalStateError("retrieval state is unavailable") from exc
        await self._authorize(request, "inspect_retrieval_state", str(snapshot.artifact_id), now)
        return snapshot

    async def _resolve_instructions(
        self, request: InstructionPolicyResolutionRequestV1Alpha1, now: datetime
    ) -> InstructionResolutionOutcome:
        recall_shape = AuthenticatedRecallRequestV1Alpha1(
            authenticated_context=request.authenticated_context,
            scope=request.scope,
            receiver=request.receiver,
            query_text="instruction-policy-channel",
            structured_question=StructuredQuestionKind.NONE,
            eligible_families=(AssertionFamilyV1Alpha1.IDENTITY,),
            temporal=TemporalQueryV1Alpha1(),
            requested_at=request.requested_at,
        )
        await self._authorize(recall_shape, "resolve_instruction_policy", str(request.artifact_id), now)
        try:
            outcome = await self.instruction_resolver.resolve(request=request)
        except Exception as exc:
            raise AgentMemoryInstructionIsolationError("instruction-policy resolution failed") from exc
        receipt = outcome.receipt
        if (
            receipt.request_ref != request.artifact_id
            or receipt.instruction_channel_ref != request.instruction_channel_ref
            or receipt.blocked
            or {item.policy_ref for item in outcome.materials} != set(receipt.resolved_policy_refs)
            or any(f"sha256:{canonical_hash(item.body)}" != item.body_digest for item in outcome.materials)
        ):
            raise AgentMemoryInstructionIsolationError("instruction-policy resolution crossed its exact channel")
        return outcome

    async def _load_decisions(
        self, request: AuthenticatedRecallRequestV1Alpha1, now: datetime
    ) -> tuple[MemoryReconciliationDecisionV1Alpha1, ...]:
        await self._authorize(request, "list_memory_candidates", str(request.scope.scope_id), now)
        records = await self.store.read_as_of(
            product_id=request.scope.product_id,
            record_space=_am2_record_space(request.scope),
            record_kind=ASSERTION_DECISION_RECORD_KIND,
            available_at=now,
        )
        decisions: list[MemoryReconciliationDecisionV1Alpha1] = []
        for record in records:
            await self._authorize(request, "inspect_memory_candidate", str(record.storage_id), now)
            decision = _reopen(MemoryReconciliationDecisionV1Alpha1, record.payload)
            await self._authorize(request, "inspect_memory_candidate", str(decision.candidate.candidate_id), now)
            decisions.append(decision)
        return tuple(sorted(decisions, key=lambda item: (item.ledger_coordinate.sequence, str(item.decision_id))))

    async def _load_projection(
        self,
        request: AuthenticatedRecallRequestV1Alpha1,
        decisions: tuple[MemoryReconciliationDecisionV1Alpha1, ...],
        snapshot: RetrievalStateSnapshotV1Alpha1,
        now: datetime,
    ) -> MemoryGraphProjectionV1Alpha1:
        await self._authorize(request, "query_memory_graph", str(request.scope.scope_id), now)
        records = await self.store.read_as_of(
            product_id=request.scope.product_id,
            record_space=_am2_record_space(request.scope),
            record_kind=GRAPH_PROJECTION_RECORD_KIND,
            available_at=now,
        )
        if not records:
            raise AgentMemoryRetrievalStateError("required graph projection is missing")
        await self._authorize(request, "inspect_memory_graph", str(records[-1].storage_id), now)
        projection = _reopen(MemoryGraphProjectionV1Alpha1, records[-1].payload)
        expected_source = (
            f"sha256:{canonical_hash(tuple((item.decision_id, item.decision_digest) for item in decisions))}"
        )
        if (
            projection.projection_digest != snapshot.projection_digest
            or projection.projection_id != snapshot.projection_ref
        ):
            raise AgentMemoryRetrievalStateError("graph projection differs from the exact retrieval snapshot")
        if projection.source_snapshot_digest != expected_source:
            raise AgentMemoryRetrievalStateError("graph projection is stale against canonical AM2 records")
        return projection

    async def _rank(
        self,
        *,
        request: AuthenticatedRecallRequestV1Alpha1,
        policy: FusedRankPolicyV1Alpha1,
        snapshot: RetrievalStateSnapshotV1Alpha1,
        decisions: tuple[MemoryReconciliationDecisionV1Alpha1, ...],
        projection: MemoryGraphProjectionV1Alpha1 | None,
        candidate_limit: int,
        now: datetime,
    ) -> tuple[tuple[AuthorizedCandidateEvidenceV1Alpha1, ...], tuple[RetrievalTier, ...], set[str]]:
        structured = request.structured_question is not StructuredQuestionKind.NONE
        route = [RetrievalTier.STRUCTURED_LOOKUP] if structured else [RetrievalTier.FUSED_RETRIEVAL]
        active_signals = (
            (
                RetrievalSignal.EXACT_ENTITY,
                RetrievalSignal.TEMPORAL,
                RetrievalSignal.LIFECYCLE_PRIORITY,
            )
            if structured
            else tuple(policy.signal_weights)
        )
        degraded: set[str] = set()
        eligible: list[MemoryReconciliationDecisionV1Alpha1] = []
        pre_omitted: dict[str, tuple[MemoryReconciliationDecisionV1Alpha1, str]] = {}
        superseded = {ref for decision in decisions for ref in decision.supersedes}
        governed_current: set[str] = set()
        for decision in decisions:
            candidate = decision.candidate
            if candidate.family is not AssertionFamilyV1Alpha1.CORRECTION:
                continue
            target = str(candidate.semantic_target.coordinate_id)
            await self._authorize(request, "resolve_current_memory_correction", target, now)
            try:
                current_ref = await self.state_owner.current_assertion_ref(
                    request=request,
                    semantic_target_ref=target,
                    promotion_kind="correction",
                )
            except Exception as exc:
                raise AgentMemoryRetrievalStateError("current correction head is unavailable") from exc
            if current_ref == candidate.candidate_id:
                governed_current.add(str(candidate.candidate_id))
        for decision in decisions:
            candidate = decision.candidate
            ref = str(candidate.candidate_id)
            await self._authorize(request, "structured_memory_lookup", ref, now)
            reason = self._eligibility_reason(request, decision, superseded, governed_current)
            if reason is None:
                eligible.append(decision)
            else:
                pre_omitted[ref] = (decision, reason)
        if len(eligible) > candidate_limit:
            for decision in eligible[candidate_limit:]:
                pre_omitted[str(decision.candidate.candidate_id)] = (decision, "candidate_budget_exhausted")
            eligible = eligible[:candidate_limit]
            degraded.add("candidate_budget_exhausted")

        source_counts: dict[str, int] = defaultdict(int)
        for decision in eligible:
            source_counts[decision.candidate.source.source_id] += 1
        graph_distances = self._graph_distances(request, projection, policy) if projection is not None else {}
        scored: list[tuple[MemoryReconciliationDecisionV1Alpha1, tuple[CandidateSignalScoreV1Alpha1, ...], float]] = []
        for decision in eligible:
            signals: list[CandidateSignalScoreV1Alpha1] = []
            for signal in active_signals:
                observed = await self._signal_score(
                    request=request,
                    decision=decision,
                    signal=signal,
                    snapshot=snapshot,
                    source_counts=source_counts,
                    graph_distances=graph_distances,
                    governed_current=governed_current,
                    now=now,
                )
                signals.append(observed)
                if not observed.available:
                    degraded.add(f"signal_unavailable:{signal.value}:{observed.unavailable_reason}")
            denominator = sum(policy.signal_weights[signal] for signal in active_signals) or 1.0
            aggregate = (
                sum(
                    policy.signal_weights[item.signal] * (item.score if item.score is not None else 0.0)
                    for item in signals
                )
                / denominator
            )
            scored.append((decision, tuple(signals), round(max(-1.0, min(1.0, aggregate)), 12)))
        scored.sort(key=lambda item: (-item[2], str(item[0].candidate.candidate_id)))
        selected_refs: set[str] = set()
        ranks: dict[str, int] = {}
        for decision, _, aggregate in scored:
            ref = str(decision.candidate.candidate_id)
            if aggregate < policy.minimum_score:
                pre_omitted[ref] = (decision, "below_minimum_score")
            elif len(selected_refs) >= policy.max_selected:
                pre_omitted[ref] = (decision, "selection_budget_exhausted")
                degraded.add("selection_budget_exhausted")
            else:
                selected_refs.add(ref)
                ranks[ref] = len(selected_refs)
        evidence: list[AuthorizedCandidateEvidenceV1Alpha1] = []
        score_map = {
            str(decision.candidate.candidate_id): (signals, aggregate) for decision, signals, aggregate in scored
        }
        all_decisions = {str(item.candidate.candidate_id): item for item in decisions}
        for ref, decision in all_decisions.items():
            signals, aggregate = score_map.get(
                ref, (await self._unavailable_signals(request, decision, active_signals, now), -1.0)
            )
            omission = pre_omitted.get(ref, (decision, None))[1]
            selected = ref in selected_refs
            evidence.append(
                AuthorizedCandidateEvidenceV1Alpha1(
                    candidate_ref=ref,
                    candidate_digest=str(decision.candidate.candidate_digest),
                    source_id=decision.candidate.source.source_id,
                    source_version_id=decision.candidate.source.source_version_id,
                    semantic_target_ref=str(decision.candidate.semantic_target.coordinate_id),
                    family=decision.candidate.family,
                    lifecycle=(
                        AssertionLifecycle.CORRECTION_ADMITTED if ref in governed_current else decision.lifecycle
                    ),
                    signal_scores=tuple(sorted(signals, key=lambda item: item.signal)),
                    aggregate_score=aggregate,
                    selected=selected,
                    omission_reason=None if selected else omission or "not_selected",
                    rank=ranks.get(ref),
                )
            )
        evidence.sort(key=lambda item: (item.rank is None, item.rank or 999, item.candidate_ref))
        if not structured and any(
            score.signal is RetrievalSignal.GRAPH and score.available and score.score and score.score > 0
            for item in evidence
            for score in item.signal_scores
        ):
            route.append(RetrievalTier.GRAPH_EXPANSION)
        return tuple(evidence), tuple(route), degraded

    def _eligibility_reason(
        self,
        request: AuthenticatedRecallRequestV1Alpha1,
        decision: MemoryReconciliationDecisionV1Alpha1,
        superseded: set[str],
        governed_current: set[str],
    ) -> str | None:
        candidate = decision.candidate
        ref = str(candidate.candidate_id)
        if candidate.family is AssertionFamilyV1Alpha1.INSTRUCTION_POLICY_PROPOSAL:
            return "instruction_policy_isolated"
        if candidate.family is AssertionFamilyV1Alpha1.CORRECTION and ref not in governed_current:
            return "correction_not_current_or_governed"
        if request.assertion_refs and ref not in request.assertion_refs:
            return "outside_exact_assertion_request"
        if candidate.family not in request.eligible_families:
            return "family_ineligible"
        if ref in superseded or decision.lifecycle in {AssertionLifecycle.SUPERSEDED, AssertionLifecycle.REJECTED}:
            return "lifecycle_ineligible"
        allowed = {
            AssertionLifecycle.PROPOSED,
            AssertionLifecycle.ADMITTED,
            AssertionLifecycle.CORRECTION_ADMITTED,
            AssertionLifecycle.UNCERTAINTY,
        }
        if decision.lifecycle not in allowed:
            return "lifecycle_ineligible"
        if not self._temporal_eligible(candidate, decision, request):
            return "temporal_ineligible"
        if request.structured_question is StructuredQuestionKind.EXACT_IDENTITY:
            if candidate.family is not AssertionFamilyV1Alpha1.IDENTITY:
                return "structured_question_mismatch"
        elif request.structured_question is StructuredQuestionKind.CURRENT_CORRECTION:
            if candidate.family is not AssertionFamilyV1Alpha1.CORRECTION:
                return "structured_question_mismatch"
        elif request.structured_question is StructuredQuestionKind.UNCERTAINTY:
            if candidate.family is not AssertionFamilyV1Alpha1.UNCERTAINTY:
                return "structured_question_mismatch"
        elif request.structured_question is StructuredQuestionKind.CURRENT_STATE:
            if candidate.family not in {
                AssertionFamilyV1Alpha1.ACTIVE_CONTEXT,
                AssertionFamilyV1Alpha1.CORRECTION,
                AssertionFamilyV1Alpha1.UNCERTAINTY,
            }:
                return "structured_question_mismatch"
        elif request.structured_question is StructuredQuestionKind.ADMITTED_INSTRUCTION_REFERENCE:
            return "instruction_policy_isolated"
        if request.semantic_target_ref and request.semantic_target_ref not in {
            candidate.semantic_target.coordinate_id,
            candidate.semantic_target.entity_ref,
            candidate.semantic_target.target_ref,
        }:
            return "semantic_target_mismatch"
        return None

    @staticmethod
    def _temporal_eligible(
        candidate: MemoryAssertionCandidateV1Alpha1,
        decision: MemoryReconciliationDecisionV1Alpha1,
        request: AuthenticatedRecallRequestV1Alpha1,
    ) -> bool:
        temporal = request.temporal
        if temporal.ledger_at is not None and (
            decision.ledger_coordinate.ledger_ref != temporal.ledger_at.ledger_ref
            or decision.ledger_coordinate.sequence > temporal.ledger_at.sequence
            or decision.ledger_coordinate.committed_at > temporal.ledger_at.committed_at
        ):
            return False
        if temporal.knowledge_at is not None:
            knowledge = candidate.knowledge_time
            if knowledge.kind is KnowledgeTimeKind.UNKNOWN:
                if not temporal.include_unknown_knowledge:
                    return False
            elif (
                knowledge.first_known_at is None
                or knowledge.first_known_at > temporal.knowledge_at
                or candidate.knowledge_revision_at > temporal.knowledge_at
            ):
                return False
        if temporal.world_at is not None:
            world = candidate.world_time
            if world.kind is WorldTimeKind.UNKNOWN:
                if not temporal.include_unknown_world:
                    return False
            elif world.kind is WorldTimeKind.INSTANT:
                if world.occurred_at is None or world.occurred_at > temporal.world_at:
                    return False
            else:
                if world.valid_from is not None and temporal.world_at < world.valid_from:
                    return False
                if world.valid_to is not None and temporal.world_at > world.valid_to:
                    return False
        return True

    def _graph_distances(
        self,
        request: AuthenticatedRecallRequestV1Alpha1,
        projection: MemoryGraphProjectionV1Alpha1,
        policy: FusedRankPolicyV1Alpha1,
    ) -> dict[str, int]:
        if not request.semantic_target_ref:
            return {}
        neighbors: dict[str, set[str]] = defaultdict(set)
        for edge in projection.edges:
            neighbors[edge.from_ref].add(edge.to_ref)
            neighbors[edge.to_ref].add(edge.from_ref)
        distances = {request.semantic_target_ref: 0}
        queue = deque([request.semantic_target_ref])
        while queue and len(distances) < policy.max_graph_nodes:
            current = queue.popleft()
            if distances[current] >= policy.max_graph_depth:
                continue
            for neighbor in sorted(neighbors[current]):
                if neighbor not in distances:
                    distances[neighbor] = distances[current] + 1
                    queue.append(neighbor)
                    if len(distances) >= policy.max_graph_nodes:
                        break
        return distances

    async def _signal_score(
        self,
        *,
        request: AuthenticatedRecallRequestV1Alpha1,
        decision: MemoryReconciliationDecisionV1Alpha1,
        signal: RetrievalSignal,
        snapshot: RetrievalStateSnapshotV1Alpha1,
        source_counts: Mapping[str, int],
        graph_distances: Mapping[str, int],
        governed_current: set[str],
        now: datetime,
    ) -> CandidateSignalScoreV1Alpha1:
        candidate = decision.candidate
        ref = str(candidate.candidate_id)
        use = await self._authorize(request, f"score_memory_{signal.value}", ref, now)
        provider = self.signal_ports.get(signal)
        if provider is not None:
            try:
                observation = await provider.score(request=request, candidate=candidate, expected_snapshot=snapshot)
                if observation.snapshot_ref not in {
                    *snapshot.index_refs,
                    snapshot.projection_ref,
                    snapshot.policy_ref,
                    *snapshot.canonical_head_refs,
                }:
                    raise AgentMemoryRetrievalStateError("signal provider returned an unbound snapshot")
                return CandidateSignalScoreV1Alpha1(
                    candidate_ref=ref,
                    signal=signal,
                    available=True,
                    score=observation.score,
                    snapshot_ref=observation.snapshot_ref,
                    authorization_receipt_ref=use.authority_receipt_ref,
                    telemetry=observation.telemetry,
                )
            except AgentMemoryRetrievalStateError:
                raise
            except Exception:
                return CandidateSignalScoreV1Alpha1(
                    candidate_ref=ref,
                    signal=signal,
                    available=False,
                    authorization_receipt_ref=use.authority_receipt_ref,
                    unavailable_reason="provider_failure",
                    telemetry=_telemetry_unknown(),
                )
        score: float | None = None
        snapshot_ref = snapshot.projection_ref
        unavailable = None
        if signal in {RetrievalSignal.LEXICAL, RetrievalSignal.VECTOR}:
            unavailable = "existing_signal_port_unavailable"
        elif signal is RetrievalSignal.EXACT_ENTITY:
            target = request.semantic_target_ref
            score = (
                1.0
                if target
                and target
                in {
                    candidate.semantic_target.coordinate_id,
                    candidate.semantic_target.entity_ref,
                    candidate.semantic_target.target_ref,
                }
                else 0.0
            )
        elif signal is RetrievalSignal.TEMPORAL:
            score = 1.0
        elif signal is RetrievalSignal.GRAPH:
            distance = graph_distances.get(ref)
            score = 0.0 if distance is None else 1.0 / (1 + distance)
        elif signal is RetrievalSignal.SOURCE_DIVERSITY:
            count = source_counts.get(candidate.source.source_id, 1)
            score = 1.0 / count if candidate.source.independence is SourceIndependence.INDEPENDENT else 0.0
        elif signal is RetrievalSignal.GOVERNED_RELIABILITY:
            reliability = candidate.source.reliability
            if reliability.status is EvidenceStatus.KNOWN:
                score = reliability.value
            else:
                unavailable = "governed_reliability_unknown"
        elif signal is RetrievalSignal.LIFECYCLE_PRIORITY:
            if ref in governed_current:
                score = 1.0
            else:
                score = {
                    AssertionLifecycle.UNCERTAINTY: 0.9,
                    AssertionLifecycle.ADMITTED: 0.7,
                    AssertionLifecycle.PROPOSED: 0.5,
                }.get(decision.lifecycle, 0.0)
        else:
            unavailable = "optional_signal_not_supported"
        if score is None:
            return CandidateSignalScoreV1Alpha1(
                candidate_ref=ref,
                signal=signal,
                available=False,
                authorization_receipt_ref=use.authority_receipt_ref,
                unavailable_reason=str(unavailable),
                telemetry=_telemetry_local(),
            )
        return CandidateSignalScoreV1Alpha1(
            candidate_ref=ref,
            signal=signal,
            available=True,
            score=score,
            snapshot_ref=snapshot_ref,
            authorization_receipt_ref=use.authority_receipt_ref,
            telemetry=_telemetry_local(),
        )

    async def _unavailable_signals(
        self,
        request: AuthenticatedRecallRequestV1Alpha1,
        decision: MemoryReconciliationDecisionV1Alpha1,
        signals: tuple[RetrievalSignal, ...],
        now: datetime,
    ) -> tuple[CandidateSignalScoreV1Alpha1, ...]:
        result = []
        for signal in signals:
            use = await self._authorize(
                request, f"score_memory_{signal.value}", str(decision.candidate.candidate_id), now
            )
            result.append(
                CandidateSignalScoreV1Alpha1(
                    candidate_ref=str(decision.candidate.candidate_id),
                    signal=signal,
                    available=False,
                    authorization_receipt_ref=use.authority_receipt_ref,
                    unavailable_reason="candidate_ineligible_before_signal",
                    telemetry=_telemetry_local(),
                )
            )
        return tuple(result)

    async def _assemble(
        self,
        *,
        request: ContextPlannerRequestV1Alpha1,
        recall: RecallReceiptV1Alpha1,
        instructions: InstructionResolutionOutcome,
        decisions: tuple[MemoryReconciliationDecisionV1Alpha1, ...],
        now: datetime,
    ) -> tuple[tuple[AssembledContextBlock, ...], tuple[str, ...]]:
        recall_request = request.recall_request
        blocks: list[AssembledContextBlock] = []
        omissions: list[str] = []
        total_tokens = 0
        total_bytes = 0
        for material in instructions.materials:
            use = await self._authorize(recall_request, "assemble_instruction_context", material.policy_ref, now)
            body_bytes = len(material.body.encode("utf-8"))
            tokens = max(1, (len(material.body) + 3) // 4)
            if not self._fits(request, blocks, total_tokens, total_bytes, tokens, body_bytes):
                raise AgentMemoryInstructionIsolationError("authorized instruction policy exceeds safe context budget")
            evidence = ContextBlockEvidenceV1Alpha1(
                kind=ContextBlockKind.INSTRUCTION,
                instruction_policy_ref=material.policy_ref,
                source_id=material.source_id,
                source_version_id=material.source_version_id,
                source_span_ref=material.source_span_ref,
                lifecycle=material.lifecycle,
                body_digest=material.body_digest,
                token_count=tokens,
                byte_count=body_bytes,
                receiving_stage_ref=recall_request.receiver.stage_ref,
                authorization_receipt_ref=use.authority_receipt_ref,
            )
            blocks.append(AssembledContextBlock(evidence, material.body))
            total_tokens += tokens
            total_bytes += body_bytes
        decisions_by_ref = {str(item.candidate.candidate_id): item for item in decisions}
        for candidate_ref in recall.selected_refs:
            decision = decisions_by_ref[candidate_ref]
            candidate = decision.candidate
            use = await self._authorize(recall_request, "fetch_memory_body", candidate_ref, now)
            try:
                body = await self.body_reader.read(candidate=candidate)
            except Exception:
                omissions.append(f"{candidate_ref}|authorized_body_unavailable")
                continue
            if f"sha256:{canonical_hash(body)}" != candidate.statement_digest:
                raise AgentMemoryRecallError("authorized body differs from canonical candidate digest")
            await self._authorize(recall_request, "assemble_memory_context", candidate_ref, now)
            body_bytes = len(body.encode("utf-8"))
            tokens = max(1, (len(body) + 3) // 4)
            if not self._fits(request, blocks, total_tokens, total_bytes, tokens, body_bytes):
                omissions.append(f"{candidate_ref}|context_budget_exhausted")
                continue
            kind = self._context_kind(candidate, decision)
            freshness_ref = next(
                (
                    str(score.artifact_id)
                    for item in recall.candidates
                    if item.candidate_ref == candidate_ref
                    for score in item.signal_scores
                    if score.signal is RetrievalSignal.TEMPORAL
                ),
                None,
            )
            evidence = ContextBlockEvidenceV1Alpha1(
                kind=kind,
                candidate_ref=candidate_ref,
                source_id=candidate.source.source_id,
                source_version_id=candidate.source.source_version_id,
                source_span_ref=str(candidate.source.span.span_id),
                lifecycle=decision.lifecycle.value,
                uncertainty_ref=decision.uncertainty_ref,
                freshness_signal_ref=freshness_ref,
                body_digest=str(candidate.statement_digest),
                token_count=tokens,
                byte_count=body_bytes,
                receiving_stage_ref=recall_request.receiver.stage_ref,
                authorization_receipt_ref=use.authority_receipt_ref,
            )
            blocks.append(AssembledContextBlock(evidence, body))
            total_tokens += tokens
            total_bytes += body_bytes
        if not blocks:
            raise AgentMemoryContextBudgetError("no authorized context block satisfied the safe budget")
        return tuple(blocks), tuple(sorted(omissions))

    @staticmethod
    def _fits(
        request: ContextPlannerRequestV1Alpha1,
        blocks: list[AssembledContextBlock],
        total_tokens: int,
        total_bytes: int,
        tokens: int,
        body_bytes: int,
    ) -> bool:
        return (
            len(blocks) < min(request.budget.max_blocks, request.policy.max_selected)
            and total_tokens + tokens <= min(request.budget.max_tokens, request.policy.max_context_tokens)
            and total_bytes + body_bytes <= min(request.budget.max_bytes, request.policy.max_context_bytes)
        )

    @staticmethod
    def _context_kind(
        candidate: MemoryAssertionCandidateV1Alpha1, decision: MemoryReconciliationDecisionV1Alpha1
    ) -> ContextBlockKind:
        if candidate.family is AssertionFamilyV1Alpha1.IDENTITY:
            return ContextBlockKind.PROFILE
        if (
            candidate.family is AssertionFamilyV1Alpha1.UNCERTAINTY
            or decision.lifecycle is AssertionLifecycle.UNCERTAINTY
        ):
            return ContextBlockKind.UNCERTAINTY
        if candidate.source.source_kind.value == "document":
            return ContextBlockKind.DOCUMENT
        if candidate.source.source_kind.value in {
            "reflection_proposal",
            "elaboration_proposal",
            "consolidation_proposal",
        }:
            return ContextBlockKind.COGNITION
        return ContextBlockKind.FACT

    async def _persist_plan(
        self,
        request: ContextPlannerRequestV1Alpha1,
        recall: RecallReceiptV1Alpha1,
        instructions: InstructionPolicyResolutionReceiptV1Alpha1,
        manifest: CanonicalContextManifestV1,
        result: ContextPlannerResultV1Alpha1,
        now: datetime,
    ) -> None:
        scope = request.recall_request.scope
        records = (
            self._record(scope, RECALL_RECEIPT_RECORD_KIND, str(recall.artifact_id), recall, now, 0),
            self._record(scope, INSTRUCTION_RECEIPT_RECORD_KIND, str(instructions.artifact_id), instructions, now, 1),
            self._record(scope, CONTEXT_MANIFEST_RECORD_KIND, str(manifest.artifact_id), manifest, now, 2),
            self._record(scope, CONTEXT_PLANNER_RESULT_RECORD_KIND, str(result.artifact_id), result, now, 3),
        )
        await self.store.append(
            AppendOnlyTransactionRequestV1(
                product_id=scope.product_id,
                record_space=_am3_record_space(scope),
                transaction_key=stable_id("context_planner_transaction", {"request_ref": request.artifact_id}),
                records=records,
                submitted_at=now,
            )
        )

    async def _persist_use(
        self,
        scope: AgentMemoryScopeV1Alpha1,
        injection: ContextInjectionReceiptV1Alpha1 | None,
        reflection: ContextReflectionReceiptV1Alpha1 | None,
        decision_material: DecisionMaterialReceiptV1Alpha1 | None,
        use: ContextUseReceiptV1Alpha1,
        comparison: MaterialityComparisonV1Alpha1 | None,
        lineages: tuple[MemoryContextLineageV1Alpha1, ...],
        now: datetime,
    ) -> None:
        artifacts: list[tuple[str, Any]] = []
        if injection:
            artifacts.append((CONTEXT_INJECTION_RECORD_KIND, injection))
        if reflection:
            artifacts.append((CONTEXT_REFLECTION_RECORD_KIND, reflection))
        if comparison:
            artifacts.append((MATERIALITY_COMPARISON_RECORD_KIND, comparison))
        if decision_material:
            artifacts.append((DECISION_MATERIAL_RECORD_KIND, decision_material))
        artifacts.append((CONTEXT_USE_RECORD_KIND, use))
        artifacts.extend((MEMORY_CONTEXT_LINEAGE_RECORD_KIND, item) for item in lineages)
        records = tuple(
            self._record(
                scope,
                kind,
                str(getattr(artifact, "artifact_id", None) or artifact.lineage_id),
                artifact,
                now,
                index,
            )
            for index, (kind, artifact) in enumerate(artifacts)
        )
        await self.store.append(
            AppendOnlyTransactionRequestV1(
                product_id=scope.product_id,
                record_space=_am3_record_space(scope),
                transaction_key=stable_id("context_use_transaction", {"use_ref": use.artifact_id}),
                records=records,
                submitted_at=now,
            )
        )

    @staticmethod
    def _record(
        scope: AgentMemoryScopeV1Alpha1,
        kind: str,
        key: str,
        artifact: Any,
        now: datetime,
        order: int,
    ) -> ImmutableRecordV1:
        return ImmutableRecordV1(
            product_id=scope.product_id,
            record_space=_am3_record_space(scope),
            record_kind=kind,
            record_key=key,
            payload_contract=str(artifact.contract),
            payload=artifact.model_dump(mode="python"),
            as_of=now,
            available_at=now,
            processing_order=order,
        )


def compare_matched_conditions(
    *,
    memory: MatchedConditionAssignmentV1Alpha1,
    no_memory: MatchedConditionAssignmentV1Alpha1,
    target_candidate_refs: tuple[str, ...],
    memory_output: Mapping[str, Any],
    no_memory_output: Mapping[str, Any],
    compared_at: datetime,
) -> MaterialityComparisonV1Alpha1:
    """Provider-free exact matched comparison; material influence is not benefit."""

    if memory.condition is not ConditionKind.MEMORY or no_memory.condition is not ConditionKind.NO_MEMORY:
        raise AgentMemoryRecallError("matched comparison requires one memory and one no-memory condition")
    dimensions = (
        "comparison_group_ref",
        "task_digest",
        "prompt_contract_digest",
        "provider_ref",
        "model_ref",
        "configuration_digest",
        "decision_schema_ref",
        "toolset_digest",
    )
    if any(getattr(memory, field) != getattr(no_memory, field) for field in dimensions):
        raise AgentMemoryRecallError("matched comparison differs on a held constant")
    changed = tuple(
        sorted(
            key
            for key in set(memory_output) | set(no_memory_output)
            if memory_output.get(key) != no_memory_output.get(key)
        )
    )
    memory_digest = f"sha256:{canonical_hash(dict(memory_output))}"
    no_memory_digest = f"sha256:{canonical_hash(dict(no_memory_output))}"
    return MaterialityComparisonV1Alpha1(
        comparison_group_ref=memory.comparison_group_ref,
        memory_assignment_ref=str(memory.artifact_id),
        no_memory_assignment_ref=str(no_memory.artifact_id),
        target_candidate_refs=target_candidate_refs,
        held_constant_fields=dimensions,
        changed_fields=changed,
        memory_output_digest=memory_digest,
        no_memory_output_digest=no_memory_digest,
        material_influence=bool(changed and memory_digest != no_memory_digest),
        compared_at=compared_at,
    )


__all__ = [
    "AM3_RECORD_SPACE",
    "CONTEXT_INJECTION_RECORD_KIND",
    "CONTEXT_MANIFEST_RECORD_KIND",
    "CONTEXT_PLANNER_RESULT_RECORD_KIND",
    "CONTEXT_REFLECTION_RECORD_KIND",
    "CONTEXT_USE_RECORD_KIND",
    "DECISION_MATERIAL_RECORD_KIND",
    "INSTRUCTION_RECEIPT_RECORD_KIND",
    "MANDATORY_SIGNALS",
    "MATERIALITY_COMPARISON_RECORD_KIND",
    "MEMORY_CONTEXT_LINEAGE_RECORD_KIND",
    "RECALL_RECEIPT_RECORD_KIND",
    "AgentMemoryContextBudgetError",
    "AgentMemoryInstructionIsolationError",
    "AgentMemoryRecallDenied",
    "AgentMemoryRecallError",
    "AgentMemoryRetrievalStateError",
    "AssembledContextBlock",
    "AuthorizedCandidateBodyReader",
    "CanonicalCandidateBodyReader",
    "CompositionContextManifestBridge",
    "ContextPlannerService",
    "InstructionMaterial",
    "InstructionPolicyResolutionPort",
    "InstructionResolutionOutcome",
    "PlannedContext",
    "RecordedContextUse",
    "RetrievalSignalPort",
    "RetrievalStateOwner",
    "SignalObservation",
    "StaticRetrievalStateOwner",
    "compare_matched_conditions",
]
