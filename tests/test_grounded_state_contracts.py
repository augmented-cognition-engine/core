from __future__ import annotations

import copy
import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path

import pytest
from pydantic import ValidationError

from core.engine.grounded_state import (
    REQUIRED_MAINTAINER_REVIEW_CASE_KEYS,
    BeliefStateAssertionV1,
    CausalStrength,
    ConsequenceRolloutRequestV1,
    CorpusMaturity,
    GroundedEvidenceRecordV1,
    ProbabilityEstimateV1,
    ReferenceCategory,
    RelationshipEndpointKind,
    ReviewDecision,
    RolloutBranchInputV1,
    RolloutBranchKind,
    StateRecordMeaning,
    TemporalReferenceCaseV1,
    TemporalReferenceCorpusV1,
    TemporalScopeV1,
    TimePrecision,
    TransitionHypothesisV1,
    TransitionReviewState,
    canonical_hash,
    evaluate_temporal_reference_corpus,
    evaluate_temporal_reference_file,
)

FIXTURE = Path(__file__).parent / "fixtures" / "grounded_state" / "temporal_reference_candidate_v1.json"
ROADMAP = Path(__file__).parents[1] / "docs" / "design" / "state-engine-roadmap.md"
OWNER_REVIEW = Path(__file__).parents[1] / "docs" / "design" / "state-engine-tp0-owner-review-v1.md"
UTC = timezone.utc


def _evidence(**overrides):
    data = {
        "product_id": "product:test",
        "kind": "claim",
        "external_id": "source-item-1",
        "source_id": "source:test",
        "source_version": "v1",
        "content": "Company Alpha has direct exposure.",
        "temporal": {"valid_from": "2026-01-01T00:00:00Z", "precision": "day"},
        "ingested_at": "2026-01-02T00:00:00Z",
        "entity_refs": ["entity:alpha"],
        "confidence": 0.9,
    }
    data.update(overrides)
    if "content_hash" not in overrides and data["content"] is not None:
        data["content_hash"] = hashlib.sha256(data["content"].encode("utf-8")).hexdigest()
    return GroundedEvidenceRecordV1.model_validate(data)


def _belief(**overrides):
    data = {
        "product_id": "product:test",
        "as_of": "2026-01-02T00:00:00Z",
        "subject": "entity:alpha",
        "predicate": "has_direct_exposure",
        "value": True,
        "validity": {"valid_from": "2026-01-01T00:00:00Z", "precision": "day"},
        "status": "supported",
        "epistemic_confidence": 0.8,
        "source_confidence": 0.9,
        "freshness": 0.95,
        "supporting_evidence_refs": ["grounded_evidence:a"],
        "ontology_version": "ace.grounded-state.ontology/v1",
        "resolver_policy_version": "ace.grounded-state.resolver/v1",
    }
    data.update(overrides)
    return BeliefStateAssertionV1.model_validate(data)


def _transition(**overrides):
    data = {
        "product_id": "product:test",
        "revision": "v1",
        "source_state": {"subject": "entity:alpha", "predicate": "exposure", "value": "active"},
        "target_state": {"subject": "entity:alpha", "predicate": "exposure", "value": "exited"},
        "trigger": "completed divestiture",
        "mechanism": "Asset transfer removes direct operating exposure.",
        "preconditions": ["transaction closes"],
        "constraints": ["indirect credit exposure is modeled separately"],
        "delay_min_seconds": 0,
        "delay_max_seconds": 86_400,
        "probability": {"lower": 0.6, "expected": 0.8, "upper": 0.9},
        "causal_strength": "mechanistic",
        "review_state": "provisional",
        "supporting_evidence_refs": ["grounded_evidence:a"],
        "ontology_version": "ace.grounded-state.ontology/v1",
        "policy_version": "ace.grounded-state.transition-policy/v1",
    }
    data.update(overrides)
    if data["causal_strength"] == "causal" and "reviewed_material_hash" not in overrides:
        data["reviewed_material_hash"] = TransitionHypothesisV1.review_material_hash_for(data)
    return TransitionHypothesisV1.model_validate(data)


