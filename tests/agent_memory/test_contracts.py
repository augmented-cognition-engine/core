from __future__ import annotations

import json
from datetime import UTC, datetime, timedelta

import pytest
from pydantic import ValidationError

from ace.core.agent_memory import (
    AgentMemoryScopeV1Alpha1,
    ByteRangeSpanV1Alpha1,
    ErasureDependencyProofV1Alpha1,
    KnowledgeTimeKind,
    KnowledgeTimeV1Alpha1,
    LedgerCoordinateV1Alpha1,
    LifecycleEventV1Alpha1,
    LifecycleOperation,
    LifecycleState,
    MemoryVisibility,
    RetentionClass,
    SourceProvenanceV1Alpha1,
    TemporalQueryV1Alpha1,
    UnavailableSourceSpanV1Alpha1,
    UnavailableSpanReason,
    WorldTimeKind,
    WorldTimeV1Alpha1,
)
from ace.core.state import ResolvedApprovalReceiptV1, ResolvedAuthorityGrantV1
from ace.intelligence.contracts.agent_memory import (
    AgentMemoryQueryV1Alpha1,
    AssertionAuthorityV1Alpha1,
    AssertionOriginKind,
    CandidateReceiptV1Alpha1,
    CandidateRecordV1Alpha1,
    CandidateSignalContributionV1Alpha1,
    MemoryAssertionV1Alpha1,
    MemoryContextLineageV1Alpha1,
    MemoryEpistemicState,
    MemoryEvolutionKind,
    MemoryEvolutionProposalV1Alpha1,
    MemorySemanticFamily,
    ReconciliationProposalV1Alpha1,
)

pytestmark = pytest.mark.unit

NOW = datetime(2026, 8, 11, 18, 0, tzinfo=UTC)
PRODUCT = "product:agent-memory-tests"


def _scope(*, product_id: str = PRODUCT, source_id: str | None = "source:session-1") -> AgentMemoryScopeV1Alpha1:
    return AgentMemoryScopeV1Alpha1(
        product_id=product_id,
        actor_id="principal:user-1",
        session_id="session:1",
        source_id=source_id,
        visibility=MemoryVisibility.PRIVATE,
        retention_class=RetentionClass.STANDARD,
        authority_receipt_ref="authority_receipt:scope-1",
    )


def _known_time() -> KnowledgeTimeV1Alpha1:
    return KnowledgeTimeV1Alpha1(
        kind=KnowledgeTimeKind.KNOWN,
        first_known_at=NOW,
        basis_refs=("source:session-1",),
    )


def _world_time() -> WorldTimeV1Alpha1:
    return WorldTimeV1Alpha1(kind=WorldTimeKind.INSTANT, occurred_at=NOW - timedelta(minutes=1))


def _ledger_coordinate(*, sequence: int = 1) -> LedgerCoordinateV1Alpha1:
    return LedgerCoordinateV1Alpha1(
        ledger_ref="agent_memory_ledger:test",
        sequence=sequence,
        event_ref=f"agent_memory_lifecycle:event-{sequence}",
        committed_at=NOW - timedelta(minutes=2),
    )


def _provenance(*, source_id: str = "source:session-1", start: int = 0) -> SourceProvenanceV1Alpha1:
    return SourceProvenanceV1Alpha1(
        source_id=source_id,
        source_version_id="source_version:session-1-v1",
        content_digest="sha256:" + "a" * 64,
        span=ByteRangeSpanV1Alpha1(
            source_version_id="source_version:session-1-v1",
            start_byte=start,
            end_byte=start + 10,
        ),
        acquisition_receipt_ref="receipt:session-1",
        capture_method_ref="session.adapter",
    )


