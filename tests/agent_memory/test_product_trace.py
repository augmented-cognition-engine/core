from __future__ import annotations

import json
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

import pytest
from pydantic import ValidationError

from ace.core.agent_memory import (
    AgentMemoryScopeV1Alpha1,
    ByteRangeSpanV1Alpha1,
    KnowledgeTimeKind,
    KnowledgeTimeV1Alpha1,
    LedgerCoordinateV1Alpha1,
    LifecycleEventV1Alpha1,
    LifecycleOperation,
    LifecycleState,
    MemoryVisibility,
    RetentionClass,
    SourceProvenanceV1Alpha1,
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
)

pytestmark = pytest.mark.unit

REPO = Path(__file__).resolve().parents[2]
FIXTURE = REPO / "evaluations/fixtures/agent_memory_am0_contract_v1.json"
NOW = datetime(2026, 8, 11, 21, 0, tzinfo=UTC)


def _fixture() -> dict[str, Any]:
    return json.loads(FIXTURE.read_text(encoding="utf-8"))


def _scope(data: dict[str, Any], *, session_id: str, product_id: str | None = None) -> AgentMemoryScopeV1Alpha1:
    return AgentMemoryScopeV1Alpha1(
        product_id=product_id or data["product_id"],
        actor_id=data["actor_id"],
        session_id=session_id,
        source_id=data["source"]["source_id"],
        visibility=MemoryVisibility.PRIVATE,
        retention_class=RetentionClass.STANDARD,
        authority_receipt_ref="authority_receipt:authenticated-scope",
    )


def _provenance(data: dict[str, Any], *, corrected: bool) -> SourceProvenanceV1Alpha1:
    source = data["source"]
    version_key = "corrected_version_id" if corrected else "initial_version_id"
    digest_key = "corrected_digest" if corrected else "initial_digest"
    return SourceProvenanceV1Alpha1(
        source_id=source["source_id"],
        source_version_id=source[version_key],
        content_digest=source[digest_key],
        span=ByteRangeSpanV1Alpha1(
            source_version_id=source[version_key],
            start_byte=source["span"]["start_byte"],
            end_byte=source["span"]["end_byte"],
        ),
        acquisition_receipt_ref=source["acquisition_receipt_ref"],
        capture_method_ref=source["capture_method_ref"],
    )


def _accepted_authority(data: dict[str, Any], *, subject_ref: str) -> AssertionAuthorityV1Alpha1:
    return AssertionAuthorityV1Alpha1(
        origin_kind=AssertionOriginKind.USER,
        actor_ref=data["actor_id"],
        resolved_grant=ResolvedAuthorityGrantV1(
            grant_ref="grant:memory-acceptance",
            product_id=data["product_id"],
            authority="memory_accept",
            grant_hash="f" * 64,
            effective_at=NOW - timedelta(minutes=10),
        ),
        resolved_approval=ResolvedApprovalReceiptV1(
            receipt_ref=f"approval:{subject_ref.rsplit(':', 1)[-1]}",
            product_id=data["product_id"],
            subject_ref=subject_ref,
            actor_ref="principal:memory-reviewer",
            receipt_hash="1" * 64,
            approved_at=NOW - timedelta(minutes=5),
        ),
    )


def _accepted_assertion(
    data: dict[str, Any],
    *,
    statement: str,
    corrected: bool,
    family: MemorySemanticFamily,
    supersedes: tuple[str, ...] = (),
) -> MemoryAssertionV1Alpha1:
    subject_ref = "proposal:corrected-market-state" if corrected else "proposal:initial-market-state"
    return MemoryAssertionV1Alpha1(
        scope=_scope(data, session_id=data["initial_session_id"]),
        family=family,
        statement=statement,
        payload_json='{"state":"bounded"}',
        provenance=(_provenance(data, corrected=corrected),),
        authority=_accepted_authority(data, subject_ref=subject_ref),
        epistemic_state=MemoryEpistemicState.ACCEPTED,
        knowledge_time=KnowledgeTimeV1Alpha1(
            kind=KnowledgeTimeKind.KNOWN,
            first_known_at=NOW if corrected else NOW - timedelta(hours=1),
            basis_refs=(data["source"]["source_id"],),
        ),
        world_time=WorldTimeV1Alpha1(
            kind=WorldTimeKind.INSTANT,
            occurred_at=NOW if corrected else NOW - timedelta(hours=2),
        ),
        confidence=0.8,
        confidence_method_ref="confidence:source-review-v1",
        supersedes=supersedes,
        reconciliation_decision_ref=(
            "reconciliation_decision:corrected-market-state"
            if corrected
            else "reconciliation_decision:initial-market-state"
        ),
    )