def _rollout(**overrides):
    transition_id = _transition().hypothesis_id()
    data = {
        "product_id": "product:test",
        "starting_state_id": "grounded_state:start",
        "starting_state_hash": "b" * 64,
        "evidence_pack_id": "evidence_pack:test",
        "evidence_pack_hash": "c" * 64,
        "as_of": "2026-01-02T00:00:00Z",
        "horizon": "2026-07-02T00:00:00Z",
        "branches": [
            {
                "branch_id": "branch:no-action",
                "kind": "no_action",
                "transition_hypothesis_ids": [],
            },
            {
                "branch_id": "branch:divest",
                "kind": "action",
                "action": "Complete the divestiture",
                "transition_hypothesis_ids": [transition_id],
            },
        ],
        "assumptions": ["market access remains available"],
        "constraints": ["no forced sale below the declared floor"],
        "policy_version": "ace.grounded-state.rollout-policy/v1",
        "seed": 17,
    }
    data.update(overrides)
    return ConsequenceRolloutRequestV1.model_validate(data)


def _payload() -> dict:
    return json.loads(FIXTURE.read_text(encoding="utf-8"))


def _case(corpus: TemporalReferenceCorpusV1, case_key: str):
    return next(case for case in corpus.cases if case.case_key == case_key)


def _reverse_mapping_keys(value):
    if isinstance(value, dict):
        return {key: _reverse_mapping_keys(item) for key, item in reversed(tuple(value.items()))}
    if isinstance(value, list):
        return [_reverse_mapping_keys(item) for item in value]
    return value


def _change_first_evidence_content(payload: dict) -> None:
    records = [item["record"] for item in payload["cases"][0]["evidence"]]
    for record in records:
        record["content"] += " Materially revised."
        record["content_hash"] = hashlib.sha256(record["content"].encode("utf-8")).hexdigest()


def test_temporal_scope_fails_closed_for_unknown_exact_and_range_shapes():
    with pytest.raises(ValidationError, match="unknown precision"):
        TemporalScopeV1(occurred_at=datetime(2026, 1, 1, tzinfo=UTC))
    with pytest.raises(ValidationError, match="exact precision"):
        TemporalScopeV1(valid_from=datetime(2026, 1, 1, tzinfo=UTC), precision=TimePrecision.EXACT)
    with pytest.raises(ValidationError, match="range precision"):
        TemporalScopeV1(occurred_at=datetime(2026, 1, 1, tzinfo=UTC), precision=TimePrecision.RANGE)


def test_known_and_inferred_time_require_honest_provenance():
    with pytest.raises(ValidationError, match="requires an instant or interval"):
        TemporalScopeV1(precision=TimePrecision.DAY)
    with pytest.raises(ValidationError, match="requires provenance references"):
        TemporalScopeV1(occurred_at=datetime(2026, 1, 1, tzinfo=UTC), precision=TimePrecision.INFERRED)
    inferred = TemporalScopeV1(
        occurred_at=datetime(2026, 1, 1, tzinfo=UTC),
        precision=TimePrecision.INFERRED,
        inferred_from=["grounded_evidence:source"],
    )
    assert inferred.inferred_from == ("grounded_evidence:source",)


def test_evidence_identity_is_exact_replay_safe_and_product_scoped():
    first = _evidence(entity_refs=["entity:z", "entity:a", "entity:a"])
    replay = _evidence(entity_refs=["entity:a", "entity:z"])
    foreign = _evidence(product_id="product:other", entity_refs=["entity:a", "entity:z"])
    changed = _evidence(source_version="v2")

    assert first.entity_refs == ("entity:a", "entity:z")
    assert first.evidence_id() == replay.evidence_id()
    assert first.evidence_id() != foreign.evidence_id()
    assert first.evidence_id() != changed.evidence_id()


def test_supplied_evidence_content_must_match_its_hash():
    with pytest.raises(ValidationError, match="content_hash must equal"):
        _evidence(content_hash="0" * 64)


def test_evidence_keeps_event_publication_ingestion_and_extraction_time_separate():
    evidence = _evidence(
        temporal={"occurred_at": "2026-01-01T12:00:00Z", "precision": "exact"},
        published_at="2026-01-01T13:00:00Z",
        ingested_at="2026-01-01T14:00:00Z",
        extracted_at="2026-01-01T15:00:00Z",
        extraction={"extractor": "rules", "extractor_version": "v1"},
    )
    assert len({evidence.temporal.occurred_at, evidence.published_at, evidence.ingested_at, evidence.extracted_at}) == 4