def _authority(*, accepted: bool = False, product_id: str = PRODUCT) -> AssertionAuthorityV1Alpha1:
    if not accepted:
        return AssertionAuthorityV1Alpha1(
            origin_kind=AssertionOriginKind.MODEL_PROPOSAL,
            actor_ref="agent:extractor",
        )
    return AssertionAuthorityV1Alpha1(
        origin_kind=AssertionOriginKind.MODEL_PROPOSAL,
        actor_ref="agent:extractor",
        resolved_grant=ResolvedAuthorityGrantV1(
            grant_ref="grant:memory-review",
            product_id=product_id,
            authority="memory_accept",
            grant_hash="b" * 64,
            effective_at=NOW - timedelta(minutes=5),
        ),
        resolved_approval=ResolvedApprovalReceiptV1(
            receipt_ref="approval:memory-1",
            product_id=product_id,
            subject_ref="proposal:memory-1",
            actor_ref="principal:reviewer",
            receipt_hash="c" * 64,
            approved_at=NOW,
        ),
    )


def _assertion(
    *,
    state: MemoryEpistemicState = MemoryEpistemicState.PROPOSED,
    authority: AssertionAuthorityV1Alpha1 | None = None,
    decision_ref: str | None = None,
    provenance: tuple[SourceProvenanceV1Alpha1, ...] | None = None,
) -> MemoryAssertionV1Alpha1:
    return MemoryAssertionV1Alpha1(
        scope=_scope(source_id=None if provenance and len(provenance) > 1 else "source:session-1"),
        family=MemorySemanticFamily.LEARNED_FACT,
        statement="The user selected the bounded option.",
        payload_json='{"choice":"bounded"}',
        provenance=provenance or (_provenance(),),
        authority=authority or _authority(),
        epistemic_state=state,
        knowledge_time=_known_time(),
        world_time=_world_time(),
        confidence=0.8,
        confidence_method_ref="confidence:extractor-v1",
        reconciliation_decision_ref=decision_ref,
    )


def test_scope_is_deterministic_and_rejects_content_supplied_authority_fields() -> None:
    first = _scope()
    second = _scope()
    assert first.scope_id == second.scope_id

    material = first.model_dump(mode="json")
    material["is_admin"] = True
    with pytest.raises(ValidationError, match="Extra inputs are not permitted"):
        AgentMemoryScopeV1Alpha1.model_validate_json(json.dumps(material))


def test_unknown_times_stay_unknown_and_cannot_carry_fabricated_values() -> None:
    knowledge = KnowledgeTimeV1Alpha1(
        kind=KnowledgeTimeKind.UNKNOWN,
        unknown_reason="the source did not expose first-known time",
    )
    world = WorldTimeV1Alpha1(
        kind=WorldTimeKind.UNKNOWN,
        unknown_reason="the statement did not specify world validity",
    )
    assert knowledge.first_known_at is None
    assert world.occurred_at is None

    with pytest.raises(ValidationError, match="cannot carry a fabricated time"):
        KnowledgeTimeV1Alpha1(
            kind=KnowledgeTimeKind.UNKNOWN,
            first_known_at=NOW,
            unknown_reason="missing",
        )
    with pytest.raises(ValidationError, match="cannot carry fabricated temporal material"):
        WorldTimeV1Alpha1(
            kind=WorldTimeKind.UNKNOWN,
            occurred_at=NOW,
            unknown_reason="missing",
        )


def test_temporal_query_keeps_knowledge_and_world_selectors_independent() -> None:
    query = TemporalQueryV1Alpha1(
        knowledge_at=NOW,
        world_at=NOW - timedelta(days=30),
        include_unknown_world=True,
    )
    assert query.knowledge_at == NOW
    assert query.world_at == NOW - timedelta(days=30)
    assert query.ledger_at is None
    assert query.include_unknown_knowledge is False


def test_source_span_binds_one_exact_source_version() -> None:
    with pytest.raises(ValidationError, match="exact provenance source version"):
        SourceProvenanceV1Alpha1(
            source_id="source:session-1",
            source_version_id="source_version:session-1-v1",
            content_digest="sha256:" + "a" * 64,
            span=ByteRangeSpanV1Alpha1(
                source_version_id="source_version:other",
                start_byte=0,
                end_byte=10,
            ),
            acquisition_receipt_ref="receipt:session-1",
            capture_method_ref="session.adapter",
        )