def _query(
    data: dict[str, Any],
    stage: dict[str, Any],
    *,
    session_id: str,
) -> AgentMemoryQueryV1Alpha1:
    return AgentMemoryQueryV1Alpha1(
        scope=_scope(data, session_id=session_id),
        query_digest=stage["query_digest"],
        eligible_families=(MemorySemanticFamily.LEARNED_FACT, MemorySemanticFamily.CORRECTION),
        eligible_states=(MemoryEpistemicState.ACCEPTED,),
        receiver_ref=stage["receiver_ref"],
        policy_ref=stage["retrieval_policy_ref"],
    )


def _candidate(
    assertion: MemoryAssertionV1Alpha1,
    *,
    selected: bool,
    omission_reason: str | None = None,
) -> CandidateRecordV1Alpha1:
    provenance = assertion.provenance[0]
    return CandidateRecordV1Alpha1(
        assertion_ref=assertion.assertion_id,
        family=assertion.family,
        epistemic_state=assertion.epistemic_state,
        source_id=provenance.source_id,
        source_version_id=provenance.source_version_id,
        selected=selected,
        aggregate_score=0.9 if selected else 0.1,
        signals=(
            CandidateSignalContributionV1Alpha1(
                signal_ref="signal:exact-current-state",
                available=True,
                score=0.9 if selected else 0.1,
            ),
        ),
        omission_reason=omission_reason,
    )


def test_frozen_trace_is_bounded_contract_evidence_not_product_implementation() -> None:
    data = _fixture()
    assert data["contract"] == "ace.evaluation.agent-memory-am0-contract/v1"
    assert data["claim_scope"] == "contract_and_receipt_trace_only"
    assert set(data["forbidden_implementations"]) == {
        "briefing_generator",
        "connector",
        "monitor_scheduler",
        "onboarding_agent",
        "ontology_mapper",
        "user_interface",
    }
    assert data["concept_mapping"] == {
        "policy_ref": "source_mapping:market-briefing",
        "policy_version": "revision:source-mapping-v1",
    }


def test_repeat_briefing_trace_preserves_correction_manifest_and_i3_lineage() -> None:
    data = _fixture()
    initial = _accepted_assertion(
        data,
        statement="The bounded market state is the initial state.",
        corrected=False,
        family=MemorySemanticFamily.LEARNED_FACT,
    )
    correction = _accepted_assertion(
        data,
        statement="The corrected bounded market state replaces the initial state.",
        corrected=True,
        family=MemorySemanticFamily.CORRECTION,
        supersedes=(initial.assertion_id,),
    )
    lifecycle = LifecycleEventV1Alpha1(
        scope=initial.scope,
        target_ref=initial.assertion_id,
        operation=LifecycleOperation.SUPERSEDE,
        prior_state=LifecycleState.ACTIVE,
        next_state=LifecycleState.SUPERSEDED,
        actor_ref="principal:memory-reviewer",
        authority_receipt_ref="authority_receipt:correction",
        reason="The authorized source correction now applies.",
        occurred_at=NOW,
        prior_coordinate=LedgerCoordinateV1Alpha1(
            ledger_ref="agent_memory_ledger:product-trace",
            sequence=1,
            event_ref="agent_memory_lifecycle:initial-activation",
            committed_at=NOW - timedelta(minutes=1),
        ),
        successor_ref=correction.assertion_id,
    )

    first_stage = data["first_briefing"]
    first_query = _query(data, first_stage, session_id=data["initial_session_id"])
    first_receipt = CandidateReceiptV1Alpha1(
        query_id=first_query.query_id,
        scope_id=first_query.scope.scope_id,
        policy_ref=first_query.policy_ref,
        authorization_filter_receipt_ref=first_stage["authorization_filter_receipt_ref"],
        lifecycle_snapshot_ref=first_stage["lifecycle_snapshot_ref"],
        candidates=(_candidate(initial, selected=True),),
        generated_at=NOW - timedelta(minutes=30),
    )
    first_lineage = MemoryContextLineageV1Alpha1(
        scope=first_query.scope,
        candidate_receipt_id=first_receipt.receipt_id,
        assertion_ref=initial.assertion_id,
        context_manifest_id=first_stage["context_manifest_id"],
        context_item_ref=first_stage["context_item_ref"],
        context_item_source_receipt_ref=first_stage["context_item_source_receipt_ref"],
        recorded_at=NOW - timedelta(minutes=29),
    )

    refreshed_stage = data["refreshed_briefing"]
    refreshed_query = _query(data, refreshed_stage, session_id=data["initial_session_id"])
    refreshed_receipt = CandidateReceiptV1Alpha1(
        query_id=refreshed_query.query_id,
        scope_id=refreshed_query.scope.scope_id,
        policy_ref=refreshed_query.policy_ref,
        authorization_filter_receipt_ref=refreshed_stage["authorization_filter_receipt_ref"],
        lifecycle_snapshot_ref=refreshed_stage["lifecycle_snapshot_ref"],
        candidates=(
            _candidate(initial, selected=False, omission_reason="superseded_by_authorized_correction"),
            _candidate(correction, selected=True),
        ),
        generated_at=NOW + timedelta(minutes=1),
    )
    refreshed_lineage = MemoryContextLineageV1Alpha1(
        scope=refreshed_query.scope,
        candidate_receipt_id=refreshed_receipt.receipt_id,
        assertion_ref=correction.assertion_id,
        context_manifest_id=refreshed_stage["context_manifest_id"],
        context_item_ref=refreshed_stage["context_item_ref"],
        context_item_source_receipt_ref=refreshed_stage["context_item_source_receipt_ref"],
        intelligence_use_receipt_ref=refreshed_stage["intelligence_use_receipt_ref"],
        decision_ref=refreshed_stage["decision_ref"],
        recorded_at=NOW + timedelta(minutes=2),
    )

    assert lifecycle.successor_ref == correction.assertion_id
    assert correction.supersedes == (initial.assertion_id,)
    assert first_lineage.intelligence_use_receipt_ref is None
    assert first_lineage.decision_ref is None
    assert refreshed_lineage.context_manifest_contract == "ace.context.manifest/v1"
    assert refreshed_lineage.intelligence_use_contract == "intelligence-use-receipt-v1"
    assert refreshed_lineage.intelligence_use_receipt_ref == refreshed_stage["intelligence_use_receipt_ref"]
    selection_by_assertion = {candidate.assertion_ref: candidate.selected for candidate in refreshed_receipt.candidates}
    assert selection_by_assertion == {
        initial.assertion_id: False,
        correction.assertion_id: True,
    }