def test_belief_projection_normalizes_refs_and_separates_confidence_meanings():
    forward = _belief(supporting_evidence_refs=["grounded_evidence:b", "grounded_evidence:a"])
    reverse = _belief(supporting_evidence_refs=["grounded_evidence:a", "grounded_evidence:b"])

    assert forward.projection_hash() == reverse.projection_hash()
    assert forward.epistemic_confidence == 0.8
    assert forward.source_confidence == 0.9
    assert forward.freshness == 0.95


def test_unknown_stale_and_superseded_beliefs_have_distinct_validation():
    unknown = _belief(
        status="unknown",
        value=None,
        epistemic_confidence=0,
        source_confidence=None,
        freshness=None,
        supporting_evidence_refs=[],
        missing_reason="No source establishes the applicable interval.",
    )
    stale = _belief(status="stale", status_reason="The last observation is outside freshness policy.")
    superseded = _belief(status="superseded", superseding_assertion_refs=["grounded_state:new"])

    assert unknown.status.value == "unknown"
    assert stale.status.value == "stale"
    assert superseded.status.value == "superseded"
    with pytest.raises(ValidationError, match="zero epistemic confidence"):
        _belief(
            status="unknown",
            value=None,
            source_confidence=None,
            freshness=None,
            supporting_evidence_refs=[],
            missing_reason="Missing.",
        )


def test_contested_belief_requires_support_and_counterevidence():
    with pytest.raises(ValidationError, match="supporting and contradicting evidence"):
        _belief(status="contested")


def test_probability_intervals_and_causal_transitions_fail_closed():
    with pytest.raises(ValidationError, match="lower <= expected <= upper"):
        ProbabilityEstimateV1(lower=0.8, expected=0.2, upper=0.9)
    with pytest.raises(ValidationError, match="accepted human confirmation"):
        _transition(causal_strength="causal")

    causal = _transition(
        causal_strength=CausalStrength.CAUSAL,
        review_state=TransitionReviewState.ACCEPTED,
        human_confirmed=True,
        human_review_ref="review:maintainer-17",
        supporting_evidence_origins=[
            {
                "evidence_ref": "grounded_evidence:a",
                "source_ref": "source:independent-a",
                "origin_group": "origin:independent-a",
            },
            {
                "evidence_ref": "grounded_evidence:b",
                "source_ref": "source:independent-b",
                "origin_group": "origin:independent-b",
            },
        ],
        source_independence_review_ref="review:source-independence-17",
        supporting_evidence_refs=["grounded_evidence:a", "grounded_evidence:b"],
    )
    assert causal.causal_strength is CausalStrength.CAUSAL

    with pytest.raises(ValidationError, match="independent source origins"):
        _transition(
            causal_strength=CausalStrength.CAUSAL,
            review_state=TransitionReviewState.ACCEPTED,
            human_confirmed=True,
            human_review_ref="review:maintainer-18",
            supporting_evidence_origins=[
                {
                    "evidence_ref": "grounded_evidence:a",
                    "source_ref": "source:one-origin",
                    "origin_group": "origin:one-origin",
                },
                {
                    "evidence_ref": "grounded_evidence:b",
                    "source_ref": "source:one-origin",
                    "origin_group": "origin:one-origin",
                },
            ],
            source_independence_review_ref="review:source-independence-18",
            supporting_evidence_refs=["grounded_evidence:a", "grounded_evidence:b"],
        )

    changed_sources = causal.model_dump(mode="json")
    changed_sources["supporting_evidence_origins"][0]["source_ref"] = "source:changed"
    with pytest.raises(ValidationError, match="exact transition review-material hash"):
        TransitionHypothesisV1.model_validate(changed_sources)


def test_transition_identity_changes_with_material_mechanism_and_policy_semantics():
    original = _transition()
    changed_mechanism = _transition(mechanism="A different inspectable mechanism.")
    changed_policy = _transition(policy_version="ace.grounded-state.transition-policy/v2")
    foreign = _transition(product_id="product:other")

    assert (
        len(
            {
                original.hypothesis_id(),
                changed_mechanism.hypothesis_id(),
                changed_policy.hypothesis_id(),
                foreign.hypothesis_id(),
            }
        )
        == 4
    )