def test_source_span_identity_is_deterministic_and_content_derived() -> None:
    first = ByteRangeSpanV1Alpha1(
        source_version_id="source_version:session-1-v1",
        start_byte=0,
        end_byte=10,
    )
    second = ByteRangeSpanV1Alpha1(
        source_version_id="source_version:session-1-v1",
        start_byte=0,
        end_byte=10,
    )
    assert first.span_id == second.span_id
    with pytest.raises(ValidationError, match="span_id does not match"):
        ByteRangeSpanV1Alpha1(
            source_version_id="source_version:session-1-v1",
            start_byte=0,
            end_byte=10,
            span_id="agent_memory_span:wrong",
        )


def test_unavailable_span_is_explicit_instead_of_inventing_a_locator() -> None:
    provenance = SourceProvenanceV1Alpha1(
        source_id="source:session-1",
        source_version_id="source_version:session-1-v1",
        content_digest="sha256:" + "a" * 64,
        span=UnavailableSourceSpanV1Alpha1(
            source_version_id="source_version:session-1-v1",
            reason=UnavailableSpanReason.ADAPTER_UNSUPPORTED,
            detail="legacy adapter supplied no stable offsets",
        ),
        acquisition_receipt_ref="receipt:session-1",
        capture_method_ref="session.legacy-adapter",
    )
    assert provenance.span.kind == "unavailable"


def test_lifecycle_supersession_is_append_only_and_erasure_needs_dependency_proof() -> None:
    event = LifecycleEventV1Alpha1(
        scope=_scope(),
        target_ref="memory_assertion:old",
        operation=LifecycleOperation.SUPERSEDE,
        prior_state=LifecycleState.ACTIVE,
        next_state=LifecycleState.SUPERSEDED,
        actor_ref="principal:reviewer",
        authority_receipt_ref="authority_receipt:lifecycle-1",
        reason="A newer assertion applies.",
        occurred_at=NOW,
        prior_coordinate=_ledger_coordinate(),
        successor_ref="memory_assertion:new",
    )
    assert event.event_id.startswith("agent_memory_lifecycle:")
    assert "trust" not in type(event).model_fields

    with pytest.raises(ValidationError, match="dependency proof"):
        LifecycleEventV1Alpha1(
            scope=_scope(),
            target_ref="memory_assertion:old",
            operation=LifecycleOperation.CONFIRM_ERASURE,
            prior_state=LifecycleState.ERASE_PENDING,
            next_state=LifecycleState.ERASED,
            actor_ref="principal:reviewer",
            authority_receipt_ref="authority_receipt:lifecycle-2",
            reason="Authorized erasure completed.",
            occurred_at=NOW,
            prior_coordinate=_ledger_coordinate(),
        )

    with pytest.raises(ValidationError, match="exact prior ledger coordinate"):
        LifecycleEventV1Alpha1(
            scope=_scope(),
            target_ref="memory_assertion:old",
            operation=LifecycleOperation.RESTRICT,
            prior_state=LifecycleState.ACTIVE,
            next_state=LifecycleState.RESTRICTED,
            actor_ref="principal:reviewer",
            authority_receipt_ref="authority_receipt:lifecycle-3",
            reason="Temporarily restrict retrieval.",
            occurred_at=NOW,
        )


def test_erasure_proof_is_content_free_and_requires_complete_dependency_removal() -> None:
    proof = ErasureDependencyProofV1Alpha1(
        scope=_scope(),
        target_ref="memory_assertion:old",
        erasure_request_event_ref="agent_memory_lifecycle:erase-request-1",
        dependency_index_snapshot_ref="dependency_index:snapshot-1",
        enumerated_dependency_refs=("embedding:1", "summary:1"),
        removed_dependency_refs=("summary:1", "embedding:1"),
        verifier_ref="service:erasure-verifier",
        authority_receipt_ref="authority_receipt:erasure-1",
        verified_at=NOW,
    )
    assert proof.proof_id.startswith("agent_memory_erasure_proof:")
    assert "content" not in type(proof).model_fields

    with pytest.raises(ValidationError, match="every enumerated dependency"):
        ErasureDependencyProofV1Alpha1(
            scope=_scope(),
            target_ref="memory_assertion:old",
            erasure_request_event_ref="agent_memory_lifecycle:erase-request-1",
            dependency_index_snapshot_ref="dependency_index:snapshot-1",
            enumerated_dependency_refs=("embedding:1", "summary:1"),
            removed_dependency_refs=("embedding:1",),
            verifier_ref="service:erasure-verifier",
            authority_receipt_ref="authority_receipt:erasure-1",
            verified_at=NOW,
        )


