"""Focused TP4 reviewed-assertion and belief-projection acceptance tests."""

from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import AsyncMock

import pytest
from pydantic import ValidationError

from core.engine.graph.assertions import RelationshipProposal, resolve_proposals
from core.engine.grounded_state.belief_contracts import (
    AssertionReviewV1,
    BoundedEvidencePackV1,
    CounterevidenceSearchReceiptV1,
    EpistemicAssertionProposalV1,
    EpistemicRelation,
    EvidenceEndpointKind,
    EvidencePackItemV1,
    InferenceRoute,
    ProjectionTargetV1,
    ReviewAuthority,
    ReviewDisposition,
    TypedEvidenceEndpointV1,
)
from core.engine.grounded_state.belief_evaluation import (
    TP4BeliefEvaluationResultV1,
    evaluate_tp4_belief_projection,
    load_tp0_corpus,
    load_tp4_config,
)
from core.engine.grounded_state.beliefs import (
    BeliefProjectionError,
    BeliefStateProjectionService,
    build_projection,
    counterevidence_search,
    derive_external_world_insight,
    reopen_and_reproject,
    resolve_assertion,
)
from core.engine.grounded_state.contracts import BeliefStatus, TemporalScopeV1

UTC = timezone.utc
AS_OF = datetime(2026, 8, 3, 12, tzinfo=UTC)
ROOT = Path(__file__).parents[1]


def _hash(value: str) -> str:
    return hashlib.sha256(value.encode()).hexdigest()


def _endpoint(
    record_id: str,
    *,
    product_id: str = "product:tp4-a",
    kind: EvidenceEndpointKind = EvidenceEndpointKind.CLAIM,
    version: str = "v1",
) -> TypedEvidenceEndpointV1:
    return TypedEvidenceEndpointV1(
        product_id=product_id,
        kind=kind,
        record_id=record_id,
        record_version=version,
        content_hash=_hash(f"{record_id}:{version}"),
    )


def _item(
    record_id: str,
    *,
    product_id: str = "product:tp4-a",
    content: str | None = None,
    source_id: str | None = None,
    temporal: TemporalScopeV1 | None = None,
) -> EvidencePackItemV1:
    return EvidencePackItemV1(
        endpoint=_endpoint(record_id, product_id=product_id),
        temporal=temporal or TemporalScopeV1(),
        published_at=datetime(2026, 7, 1, tzinfo=UTC),
        ingested_at=datetime(2026, 7, 2, tzinfo=UTC),
        extracted_at=datetime(2026, 7, 3, tzinfo=UTC),
        ace_created_at=datetime(2026, 7, 4, tzinfo=UTC),
        source_id=source_id or f"source:{record_id.rsplit(':', 1)[-1]}",
        publisher_id=source_id or f"source:{record_id.rsplit(':', 1)[-1]}",
        compact_content=content or f"Evidence material for {record_id}",
        source_confidence=0.8,
        candidate_rank=1,
        selection_signals=("entity", "lexical"),
    )


def _pack(
    *record_ids: str,
    product_id: str = "product:tp4-a",
    candidate_count: int | None = None,
    contents: dict[str, str] | None = None,
) -> BoundedEvidencePackV1:
    items = tuple(
        _item(record_id, product_id=product_id, content=(contents or {}).get(record_id)) for record_id in record_ids
    )
    selected_chars = sum(len(item.compact_content or "") for item in items)
    total = candidate_count if candidate_count is not None else len(items)
    return BoundedEvidencePackV1(
        product_id=product_id,
        as_of=AS_OF,
        query_hash=_hash("tp4-query"),
        candidate_receipt_id="candidate_receipt:tp4",
        candidate_receipt_hash=_hash("tp4-candidate-receipt"),
        resolver_policy_version="ace.grounded-state.belief-resolver/v1",
        ontology_version="ace.grounded-state.epistemic-ontology/v1",
        items=items,
        candidate_count=total,
        selected_count=len(items),
        max_records=200,
        max_chars=64_000,
        selected_chars=selected_chars,
        omissions=("tp3_candidate_cap_omitted:1",) if total > len(items) else (),
        degraded_reasons=("candidate_pack_truncated",) if total > len(items) else (),
        truncated=total > len(items),
    )