def test_rollout_requires_one_baseline_and_a_real_alternative():
    valid = _rollout()
    assert valid.branches[0].branch_id == "branch:divest"
    assert valid.branches[1].kind is RolloutBranchKind.NO_ACTION
    assert valid.branches[1].transition_hypothesis_ids == ()

    action_only = [
        RolloutBranchInputV1(
            branch_id="branch:one",
            kind="action",
            action="Act",
            transition_hypothesis_ids=[_transition().hypothesis_id()],
        ),
        RolloutBranchInputV1(
            branch_id="branch:two",
            kind="alternative",
            action="Act differently",
            transition_hypothesis_ids=[_transition().hypothesis_id()],
        ),
    ]
    with pytest.raises(ValidationError, match="exactly one no_action"):
        _rollout(branches=action_only)


def test_rollout_identity_is_order_independent_and_material_input_sensitive():
    first = _rollout()
    reverse = _rollout(branches=list(reversed(first.branches)))
    degraded = _rollout(unavailable_inputs=["counterfactual_market_data"])
    foreign = _rollout(product_id="product:other")

    assert first.request_hash() == reverse.request_hash()
    assert first.rollout_id() == reverse.rollout_id()
    assert first.request_hash() != degraded.request_hash()
    assert first.request_hash() != foreign.request_hash()


def test_frozen_corpus_validates_all_40_cases_and_required_categories():
    corpus = TemporalReferenceCorpusV1.model_validate(_payload())

    assert corpus.maturity is CorpusMaturity.FROZEN
    assert len(corpus.cases) == 40
    assert set(corpus.required_review_case_keys) == REQUIRED_MAINTAINER_REVIEW_CASE_KEYS
    assert set(corpus.category_counts()) == {category.value for category in ReferenceCategory}
    for item in corpus.cases:
        assert item.evidence
        assert item.as_of_times
        assert item.expected.beliefs
        assert item.expected.relationships
        assert item.expected.prohibited_relationships
        assert item.rationale
        evidence_by_key = {evidence.input_key: evidence.record for evidence in item.evidence}
        for belief in item.expected.beliefs:
            cited = (*belief.supporting_evidence_keys, *belief.contradicting_evidence_keys)
            assert all(evidence_by_key[key].ingested_at <= belief.as_of for key in cited)


def test_relationship_expectations_separate_semantic_endpoints_from_provenance():
    corpus = TemporalReferenceCorpusV1.model_validate(_payload())
    restatement = _case(corpus, "restatement_not_corroboration").expected.relationships[0]
    alias = _case(corpus, "entity_alias_same_identity").expected.relationships[0]
    causal = _case(corpus, "causal_claim_requires_human_gate").expected.relationships[0]

    assert restatement.subject.kind is RelationshipEndpointKind.EVIDENCE
    assert restatement.object is not None and restatement.object.kind is RelationshipEndpointKind.EVIDENCE
    assert set(restatement.supporting_evidence_keys) == {"origin", "wire"}
    assert alias.subject.kind is RelationshipEndpointKind.MENTION
    assert alias.object is not None and alias.object.kind is RelationshipEndpointKind.ENTITY
    assert causal.subject.kind is RelationshipEndpointKind.STATE
    assert causal.object is not None and causal.object.kind is RelationshipEndpointKind.STATE
    assert causal.subject.identity == "state:irrigation-timing-protocol"
    assert causal.object.identity == "state:higher-yield"


