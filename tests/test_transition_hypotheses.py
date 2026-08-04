from __future__ import annotations

from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest
from pydantic import ValidationError

from core.engine.grounded_state.belief_contracts import (
    BeliefStateProjectionV1,
    BoundedEvidencePackV1,
    EvidenceEndpointKind,
    EvidencePackItemV1,
    ProjectionAssertionEntryV1,
    ReviewAuthority,
    TypedEvidenceEndpointV1,
)
from core.engine.grounded_state.contracts import (
    BeliefStatus,
    CausalStrength,
    ProbabilityEstimateV1,
    SupportingEvidenceOriginV1,
    TemporalScopeV1,
    TransitionReviewState,
    canonical_hash,
)
from core.engine.grounded_state.transition_contracts import (
    ConditionOperator,
    ObservedTransitionOutcomeV1,
    StateAssignmentV1,
    StateConditionV1,
    StateValueType,
    StateVariableV1,
    TransitionDerivationRoute,
    TransitionHypothesisProposalV1,
    TransitionOutcomeDisposition,
    TransitionReviewV1,
    TransitionRuleKind,
    TransitionRuleV1,
    TransitionTriggerKind,
    TransitionTriggerV1,
)
from core.engine.grounded_state.transitions import (
    TransitionResolutionError,
    build_transition_branch_input,
    calibrate_transition,
    challenge_transition,
    resolve_transition,
    review_transition,
)

PRODUCT = "product:tp5"
AS_OF = datetime(2026, 8, 3, 12, tzinfo=UTC)


def _endpoint(record_id: str, *, product_id: str = PRODUCT) -> TypedEvidenceEndpointV1:
    kind = EvidenceEndpointKind.ENTITY if record_id.startswith("entity:") else EvidenceEndpointKind.CLAIM
    return TypedEvidenceEndpointV1(
        product_id=product_id,
        kind=kind,
        record_id=record_id,
        record_version="v1",
        content_hash=canonical_hash(record_id),
    )


def _pack(*refs: str, product_id: str = PRODUCT, truncated: bool = False) -> BoundedEvidencePackV1:
    items = tuple(
        EvidencePackItemV1(
            endpoint=_endpoint(ref, product_id=product_id),
            ingested_at=AS_OF - timedelta(hours=1),
            ace_created_at=AS_OF - timedelta(hours=1),
            source_id=f"source:{index}",
            publisher_id=f"publisher:{index}",
            compact_content=ref,
            candidate_rank=index,
        )
        for index, ref in enumerate(refs, start=1)
    )
    omitted = ("grounded_claim:omitted",) if truncated else ()
    return BoundedEvidencePackV1(
        product_id=product_id,
        as_of=AS_OF,
        query_hash=canonical_hash("tp5-query"),
        candidate_receipt_id="candidate_receipt:tp5",
        candidate_receipt_hash=canonical_hash("candidate-receipt"),
        resolver_policy_version="ace.grounded-state.candidate-resolver/v1",
        ontology_version="ace.grounded-state.ontology/v1",
        items=items,
        candidate_count=len(items) + len(omitted),
        selected_count=len(items),
        max_records=200,
        max_chars=64_000,
        selected_chars=sum(len(ref) for ref in refs),
        omitted_evidence_refs=omitted,
        omissions=("record_bound",) if truncated else (),
        truncated=truncated,
    )


def _projection(pack: BoundedEvidencePackV1, *, bypass: str = "absent") -> BeliefStateProjectionV1:
    subject = _endpoint("entity:chamber", product_id=pack.product_id)
    values = (("cooling_status", "active"), ("bypass_status", bypass))
    entries = tuple(
        ProjectionAssertionEntryV1(
            product_id=pack.product_id,
            as_of=AS_OF,
            subject=subject,
            predicate=predicate,
            value=value,
            validity=TemporalScopeV1(),
            status=BeliefStatus.SUPPORTED,
            operational=True,
            accepted_assertion_id=f"grounded_epistemic_assertion:{index}",
            assertion_revision_id=f"grounded_assertion_revision:{index}",
            review_id=f"grounded_assertion_review:{index}",
            evidence_pack_id=str(pack.pack_id),
            evidence_pack_hash=str(pack.pack_hash),
            supporting_evidence_refs=(pack.items[0].endpoint.record_id,),
            epistemic_confidence=0.9,
            ontology_version="ace.grounded-state.epistemic-ontology/v1",
            resolver_policy_version="ace.grounded-state.belief-resolver/v1",
        )
        for index, (predicate, value) in enumerate(values, start=1)
    )
    return BeliefStateProjectionV1(
        product_id=pack.product_id,
        as_of=AS_OF,
        evidence_pack_id=str(pack.pack_id),
        evidence_pack_hash=str(pack.pack_hash),
        ontology_version="ace.grounded-state.epistemic-ontology/v1",
        resolver_policy_version="ace.grounded-state.belief-resolver/v1",
        projection_policy_version="ace.grounded-state.belief-projection/v1",
        entries=entries,
        evaluated_assertion_refs=("grounded_epistemic_assertion:1", "grounded_epistemic_assertion:2"),
        assertion_revision_refs=("grounded_assertion_revision:1", "grounded_assertion_revision:2"),
    )