def _proposal(
    pack: BoundedEvidencePackV1,
    *,
    relation: EpistemicRelation = EpistemicRelation.CORROBORATES,
    subject: str = "grounded_claim:a",
    object_: str = "grounded_claim:b",
    supports: tuple[str, ...] = ("grounded_claim:a", "grounded_claim:b"),
    origins: tuple[str, ...] = ("source:a", "source:b"),
    validity: TemporalScopeV1 | None = None,
    belief_subject: str | None = None,
    belief_predicate: str | None = None,
    belief_value=None,
    supersedes_assertion_refs: tuple[str, ...] = (),
) -> EpistemicAssertionProposalV1:
    return EpistemicAssertionProposalV1(
        product_id=pack.product_id,
        subject=_endpoint(subject, product_id=pack.product_id),
        relation=relation,
        object=_endpoint(object_, product_id=pack.product_id),
        belief_subject=(
            TypedEvidenceEndpointV1(
                product_id=pack.product_id,
                kind=EvidenceEndpointKind.ENTITY,
                record_id=belief_subject,
                record_version="v1",
                content_hash=_hash(belief_subject),
            )
            if belief_subject is not None
            else None
        ),
        belief_predicate=belief_predicate,
        belief_value=belief_value,
        supersedes_assertion_refs=supersedes_assertion_refs,
        validity=validity or TemporalScopeV1(),
        proposed_at=AS_OF,
        evidence_pack_id=str(pack.pack_id),
        evidence_pack_hash=str(pack.pack_hash),
        supporting_evidence_refs=supports,
        source_origin_ids=origins,
        source_confidence=0.8,
        epistemic_confidence=0.75,
        freshness=0.9,
        rationale="The bounded material supports a reviewed relation.",
        proposer_authority="model",
        proposer_ref="model:fixture",
        model="fixture-model",
        provider="fixture-provider",
        prompt_version="tp4.fixture/v1",
    )


def _counter(
    proposal: EpistemicAssertionProposalV1,
    pack: BoundedEvidencePackV1,
    *,
    completed: bool = True,
) -> CounterevidenceSearchReceiptV1:
    refs = tuple(item.endpoint.record_id for item in pack.items)
    return CounterevidenceSearchReceiptV1(
        product_id=pack.product_id,
        assertion_material_hash=proposal.review_material_hash(),
        as_of=AS_OF,
        evidence_pack_id=str(pack.pack_id),
        evidence_pack_hash=str(pack.pack_hash),
        searched_evidence_refs=refs,
        missing_inputs=() if completed else ("counter_index_unavailable",),
        index_versions={"grounded_state": "ace.grounded-state.schema/v164"},
        policy_version="ace.grounded-state.assertion-policy/v1",
        max_records=50,
        records_searched=len(refs),
        degraded_reasons=() if completed else ("counterevidence_inputs_missing",),
        completed=completed,
    )


def _review(
    proposal: EpistemicAssertionProposalV1,
    *,
    disposition: ReviewDisposition = ReviewDisposition.ACCEPTED,
    authority: ReviewAuthority = ReviewAuthority.DETERMINISTIC_POLICY,
    counter: CounterevidenceSearchReceiptV1 | None = None,
) -> AssertionReviewV1:
    return AssertionReviewV1(
        product_id=proposal.product_id,
        proposal_id=str(proposal.proposal_id),
        assertion_id=proposal.assertion_id(),
        reviewed_material_hash=proposal.review_material_hash(),
        disposition=disposition,
        authority=authority,
        reviewer_ref="human:owner" if authority is ReviewAuthority.HUMAN else "policy:tp4",
        reviewed_at=AS_OF,
        rationale="Exact material reviewed under frozen policy.",
        counterevidence_receipt_id=str(counter.receipt_id) if counter else None,
        counterevidence_receipt_hash=str(counter.receipt_hash) if counter else None,
        policy_version="ace.grounded-state.assertion-policy/v1",
    )