def test_audited_case_revisions_match_the_evidence_meanings():
    corpus = TemporalReferenceCorpusV1.model_validate(_payload())
    restatement = _case(corpus, "restatement_not_corroboration")
    corroboration = _case(corpus, "independent_factory_corroboration")
    temporal_change = _case(corpus, "world_state_changes_over_time")
    overlap = _case(corpus, "overlapping_capacity_reports")
    delivery = _case(corpus, "contested_delivery_belief")
    reaction = _case(corpus, "price_reaction_not_causal_fact")
    sequence = _case(corpus, "sequence_without_causal_promotion")
    contrary = _case(corpus, "mechanism_with_contrary_evidence")
    alias_change = _case(corpus, "alias_registry_version_change")
    collision = _case(corpus, "entity_name_collision")
    causal_gate = _case(corpus, "causal_claim_requires_human_gate")

    scheduled_closure = restatement.expected.beliefs[0]
    assert scheduled_closure.predicate == "scheduled_closure_date"
    assert scheduled_closure.value == "2026-06-01"
    assert scheduled_closure.validity.occurred_at == datetime(2026, 6, 1, tzinfo=UTC)
    assert scheduled_closure.validity.precision is TimePrecision.DAY
    registry = next(item.record for item in corroboration.evidence if item.input_key == "registry")
    assert "factory operations ended" in (registry.content or "")
    corroborated_closure = corroboration.expected.beliefs[0]
    assert corroborated_closure.validity.valid_from == datetime(2026, 5, 1, tzinfo=UTC)
    assert corroborated_closure.validity.precision is TimePrecision.RANGE
    later_state = next(belief for belief in temporal_change.expected.beliefs if belief.value == "closed")
    assert later_state.validity.valid_from == datetime(2026, 4, 1, tzinfo=UTC)
    assert later_state.validity.precision is TimePrecision.RANGE
    assert temporal_change.expected.transition_hypothesis.state.value == "ineligible"
    assert {item.classification.value for item in overlap.expected.relationships} == {
        "overlaps",
        "same_interval_contradiction",
    }
    customer_log = next(item.record for item in delivery.evidence if item.input_key == "not_delivered")
    assert "not delivered to the customer" in (customer_log.content or "")
    assert delivery.expected.beliefs[0].validity.occurred_at == datetime(2026, 6, 10, tzinfo=UTC)
    assert delivery.expected.beliefs[0].validity.precision is TimePrecision.DAY
    assert {item.classification.value for item in reaction.expected.prohibited_relationships} == {"causes"}
    assert reaction.expected.beliefs[0].validity.occurred_at == datetime(2026, 6, 1, 11, tzinfo=UTC)
    assert reaction.expected.beliefs[0].validity.precision is TimePrecision.EXACT
    assert sequence.expected.beliefs[0].validity.valid_from == datetime(2026, 6, 1, tzinfo=UTC)
    assert sequence.expected.beliefs[0].validity.valid_to == datetime(2026, 6, 2, 23, 59, 59, tzinfo=UTC)
    assert sequence.expected.beliefs[0].validity.precision is TimePrecision.RANGE
    assert contrary.expected.beliefs[0].status.value == "supported"
    assert contrary.expected.beliefs[0].value == "active"
    assert contrary.expected.transition_hypothesis.state.value == "eligible"
    assert {item.classification.value for item in alias_change.expected.relationships} == {
        "entity_changed",
        "source_version_replacement",
    }
    assert alias_change.expected.beliefs[0].validity.valid_from == datetime(2026, 6, 1, tzinfo=UTC)
    collision_negative = collision.expected.prohibited_relationships[0]
    assert collision_negative.subject.identity == "mention:entity_name_collision:company"
    assert collision_negative.object is not None
    assert collision_negative.object.identity == "entity:mercury-city"
    assert {item.classification.value for item in causal_gate.expected.prohibited_relationships} == {
        "causes",
        "mechanistic_support",
    }


def test_corpus_hash_ignores_json_key_case_evidence_and_reference_order():
    payload = _payload()
    original = TemporalReferenceCorpusV1.model_validate(payload)
    reordered = _reverse_mapping_keys(payload)
    reordered["cases"].reverse()
    for item in reordered["cases"]:
        item["categories"].reverse()
        item["product_ids"].reverse()
        item["evidence"].reverse()
        item["as_of_times"].reverse()
        item["expected"]["beliefs"].reverse()
        item["expected"]["relationships"].reverse()
        item["expected"]["prohibited_relationships"].reverse()
        item["expected"]["record_meanings"].reverse()
        item["expected"]["prohibited_record_meanings"].reverse()
        for belief in item["expected"]["beliefs"]:
            belief["supporting_evidence_keys"].reverse()
            belief["contradicting_evidence_keys"].reverse()
        for relationship in item["expected"]["relationships"] + item["expected"]["prohibited_relationships"]:
            relationship["supporting_evidence_keys"].reverse()

    normalized = TemporalReferenceCorpusV1.model_validate(reordered)
    assert original.corpus_hash() == normalized.corpus_hash()
    assert original.corpus_id() == normalized.corpus_id()


def test_editorial_corpus_metadata_does_not_change_material_identity():
    payload = _payload()
    original = TemporalReferenceCorpusV1.model_validate(payload)
    payload["name"] = "Editorially renamed TP0 candidate"
    payload["purpose"] = "Copyedited description with identical evaluation semantics."
    renamed = TemporalReferenceCorpusV1.model_validate(payload)

    assert original.corpus_hash() == renamed.corpus_hash()
    assert original.corpus_id() == renamed.corpus_id()