def _variable(
    predicate: str,
    values: tuple[str, ...],
    *,
    product_id: str = PRODUCT,
) -> StateVariableV1:
    return StateVariableV1(
        subject=_endpoint("entity:chamber", product_id=product_id),
        predicate=predicate,
        value_type=StateValueType.CATEGORICAL,
        allowed_values=values,
    )


def _proposal(
    pack: BoundedEvidencePackV1,
    projection: BeliefStateProjectionV1,
    *,
    strength: CausalStrength = CausalStrength.MECHANISTIC,
    supports: tuple[str, ...] | None = None,
    contrary: tuple[str, ...] = (),
    origins: tuple[SupportingEvidenceOriginV1, ...] = (),
) -> TransitionHypothesisProposalV1:
    support_refs = (
        supports
        if supports is not None
        else tuple(item.endpoint.record_id for item in pack.items if item.endpoint.record_id not in contrary)[:2]
    )
    bypass = _variable("bypass_status", ("absent", "present"), product_id=pack.product_id)
    return TransitionHypothesisProposalV1(
        product_id=pack.product_id,
        projection_id=str(projection.projection_id),
        projection_hash=str(projection.projection_hash),
        projection_entry_refs=tuple(str(entry.entry_id) for entry in projection.entries),
        evidence_pack_id=str(pack.pack_id),
        evidence_pack_hash=str(pack.pack_hash),
        as_of=AS_OF,
        source=StateConditionV1(
            variable=_variable("cooling_status", ("active", "inactive"), product_id=pack.product_id),
            operator=ConditionOperator.EQ,
            value="active",
        ),
        target=StateAssignmentV1(
            variable=_variable("temperature_trend", ("stable", "rising"), product_id=pack.product_id),
            value="rising",
        ),
        trigger=TransitionTriggerV1(
            kind=TransitionTriggerKind.ACTION,
            description="disconnect the cooling circuit",
            trigger_ref="action:disconnect-cooling",
        ),
        mechanism="Removing active cooling permits chamber temperature to rise after thermal lag"
        if strength in {CausalStrength.MECHANISTIC, CausalStrength.CAUSAL}
        else None,
        rules=(
            TransitionRuleV1(
                kind=TransitionRuleKind.PRECONDITION,
                condition=StateConditionV1(variable=bypass, operator=ConditionOperator.EQ, value="absent"),
                rationale="A bypass would preserve cooling flow",
                rule_source_ref="domain_rule:no-bypass",
            ),
        ),
        delay_min_seconds=60,
        delay_max_seconds=600,
        probability=ProbabilityEstimateV1(lower=0.6, expected=0.8, upper=0.95),
        causal_strength=strength,
        derivation_routes=(TransitionDerivationRoute.ACCEPTED_MECHANISM,)
        if strength is not CausalStrength.ASSOCIATIVE
        else (TransitionDerivationRoute.TEMPORAL_SEQUENCE,),
        supporting_evidence_refs=support_refs,
        contrary_evidence_refs=contrary,
        supporting_assertion_refs=("grounded_epistemic_assertion:1",),
        supporting_evidence_origins=origins,
        proposer_authority=ReviewAuthority.DETERMINISTIC_POLICY,
        proposer_ref="policy:tp5-test",
    )


def _resolved(
    *,
    bypass: str = "absent",
    strength: CausalStrength = CausalStrength.MECHANISTIC,
):
    pack = _pack("grounded_claim:state", "grounded_claim:mechanism")
    projection = _projection(pack, bypass=bypass)
    proposal = _proposal(pack, projection, strength=strength)
    challenge = challenge_transition(proposal, projection=projection, evidence_pack=pack)
    review = review_transition(
        proposal,
        challenge,
        disposition=TransitionReviewState.PROVISIONAL,
        authority=ReviewAuthority.DETERMINISTIC_POLICY,
        reviewer_ref="policy:tp5-test",
        reviewed_at=AS_OF,
        rationale="Mechanism and complete challenge support bounded provisional rollout use.",
    )
    revision = resolve_transition(proposal, challenge, review)
    return pack, projection, proposal, challenge, review, revision