def _accepted(
    pack: BoundedEvidencePackV1,
    *,
    relation: EpistemicRelation = EpistemicRelation.CORROBORATES,
    subject: str = "grounded_claim:a",
    object_: str = "grounded_claim:b",
    supports: tuple[str, ...] = ("grounded_claim:a", "grounded_claim:b"),
    origins: tuple[str, ...] = ("source:a", "source:b"),
):
    proposal = _proposal(
        pack,
        relation=relation,
        subject=subject,
        object_=object_,
        supports=supports,
        origins=origins,
    )
    review = _review(proposal)
    return resolve_assertion(proposal, review)


def test_contracts_are_extra_forbid_immutable_and_identity_order_independent():
    pack = _pack("grounded_claim:a", "grounded_claim:b")
    replay = BoundedEvidencePackV1.model_validate(
        {**pack.model_dump(mode="python", exclude={"pack_id", "pack_hash"}), "items": tuple(reversed(pack.items))}
    )
    assert replay == pack
    with pytest.raises(ValidationError):
        BoundedEvidencePackV1.model_validate({**pack.model_dump(mode="python"), "unexpected": True})
    with pytest.raises(ValidationError):
        pack.selected_count = 0


def test_typed_endpoints_extend_to_tp2_evidence_and_reject_kind_confusion():
    assert _endpoint("grounded_event:event", kind=EvidenceEndpointKind.EVENT).kind is EvidenceEndpointKind.EVENT
    with pytest.raises(ValidationError, match="kind"):
        _endpoint("insight:not-a-claim", kind=EvidenceEndpointKind.CLAIM)


def test_source_claim_proposal_does_not_auto_accept_or_become_operational():
    pack = _pack("grounded_claim:a", "grounded_claim:b")
    proposal = _proposal(pack)
    assertion = resolve_assertion(
        proposal,
        _review(proposal, disposition=ReviewDisposition.PROPOSED, authority=ReviewAuthority.MODEL),
    )
    projection = build_projection(product_id=pack.product_id, as_of=AS_OF, evidence_pack=pack, assertions=[assertion])
    assert assertion.disposition is ReviewDisposition.PROPOSED
    assert projection.entries[0].status is BeliefStatus.PROVISIONAL
    assert projection.entries[0].operational is False


def test_causal_acceptance_fails_closed_without_countersearch_diversity_and_human_review():
    pack = _pack("grounded_claim:a", "grounded_claim:b")
    weak = _proposal(pack, relation=EpistemicRelation.CAUSES, origins=("source:a",))
    weak_review = _review(weak, authority=ReviewAuthority.DETERMINISTIC_POLICY)
    assertion = resolve_assertion(weak, weak_review, evidence_pack=pack)
    assert assertion.disposition is ReviewDisposition.PROPOSED
    assert set(assertion.degraded_reasons) == {
        "counterevidence_search_required",
        "human_confirmation_required",
        "independent_source_diversity_insufficient",
    }


def test_causal_acceptance_requires_exact_human_review_and_completed_countersearch():
    pack = _pack("grounded_claim:a", "grounded_claim:b")
    proposal = _proposal(pack, relation=EpistemicRelation.CAUSES)
    incomplete = _counter(proposal, pack, completed=False)
    provisional = resolve_assertion(
        proposal,
        _review(proposal, authority=ReviewAuthority.HUMAN, counter=incomplete),
        counterevidence=incomplete,
        evidence_pack=pack,
    )
    assert provisional.disposition is ReviewDisposition.PROPOSED
    assert "counterevidence_search_incomplete" in provisional.degraded_reasons

    counter = _counter(proposal, pack)
    accepted = resolve_assertion(
        proposal,
        _review(proposal, authority=ReviewAuthority.HUMAN, counter=counter),
        counterevidence=counter,
        evidence_pack=pack,
    )
    assert accepted.disposition is ReviewDisposition.ACCEPTED
    assert accepted.review_authority is ReviewAuthority.HUMAN
    assert accepted.counterevidence_receipt_id == counter.receipt_id