@pytest.mark.parametrize(
    ("mutation", "expected_change"),
    [
        (_change_first_evidence_content, "evidence"),
        (lambda payload: payload["cases"][0].update(product_ids=["product:changed"]), "product"),
        (lambda payload: payload["cases"][0]["expected"]["beliefs"][0].update(value="changed"), "expectation"),
        (lambda payload: payload.update(maturity="seed"), "corpus maturity"),
    ],
)
def test_material_semantics_change_corpus_identity(mutation, expected_change):
    payload = _payload()
    original = TemporalReferenceCorpusV1.model_validate(payload)
    mutation(payload)
    if expected_change == "product":
        for evidence in payload["cases"][0]["evidence"]:
            evidence["record"]["product_id"] = "product:changed"
        for belief in payload["cases"][0]["expected"]["beliefs"]:
            belief["product_id"] = "product:changed"
        for relationship in (
            payload["cases"][0]["expected"]["relationships"]
            + payload["cases"][0]["expected"]["prohibited_relationships"]
        ):
            relationship["subject"]["product_id"] = "product:changed"
            if relationship.get("object") is not None:
                relationship["object"]["product_id"] = "product:changed"
    changed = TemporalReferenceCorpusV1.model_validate(payload)
    assert original.corpus_hash() != changed.corpus_hash(), expected_change


def test_contract_versions_participate_in_canonical_identity_material():
    payload = _payload()
    case = TemporalReferenceCorpusV1.model_validate(payload).cases[0]
    changed_case = case.model_dump(mode="json")
    changed_case["contract_version"] = "ace.grounded-state.temporal-reference-case/v2"
    changed_expected = case.model_dump(mode="json")
    changed_expected["expected"]["contract_version"] = "ace.grounded-state.temporal-reference-expectation/v2"

    assert case.case_hash() != canonical_hash(changed_case)
    assert case.case_hash() != canonical_hash(changed_expected)


def test_temporal_change_and_same_interval_contradiction_are_distinct():
    corpus = TemporalReferenceCorpusV1.model_validate(_payload())
    replacement = _case(corpus, "source_version_replaces_prior")
    changed = _case(corpus, "world_state_changes_over_time")
    contested = _case(corpus, "same_interval_operating_conflict")

    old = next(item.record for item in replacement.evidence if item.input_key == "old")
    new = next(item.record for item in replacement.evidence if item.input_key == "new")
    assert old.evidence_id() in new.supersedes
    assert {item.classification.value for item in changed.expected.relationships} == {"state_transition"}
    assert {item.classification.value for item in changed.expected.prohibited_relationships} == {
        "same_interval_contradiction"
    }
    assert contested.expected.beliefs[0].status.value == "contested"
    assert {item.classification.value for item in contested.expected.relationships} == {"same_interval_contradiction"}


def test_unknown_time_association_and_predictions_preserve_meaning_boundaries():
    corpus = TemporalReferenceCorpusV1.model_validate(_payload())
    unknown = _case(corpus, "unknown_event_time_remains_unknown")
    reaction = _case(corpus, "price_reaction_not_causal_fact")
    prediction = _case(corpus, "prediction_never_becomes_observation")

    assert unknown.evidence[0].record.temporal.precision is TimePrecision.UNKNOWN
    assert unknown.evidence[0].record.temporal.occurred_at is None
    assert {item.classification.value for item in reaction.expected.prohibited_relationships} == {"causes"}
    assert StateRecordMeaning.PREDICTION in prediction.expected.record_meanings
    assert StateRecordMeaning.OBSERVED_OUTCOME in prediction.expected.prohibited_record_meanings


def test_provider_free_evaluator_reports_frozen_corpus_and_completed_reviews():
    report = evaluate_temporal_reference_file(FIXTURE)

    assert report.total_cases == report.validated_cases == 40
    assert report.contract_validation_failures == ()
    assert report.duplicate_case_identities == ()
    assert len(report.duplicate_evidence_identities) == 2
    assert all(item.matches_declared_expectation for item in report.duplicate_evidence_identities)
    assert report.missing_required_categories == ()
    assert report.unreviewed_subjective_expectations == ()
    assert report.unaccepted_subjective_expectations == ()
    assert report.corpus_hash == "4b029bff64564abc226d431b373a3d75cbf971c66aa6bb53e2cf29c7198c4b09"
    assert report.contract_valid is True
    assert report.candidate_complete is True
    assert report.frozen_acceptance_ready is True