def test_transition_contracts_are_extra_forbid_and_identity_sensitive():
    pack, projection, proposal, *_ = _resolved()
    with pytest.raises(ValidationError, match="Extra inputs are not permitted"):
        TransitionHypothesisProposalV1.model_validate({**proposal.model_dump(mode="python"), "truth": True})
    changed = proposal.model_copy(update={"delay_max_seconds": proposal.delay_max_seconds + 1, "proposal_id": None})
    changed = TransitionHypothesisProposalV1.model_validate(changed.model_dump(mode="python"))
    assert changed.proposal_id != proposal.proposal_id
    assert changed.hypothesis_id() != proposal.hypothesis_id()
    assert pack.product_id == projection.product_id == proposal.product_id


def test_mechanistic_transition_replays_and_freezes_identical_branch_inputs():
    _, projection, proposal, challenge, review, revision = _resolved()
    assert challenge.completed is True
    assert revision.review_state is TransitionReviewState.PROVISIONAL
    assert revision.rollout_eligible is True
    replayed = resolve_transition(proposal, challenge, review, created_at=revision.created_at)
    assert replayed == revision
    first = build_transition_branch_input(projection, revision)
    reverse_projection = projection.model_copy(update={"entries": tuple(reversed(projection.entries))})
    reverse_projection = BeliefStateProjectionV1.model_validate(reverse_projection.model_dump(mode="python"))
    second = build_transition_branch_input(reverse_projection, revision)
    assert first == second
    assert first.applicable is True


def test_truncated_challenge_fails_closed_before_rollout_review():
    pack = _pack("grounded_claim:state", "grounded_claim:mechanism", truncated=True)
    projection = _projection(pack)
    proposal = _proposal(pack, projection)
    challenge = challenge_transition(proposal, projection=projection, evidence_pack=pack)
    assert challenge.completed is False
    assert "evidence_pack_truncated" in challenge.omissions
    with pytest.raises(TransitionResolutionError, match="incomplete challenge"):
        review_transition(
            proposal,
            challenge,
            disposition=TransitionReviewState.PROVISIONAL,
            authority=ReviewAuthority.DETERMINISTIC_POLICY,
            reviewer_ref="policy:tp5-test",
            reviewed_at=AS_OF,
            rationale="must fail closed",
        )


def test_completed_challenge_cannot_claim_search_coverage_it_did_not_execute():
    pack, projection, proposal, challenge, *_ = _resolved()
    payload = challenge.model_dump(mode="python", exclude={"receipt_id", "receipt_hash"})
    first_ref = challenge.searched_evidence_refs[:1]
    payload.update(
        {
            "searched_evidence_refs": first_ref,
            "supporting_evidence_refs": first_ref,
            "records_searched": 1,
            "pack_selected_count": pack.selected_count,
            "completed": True,
        }
    )
    with pytest.raises(ValidationError, match="cannot hide incomplete"):
        type(challenge).model_validate(payload)
    assert projection.product_id == proposal.product_id


def test_contrary_episode_remains_contested_and_rollout_ineligible():
    pack = _pack("grounded_claim:state", "grounded_claim:mechanism", "grounded_claim:bypass")
    projection = _projection(pack)
    proposal = _proposal(pack, projection, contrary=("grounded_claim:bypass",))
    challenge = challenge_transition(proposal, projection=projection, evidence_pack=pack)
    review = review_transition(
        proposal,
        challenge,
        disposition=TransitionReviewState.CONTESTED,
        authority=ReviewAuthority.HUMAN,
        reviewer_ref="human:reviewer",
        reviewed_at=AS_OF,
        rationale="A bypass episode violates the unqualified mechanism.",
    )
    revision = resolve_transition(proposal, challenge, review)
    assert revision.review_state is TransitionReviewState.CONTESTED
    assert revision.contrary_evidence_refs == ("grounded_claim:bypass",)
    assert revision.rollout_eligible is False