def test_model_cannot_accept_assertion_and_mismatched_review_material_fails():
    pack = _pack("grounded_claim:a", "grounded_claim:b")
    proposal = _proposal(pack)
    with pytest.raises(ValidationError, match="model may not accept"):
        _review(proposal, authority=ReviewAuthority.MODEL)
    bad = _review(proposal).model_copy(update={"reviewed_material_hash": "0" * 64})
    with pytest.raises(BeliefProjectionError, match="exact assertion proposal"):
        resolve_assertion(proposal, bad)


def test_projection_is_order_independent_and_every_operational_entry_is_fully_linked():
    pack = _pack("grounded_claim:a", "grounded_claim:b", "grounded_claim:c")
    first = _accepted(pack)
    second = _accepted(
        pack,
        subject="grounded_claim:b",
        object_="grounded_claim:c",
        supports=("grounded_claim:b", "grounded_claim:c"),
        origins=("source:b", "source:c"),
    )
    forward = build_projection(
        product_id=pack.product_id,
        as_of=AS_OF,
        evidence_pack=pack,
        assertions=[first, second],
    )
    reverse = build_projection(
        product_id=pack.product_id,
        as_of=AS_OF,
        evidence_pack=pack,
        assertions=[second, first],
    )
    assert forward == reverse
    assert all(entry.status is BeliefStatus.SUPPORTED for entry in forward.entries)
    assert all(
        entry.operational
        and entry.accepted_assertion_id
        and entry.assertion_revision_id
        and entry.review_id
        and entry.supporting_evidence_refs
        for entry in forward.entries
    )


def test_reciprocal_and_mutually_exclusive_assertions_remain_contested():
    pack = _pack("grounded_claim:a", "grounded_claim:b")
    forward = _accepted(pack, relation=EpistemicRelation.SUPERSEDES)
    reverse = _accepted(
        pack,
        relation=EpistemicRelation.SUPERSEDES,
        subject="grounded_claim:b",
        object_="grounded_claim:a",
    )
    reciprocal = build_projection(
        product_id=pack.product_id,
        as_of=AS_OF,
        evidence_pack=pack,
        assertions=[reverse, forward],
    )
    assert {entry.status for entry in reciprocal.entries} == {BeliefStatus.CONTESTED}
    assert all(not entry.operational for entry in reciprocal.entries)
    assert all("reciprocal_directional_assertion" in entry.degraded_reasons for entry in reciprocal.entries)

    corroborates = _accepted(pack)
    contradicts = _accepted(pack, relation=EpistemicRelation.CONTRADICTS)
    exclusive = build_projection(
        product_id=pack.product_id,
        as_of=AS_OF,
        evidence_pack=pack,
        assertions=[corroborates, contradicts],
    )
    assert {entry.status for entry in exclusive.entries} == {BeliefStatus.CONTESTED}
    assert all("mutually_exclusive_assertions" in entry.degraded_reasons for entry in exclusive.entries)


def test_unknown_time_remains_unknown_and_unknown_target_is_visible():
    pack = _pack("grounded_claim:a", "grounded_claim:b")
    assertion = _accepted(pack)
    assert assertion.validity.precision.value == "unknown"
    target = ProjectionTargetV1(subject=_endpoint("grounded_claim:a"), predicate="unobserved_property")
    projection = build_projection(
        product_id=pack.product_id,
        as_of=AS_OF,
        evidence_pack=pack,
        assertions=[assertion],
        targets=[target],
    )
    unknown = next(entry for entry in projection.entries if entry.predicate == "unobserved_property")
    assert unknown.status is BeliefStatus.UNKNOWN
    assert unknown.value is None
    assert unknown.missing_evidence == ("no_accepted_assertion_as_of",)