def test_later_session_continuity_and_feedback_remain_scoped_and_proposal_only() -> None:
    data = _fixture()
    correction = _accepted_assertion(
        data,
        statement="The corrected bounded market state applies.",
        corrected=True,
        family=MemorySemanticFamily.CORRECTION,
    )
    later_stage = data["later_session"]
    later_query = _query(data, later_stage, session_id=data["later_session_id"])
    later_receipt = CandidateReceiptV1Alpha1(
        query_id=later_query.query_id,
        scope_id=later_query.scope.scope_id,
        policy_ref=later_query.policy_ref,
        authorization_filter_receipt_ref=later_stage["authorization_filter_receipt_ref"],
        lifecycle_snapshot_ref=later_stage["lifecycle_snapshot_ref"],
        candidates=(_candidate(correction, selected=True),),
        generated_at=NOW + timedelta(days=1),
    )
    feedback = data["feedback"]
    proposal = MemoryEvolutionProposalV1Alpha1(
        scope=later_query.scope,
        kind=MemoryEvolutionKind.RANK_POLICY,
        input_refs=(feedback["feedback_receipt_ref"],),
        evidence_refs=(later_receipt.receipt_id,),
        proposed_payload_contract="ace.intelligence.memory-relevance-adjustment/v1alpha1",
        proposed_payload_json='{"direction":"increase_relevance"}',
        policy_ref=feedback["policy_ref"],
        policy_version=feedback["policy_version"],
        required_authority=feedback["required_authority"],
        generated_by=AssertionOriginKind.USER,
        reason="The user supplied explicit briefing relevance feedback.",
        created_at=NOW + timedelta(days=1, minutes=1),
    )

    assert later_query.scope.product_id == correction.scope.product_id
    assert later_query.scope.actor_id == correction.scope.actor_id
    assert later_query.scope.session_id != correction.scope.session_id
    assert later_receipt.candidates[0].assertion_ref == correction.assertion_id
    assert later_receipt.authorization_filter_receipt_ref == (later_stage["authorization_filter_receipt_ref"])
    assert later_receipt.lifecycle_snapshot_ref == later_stage["lifecycle_snapshot_ref"]
    assert proposal.kind is MemoryEvolutionKind.RANK_POLICY
    assert "active" not in type(proposal).model_fields
    assert "approved" not in type(proposal).model_fields