def test_temporal_association_cannot_become_accepted_transition():
    pack = _pack("grounded_claim:first", "grounded_claim:second")
    projection = _projection(pack)
    proposal = _proposal(pack, projection, strength=CausalStrength.ASSOCIATIVE)
    challenge = challenge_transition(proposal, projection=projection, evidence_pack=pack)
    review = review_transition(
        proposal,
        challenge,
        disposition=TransitionReviewState.REJECTED,
        authority=ReviewAuthority.DETERMINISTIC_POLICY,
        reviewer_ref="policy:causality",
        reviewed_at=AS_OF,
        rationale="Temporal order is evidence, not a transition mechanism.",
    )
    revision = resolve_transition(proposal, challenge, review)
    assert revision.review_state is TransitionReviewState.REJECTED
    assert revision.rollout_eligible is False
    with pytest.raises(TransitionResolutionError, match="temporal association"):
        review_transition(
            proposal,
            challenge,
            disposition=TransitionReviewState.ACCEPTED,
            authority=ReviewAuthority.HUMAN,
            reviewer_ref="human:reviewer",
            reviewed_at=AS_OF,
            rationale="Sequence cannot be promoted by disposition alone.",
        )


def test_causal_acceptance_requires_independent_source_origins():
    pack = _pack("grounded_claim:study", "grounded_claim:trial")
    projection = _projection(pack)
    proposal = _proposal(
        pack,
        projection,
        strength=CausalStrength.CAUSAL,
        origins=(
            SupportingEvidenceOriginV1(
                evidence_ref="grounded_claim:study",
                source_ref="source:shared",
                origin_group="origin:shared",
            ),
            SupportingEvidenceOriginV1(
                evidence_ref="grounded_claim:trial",
                source_ref="source:shared",
                origin_group="origin:shared",
            ),
        ),
    )
    challenge = challenge_transition(proposal, projection=projection, evidence_pack=pack)
    review = review_transition(
        proposal,
        challenge,
        disposition=TransitionReviewState.ACCEPTED,
        authority=ReviewAuthority.HUMAN,
        reviewer_ref="human:reviewer",
        reviewed_at=AS_OF,
        rationale="Human review cannot manufacture source independence.",
    )
    with pytest.raises(ValidationError, match="independent sources"):
        resolve_transition(proposal, challenge, review)


def test_independently_sourced_human_review_can_accept_causal_transition():
    pack = _pack("grounded_claim:study", "grounded_claim:trial")
    projection = _projection(pack)
    proposal = _proposal(
        pack,
        projection,
        strength=CausalStrength.CAUSAL,
        origins=(
            SupportingEvidenceOriginV1(
                evidence_ref="grounded_claim:study",
                source_ref="source:study",
                origin_group="origin:study",
            ),
            SupportingEvidenceOriginV1(
                evidence_ref="grounded_claim:trial",
                source_ref="source:trial",
                origin_group="origin:trial",
            ),
        ),
    )
    challenge = challenge_transition(proposal, projection=projection, evidence_pack=pack)
    review = review_transition(
        proposal,
        challenge,
        disposition=TransitionReviewState.ACCEPTED,
        authority=ReviewAuthority.HUMAN,
        reviewer_ref="human:reviewer",
        reviewed_at=AS_OF,
        rationale="Independent mechanism evidence passed human causal review.",
    )
    revision = resolve_transition(proposal, challenge, review)
    assert revision.review_state is TransitionReviewState.ACCEPTED
    assert revision.rollout_eligible is True


def test_deterministic_precondition_blocks_inapplicable_transition():
    _, projection, _, _, _, revision = _resolved(bypass="present")
    branch_input = build_transition_branch_input(projection, revision)
    assert branch_input.applicable is False
    assert any(reason.startswith("precondition_not_satisfied") for reason in branch_input.blocked_reasons)
    assert revision.rollout_eligible is True


def test_wrong_typed_starting_state_degrades_instead_of_crashing_rule_execution():
    _, projection, _, _, _, revision = _resolved(bypass=1)
    branch_input = build_transition_branch_input(projection, revision)
    assert branch_input.applicable is False
    assert any(reason.startswith("precondition_input_missing") for reason in branch_input.missing_inputs)
    assert any(evaluation.satisfied is None for evaluation in branch_input.rule_evaluations)


def test_impossible_target_value_is_rejected_by_typed_invariant():
    with pytest.raises(ValidationError, match="outside the declared categorical domain"):
        StateAssignmentV1(
            variable=_variable("temperature_trend", ("stable", "rising")),
            value="impossible",
        )