def test_bounded_pack_and_unavailable_evidence_degrade_visibly():
    pack = _pack("grounded_claim:a", candidate_count=2)
    assert pack.truncated is True
    assert pack.selected_count == 1
    assert pack.candidate_count == 2
    proposal = _proposal(pack, supports=("grounded_claim:a", "grounded_claim:b"))
    assertion = resolve_assertion(proposal, _review(proposal))
    projection = build_projection(
        product_id=pack.product_id,
        as_of=AS_OF,
        evidence_pack=pack,
        assertions=[assertion],
    )
    assert projection.entries[0].status is BeliefStatus.PROVISIONAL
    assert projection.entries[0].missing_evidence == ("grounded_claim:b",)
    assert "accepted_evidence_unavailable" in projection.entries[0].degraded_reasons
    assert "candidate_pack_truncated" in projection.degraded_reasons


def test_external_world_insight_and_inference_receipt_replay_exactly():
    pack = _pack("grounded_claim:a", "grounded_claim:b")
    proposal = _proposal(pack)
    counter = _counter(proposal, pack)
    assertion = resolve_assertion(proposal, _review(proposal, counter=counter), counterevidence=counter)
    text = "Independent reviewed material supports the shared production-capacity assessment."
    first = derive_external_world_insight(
        assertion_text=text,
        as_of=AS_OF,
        validity=TemporalScopeV1(),
        evidence_pack=pack,
        assertions=[assertion],
        counterevidence=counter,
        inference_route=InferenceRoute.DETERMINISTIC_RULE,
    )
    replay = derive_external_world_insight(
        assertion_text=text,
        as_of=AS_OF,
        validity=TemporalScopeV1(),
        evidence_pack=pack,
        assertions=[assertion],
        counterevidence=counter,
        inference_route=InferenceRoute.DETERMINISTIC_RULE,
    )
    assert first == replay
    assert first[0].insight_id.startswith("grounded_external_insight:")
    assert first[1].provider_usage.model_calls == 0
    with pytest.raises(BeliefProjectionError, match="renamed source claim"):
        derive_external_world_insight(
            assertion_text=pack.items[0].compact_content or "",
            as_of=AS_OF,
            validity=TemporalScopeV1(),
            evidence_pack=pack,
            assertions=[assertion],
            counterevidence=counter,
        )


def test_incremental_reopening_touches_only_affected_assertion_and_preserves_prior_revision():
    pack = _pack("grounded_claim:a", "grounded_claim:b", "grounded_claim:c")
    affected = _accepted(pack)
    unaffected = _accepted(
        pack,
        subject="grounded_claim:b",
        object_="grounded_claim:c",
        supports=("grounded_claim:b", "grounded_claim:c"),
        origins=("source:b", "source:c"),
    )
    prior = build_projection(
        product_id=pack.product_id,
        as_of=AS_OF,
        evidence_pack=pack,
        assertions=[affected, unaffected],
    )
    reopened, resulting, receipt = reopen_and_reproject(
        prior_projection=prior,
        evidence_pack=pack,
        assertions=[unaffected, affected],
        changed_input_refs=["grounded_claim:a"],
        reopened_at=datetime(2026, 8, 4, tzinfo=UTC),
        reasons=["new_source_version"],
    )
    assert len(reopened) == 1
    assert reopened[0].assertion_id == affected.assertion_id
    assert reopened[0].prior_revision_id == affected.revision_id
    assert reopened[0].disposition is ReviewDisposition.REOPENED
    assert receipt.affected_assertion_refs == (affected.assertion_id,)
    assert receipt.unaffected_assertion_refs == (unaffected.assertion_id,)
    assert resulting.revision == prior.revision + 1


def test_product_scope_changes_identity_and_foreign_projection_fails_closed():
    local_pack = _pack("grounded_claim:a", "grounded_claim:b")
    foreign_pack = _pack("grounded_claim:a", "grounded_claim:b", product_id="product:tp4-b")
    local = _proposal(local_pack)
    foreign = _proposal(foreign_pack)
    assert local.assertion_id() != foreign.assertion_id()
    with pytest.raises(BeliefProjectionError, match="cannot cross product scope"):
        build_projection(
            product_id=local_pack.product_id,
            as_of=AS_OF,
            evidence_pack=local_pack,
            assertions=[resolve_assertion(foreign, _review(foreign))],
        )