def test_unknown_contract_and_memory_family_versions_fail_closed() -> None:
    scope = _scope().model_dump(mode="json")
    scope["contract"] = "ace.core.agent-memory-scope/v9"
    with pytest.raises(ValidationError, match="Input should be"):
        AgentMemoryScopeV1Alpha1.model_validate_json(json.dumps(scope))

    assertion = _assertion().model_dump(mode="json")
    assertion["family"] = "invented_family"
    with pytest.raises(ValidationError, match="invented_family"):
        MemoryAssertionV1Alpha1.model_validate_json(json.dumps(assertion))


def test_model_output_remains_a_proposal_without_reconciliation_authority() -> None:
    assertion = _assertion()
    assert assertion.epistemic_state is MemoryEpistemicState.PROPOSED
    assert assertion.authority.origin_kind is AssertionOriginKind.MODEL_PROPOSAL
    assert assertion.reconciliation_decision_ref is None

    with pytest.raises(ValidationError, match="resolved authority and approval"):
        _assertion(
            state=MemoryEpistemicState.ACCEPTED,
            decision_ref="decision:accept-memory-1",
        )


def test_accepted_assertion_requires_exact_product_scoped_approval_and_grant() -> None:
    accepted = _assertion(
        state=MemoryEpistemicState.ACCEPTED,
        authority=_authority(accepted=True),
        decision_ref="decision:accept-memory-1",
    )
    assert accepted.epistemic_state is MemoryEpistemicState.ACCEPTED

    with pytest.raises(ValidationError, match="exact product scope"):
        _assertion(
            state=MemoryEpistemicState.ACCEPTED,
            authority=_authority(accepted=True, product_id="product:foreign"),
            decision_ref="decision:accept-memory-1",
        )


def test_confidence_never_exists_without_an_explicit_method() -> None:
    material = _assertion().model_dump(mode="python")
    material["confidence_method_ref"] = None
    material["assertion_id"] = None
    material["assertion_digest"] = None
    with pytest.raises(ValidationError, match="supplied together"):
        MemoryAssertionV1Alpha1.model_validate(material)


def test_reconciliation_is_a_proposal_with_evidence_not_a_state_mutation() -> None:
    assertion = _assertion()
    proposal = ReconciliationProposalV1Alpha1(
        scope=_scope(),
        assertion_refs=(str(assertion.assertion_id),),
        requested_state=MemoryEpistemicState.ACCEPTED,
        policy_ref="policy:memory-reconciliation",
        policy_version="1.0.0",
        evidence_refs=("source:session-1",),
        required_authority="authority:memory-review",
        generated_by=AssertionOriginKind.TELEMETRY,
        reason="Observed outcome supports review; it does not self-activate.",
        created_at=NOW,
    )
    assert proposal.proposal_id.startswith("memory_reconciliation_proposal:")
    assert assertion.epistemic_state is MemoryEpistemicState.PROPOSED

    with pytest.raises(ValidationError, match="assertions and evidence"):
        ReconciliationProposalV1Alpha1(
            scope=_scope(),
            assertion_refs=(str(assertion.assertion_id),),
            requested_state=MemoryEpistemicState.ACCEPTED,
            policy_ref="policy:memory-reconciliation",
            policy_version="1.0.0",
            evidence_refs=(),
            required_authority="authority:memory-review",
            generated_by=AssertionOriginKind.MODEL_PROPOSAL,
            reason="No evidence was supplied.",
            created_at=NOW,
        )


