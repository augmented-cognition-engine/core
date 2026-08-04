from itertools import permutations

import pytest

from core.engine.graph.assertions import (
    AssertionReview,
    RelationshipProposal,
    rebuild_projection,
    resolve_proposals,
    review_depth_for,
    transition_status,
)


def proposal(
    predicate="depends_on", *, subject="insight:a", object="insight:b", provider="one", scope=None, evidence=None
):
    return RelationshipProposal(
        product_id="product:test",
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


def test_symmetric_relationship_directions_collapse_to_one_assertion():
    result = resolve_proposals(
        [
            proposal("contradicts", subject="insight:a", object="insight:b"),
            proposal("contradicts", subject="insight:b", object="insight:a", provider="two"),
        ]
    )
    assert len(result) == 1
    assert result[0].subject == "insight:a"
    assert result[0].object == "insight:b"
    assert len(result[0].proposal_ids) == 2


def test_reciprocal_directional_relationships_become_contested():
    result = resolve_proposals(
        [
            proposal("depends_on", subject="insight:a", object="insight:b"),
            proposal("depends_on", subject="insight:b", object="insight:a", provider="two"),
        ]
    )
    assert len(result) == 2
    assert {a.status for a in result} == {"contested"}
    assert operational(result) == []
    assert all("asymmetry" in a.explanation for a in result)


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


def test_causal_claim_accepts_only_with_independent_sources_countersearch_and_exact_human_review():
    p = proposal("causes", evidence=["observation:1", "observation:2"])
    p = p.model_copy(update={"source_origin_ids": ["source:a", "source:b"]})
    aid = resolve_proposals([p])[0].id
    review = AssertionReview(
        product_id="product:test",
        target_assertion=aid,
        verdict="support",
        authority="human",
        review_ref="human_review:tp4",
        reviewed_material_hash=p.review_material_hash(),
        counterevidence_search_ref="counterevidence_search:tp4",
        counterevidence_complete=True,
    )
    accepted = resolve_proposals([p], reviews=[review], human_confirmed={aid})[0]
    assert accepted.status == "accepted"
    assert accepted.projection_eligible is True
    assert accepted.review_refs == [review.review_id()]


def test_causal_group_cannot_borrow_unreviewed_evidence_or_source_diversity():
    reviewed = proposal("causes", evidence=["observation:1"]).model_copy(update={"source_origin_ids": ["source:a"]})
    unreviewed = proposal("causes", evidence=["observation:2"], provider="other").model_copy(
        update={"source_origin_ids": ["source:b"]}
    )
    aid = resolve_proposals([reviewed])[0].id
    review = AssertionReview(
        product_id="product:test",
        target_assertion=aid,
        verdict="support",
        authority="human",
        review_ref="human_review:exact-weak-material",
        reviewed_material_hash=reviewed.review_material_hash(),
        counterevidence_search_ref="counterevidence_search:reviewed-only",
        counterevidence_complete=True,
    )
    result = resolve_proposals(
        [reviewed, unreviewed],
        reviews=[review],
        human_confirmed={aid},
    )[0]
    assert result.status == "provisional"
    assert result.evidence_refs == ["observation:1"]
    assert result.proposal_ids == [reviewed.event_id()]


def test_critic_cannot_mutate_and_objection_is_deterministic():
    p = proposal()
    aid = resolve_proposals([p])[0].id
    reviews = [
        AssertionReview(
            product_id="product:test", target_assertion=aid, verdict="object", severity="high", provider="z"
        ),
        AssertionReview(product_id="product:test", target_assertion=aid, verdict="support", provider="a"),
    ]
    forward = resolve_proposals([p], reviews=reviews)
    reverse = resolve_proposals([p], reviews=list(reversed(reviews)))
    assert forward == reverse
    assert forward[0].status == "contested"
    assert operational(forward) == []


def test_unavailable_reviewer_is_explicit_degraded_state():
    p = proposal()
    aid = resolve_proposals([p])[0].id
    r = AssertionReview(product_id="product:test", target_assertion=aid, verdict="unavailable")
    assert resolve_proposals([p], reviews=[r])[0].degraded_reason == "reviewer_unavailable"


def test_lifecycle_enforces_actor_and_legal_transitions():
    transition_status("proposed", "accepted", actor="resolver")
    with pytest.raises(ValueError):
        transition_status("accepted", "proposed", actor="resolver")
    with pytest.raises(ValueError):
        transition_status("proposed", "accepted", actor="critic")


@pytest.mark.asyncio
async def test_projection_prune_binds_stale_edge_id_as_record():
    from surrealdb import RecordID

    class FakeDB:
        def __init__(self):
            self.deleted_with = None

        async def query(self, sql, params=None):
            if "projection_eligible = true" in sql:
                return []
            if sql.startswith("SELECT id, assertion_id"):
                return [
                    {
                        "id": RecordID("operational_relationship", "stale"),
                        "assertion_id": RecordID("relationship_assertion", "retired"),
                        "projection_version": "ace.assertion-resolver.v1",
                    }
                ]
            if sql.startswith("DELETE"):
                self.deleted_with = params["id"]
                return []
            raise AssertionError(f"unexpected query: {sql}")

    db = FakeDB()
    assert await rebuild_projection(product_id="product:test", db=db) == 0
    assert isinstance(db.deleted_with, RecordID)


@pytest.mark.asyncio
async def test_projection_prune_removes_stale_edge_in_surrealdb(db_pool):
    edge_id = "operational_relationship:projection_prune_regression_51001"
    async with db_pool.connection() as db:
        await db.query(
            """
            CREATE operational_relationship:projection_prune_regression_51001 SET
                product = product:test,
                in = insight:projection_prune_source_51001,
                out = insight:projection_prune_target_51001,
                predicate = 'depends_on',
                assertion_id = relationship_assertion:projection_prune_retired_51001,
                ontology_version = 'ace.relationships.v1',
                resolver_version = 'ace.assertion-resolver.v1',
                projection_version = 'ace.assertion-resolver.v1',
                projected_at = time::now()
            """
        )
        try:
            await rebuild_projection(product_id="product:test", db=db)
            remaining = await db.query("SELECT id FROM <record>$id", {"id": edge_id})
            assert remaining == []
        finally:
            await db.query("DELETE <record>$id", {"id": edge_id})