def test_legacy_assertion_resolver_identity_is_product_scoped_and_causal_gate_is_strict():
    local = RelationshipProposal(
        product_id="product:tp4-a",
        subject="grounded_claim:a",
        predicate="causes",
        object="grounded_claim:b",
        evidence_refs=["grounded_claim:a", "grounded_claim:b"],
        source_origin_ids=["source:a", "source:b"],
    )
    foreign = local.model_copy(update={"product_id": "product:tp4-b"})
    local_result = resolve_proposals([local], human_confirmed=set())
    foreign_result = resolve_proposals([foreign], human_confirmed=set())
    assert local_result[0].id != foreign_result[0].id
    assert local_result[0].status == "provisional"
    assert local_result[0].projection_eligible is False


def test_frozen_tp4_evaluation_replays_recorded_first_run_without_provider_usage():
    config = load_tp4_config()
    corpus = load_tp0_corpus()
    result = evaluate_tp4_belief_projection(corpus, config)
    recorded = TP4BeliefEvaluationResultV1.model_validate_json(
        (ROOT / "evaluations/results/state_engine_tp4_belief_projection_v1.json").read_text()
    )
    assert result == recorded
    assert result.passed is True
    assert result.cases_matched == result.cases_evaluated == 13
    assert result.deterministic_replay_matches == result.deterministic_replays == 13
    assert result.primary_model_calls == result.input_tokens == result.output_tokens == 0
    assert result.estimated_cost_usd == 0
    assert result.outcome_hash == "f09127fda74a31246c69eded4e78983f9a6678d770de2134082c21e5bd757bd0"


def test_frozen_tp4_evaluation_refuses_corpus_or_target_drift():
    config = load_tp4_config()
    corpus = load_tp0_corpus()
    changed = config.model_copy(update={"corpus_hash": "0" * 64})
    with pytest.raises(ValueError, match="different frozen TP0 corpus"):
        evaluate_tp4_belief_projection(corpus, changed)
    payload = json.loads((ROOT / "evaluations/fixtures/state_engine_tp4_belief_projection_v1.json").read_text())
    payload["expected_classifications"].pop("exact_replay_identical")
    changed_target = type(config).model_validate(payload)
    with pytest.raises(ValueError, match="case set"):
        evaluate_tp4_belief_projection(corpus, changed_target)


def test_frozen_evaluation_executes_the_real_projection(monkeypatch):
    import core.engine.grounded_state.belief_evaluation as evaluation

    def broken_projection(**_kwargs):
        raise RuntimeError("projection path was executed")

    monkeypatch.setattr(evaluation, "build_projection", broken_projection)
    with pytest.raises(RuntimeError, match="projection path was executed"):
        evaluation.evaluate_tp4_belief_projection(evaluation.load_tp0_corpus(), evaluation.load_tp4_config())


def test_projection_emits_world_state_and_preserves_superseded_history():
    pack = _pack("grounded_claim:old", "grounded_claim:new")
    old_proposal = _proposal(
        pack,
        relation=EpistemicRelation.SUPPORTS,
        subject="grounded_claim:old",
        object_="grounded_claim:new",
        supports=("grounded_claim:old",),
        origins=("source:rail",),
        belief_subject="entity:orchid-rail",
        belief_predicate="planned_station_count",
        belief_value=12,
        validity=TemporalScopeV1(
            valid_from=datetime(2026, 1, 1, tzinfo=UTC),
            valid_to=datetime(2026, 1, 1, 23, 59, 59, tzinfo=UTC),
            precision="range",
        ),
    )
    old = resolve_assertion(old_proposal, _review(old_proposal))
    new_proposal = _proposal(
        pack,
        relation=EpistemicRelation.SUPERSEDES,
        subject="grounded_claim:new",
        object_="grounded_claim:old",
        supports=("grounded_claim:new",),
        origins=("source:rail",),
        belief_subject="entity:orchid-rail",
        belief_predicate="planned_station_count",
        belief_value=10,
        supersedes_assertion_refs=(old.assertion_id,),
        validity=TemporalScopeV1(valid_from=datetime(2026, 1, 2, tzinfo=UTC), precision="range"),
    )
    new = resolve_assertion(new_proposal, _review(new_proposal))
    projection = build_projection(
        product_id=pack.product_id,
        as_of=pack.as_of,
        evidence_pack=pack,
        assertions=[new, old],
    )
    by_value = {entry.value: entry for entry in projection.entries}
    assert set(by_value) == {10, 12}
    assert all(entry.subject.record_id == "entity:orchid-rail" for entry in projection.entries)
    assert all(entry.predicate == "planned_station_count" for entry in projection.entries)
    assert by_value[12].status is BeliefStatus.SUPERSEDED
    assert by_value[12].superseding_assertion_refs == (new.assertion_id,)
    assert by_value[10].status is BeliefStatus.SUPPORTED