def test_evolution_output_is_only_a_reviewable_proposal() -> None:
    proposal = MemoryEvolutionProposalV1Alpha1(
        scope=_scope(),
        kind=MemoryEvolutionKind.CONSOLIDATION,
        input_refs=("memory_assertion:1", "memory_assertion:2"),
        evidence_refs=("source:session-1", "source:session-2"),
        proposed_payload_contract="ace.intelligence.memory-assertion/v1alpha1",
        proposed_payload_json='{"statement":"possible durable pattern"}',
        policy_ref="policy:memory-evolution",
        policy_version="1.0.0",
        required_authority="authority:memory-review",
        generated_by=AssertionOriginKind.TELEMETRY,
        reason="Independent evidence may justify a reviewed consolidation.",
        created_at=NOW,
    )
    assert proposal.proposal_id.startswith("memory_evolution_proposal:")
    assert not hasattr(proposal, "active")


def test_candidate_receipt_links_to_existing_manifest_and_i3_without_redefining_use() -> None:
    query = AgentMemoryQueryV1Alpha1(
        scope=_scope(),
        query_digest="sha256:" + "d" * 64,
        eligible_families=(MemorySemanticFamily.LEARNED_FACT,),
        eligible_states=(MemoryEpistemicState.ACCEPTED,),
        receiver_ref="reasoning_stage:orientation",
        policy_ref="policy:memory-retrieval-v1",
    )
    receipt = CandidateReceiptV1Alpha1(
        query_id=str(query.query_id),
        scope_id=str(query.scope.scope_id),
        policy_ref=query.policy_ref,
        authorization_filter_receipt_ref="authority_receipt:retrieval-filter-1",
        lifecycle_snapshot_ref="lifecycle_snapshot:retrieval-1",
        candidates=(
            CandidateRecordV1Alpha1(
                assertion_ref="memory_assertion:1",
                family=MemorySemanticFamily.LEARNED_FACT,
                epistemic_state=MemoryEpistemicState.ACCEPTED,
                source_id="source:session-1",
                source_version_id="source_version:session-1-v1",
                selected=True,
                aggregate_score=0.8,
                signals=(
                    CandidateSignalContributionV1Alpha1(
                        signal_ref="lexical.score",
                        available=True,
                        score=0.8,
                    ),
                ),
            ),
        ),
        generated_at=NOW,
    )
    lineage = MemoryContextLineageV1Alpha1(
        scope=_scope(),
        candidate_receipt_id=str(receipt.receipt_id),
        assertion_ref="memory_assertion:1",
        context_manifest_id="context_manifest:task-1",
        context_item_ref="context_item:memory-1",
        context_item_source_receipt_ref="memory_candidate_receipt:receipt-1",
        recorded_at=NOW,
    )
    assert lineage.intelligence_use_receipt_ref is None
    assert receipt.authorization_filter_receipt_ref == "authority_receipt:retrieval-filter-1"
    assert receipt.lifecycle_snapshot_ref == "lifecycle_snapshot:retrieval-1"
    assert {
        "authorized",
        "injected",
        "materially_used",
        "decision_material",
    }.isdisjoint(type(receipt).model_fields)

    missing_filter_evidence = receipt.model_dump(
        mode="python",
        exclude={"receipt_id", "authorization_filter_receipt_ref"},
    )
    with pytest.raises(ValidationError, match="authorization_filter_receipt_ref"):
        CandidateReceiptV1Alpha1.model_validate(missing_filter_evidence)
    assert {
        "eligible",
        "authorized",
        "selected",
        "injected",
        "materially_used",
    }.isdisjoint(type(lineage).model_fields)

    with pytest.raises(ValidationError, match="I3 intelligence-use receipt"):
        MemoryContextLineageV1Alpha1(
            scope=_scope(),
            candidate_receipt_id=str(receipt.receipt_id),
            assertion_ref="memory_assertion:1",
            context_manifest_id="context_manifest:task-1",
            context_item_ref="context_item:memory-1",
            context_item_source_receipt_ref="memory_candidate_receipt:receipt-1",
            decision_ref="decision:1",
            recorded_at=NOW,
        )