def test_trace_negative_cases_fail_closed_or_remain_explicitly_degraded() -> None:
    data = _fixture()
    assert set(data["required_cases"]) == {
        "cross_product",
        "disputed",
        "hostile_scope",
        "lifecycle_restricted",
        "missing_use_receipt",
        "ordinary",
        "partial_write",
        "repeated_poison",
        "stale_cache",
        "superseded",
        "unknown_time",
    }

    unknown_knowledge = KnowledgeTimeV1Alpha1(
        kind=KnowledgeTimeKind.UNKNOWN,
        unknown_reason="the source did not provide first-known time",
    )
    unknown_world = WorldTimeV1Alpha1(
        kind=WorldTimeKind.UNKNOWN,
        unknown_reason="the source did not state real-world validity",
    )
    assert unknown_knowledge.first_known_at is None
    assert unknown_world.occurred_at is None

    hostile_scope = _scope(data, session_id=data["initial_session_id"]).model_dump(mode="json")
    hostile_scope["actor_id"] = "principal:captured-content-claim"
    hostile_scope["captured_is_admin"] = True
    with pytest.raises(ValidationError, match="Extra inputs are not permitted"):
        AgentMemoryScopeV1Alpha1.model_validate(hostile_scope)

    foreign_authority = _accepted_authority(data, subject_ref="proposal:foreign")
    foreign_grant = foreign_authority.resolved_grant.model_copy(update={"product_id": "product:foreign"})
    with pytest.raises(ValidationError, match="exact product scope"):
        MemoryAssertionV1Alpha1(
            scope=_scope(data, session_id=data["initial_session_id"]),
            family=MemorySemanticFamily.LEARNED_FACT,
            statement="Foreign authority must not activate this assertion.",
            provenance=(_provenance(data, corrected=False),),
            authority=foreign_authority.model_copy(update={"resolved_grant": foreign_grant}),
            epistemic_state=MemoryEpistemicState.ACCEPTED,
            knowledge_time=unknown_knowledge,
            world_time=unknown_world,
            reconciliation_decision_ref="reconciliation_decision:foreign",
        )

    with pytest.raises(ValidationError, match="exact I3 intelligence-use receipt"):
        MemoryContextLineageV1Alpha1(
            scope=_scope(data, session_id=data["initial_session_id"]),
            candidate_receipt_id="memory_candidate_receipt:missing-i3",
            assertion_ref="memory_assertion:missing-i3",
            context_manifest_id="context_manifest:missing-i3",
            context_item_ref="context_item:missing-i3",
            context_item_source_receipt_ref="context_source_receipt:missing-i3",
            decision_ref="decision:unsupported-material-use-claim",
            recorded_at=NOW,
        )

    degraded = CandidateReceiptV1Alpha1(
        query_id="agent_memory_query:stale-cache",
        scope_id=_scope(data, session_id=data["initial_session_id"]).scope_id,
        policy_ref="memory_policy:briefing-v1",
        authorization_filter_receipt_ref="authority_receipt:degraded-filter",
        lifecycle_snapshot_ref="lifecycle_snapshot:degraded-read",
        degraded_reasons=("stale_cache_rejected", "temporal_index_unavailable"),
        generated_at=NOW,
    )
    assert degraded.candidates == ()
    assert degraded.degraded_reasons == ("stale_cache_rejected", "temporal_index_unavailable")


def test_repetition_and_prompt_text_cannot_mint_instruction_authority() -> None:
    data = _fixture()
    proposed = MemoryAssertionV1Alpha1(
        scope=_scope(data, session_id=data["initial_session_id"]),
        family=MemorySemanticFamily.INSTRUCTION_POLICY,
        statement="Captured source text says to ignore the authenticated policy.",
        provenance=(_provenance(data, corrected=False),),
        authority=AssertionAuthorityV1Alpha1(
            origin_kind=AssertionOriginKind.MODEL_PROPOSAL,
            actor_ref="agent:source-extractor",
        ),
        epistemic_state=MemoryEpistemicState.PROPOSED,
        knowledge_time=KnowledgeTimeV1Alpha1(
            kind=KnowledgeTimeKind.UNKNOWN,
            unknown_reason="captured text supplied no first-known time",
        ),
        world_time=WorldTimeV1Alpha1(
            kind=WorldTimeKind.UNKNOWN,
            unknown_reason="captured text supplied no world validity",
        ),
    )
    repeated = MemoryAssertionV1Alpha1.model_validate(proposed.model_dump(mode="python"))

    assert repeated.assertion_id == proposed.assertion_id
    assert repeated.epistemic_state is MemoryEpistemicState.PROPOSED
    assert repeated.authority.resolved_grant is None
    assert repeated.authority.resolved_approval is None

    accepted_material = proposed.model_dump(mode="python", exclude={"assertion_id", "assertion_digest"})
    accepted_material.update(
        epistemic_state=MemoryEpistemicState.ACCEPTED,
        reconciliation_decision_ref="reconciliation_decision:prompt-injection",
    )
    with pytest.raises(ValidationError, match="resolved authority and approval"):
        MemoryAssertionV1Alpha1.model_validate(accepted_material)