def test_truncated_evidence_pack_cannot_complete_causal_countersearch():
    pack = _pack("grounded_claim:a", "grounded_claim:b", candidate_count=3)
    proposal = _proposal(pack, relation=EpistemicRelation.CAUSES)
    counter = counterevidence_search(proposal, pack)
    assert counter.completed is False
    assert "evidence_pack_incomplete" in counter.missing_inputs
    assertion = resolve_assertion(
        proposal,
        _review(proposal, authority=ReviewAuthority.HUMAN, counter=counter),
        counterevidence=counter,
        evidence_pack=pack,
    )
    assert assertion.disposition is ReviewDisposition.PROPOSED
    assert "counterevidence_search_incomplete" in assertion.degraded_reasons
    forged_complete = _counter(proposal, pack)
    forged_result = resolve_assertion(
        proposal,
        _review(proposal, authority=ReviewAuthority.HUMAN, counter=forged_complete),
        counterevidence=forged_complete,
        evidence_pack=pack,
    )
    assert forged_result.disposition is ReviewDisposition.PROPOSED
    assert "evidence_pack_incomplete" in forged_result.degraded_reasons


def test_incremental_reprojection_preserves_unaffected_entry_material():
    prior_pack = _pack("grounded_claim:a", "grounded_claim:b", "grounded_claim:c")
    affected = _accepted(prior_pack)
    unaffected = _accepted(
        prior_pack,
        subject="grounded_claim:b",
        object_="grounded_claim:c",
        supports=("grounded_claim:b", "grounded_claim:c"),
        origins=("source:b", "source:c"),
    )
    prior = build_projection(
        product_id=prior_pack.product_id,
        as_of=prior_pack.as_of,
        evidence_pack=prior_pack,
        assertions=[affected, unaffected],
    )
    prior_unaffected = next(entry for entry in prior.entries if entry.assertion_revision_id == unaffected.revision_id)
    changed_pack = _pack("grounded_claim:a", "grounded_claim:b")
    _, resulting, receipt = reopen_and_reproject(
        prior_projection=prior,
        evidence_pack=changed_pack,
        assertions=[affected, unaffected],
        changed_input_refs=["grounded_claim:a"],
        reopened_at=datetime(2026, 8, 4, tzinfo=UTC),
        reasons=["source_version_changed"],
    )
    resulting_unaffected = next(
        entry for entry in resulting.entries if entry.assertion_revision_id == unaffected.revision_id
    )
    assert resulting_unaffected == prior_unaffected
    assert receipt.unaffected_assertion_refs == (unaffected.assertion_id,)


def test_external_insight_rejects_unrelated_counterreceipt_and_asof():
    pack = _pack("grounded_claim:a", "grounded_claim:b")
    assertion = _accepted(pack)
    foreign_pack = _pack("grounded_claim:c", "grounded_claim:d")
    foreign_proposal = _proposal(
        foreign_pack,
        subject="grounded_claim:c",
        object_="grounded_claim:d",
        supports=("grounded_claim:c", "grounded_claim:d"),
        origins=("source:c", "source:d"),
    )
    foreign_counter = _counter(foreign_proposal, foreign_pack)
    with pytest.raises(BeliefProjectionError, match="counterevidence search"):
        derive_external_world_insight(
            assertion_text="A derived assessment.",
            as_of=AS_OF,
            validity=TemporalScopeV1(),
            evidence_pack=pack,
            assertions=[assertion],
            counterevidence=foreign_counter,
        )