def test_later_outcome_calibrates_without_rewriting_revision():
    pack, _, _, _, _, revision = _resolved()
    revision_hash = revision.revision_hash
    outcome = ObservedTransitionOutcomeV1(
        product_id=PRODUCT,
        hypothesis_id=revision.hypothesis_id,
        transition_revision_id=str(revision.revision_id),
        transition_revision_hash=str(revision.revision_hash),
        observed_at=AS_OF + timedelta(days=1),
        disposition=TransitionOutcomeDisposition.CONTRADICTED,
        observed_target=StateAssignmentV1(
            variable=revision.target.variable,
            value="stable",
        ),
        evidence_pack_id=str(pack.pack_id),
        evidence_pack_hash=str(pack.pack_hash),
        evidence_refs=("grounded_claim:state",),
        forecast_ref="decision_prediction:tp5-test",
        forecast_resolution_ref="prediction_outcome:tp5-test",
        authority=ReviewAuthority.HUMAN,
        observer_ref="human:observer",
        rationale="The chamber remained stable through the horizon.",
    )
    calibration = calibrate_transition(revision, [outcome], calibrated_at=AS_OF + timedelta(days=2))
    assert revision.revision_hash == revision_hash
    assert calibration.transition_revision_hash == revision_hash
    assert calibration.calibrated_probability.expected < revision.probability.expected


def test_calibration_rejects_an_outcome_that_is_not_later_than_the_revision():
    pack, _, _, _, _, revision = _resolved()
    outcome = ObservedTransitionOutcomeV1(
        product_id=PRODUCT,
        hypothesis_id=revision.hypothesis_id,
        transition_revision_id=str(revision.revision_id),
        transition_revision_hash=str(revision.revision_hash),
        observed_at=revision.as_of,
        disposition=TransitionOutcomeDisposition.UNRESOLVED,
        evidence_pack_id=str(pack.pack_id),
        evidence_pack_hash=str(pack.pack_hash),
        evidence_refs=("grounded_claim:state",),
        authority=ReviewAuthority.HUMAN,
        observer_ref="human:observer",
        rationale="This same-instant observation cannot calibrate a frozen revision.",
    )
    with pytest.raises(TransitionResolutionError, match="observed after the revision"):
        calibrate_transition(revision, [outcome], calibrated_at=AS_OF + timedelta(days=1))


def test_superseded_and_stale_revisions_preserve_prior_lineage():
    pack, projection, proposal, _, _, first = _resolved()
    second_proposal = proposal.model_copy(update={"proposal_id": None, "proposer_ref": "policy:tp5-revision-2"})
    second_proposal = TransitionHypothesisProposalV1.model_validate(second_proposal.model_dump(mode="python"))
    assert second_proposal.hypothesis_id() == first.hypothesis_id
    second_challenge = challenge_transition(second_proposal, projection=projection, evidence_pack=pack)
    second_review = review_transition(
        second_proposal,
        second_challenge,
        disposition=TransitionReviewState.SUPERSEDED,
        authority=ReviewAuthority.HUMAN,
        reviewer_ref="human:reviewer",
        reviewed_at=AS_OF + timedelta(seconds=1),
        rationale="A newer exact revision retires the prior hypothesis state.",
    )
    second = resolve_transition(
        second_proposal,
        second_challenge,
        second_review,
        revision=2,
        prior_revision=first,
        superseded_revision_refs=(str(first.revision_id),),
    )
    third_proposal = proposal.model_copy(update={"proposal_id": None, "proposer_ref": "policy:tp5-revision-3"})
    third_proposal = TransitionHypothesisProposalV1.model_validate(third_proposal.model_dump(mode="python"))
    third_challenge = challenge_transition(third_proposal, projection=projection, evidence_pack=pack)
    third_review = review_transition(
        third_proposal,
        third_challenge,
        disposition=TransitionReviewState.STALE,
        authority=ReviewAuthority.DETERMINISTIC_POLICY,
        reviewer_ref="policy:freshness",
        reviewed_at=AS_OF + timedelta(seconds=2),
        rationale="The mechanism review expired under the frozen freshness policy.",
    )
    stale_at = AS_OF + timedelta(seconds=2)
    third = resolve_transition(
        third_proposal,
        third_challenge,
        third_review,
        revision=3,
        prior_revision=second,
        stale_at=stale_at,
    )
    assert first.review_state is TransitionReviewState.PROVISIONAL
    assert second.prior_revision_id == first.revision_id
    assert second.review_state is TransitionReviewState.SUPERSEDED
    assert third.prior_revision_id == second.revision_id
    assert third.review_state is TransitionReviewState.STALE
    assert third.stale_at == stale_at


