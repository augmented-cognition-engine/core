from itertools import permutations

import pytest

from core.engine.graph.assertions import (
    AssertionReview,
    RelationshipProposal,
    resolve_proposals,
    review_depth_for,
    transition_status,
)


def proposal(
    predicate="depends_on", *, subject="insight:a", object="insight:b", provider="one", scope=None, evidence=None
):
    return RelationshipProposal(
        subject=subject,
        predicate=predicate,
        object=object,
        provider=provider,
        model=f"model-{provider}",
        scope=scope or {},
        evidence_refs=evidence or ["observation:1"],
        proposal_confidence=0.9,
    )


def operational(resolved):
    return [(a.id, a.subject, a.predicate, a.object) for a in resolved if a.projection_eligible]


def test_cross_model_alias_and_inverse_normalize_to_same_assertion():
    proposals = [
        proposal("requires", provider="api"),
        proposal("enables", subject="insight:b", object="insight:a", provider="local"),
    ]
    resolved = resolve_proposals(proposals)
    assert len(resolved) == 1
    assert resolved[0].predicate == "depends_on"
    assert len(resolved[0].proposal_ids) == 2
    assert operational(resolved) == [(resolved[0].id, "insight:a", "depends_on", "insight:b")]


def test_all_proposal_orders_have_identical_authoritative_output():
    ps = [
        proposal("depends_on", provider="a"),
        proposal("requires", provider="b"),
        proposal("enables", subject="insight:b", object="insight:a", provider="c"),
    ]
    outputs = {tuple(operational(resolve_proposals(list(order)))) for order in permutations(ps)}
    assert len(outputs) == 1


def test_repeated_proposal_is_idempotent():
    p = proposal()
    one = resolve_proposals([p])
    repeated = resolve_proposals([p, p])
    assert operational(one) == operational(repeated)
    assert repeated[0].proposal_ids == [p.event_id()]


def test_invalid_typing_cannot_project():
    result = resolve_proposals([proposal(subject="graph_file:a", object="insight:b")])[0]
    assert result.status == "rejected"
    assert not result.projection_eligible


def test_complementary_relationships_do_not_collapse():
    result = resolve_proposals([proposal("informed_by"), proposal("depends_on")])
    assert {a.predicate for a in result} == {"informed_by", "depends_on"}
    assert len(operational(result)) == 2


def test_exclusive_relationships_become_contested():
    result = resolve_proposals([proposal("improves"), proposal("breaks")])
    assert {a.status for a in result} == {"contested"}
    assert operational(result) == []


def test_contexts_have_distinct_assertion_identity():
    result = resolve_proposals([proposal(scope={"phase": "alpha"}), proposal(scope={"phase": "ga"})])
    assert len(result) == 2
    assert result[0].id != result[1].id


def test_causal_claim_routes_human_required_and_stays_provisional():
    p = proposal("causes", evidence=["observation:1", "observation:2"])
    result = resolve_proposals([p])[0]
    assert review_depth_for(p) == "human-required"
    assert result.status == "provisional"
    assert not result.projection_eligible


def test_critic_cannot_mutate_and_objection_is_deterministic():
    p = proposal()
    aid = resolve_proposals([p])[0].id
    reviews = [
        AssertionReview(target_assertion=aid, verdict="object", severity="high", provider="z"),
        AssertionReview(target_assertion=aid, verdict="support", provider="a"),
    ]
    forward = resolve_proposals([p], reviews=reviews)
    reverse = resolve_proposals([p], reviews=list(reversed(reviews)))
    assert forward == reverse
    assert forward[0].status == "contested"
    assert operational(forward) == []


def test_unavailable_reviewer_is_explicit_degraded_state():
    p = proposal()
    aid = resolve_proposals([p])[0].id
    r = AssertionReview(target_assertion=aid, verdict="unavailable")
    assert resolve_proposals([p], reviews=[r])[0].degraded_reason == "reviewer_unavailable"


def test_lifecycle_enforces_actor_and_legal_transitions():
    transition_status("proposed", "accepted", actor="resolver")
    with pytest.raises(ValueError):
        transition_status("accepted", "proposed", actor="resolver")
    with pytest.raises(ValueError):
        transition_status("proposed", "accepted", actor="critic")