@pytest.mark.asyncio
async def test_bounded_projection_replay_loads_omitted_assertion_revisions():
    pack = _pack("grounded_claim:a", "grounded_claim:b", "grounded_claim:c")
    first = _accepted(pack)
    second = _accepted(
        pack,
        subject="grounded_claim:b",
        object_="grounded_claim:c",
        supports=("grounded_claim:b", "grounded_claim:c"),
        origins=("source:b", "source:c"),
    )
    projection = build_projection(
        product_id=pack.product_id,
        as_of=pack.as_of,
        evidence_pack=pack,
        assertions=[first, second],
        targets=[ProjectionTargetV1(subject=_endpoint("grounded_claim:a"), predicate="omitted_target")],
        max_entries=1,
    )
    assert any(reason.startswith("projection_target_bound:") for reason in projection.omissions)

    class Store:
        async def require(self, _model, stable_id, *, product_id):
            assert product_id == pack.product_id
            return {
                str(projection.projection_id): projection,
                str(pack.pack_id): pack,
                str(first.revision_id): first,
                str(second.revision_id): second,
            }[stable_id]

    service = BeliefStateProjectionService.__new__(BeliefStateProjectionService)
    service.store = Store()
    assert await service.replay_projection(str(projection.projection_id), product_id=pack.product_id) == projection


@pytest.mark.asyncio
async def test_projection_service_requires_and_persists_complete_lineage():
    pack = _pack("grounded_claim:a", "grounded_claim:b")
    proposal = _proposal(pack)
    review = _review(proposal)
    assertion = resolve_assertion(proposal, review)

    class Store:
        persisted = None

        async def persist_all(self, records):
            self.persisted = tuple(records)

    service = BeliefStateProjectionService.__new__(BeliefStateProjectionService)
    service.store = Store()
    service.freeze_related_evidence = AsyncMock(return_value=pack)
    with pytest.raises(BeliefProjectionError, match="proposal and review chain"):
        await service.project_related(
            "grounded_claim:a",
            product_id=pack.product_id,
            as_of=pack.as_of,
            assertions=[assertion],
            proposals=[],
            reviews=[],
        )
    projection = await service.project_related(
        "grounded_claim:a",
        product_id=pack.product_id,
        as_of=pack.as_of,
        assertions=[assertion],
        proposals=[proposal],
        reviews=[review],
    )
    assert service.store.persisted == (pack, proposal, review, assertion, projection)


@pytest.mark.asyncio
async def test_assertion_api_requires_an_explicit_matching_product_claim():
    from fastapi import HTTPException

    from core.engine.api.graph import get_assertion

    with pytest.raises(HTTPException) as exc_info:
        await get_assertion(
            "relationship_assertion:test",
            product="product:tp4-a",
            user={"sub": "user:legacy"},
        )
    assert exc_info.value.status_code == 404


def test_assertion_cli_forwards_required_product_scope(monkeypatch):
    from click.testing import CliRunner

    import core.engine.cli.commands.assertions as command

    captured = {}

    class Response:
        def raise_for_status(self):
            return None

        def json(self):
            return {"ok": True}

    def fake_get(url, **kwargs):
        captured.update(url=url, **kwargs)
        return Response()

    monkeypatch.setattr(command, "get_headers", lambda: {"Authorization": "Bearer test"})
    monkeypatch.setattr(command.httpx, "get", fake_get)
    result = CliRunner().invoke(
        command.assertion,
        ["relationship_assertion:test", "--product", "product:tp4-a"],
        obj={"url": "http://ace.test"},
    )
    assert result.exit_code == 0
    assert captured["params"] == {"product": "product:tp4-a"}