def test_owner_review_ledger_matches_every_frozen_subjective_judgment():
    corpus = TemporalReferenceCorpusV1.model_validate(_payload())
    reviewed = [case for case in corpus.cases if case.case_key in REQUIRED_MAINTAINER_REVIEW_CASE_KEYS]
    ledger = OWNER_REVIEW.read_text(encoding="utf-8")

    assert len(reviewed) == 18
    assert sum(len(case.review.judgments) for case in reviewed) == 112
    assert all(case.review.reviewer == "maintainer:eamirian" for case in reviewed)
    assert all(case.review.review_ref.startswith("review:tp0:owner-approval:") for case in reviewed)
    assert all(judgment.decision is ReviewDecision.ACCEPTED for case in reviewed for judgment in case.review.judgments)
    assert all(case.review.reviewed_expectation_hash in ledger for case in reviewed)
    assert corpus.corpus_hash() in ledger


def test_evaluator_reports_duplicates_missing_categories_and_contract_failures():
    duplicate_payload = _payload()
    duplicate_payload["cases"].append(copy.deepcopy(duplicate_payload["cases"][0]))
    duplicate = evaluate_temporal_reference_corpus(duplicate_payload)
    assert duplicate.duplicate_case_identities
    assert duplicate.contract_valid is False

    invalid_payload = _payload()
    invalid_payload["cases"][0]["evidence"] = []
    invalid_payload["cases"] = [
        item for item in invalid_payload["cases"] if "independent_corroboration" not in item["categories"]
    ]
    invalid = evaluate_temporal_reference_corpus(invalid_payload)
    assert invalid.contract_validation_failures
    assert ReferenceCategory.INDEPENDENT_CORROBORATION in invalid.missing_required_categories
    assert invalid.corpus_hash is None


def test_evaluator_rejects_an_undeclared_duplicate_occurrence():
    payload = _payload()
    replay = next(item for item in payload["cases"] if item["case_key"] == "exact_replay_identical")
    target = next(item for item in payload["cases"] if item["case_key"] == "unknown_property_belief")
    target["evidence"].append(
        {
            "input_key": "leaked_replay",
            "record": copy.deepcopy(replay["evidence"][0]["record"]),
        }
    )

    report = evaluate_temporal_reference_corpus(payload)
    leaked = next(item for item in report.duplicate_evidence_identities if len(item.occurrences) == 3)
    assert leaked.matches_declared_expectation is False
    assert report.candidate_complete is False


def test_case_contract_rejects_future_evidence_at_an_as_of_cutoff():
    raw_case = copy.deepcopy(_payload()["cases"][0])
    raw_case["evidence"][0]["record"]["ingested_at"] = "2026-07-03T00:00:00Z"
    with pytest.raises(ValidationError, match="ingested after their as_of cutoff"):
        TemporalReferenceCaseV1.model_validate(raw_case)


def test_deterministic_relationships_bind_replay_and_version_lineage():
    replay = copy.deepcopy(next(item for item in _payload()["cases"] if item["case_key"] == "exact_replay_identical"))
    replay["evidence"][1]["record"]["source_version"] = "v2"
    with pytest.raises(ValidationError, match="one evidence identity"):
        TemporalReferenceCaseV1.model_validate(replay)

    replacement = copy.deepcopy(
        next(item for item in _payload()["cases"] if item["case_key"] == "source_version_replaces_prior")
    )
    replacement["evidence"][1]["record"]["supersedes"] = []
    with pytest.raises(ValidationError, match="superseded evidence identity"):
        TemporalReferenceCaseV1.model_validate(replacement)


def test_duplicate_semantic_expectations_are_rejected():
    raw_case = copy.deepcopy(
        next(item for item in _payload()["cases"] if item["case_key"] == "restatement_not_corroboration")
    )
    raw_case["expected"]["relationships"].append(copy.deepcopy(raw_case["expected"]["relationships"][0]))
    with pytest.raises(ValidationError, match="duplicate semantic expectations"):
        TemporalReferenceCaseV1.model_validate(raw_case)


def test_versioned_review_policy_cannot_be_downgraded_to_deterministic():
    payload = _payload()
    for case in payload["cases"]:
        if case["case_key"] in REQUIRED_MAINTAINER_REVIEW_CASE_KEYS:
            case["review"] = {"requirement": "deterministic", "status": "not_required"}
    payload["maturity"] = "frozen"

    report = evaluate_temporal_reference_corpus(payload)
    assert report.contract_valid is False
    assert report.frozen_acceptance_ready is False
    assert set(report.unaccepted_subjective_expectations) == REQUIRED_MAINTAINER_REVIEW_CASE_KEYS


