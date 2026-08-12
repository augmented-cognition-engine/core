"""Authorized AM2 extraction, reconciliation, temporal inspection, and graph projection.

The service is deliberately provider-neutral.  Adapters return inert structured
candidates; only this application boundary binds authenticated scope, source
envelopes, immutable identity, lifecycle, commit coordinates, and receipts.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any, Callable, Mapping, Protocol, Sequence, runtime_checkable

from ace.application.agent_memory_ingestion import (
    AgentMemoryApplicationError,
    AgentMemoryAuthorizationDenied,
    AgentMemoryAuthorizationResolver,
    AgentMemoryReplayConflict,
    AuthorizedAgentMemoryUse,
)
from ace.core.agent_memory import AgentMemoryScopeV1Alpha1, KnowledgeTimeKind, LedgerCoordinateV1Alpha1, WorldTimeKind
from ace.core.contracts import canonical_hash, stable_id
from ace.core.records import (
    AppendOnlyTransactionReceiptV1,
    AppendOnlyTransactionRequestV1,
    ImmutableRecordPersistenceError,
    ImmutableRecordReplayConflict,
    ImmutableRecordStore,
    ImmutableRecordV1,
)
from ace.core.runtime_use import AuthenticatedRuntimeContextV1Alpha1
from ace.core.state import (
    CoreAuthorityResolver,
    GovernedStateCommitRequestV1,
    GovernedStateRevisionV1,
    GovernedStateStore,
)
from ace.intelligence.contracts.agent_memory_assertions import (
    AssertionFamilyV1Alpha1,
    AssertionLifecycle,
    AssertionSourceEnvelopeV1Alpha1,
    EntityResolution,
    EvidenceStatus,
    GovernedEvidenceV1Alpha1,
    MemoryAssertionCandidateV1Alpha1,
    MemoryAssertionQueryReceiptV1Alpha1,
    MemoryAssertionQueryV1Alpha1,
    MemoryExtractionReceiptV1Alpha1,
    MemoryExtractionRequestV1Alpha1,
    MemoryGraphEdgeKind,
    MemoryGraphEdgeV1Alpha1,
    MemoryGraphNodeKind,
    MemoryGraphNodeV1Alpha1,
    MemoryGraphProjectionV1Alpha1,
    MemoryGraphQueryReceiptV1Alpha1,
    MemoryPromotionReceiptV1Alpha1,
    MemoryReconciliationDecisionV1Alpha1,
    MemoryReconciliationPolicyV1Alpha1,
    MemoryReconciliationReceiptV1Alpha1,
    ReconciliationDisposition,
    SemanticTargetV1Alpha1,
    SourceIndependence,
)

ASSERTION_DECISION_RECORD_KIND = "memory_assertion_decision"
EXTRACTION_RECEIPT_RECORD_KIND = "memory_extraction_receipt"
RECONCILIATION_RECEIPT_RECORD_KIND = "memory_reconciliation_receipt"
GRAPH_PROJECTION_RECORD_KIND = "memory_graph_projection"


class AgentMemoryAssertionError(AgentMemoryApplicationError):
    """A bounded AM2 operation failed closed."""


class AgentMemoryExtractionError(AgentMemoryAssertionError):
    """Provider or structured candidate failure produced no partial result."""


class AgentMemoryStaleProjection(AgentMemoryAssertionError):
    """A derived graph no longer binds the current immutable source snapshot."""


def _now() -> datetime:
    return datetime.now(UTC)


def _record_space(scope: AgentMemoryScopeV1Alpha1) -> str:
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


def _ledger_ref(scope: AgentMemoryScopeV1Alpha1) -> str:
    return stable_id("memory_assertion_ledger", {"scope_id": scope.scope_id})


def _transaction_key(request: MemoryExtractionRequestV1Alpha1) -> str:
    return stable_id(
        "memory_reconciliation_transaction",
        {"scope_id": request.scope.scope_id, "idempotency_ref": request.idempotency_ref},
    )


def _aware(value: datetime, *, name: str) -> datetime:
    if value.tzinfo is None or value.utcoffset() is None:
        raise AgentMemoryAssertionError(f"{name} must include a timezone")
    return value.astimezone(UTC)


def _reopen(model: Any, payload: Mapping[str, Any]) -> Any:
    try:
        return model.model_validate(payload, strict=False)
    except (TypeError, ValueError) as exc:
        raise AgentMemoryAssertionError("durable AM2 contract failed exact validation") from exc


@dataclass(frozen=True, slots=True)
class InertAssertionCandidate:
    """Adapter output with no identity, evidence, authority, lifecycle, or promotion fields."""

    source_index: int
    family: AssertionFamilyV1Alpha1
    predicate_ref: str
    statement: str
    entity_ref: str | None = None
    unresolved_entity_ref: str | None = None
    target_ref: str | None = None
    correction_target_ref: str | None = None
    proposed_confidence: float | None = None

    def __post_init__(self) -> None:
        if self.source_index < 0:
            raise ValueError("source_index must be non-negative")
        if not self.statement or len(self.statement) > 8_000 or self.statement != self.statement.strip():
            raise ValueError("statement must be bounded, non-empty, and trimmed")
        if (self.entity_ref is None) == (self.unresolved_entity_ref is None):
            raise ValueError("candidate requires exactly one resolved or unresolved entity coordinate")
        if self.proposed_confidence is not None and not 0 <= self.proposed_confidence <= 1:
            raise ValueError("proposed confidence must be between zero and one")
        if self.family is AssertionFamilyV1Alpha1.CORRECTION:
            if self.correction_target_ref is None:
                raise ValueError("correction candidate requires an exact target")
        elif self.correction_target_ref is not None:
            raise ValueError("only correction candidates may name a correction target")


@runtime_checkable
class AssertionExtractionAdapter(Protocol):
    adapter_ref: str
    adapter_version: str
    adapter_digest: str

    def extract(self, source_bodies: tuple[str, ...]) -> Sequence[InertAssertionCandidate]: ...


@runtime_checkable
class AuthorizedAssertionSourceReader(Protocol):
    """Private source-body channel invoked only after present-tense authorization."""

    async def read(self, *, source: AssertionSourceEnvelopeV1Alpha1) -> str: ...


@dataclass(frozen=True, slots=True)
class ExtractionPreview:
    candidates: tuple[MemoryAssertionCandidateV1Alpha1, ...]
    receipt: MemoryExtractionReceiptV1Alpha1


@dataclass(frozen=True, slots=True)
class ReconciliationAdmission:
    candidates: tuple[MemoryAssertionCandidateV1Alpha1, ...]
    extraction_receipt: MemoryExtractionReceiptV1Alpha1
    decisions: tuple[MemoryReconciliationDecisionV1Alpha1, ...]
    receipt: MemoryReconciliationReceiptV1Alpha1
    transaction_receipt: AppendOnlyTransactionReceiptV1
    replayed: bool


@dataclass(frozen=True, slots=True)
class AuthorizedAssertionInspection:
    decisions: tuple[MemoryReconciliationDecisionV1Alpha1, ...]
    receipt: MemoryAssertionQueryReceiptV1Alpha1


@dataclass(frozen=True, slots=True)
class AuthorizedGraphView:
    projection: MemoryGraphProjectionV1Alpha1
    receipt: MemoryGraphQueryReceiptV1Alpha1


@dataclass(frozen=True, slots=True)
class PromotionAdmission:
    receipt: MemoryPromotionReceiptV1Alpha1
    governed_receipt: Any


class DeterministicFixtureExtractionAdapter:
    """Provider-free exact adapter used by conformance fixtures and installed-wheel proof."""

    adapter_ref = "adapter:memory-assertion-deterministic-fixture"
    adapter_version = "1.0.0"
    adapter_digest = "sha256:" + "d" * 64

    def __init__(self, candidates: Sequence[InertAssertionCandidate]) -> None:
        self._candidates = tuple(candidates)

    def extract(self, source_bodies: tuple[str, ...]) -> Sequence[InertAssertionCandidate]:
        if not source_bodies or any(not isinstance(item, str) for item in source_bodies):
            raise ValueError("fixture adapter requires source bodies")
        return self._candidates


class _AuthorizedAssertionService:
    def __init__(
        self,
        *,
        store: ImmutableRecordStore,
        authorization: AgentMemoryAuthorizationResolver,
        clock: Callable[[], datetime] = _now,
    ) -> None:
        self.store = store
        self.authorization = authorization
        self.clock = clock

    async def _authorize(
        self,
        *,
        context: AuthenticatedRuntimeContextV1Alpha1,
        scope: AgentMemoryScopeV1Alpha1,
        operation: str,
        subject_ref: str,
    ) -> AuthorizedAgentMemoryUse:
        evaluated = _aware(self.clock(), name="service clock")
        try:
            use = await self.authorization.authorize(
                context=context,
                scope=scope,
                operation=operation,
                subject_ref=subject_ref,
                evaluated_at=evaluated,
            )
        except Exception as exc:
            raise AgentMemoryAuthorizationDenied() from exc
        if (
            use.product_id != scope.product_id
            or use.actor_id != scope.actor_id
            or use.operation != operation
            or use.subject_ref != subject_ref
            or use.authority_receipt_ref != scope.authority_receipt_ref
            or use.evaluated_at != evaluated
            or use.lifecycle_snapshot_ref == "lifecycle_snapshot:unspecified"
            or use.lifecycle_state.value != "active"
            or context.product_id != scope.product_id
            or context.actor_ref != scope.actor_id
            or not (context.authenticated_at <= evaluated < context.expires_at)
            or (use.expires_at is not None and use.expires_at <= evaluated)
        ):
            raise AgentMemoryAuthorizationDenied()
        return use

    async def _decisions(
        self,
        *,
        context: AuthenticatedRuntimeContextV1Alpha1,
        scope: AgentMemoryScopeV1Alpha1,
        operation: str,
        subject_ref: str,
        through: datetime,
    ) -> tuple[MemoryReconciliationDecisionV1Alpha1, ...]:
        await self._authorize(context=context, scope=scope, operation=operation, subject_ref=subject_ref)
        records = await self.store.read_as_of(
            product_id=scope.product_id,
            record_space=_record_space(scope),
            record_kind=ASSERTION_DECISION_RECORD_KIND,
            available_at=through,
        )
        result: list[MemoryReconciliationDecisionV1Alpha1] = []
        for record in records:
            await self._authorize(context=context, scope=scope, operation=operation, subject_ref=subject_ref)
            result.append(_reopen(MemoryReconciliationDecisionV1Alpha1, record.payload))
        return tuple(sorted(result, key=lambda item: item.ledger_coordinate.sequence))


class MemoryAssertionReconciliationService(_AuthorizedAssertionService):
    """One canonical provider-neutral path for every authorized source kind."""

    def __init__(
        self,
        *,
        store: ImmutableRecordStore,
        authorization: AgentMemoryAuthorizationResolver,
        source_reader: AuthorizedAssertionSourceReader,
        adapters: Sequence[AssertionExtractionAdapter],
        clock: Callable[[], datetime] = _now,
    ) -> None:
        super().__init__(store=store, authorization=authorization, clock=clock)
        self.source_reader = source_reader
        self.adapters = {(item.adapter_ref, item.adapter_version, item.adapter_digest): item for item in adapters}
        if len(self.adapters) != len(tuple(adapters)):
            raise ValueError("extraction adapter identities must be unique")

    def _adapter(self, request: MemoryExtractionRequestV1Alpha1) -> AssertionExtractionAdapter:
        try:
            return self.adapters[(request.adapter_ref, request.adapter_version, request.adapter_digest)]
        except KeyError as exc:
            raise AgentMemoryExtractionError("exact extraction adapter is unavailable") from exc

    async def preview(
        self,
        *,
        context: AuthenticatedRuntimeContextV1Alpha1,
        request: MemoryExtractionRequestV1Alpha1,
    ) -> ExtractionPreview:
        validated = MemoryExtractionRequestV1Alpha1.model_validate(request.model_dump(mode="python"))
        return await self._extract(context=context, request=validated, preview=True)

    async def _extract(
        self,
        *,
        context: AuthenticatedRuntimeContextV1Alpha1,
        request: MemoryExtractionRequestV1Alpha1,
        preview: bool,
    ) -> ExtractionPreview:
        use = await self._authorize(
            context=context,
            scope=request.scope,
            operation="preview_memory_assertions" if preview else "create_memory_assertion_proposals",
            subject_ref=str(request.request_id),
        )
        bodies: list[str] = []
        for source in request.source_envelopes:
            await self._authorize(
                context=context,
                scope=request.scope,
                operation="read_memory_source_body",
                subject_ref=str(source.envelope_id),
            )
            try:
                body = await self.source_reader.read(source=source)
            except Exception as exc:
                raise AgentMemoryExtractionError("authorized source body could not be read") from exc
            if not isinstance(body, str) or not body or len(body.encode("utf-8")) > 1_000_000:
                raise AgentMemoryExtractionError("authorized source body violated the bounded private channel")
            bodies.append(body)
        adapter = self._adapter(request)
        try:
            raw = tuple(adapter.extract(tuple(bodies)))
            if not raw or len(raw) > 200 or any(type(item) is not InertAssertionCandidate for item in raw):
                raise ValueError("adapter returned an invalid or empty candidate set")
            candidates = tuple(self._candidate(request=request, item=item) for item in raw)
        except Exception as exc:
            raise AgentMemoryExtractionError("structured extraction failed closed without partial candidates") from exc
        generated = _aware(self.clock(), name="service clock")
        receipt = MemoryExtractionReceiptV1Alpha1(
            request_id=str(request.request_id),
            request_digest=str(request.request_digest),
            preview=preview,
            authorization_receipt_ref=use.authority_receipt_ref,
            lifecycle_snapshot_ref=use.lifecycle_snapshot_ref,
            source_envelope_refs=tuple(str(item.envelope_id) for item in request.source_envelopes),
            candidate_refs=tuple(str(item.candidate_id) for item in candidates),
            candidate_digests=tuple(str(item.candidate_digest) for item in candidates),
            generated_at=generated,
        )
        return ExtractionPreview(candidates=candidates, receipt=receipt)

    def _candidate(
        self,
        *,
        request: MemoryExtractionRequestV1Alpha1,
        item: InertAssertionCandidate,
    ) -> MemoryAssertionCandidateV1Alpha1:
        try:
            source = request.source_envelopes[item.source_index]
        except IndexError as exc:
            raise ValueError("candidate source index is outside the authorized envelope set") from exc
        target = SemanticTargetV1Alpha1(
            entity_resolution=(
                EntityResolution.RESOLVED if item.entity_ref is not None else EntityResolution.UNRESOLVED
            ),
            entity_ref=item.entity_ref,
            unresolved_entity_ref=item.unresolved_entity_ref,
            predicate_ref=item.predicate_ref,
            target_ref=item.target_ref,
        )
        confidence = (
            GovernedEvidenceV1Alpha1(
                status=EvidenceStatus.KNOWN,
                value=item.proposed_confidence,
                policy_ref="policy:adapter-proposed-confidence-v1",
                evidence_receipt_ref=stable_id(
                    "memory_extraction_signal",
                    {
                        "adapter_digest": request.adapter_digest,
                        "source_envelope": source.envelope_id,
                        "statement_digest": f"sha256:{canonical_hash(item.statement)}",
                    },
                ),
            )
            if item.proposed_confidence is not None
            else GovernedEvidenceV1Alpha1(
                status=EvidenceStatus.UNKNOWN,
                unknown_reason_ref="reason:adapter-confidence-unavailable",
            )
        )
        return MemoryAssertionCandidateV1Alpha1(
            scope=request.scope,
            family=item.family,
            semantic_target=target,
            statement=item.statement,
            statement_digest=f"sha256:{canonical_hash(item.statement)}",
            source=source,
            knowledge_time=source.knowledge_time,
            knowledge_revision_at=source.knowledge_revision_at,
            world_time=source.world_time,
            confidence=confidence,
            correction_target_ref=item.correction_target_ref,
        )

    async def extract_and_reconcile(
        self,
        *,
        context: AuthenticatedRuntimeContextV1Alpha1,
        request: MemoryExtractionRequestV1Alpha1,
        policy: MemoryReconciliationPolicyV1Alpha1,
    ) -> ReconciliationAdmission:
        validated = MemoryExtractionRequestV1Alpha1.model_validate(request.model_dump(mode="python"))
        await self._authorize(
            context=context,
            scope=validated.scope,
            operation="reconcile_memory_assertions",
            subject_ref=validated.idempotency_ref,
        )
        replay = await self._load_replay(context=context, request=validated)
        if replay is not None:
            return replay
        preview = await self._extract(context=context, request=validated, preview=False)
        committed_at = _aware(self.clock(), name="service clock")
        prior = await self._decisions(
            context=context,
            scope=validated.scope,
            operation="reconcile_memory_assertions",
            subject_ref=validated.idempotency_ref,
            through=committed_at,
        )
        decisions = self._reconcile(
            candidates=preview.candidates,
            prior=prior,
            policy=policy,
            scope=validated.scope,
            committed_at=committed_at,
        )
        use = await self._authorize(
            context=context,
            scope=validated.scope,
            operation="reconcile_memory_assertions",
            subject_ref=validated.idempotency_ref,
        )
        receipt = MemoryReconciliationReceiptV1Alpha1(
            idempotency_ref=validated.idempotency_ref,
            request_digest=str(validated.request_digest),
            authorization_receipt_ref=use.authority_receipt_ref,
            lifecycle_snapshot_ref=use.lifecycle_snapshot_ref,
            extraction_receipt_ref=str(preview.receipt.receipt_id),
            decision_refs=tuple(str(item.decision_id) for item in decisions),
            decision_digests=tuple(str(item.decision_digest) for item in decisions),
            ledger_coordinates=tuple(item.ledger_coordinate for item in decisions),
            committed_at=committed_at,
        )
        records: list[ImmutableRecordV1] = []
        records.append(
            self._record(
                validated.scope,
                preview.receipt,
                EXTRACTION_RECEIPT_RECORD_KIND,
                str(preview.receipt.receipt_id),
                committed_at,
                len(records),
            )
        )
        base_sequence = len(prior)
        for offset, decision in enumerate(decisions, start=1):
            records.append(
                self._record(
                    validated.scope,
                    decision,
                    ASSERTION_DECISION_RECORD_KIND,
                    stable_id(
                        "memory_assertion_decision_slot",
                        {"scope_id": validated.scope.scope_id, "sequence": base_sequence + offset},
                    ),
                    committed_at,
                    len(records),
                )
            )
        records.append(
            self._record(
                validated.scope,
                receipt,
                RECONCILIATION_RECEIPT_RECORD_KIND,
                str(receipt.receipt_id),
                committed_at,
                len(records),
            )
        )
        request_tx = AppendOnlyTransactionRequestV1(
            product_id=validated.scope.product_id,
            record_space=_record_space(validated.scope),
            transaction_key=_transaction_key(validated),
            records=tuple(records),
            submitted_at=committed_at,
            governed_state_preconditions=(
                (use.state_head_precondition,) if use.state_head_precondition is not None else ()
            ),
        )
        try:
            tx = await self.store.append(request_tx)
        except ImmutableRecordReplayConflict as exc:
            recovered = await self._load_replay(context=context, request=validated)
            if recovered is not None:
                return recovered
            raise AgentMemoryReplayConflict("concurrent reconciliation lost exact CAS or divergent replay") from exc
        except ImmutableRecordPersistenceError:
            recovered = await self._load_replay(context=context, request=validated)
            if recovered is not None:
                return recovered
            raise
        return ReconciliationAdmission(preview.candidates, preview.receipt, decisions, receipt, tx, False)

    @staticmethod
    def _record(
        scope: AgentMemoryScopeV1Alpha1,
        payload: Any,
        kind: str,
        key: str,
        when: datetime,
        order: int,
    ) -> ImmutableRecordV1:
        return ImmutableRecordV1(
            product_id=scope.product_id,
            record_space=_record_space(scope),
            record_kind=kind,
            record_key=key,
            payload_contract=payload.contract,
            payload=payload.model_dump(mode="python"),
            as_of=when,
            available_at=when,
            processing_order=order,
        )

    def _reconcile(
        self,
        *,
        candidates: tuple[MemoryAssertionCandidateV1Alpha1, ...],
        prior: tuple[MemoryReconciliationDecisionV1Alpha1, ...],
        policy: MemoryReconciliationPolicyV1Alpha1,
        scope: AgentMemoryScopeV1Alpha1,
        committed_at: datetime,
    ) -> tuple[MemoryReconciliationDecisionV1Alpha1, ...]:
        decisions: list[MemoryReconciliationDecisionV1Alpha1] = []
        all_prior = list(prior)
        for candidate in candidates:
            same_target = [
                item
                for item in all_prior
                if item.candidate.semantic_target.coordinate_id == candidate.semantic_target.coordinate_id
            ]
            exact = [item for item in same_target if item.candidate.candidate_id == candidate.candidate_id]
            same_source = [
                item for item in same_target if item.candidate.source.source_id == candidate.source.source_id
            ]
            agrees = [
                item
                for item in same_target
                if item.candidate.statement_digest == candidate.statement_digest
                and item.candidate.source.source_id != candidate.source.source_id
                and self._independent(item.candidate.source, candidate.source)
            ]
            conflicts = [
                item
                for item in same_target
                if item.candidate.statement_digest != candidate.statement_digest
                and item.candidate.source.source_id != candidate.source.source_id
                and self._independent(item.candidate.source, candidate.source)
            ]
            syndicated_duplicates = [
                item
                for item in same_target
                if item.candidate.statement_digest == candidate.statement_digest
                and item.candidate.source.source_id != candidate.source.source_id
                and (
                    candidate.source.origin_ref == item.candidate.source.source_id
                    or item.candidate.source.origin_ref == candidate.source.source_id
                    or (
                        candidate.source.origin_ref is not None
                        and candidate.source.origin_ref == item.candidate.source.origin_ref
                    )
                )
            ]
            duplicate_of: tuple[str, ...] = ()
            supersedes: tuple[str, ...] = ()
            agrees_with: tuple[str, ...] = ()
            conflicts_with: tuple[str, ...] = ()
            uncertainty_ref: str | None = None
            lifecycle = AssertionLifecycle.PROPOSED
            if exact:
                disposition = ReconciliationDisposition.EXACT_DUPLICATE
                duplicate_of = tuple(str(item.candidate.candidate_id) for item in exact)
            elif syndicated_duplicates:
                disposition = ReconciliationDisposition.EXACT_DUPLICATE
                duplicate_of = tuple(str(item.candidate.candidate_id) for item in syndicated_duplicates)
            elif candidate.family is AssertionFamilyV1Alpha1.INSTRUCTION_POLICY_PROPOSAL:
                disposition = ReconciliationDisposition.INSTRUCTION_ISOLATED
            elif candidate.family is AssertionFamilyV1Alpha1.CORRECTION:
                disposition = ReconciliationDisposition.CORRECTION_PROPOSAL
            elif candidate.semantic_target.entity_resolution is EntityResolution.UNRESOLVED:
                disposition = ReconciliationDisposition.UNRESOLVED_IDENTITY
                lifecycle = AssertionLifecycle.UNCERTAINTY
                uncertainty_ref = self._uncertainty(candidate, (), "unresolved_identity")
            elif self._insufficient(candidate, policy):
                disposition = ReconciliationDisposition.INSUFFICIENT_EVIDENCE
                lifecycle = AssertionLifecycle.UNCERTAINTY
                uncertainty_ref = self._uncertainty(candidate, (), "insufficient_evidence")
            elif same_source:
                latest = max(same_source, key=lambda item: item.ledger_coordinate.sequence)
                if latest.candidate.statement_digest == candidate.statement_digest:
                    disposition = ReconciliationDisposition.EXACT_DUPLICATE
                    duplicate_of = (str(latest.candidate.candidate_id),)
                else:
                    disposition = ReconciliationDisposition.SAME_SOURCE_UPDATE
                    supersedes = (str(latest.candidate.candidate_id),)
            elif conflicts:
                disposition = ReconciliationDisposition.CROSS_SOURCE_DISAGREEMENT
                lifecycle = AssertionLifecycle.UNCERTAINTY
                conflicts_with = tuple(str(item.candidate.candidate_id) for item in conflicts)
                uncertainty_ref = self._uncertainty(candidate, conflicts_with, "cross_source_disagreement")
            elif agrees:
                disposition = ReconciliationDisposition.CROSS_SOURCE_AGREEMENT
                agrees_with = tuple(str(item.candidate.candidate_id) for item in agrees)
            else:
                disposition = ReconciliationDisposition.NEW_PROPOSAL
            evidence = tuple(
                sorted(
                    {
                        str(candidate.source.envelope_id),
                        candidate.source.acquisition_receipt_ref,
                        *duplicate_of,
                        *supersedes,
                        *agrees_with,
                        *conflicts_with,
                    }
                )
            )
            material = {
                "contract": "ace.intelligence.memory-reconciliation-decision/v1alpha1",
                "candidate": candidate.model_dump(mode="json"),
                "disposition": disposition,
                "lifecycle": lifecycle,
                "duplicate_of": duplicate_of,
                "supersedes": supersedes,
                "agrees_with": agrees_with,
                "conflicts_with": conflicts_with,
                "uncertainty_ref": uncertainty_ref,
                "policy_ref": policy.policy_ref,
                "policy_version": policy.policy_version,
                "evidence_refs": evidence,
                "decided_at": committed_at.isoformat().replace("+00:00", "Z"),
            }
            decision_ref = f"memory_reconciliation_decision:{canonical_hash(material)[:32]}"
            coordinate = LedgerCoordinateV1Alpha1(
                ledger_ref=_ledger_ref(scope),
                sequence=len(prior) + len(decisions) + 1,
                event_ref=decision_ref,
                committed_at=committed_at,
            )
            decision = MemoryReconciliationDecisionV1Alpha1(
                candidate=candidate,
                disposition=disposition,
                lifecycle=lifecycle,
                duplicate_of=duplicate_of,
                supersedes=supersedes,
                agrees_with=agrees_with,
                conflicts_with=conflicts_with,
                uncertainty_ref=uncertainty_ref,
                policy_ref=policy.policy_ref,
                policy_version=policy.policy_version,
                evidence_refs=evidence,
                ledger_coordinate=coordinate,
                decided_at=committed_at,
            )
            decisions.append(decision)
            all_prior.append(decision)
        return tuple(decisions)

    @staticmethod
    def _independent(first: AssertionSourceEnvelopeV1Alpha1, second: AssertionSourceEnvelopeV1Alpha1) -> bool:
        if (
            first.independence is not SourceIndependence.INDEPENDENT
            or second.independence is not SourceIndependence.INDEPENDENT
        ):
            return False
        return first.source_id != second.source_id

    @staticmethod
    def _insufficient(candidate: MemoryAssertionCandidateV1Alpha1, policy: MemoryReconciliationPolicyV1Alpha1) -> bool:
        if candidate.confidence.status is EvidenceStatus.UNKNOWN:
            return True
        if candidate.confidence.value is None or candidate.confidence.value < policy.minimum_confidence:
            return True
        if policy.require_known_reliability and candidate.source.reliability.status is EvidenceStatus.UNKNOWN:
            return True
        if policy.require_known_freshness and candidate.source.freshness.status is EvidenceStatus.UNKNOWN:
            return True
        if candidate.source.independence is SourceIndependence.UNKNOWN:
            return True
        return policy.require_known_world_time and candidate.world_time.kind is WorldTimeKind.UNKNOWN

    @staticmethod
    def _uncertainty(candidate: MemoryAssertionCandidateV1Alpha1, conflicts: tuple[str, ...], reason: str) -> str:
        return stable_id(
            "memory_uncertainty",
            {"candidate_ref": candidate.candidate_id, "conflicts": conflicts, "reason": reason},
        )

    async def _load_replay(
        self,
        *,
        context: AuthenticatedRuntimeContextV1Alpha1,
        request: MemoryExtractionRequestV1Alpha1,
    ) -> ReconciliationAdmission | None:
        await self._authorize(
            context=context,
            scope=request.scope,
            operation="reconcile_memory_assertions",
            subject_ref=request.idempotency_ref,
        )
        tx = await self.store.load_transaction_receipt(
            product_id=request.scope.product_id,
            record_space=_record_space(request.scope),
            transaction_key=_transaction_key(request),
        )
        if tx is None:
            return None
        extraction: MemoryExtractionReceiptV1Alpha1 | None = None
        receipt: MemoryReconciliationReceiptV1Alpha1 | None = None
        decisions: list[MemoryReconciliationDecisionV1Alpha1] = []
        for reference in tx.records:
            await self._authorize(
                context=context,
                scope=request.scope,
                operation="reconcile_memory_assertions",
                subject_ref=request.idempotency_ref,
            )
            stored = await self.store.load_record(
                reference.storage_id,
                product_id=request.scope.product_id,
                record_space=_record_space(request.scope),
                record_kind=reference.record_kind,
            )
            if stored is None or stored.reference() != reference:
                raise AgentMemoryAssertionError("durable reconciliation transaction is incomplete")
            if stored.record_kind == EXTRACTION_RECEIPT_RECORD_KIND:
                extraction = _reopen(MemoryExtractionReceiptV1Alpha1, stored.payload)
            elif stored.record_kind == ASSERTION_DECISION_RECORD_KIND:
                decisions.append(_reopen(MemoryReconciliationDecisionV1Alpha1, stored.payload))
            elif stored.record_kind == RECONCILIATION_RECEIPT_RECORD_KIND:
                receipt = _reopen(MemoryReconciliationReceiptV1Alpha1, stored.payload)
        if extraction is None or receipt is None or not decisions:
            raise AgentMemoryAssertionError("durable reconciliation lost exact records")
        if receipt.request_digest != request.request_digest:
            raise AgentMemoryReplayConflict("idempotency coordinate binds divergent extraction material")
        decisions.sort(key=lambda item: item.ledger_coordinate.sequence)
        candidates = tuple(item.candidate for item in decisions)
        return ReconciliationAdmission(candidates, extraction, tuple(decisions), receipt, tx, True)


class MemoryAssertionInspectionService(_AuthorizedAssertionService):
    """Present-tense authorized assertion inspection with independent clocks."""

    async def inspect(
        self,
        *,
        context: AuthenticatedRuntimeContextV1Alpha1,
        query: MemoryAssertionQueryV1Alpha1,
    ) -> AuthorizedAssertionInspection:
        validated = MemoryAssertionQueryV1Alpha1.model_validate(query.model_dump(mode="python"))
        use = await self._authorize(
            context=context,
            scope=validated.scope,
            operation="inspect_memory_assertions",
            subject_ref=str(validated.query_id),
        )
        decisions = await self._decisions(
            context=context,
            scope=validated.scope,
            operation="inspect_memory_assertions",
            subject_ref=str(validated.query_id),
            through=use.evaluated_at,
        )
        selected = [item for item in decisions if self._matches(item, validated)]
        if not validated.include_superseded:
            superseded = {ref for item in decisions for ref in item.supersedes}
            selected = [item for item in selected if item.candidate.candidate_id not in superseded]
        total = len(selected)
        selected = selected[: validated.limit]
        receipt = MemoryAssertionQueryReceiptV1Alpha1(
            query_id=str(validated.query_id),
            authorization_receipt_ref=use.authority_receipt_ref,
            lifecycle_snapshot_ref=use.lifecycle_snapshot_ref,
            assertion_refs=tuple(str(item.candidate.candidate_id) for item in selected),
            decision_refs=tuple(str(item.decision_id) for item in selected),
            omitted_count=max(0, total - len(selected)),
            generated_at=use.evaluated_at,
        )
        return AuthorizedAssertionInspection(tuple(selected), receipt)

    @staticmethod
    def _matches(decision: MemoryReconciliationDecisionV1Alpha1, query: MemoryAssertionQueryV1Alpha1) -> bool:
        candidate = decision.candidate
        temporal = query.temporal
        if (
            query.semantic_target_ref is not None
            and candidate.semantic_target.coordinate_id != query.semantic_target_ref
        ):
            return False
        if query.assertion_refs and candidate.candidate_id not in query.assertion_refs:
            return False
        if temporal.ledger_at is not None:
            if decision.ledger_coordinate.ledger_ref != temporal.ledger_at.ledger_ref:
                return False
            if decision.ledger_coordinate.sequence > temporal.ledger_at.sequence:
                return False
        if temporal.knowledge_at is not None:
            if candidate.knowledge_time.kind is KnowledgeTimeKind.UNKNOWN:
                if not temporal.include_unknown_knowledge:
                    return False
            elif (
                candidate.knowledge_time.first_known_at is None
                or candidate.knowledge_time.first_known_at > temporal.knowledge_at
                or candidate.knowledge_revision_at > temporal.knowledge_at
            ):
                return False
        if temporal.world_at is not None:
            world = candidate.world_time
            if world.kind is WorldTimeKind.UNKNOWN:
                if not temporal.include_unknown_world:
                    return False
            elif world.kind is WorldTimeKind.INSTANT and world.occurred_at is not None:
                if world.occurred_at > temporal.world_at:
                    return False
            elif world.kind in {WorldTimeKind.INTERVAL, WorldTimeKind.RECURRING}:
                if world.valid_from is not None and temporal.world_at < world.valid_from:
                    return False
                if world.valid_to is not None and temporal.world_at > world.valid_to:
                    return False
        return True


class MemoryGraphProjectionService(_AuthorizedAssertionService):
    """Rebuild and query identifiers-only projections with stale-cache refusal."""

    async def rebuild(
        self,
        *,
        context: AuthenticatedRuntimeContextV1Alpha1,
        scope: AgentMemoryScopeV1Alpha1,
        external_nodes: tuple[MemoryGraphNodeV1Alpha1, ...] = (),
        external_edges: tuple[MemoryGraphEdgeV1Alpha1, ...] = (),
    ) -> MemoryGraphProjectionV1Alpha1:
        use = await self._authorize(
            context=context, scope=scope, operation="rebuild_memory_graph", subject_ref=str(scope.scope_id)
        )
        decisions = await self._decisions(
            context=context,
            scope=scope,
            operation="rebuild_memory_graph",
            subject_ref=str(scope.scope_id),
            through=use.evaluated_at,
        )
        snapshot = self._snapshot(decisions)
        nodes: dict[str, MemoryGraphNodeV1Alpha1] = {item.ref: item for item in external_nodes}
        edges: set[tuple[MemoryGraphEdgeKind, str, str]] = {
            (item.kind, item.from_ref, item.to_ref) for item in external_edges
        }
        for decision in decisions:
            candidate = decision.candidate
            source = candidate.source
            self._node(nodes, MemoryGraphNodeKind.SOURCE, source.source_id, source.contract, source.envelope_digest)
            self._node(
                nodes,
                MemoryGraphNodeKind.ASSERTION,
                str(candidate.candidate_id),
                candidate.contract,
                candidate.candidate_digest,
            )
            self._node(
                nodes,
                MemoryGraphNodeKind.DECISION,
                str(decision.decision_id),
                decision.contract,
                decision.decision_digest,
            )
            entity = candidate.semantic_target.entity_ref or candidate.semantic_target.unresolved_entity_ref
            assert entity is not None
            self._node(nodes, MemoryGraphNodeKind.ENTITY, entity)
            edges.add((MemoryGraphEdgeKind.GROUNDED_IN, str(candidate.candidate_id), source.source_id))
            edges.add((MemoryGraphEdgeKind.TARGETS, str(candidate.candidate_id), entity))
            if source.session_ref is not None:
                self._node(nodes, MemoryGraphNodeKind.SESSION, source.session_ref)
                edges.add((MemoryGraphEdgeKind.OCCURRED_IN, source.source_id, source.session_ref))
            if source.turn_ref is not None:
                self._node(nodes, MemoryGraphNodeKind.TURN, source.turn_ref)
                edges.add((MemoryGraphEdgeKind.OCCURRED_IN, source.turn_ref, str(source.session_ref)))
            if source.event_ref is not None:
                self._node(nodes, MemoryGraphNodeKind.EVENT, source.event_ref)
                edges.add((MemoryGraphEdgeKind.OCCURRED_IN, source.event_ref, str(source.session_ref)))
            for ref in decision.supersedes:
                self._node(nodes, MemoryGraphNodeKind.ASSERTION, ref)
                edges.add((MemoryGraphEdgeKind.SUPERSEDES, str(candidate.candidate_id), ref))
            for ref in decision.agrees_with:
                self._node(nodes, MemoryGraphNodeKind.ASSERTION, ref)
                edges.add((MemoryGraphEdgeKind.AGREES_WITH, str(candidate.candidate_id), ref))
            for ref in decision.conflicts_with:
                self._node(nodes, MemoryGraphNodeKind.ASSERTION, ref)
                edges.add((MemoryGraphEdgeKind.CONFLICTS_WITH, str(candidate.candidate_id), ref))
            if candidate.family is AssertionFamilyV1Alpha1.CORRECTION:
                self._node(
                    nodes,
                    MemoryGraphNodeKind.CORRECTION,
                    str(candidate.candidate_id),
                    candidate.contract,
                    candidate.candidate_digest,
                )
                assert candidate.correction_target_ref is not None
                self._node(nodes, MemoryGraphNodeKind.ASSERTION, candidate.correction_target_ref)
                edges.add((MemoryGraphEdgeKind.CORRECTS, str(candidate.candidate_id), candidate.correction_target_ref))
            if decision.uncertainty_ref is not None:
                self._node(nodes, MemoryGraphNodeKind.UNCERTAINTY, decision.uncertainty_ref)
                edges.add((MemoryGraphEdgeKind.TARGETS, decision.uncertainty_ref, str(candidate.candidate_id)))
        projection = MemoryGraphProjectionV1Alpha1(
            scope_id=str(scope.scope_id),
            source_snapshot_digest=snapshot,
            nodes=tuple(nodes.values()),
            edges=tuple(MemoryGraphEdgeV1Alpha1(kind=kind, from_ref=left, to_ref=right) for kind, left, right in edges),
            rebuilt_at=use.evaluated_at,
        )
        record = ImmutableRecordV1(
            product_id=scope.product_id,
            record_space=_record_space(scope),
            record_kind=GRAPH_PROJECTION_RECORD_KIND,
            record_key=str(projection.projection_id),
            payload_contract=projection.contract,
            payload=projection.model_dump(mode="python"),
            as_of=use.evaluated_at,
            available_at=use.evaluated_at,
            processing_order=0,
        )
        tx = AppendOnlyTransactionRequestV1(
            product_id=scope.product_id,
            record_space=_record_space(scope),
            transaction_key=stable_id("memory_graph_rebuild", {"projection_id": projection.projection_id}),
            records=(record,),
            submitted_at=use.evaluated_at,
            governed_state_preconditions=(
                (use.state_head_precondition,) if use.state_head_precondition is not None else ()
            ),
        )
        await self.store.append(tx)
        return projection

    async def query(
        self,
        *,
        context: AuthenticatedRuntimeContextV1Alpha1,
        scope: AgentMemoryScopeV1Alpha1,
    ) -> AuthorizedGraphView:
        use = await self._authorize(
            context=context, scope=scope, operation="query_memory_graph", subject_ref=str(scope.scope_id)
        )
        decisions = await self._decisions(
            context=context,
            scope=scope,
            operation="query_memory_graph",
            subject_ref=str(scope.scope_id),
            through=use.evaluated_at,
        )
        records = await self.store.read_as_of(
            product_id=scope.product_id,
            record_space=_record_space(scope),
            record_kind=GRAPH_PROJECTION_RECORD_KIND,
            available_at=use.evaluated_at,
        )
        if not records:
            raise AgentMemoryStaleProjection("graph projection is missing")
        projection = _reopen(MemoryGraphProjectionV1Alpha1, records[-1].payload)
        snapshot = self._snapshot(decisions)
        if projection.source_snapshot_digest != snapshot:
            raise AgentMemoryStaleProjection("graph projection is stale")
        receipt = MemoryGraphQueryReceiptV1Alpha1(
            projection_ref=str(projection.projection_id),
            source_snapshot_digest=snapshot,
            authorization_receipt_ref=use.authority_receipt_ref,
            lifecycle_snapshot_ref=use.lifecycle_snapshot_ref,
            node_refs=tuple(item.ref for item in projection.nodes),
            edge_count=len(projection.edges),
            generated_at=use.evaluated_at,
        )
        return AuthorizedGraphView(projection, receipt)

    @staticmethod
    def _snapshot(decisions: tuple[MemoryReconciliationDecisionV1Alpha1, ...]) -> str:
        return f"sha256:{canonical_hash(tuple((item.decision_id, item.decision_digest) for item in decisions))}"

    @staticmethod
    def _node(
        nodes: dict[str, MemoryGraphNodeV1Alpha1],
        kind: MemoryGraphNodeKind,
        ref: str,
        contract_ref: str | None = None,
        digest: str | None = None,
    ) -> None:
        node = MemoryGraphNodeV1Alpha1(kind=kind, ref=ref, contract_ref=contract_ref, digest=digest)
        existing = nodes.get(ref)
        if existing is None:
            nodes[ref] = node
            return
        if existing.kind is not kind:
            raise AgentMemoryAssertionError("graph coordinate has conflicting typed identities")
        if existing.contract_ref is not None and contract_ref is not None and existing.contract_ref != contract_ref:
            raise AgentMemoryAssertionError("graph coordinate has conflicting contract identities")
        if existing.digest is not None and digest is not None and existing.digest != digest:
            raise AgentMemoryAssertionError("graph coordinate has conflicting material digests")
        nodes[ref] = MemoryGraphNodeV1Alpha1(
            kind=kind,
            ref=ref,
            contract_ref=existing.contract_ref or contract_ref,
            digest=existing.digest or digest,
        )


class MemoryGovernedPromotionService(_AuthorizedAssertionService):
    """Exact correction or instruction-policy admission through existing Core governance."""

    def __init__(
        self,
        *,
        store: ImmutableRecordStore,
        authorization: AgentMemoryAuthorizationResolver,
        authority: CoreAuthorityResolver,
        governed_state: GovernedStateStore,
        clock: Callable[[], datetime] = _now,
    ) -> None:
        super().__init__(store=store, authorization=authorization, clock=clock)
        self.authority = authority
        self.governed_state = governed_state

    async def admit(
        self,
        *,
        context: AuthenticatedRuntimeContextV1Alpha1,
        candidate: MemoryAssertionCandidateV1Alpha1,
        approval_receipt_ref: str,
        grant_ref: str,
    ) -> PromotionAdmission:
        if candidate.family is AssertionFamilyV1Alpha1.CORRECTION:
            kind = "correction"
            operation = "promote_memory_correction"
            authority_name = "memory_correction_admit"
            target = candidate.correction_target_ref
        elif candidate.family is AssertionFamilyV1Alpha1.INSTRUCTION_POLICY_PROPOSAL:
            kind = "instruction_policy"
            operation = "promote_memory_instruction_policy"
            authority_name = "memory_instruction_policy_admit"
            target = candidate.semantic_target.coordinate_id
        else:
            raise AgentMemoryAssertionError("ordinary assertions cannot enter governed policy admission")
        assert target is not None
        when = _aware(self.clock(), name="service clock")
        await self._authorize(
            context=context,
            scope=candidate.scope,
            operation=operation,
            subject_ref=str(candidate.candidate_id),
        )
        decisions = await self._decisions(
            context=context,
            scope=candidate.scope,
            operation=operation,
            subject_ref=str(candidate.candidate_id),
            through=when,
        )
        matching = [item for item in decisions if item.candidate == candidate]
        if not matching:
            raise AgentMemoryAuthorizationDenied()
        if kind == "correction" and not any(item.candidate.candidate_id == target for item in decisions):
            raise AgentMemoryAuthorizationDenied()
        try:
            approval = await self.authority.resolve_approval(
                receipt_ref=approval_receipt_ref,
                product_id=candidate.scope.product_id,
                subject_ref=str(candidate.candidate_id),
                actor_ref=context.actor_ref,
                effective_at=when,
            )
            grant = await self.authority.resolve_grant(
                grant_ref=grant_ref,
                product_id=candidate.scope.product_id,
                authority=authority_name,
                effective_at=when,
            )
        except Exception as exc:
            raise AgentMemoryAuthorizationDenied() from exc
        if (
            approval.subject_ref != candidate.candidate_id
            or approval.product_id != candidate.scope.product_id
            or approval.actor_ref != context.actor_ref
            or grant.product_id != candidate.scope.product_id
            or grant.authority != authority_name
            or grant.effective_at > when
            or (grant.expires_at is not None and grant.expires_at <= when)
        ):
            raise AgentMemoryAuthorizationDenied()
        state_kind = f"agent_memory_{kind}"
        state_id = str(candidate.semantic_target.coordinate_id)
        head = await self.governed_state.load_head(
            state_kind=state_kind,
            product_id=candidate.scope.product_id,
            state_id=state_id,
        )
        sequence = 1 if head is None else head.sequence + 1
        prior = None if head is None else head.revision_id
        payload = {
            "assertion_ref": candidate.candidate_id,
            "assertion_digest": candidate.candidate_digest,
            "family": candidate.family,
            "semantic_target_ref": candidate.semantic_target.coordinate_id,
            "correction_target_ref": candidate.correction_target_ref,
            "source_envelope_ref": candidate.source.envelope_id,
        }
        material_hash = canonical_hash(payload)
        revision = GovernedStateRevisionV1(
            state_kind=state_kind,
            product_id=candidate.scope.product_id,
            state_id=state_id,
            sequence=sequence,
            revision_id=stable_id(
                "memory_governed_revision",
                {"state_kind": state_kind, "state_id": state_id, "sequence": sequence, "material_hash": material_hash},
            ),
            material_hash=material_hash,
            prior_revision_id=prior,
            approval_subject_ref=str(candidate.candidate_id),
            payload_contract="ace.intelligence.memory-governed-admission/v1alpha1",
            payload=payload,
        )
        await self._authorize(
            context=context,
            scope=candidate.scope,
            operation=operation,
            subject_ref=str(candidate.candidate_id),
        )
        governed_receipt = await self.governed_state.commit(
            GovernedStateCommitRequestV1(
                revision=revision,
                expected_head_revision_id=prior,
                actor_ref=context.actor_ref,
                approval=approval,
                authority_grants=(grant,),
                committed_at=when,
            )
        )
        receipt = MemoryPromotionReceiptV1Alpha1(
            assertion_ref=str(candidate.candidate_id),
            assertion_digest=str(candidate.candidate_digest),
            target_ref=str(target),
            promotion_kind=kind,
            governed_state_receipt_ref=str(governed_receipt.receipt_id),
            governed_state_receipt_hash=str(governed_receipt.receipt_hash),
            promoted_at=when,
        )
        return PromotionAdmission(receipt, governed_receipt)

    async def current_assertion_ref(
        self,
        *,
        context: AuthenticatedRuntimeContextV1Alpha1,
        scope: AgentMemoryScopeV1Alpha1,
        semantic_target_ref: str,
        promotion_kind: str,
    ) -> str | None:
        """Return only a successfully governed current assertion coordinate."""

        if promotion_kind not in {"correction", "instruction_policy"}:
            raise AgentMemoryAssertionError("unsupported governed memory kind")
        await self._authorize(
            context=context,
            scope=scope,
            operation="inspect_governed_memory_state",
            subject_ref=semantic_target_ref,
        )
        head = await self.governed_state.load_head(
            state_kind=f"agent_memory_{promotion_kind}",
            product_id=scope.product_id,
            state_id=semantic_target_ref,
        )
        if head is None:
            return None
        await self._authorize(
            context=context,
            scope=scope,
            operation="inspect_governed_memory_state",
            subject_ref=semantic_target_ref,
        )
        revision = await self.governed_state.load_revision(head.revision_id, product_id=scope.product_id)
        if revision is None or revision.state_id != semantic_target_ref:
            raise AgentMemoryAuthorizationDenied()
        assertion_ref = revision.payload.get("assertion_ref")
        if not isinstance(assertion_ref, str):
            raise AgentMemoryAuthorizationDenied()
        return assertion_ref


__all__ = [
    "ASSERTION_DECISION_RECORD_KIND",
    "EXTRACTION_RECEIPT_RECORD_KIND",
    "GRAPH_PROJECTION_RECORD_KIND",
    "RECONCILIATION_RECEIPT_RECORD_KIND",
    "AgentMemoryAssertionError",
    "AgentMemoryExtractionError",
    "AgentMemoryStaleProjection",
    "AssertionExtractionAdapter",
    "AuthorizedAssertionInspection",
    "AuthorizedAssertionSourceReader",
    "AuthorizedGraphView",
    "DeterministicFixtureExtractionAdapter",
    "ExtractionPreview",
    "InertAssertionCandidate",
    "MemoryAssertionInspectionService",
    "MemoryAssertionReconciliationService",
    "MemoryGovernedPromotionService",
    "MemoryGraphProjectionService",
    "PromotionAdmission",
    "ReconciliationAdmission",
]