def test_transition_material_fails_closed_across_product_scope():
    pack = _pack("grounded_claim:state", "grounded_claim:mechanism")
    projection = _projection(pack)
    proposal = _proposal(pack, projection)
    foreign_pack = _pack(
        "grounded_claim:state",
        "grounded_claim:mechanism",
        product_id="product:foreign",
    )
    with pytest.raises(TransitionResolutionError, match="cross product"):
        challenge_transition(proposal, projection=projection, evidence_pack=foreign_pack)


def test_model_cannot_reject_or_accept_transition_lifecycle():
    _, _, proposal, challenge, *_ = _resolved()
    with pytest.raises(ValidationError, match="cannot govern"):
        TransitionReviewV1(
            product_id=PRODUCT,
            proposal_id=str(proposal.proposal_id),
            hypothesis_id=proposal.hypothesis_id(),
            reviewed_material_hash=proposal.review_material_hash(),
            challenge_receipt_id=str(challenge.receipt_id),
            challenge_receipt_hash=str(challenge.receipt_hash),
            disposition=TransitionReviewState.REJECTED,
            authority=ReviewAuthority.MODEL,
            reviewer_ref="model:test",
            reviewed_at=AS_OF,
            rationale="model output is non-authoritative",
        )


def test_frozen_tp5_evaluation_matches_recorded_provider_free_result():
    from core.engine.grounded_state.transition_evaluation import (
        TP5TransitionEvaluationResultV1,
        evaluate_tp5_transition_dynamics,
        load_tp0_corpus,
        load_tp5_config,
    )

    root = Path(__file__).parents[1]
    result = evaluate_tp5_transition_dynamics(load_tp0_corpus(), load_tp5_config())
    recorded = TP5TransitionEvaluationResultV1.model_validate_json(
        (root / "evaluations/results/state_engine_tp5_transition_dynamics_v1.json").read_text()
    )
    assert result == recorded
    assert result.passed is True
    assert result.cases_matched == result.cases_evaluated == 8
    assert result.deterministic_replay_matches == result.deterministic_replays == 8
    assert result.primary_model_calls == result.input_tokens == result.output_tokens == 0
    assert result.outcome_hash == "233c24afb28a273c057c5adaf988dc77824caef267e3442ae380405b69989a15"


def test_frozen_tp5_evaluation_refuses_corpus_or_target_drift():
    from core.engine.grounded_state.transition_evaluation import (
        TP5TransitionEvaluationConfigV1,
        evaluate_tp5_transition_dynamics,
        load_tp0_corpus,
        load_tp5_config,
    )

    corpus = load_tp0_corpus()
    config = load_tp5_config()
    with pytest.raises(ValueError, match="different frozen TP0 corpus"):
        evaluate_tp5_transition_dynamics(corpus, config.model_copy(update={"corpus_hash": "0" * 64}))
    payload = config.model_dump(mode="python")
    payload["expected_cases"].pop("price_reaction_not_causal_fact")
    with pytest.raises(ValidationError, match="exactly eight"):
        TP5TransitionEvaluationConfigV1.model_validate(payload)


def test_frozen_tp5_evaluation_executes_real_transition_resolver(monkeypatch):
    import core.engine.grounded_state.transition_evaluation as evaluation

    def broken_resolver(*_args, **_kwargs):
        raise RuntimeError("transition resolver path was executed")

    monkeypatch.setattr(evaluation, "resolve_transition", broken_resolver)
    with pytest.raises(RuntimeError, match="transition resolver path was executed"):
        evaluation.evaluate_tp5_transition_dynamics(evaluation.load_tp0_corpus(), evaluation.load_tp5_config())


def test_tp5_schema_and_current_readiness_closeout_remain_explicit():
    root = Path(__file__).parents[1]
    migration = (root / "core/schema/v165_state_engine_tp5_transition_dynamics.surql").read_text()
    roadmap = (root / "docs/design/state-engine-roadmap.md").read_text()
    public_roadmap = (root / "ROADMAP.md").read_text()
    assert migration.count("DEFINE TABLE IF NOT EXISTS grounded_transition_") == 7
    assert migration.count("FOR update NONE, FOR delete NONE") == 7
    assert "TP5 is complete on the current worktree" in roadmap
    assert "233c24afb28a273c057c5adaf988dc77824caef267e3442ae380405b69989a15" in roadmap
    assert "| K2 | ready |" in public_roadmap
    assert "State Engine K1-K3 readiness" in public_roadmap
    assert "TP8 closes the single-node scale" in public_roadmap