def test_positive_causal_assertions_always_require_maintainer_review():
    raw_case = copy.deepcopy(
        next(item for item in _payload()["cases"] if item["case_key"] == "publication_precedes_future_event")
    )
    raw_case["expected"]["relationships"][0]["classification"] = "causes"
    with pytest.raises(ValidationError, match="review-sensitive expectations"):
        TemporalReferenceCaseV1.model_validate(raw_case)


def test_completed_review_binds_every_current_judgment_hash():
    raw_case = copy.deepcopy(
        next(item for item in _payload()["cases"] if item["case_key"] == "restatement_not_corroboration")
    )
    pending = TemporalReferenceCaseV1.model_validate(raw_case)
    raw_case["review"] = {
        "requirement": "maintainer_adjudication",
        "status": "completed",
        "reviewer": "maintainer:tp0-reviewer",
        "reviewed_at": "2026-08-03T20:00:00Z",
        "review_ref": "review:tp0:restatement-not-corroboration",
        "disposition": "Approved each current expectation after reviewing both source records.",
        "reviewed_expectation_hash": pending.expected.expectation_hash(),
        "judgments": [
            {
                "judgment_hash": judgment_hash,
                "decision": "accepted",
                "rationale": "The current judgment follows from the attributed fictional evidence.",
            }
            for judgment_hash in pending.expected.judgment_hashes()
        ],
    }
    reviewed = TemporalReferenceCaseV1.model_validate(raw_case)
    assert all(judgment.decision is ReviewDecision.ACCEPTED for judgment in reviewed.review.judgments)

    raw_case["expected"]["relationships"][0]["rationale"] += " Materially changed after review."
    with pytest.raises(ValidationError, match="exact expected-semantics hash"):
        TemporalReferenceCaseV1.model_validate(raw_case)


def test_pending_subjective_reviews_prevent_frozen_status():
    payload = _payload()
    for raw_case in payload["cases"]:
        if raw_case["case_key"] in REQUIRED_MAINTAINER_REVIEW_CASE_KEYS:
            raw_case["review"] = {
                "requirement": "maintainer_adjudication",
                "status": "pending",
            }
    payload["maturity"] = "frozen"
    with pytest.raises(ValidationError, match="incomplete maintainer adjudication"):
        TemporalReferenceCorpusV1.model_validate(payload)


def test_synthetic_completed_review_set_exercises_the_frozen_success_path():
    payload = _payload()
    for raw_case in payload["cases"]:
        if raw_case["case_key"] not in REQUIRED_MAINTAINER_REVIEW_CASE_KEYS:
            continue
        pending = TemporalReferenceCaseV1.model_validate(raw_case)
        raw_case["review"] = {
            "requirement": "maintainer_adjudication",
            "status": "completed",
            "reviewer": "test:synthetic-reviewer",
            "reviewed_at": "2026-08-03T20:00:00Z",
            "review_ref": f"review:test:{raw_case['case_key']}",
            "disposition": "Synthetic contract success-path exercise; not a real adjudication.",
            "reviewed_expectation_hash": pending.expected.expectation_hash(),
            "judgments": [
                {
                    "judgment_hash": judgment_hash,
                    "decision": "accepted",
                    "rationale": "Synthetic acceptance used only to verify the frozen contract path.",
                }
                for judgment_hash in pending.expected.judgment_hashes()
            ],
        }
    payload["maturity"] = "frozen"

    frozen = TemporalReferenceCorpusV1.model_validate(payload)
    report = evaluate_temporal_reference_corpus(payload)
    assert frozen.maturity is CorpusMaturity.FROZEN
    assert report.unaccepted_subjective_expectations == ()
    assert report.frozen_acceptance_ready is True


def test_roadmap_records_frozen_results_and_tp2_persistence_closeout():
    roadmap = ROADMAP.read_text(encoding="utf-8")
    assert "40-case" in roadmap
    assert "4b029bff64564abc226d431b373a3d75cbf971c66aa6bb53e2cf29c7198c4b09" in roadmap
    assert "Completed subjective owner adjudications | 18" in roadmap
    assert "TP0 is complete on the current worktree" in roadmap
    assert "TP2 is complete on the current worktree" in roadmap
    assert "K1–K3 remain `not ready`" in roadmap
