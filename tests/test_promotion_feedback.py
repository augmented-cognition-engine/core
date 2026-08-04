from __future__ import annotations

import hashlib
import json
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest
from pydantic import ValidationError

from core.engine.grounded_state.belief_contracts import ReviewAuthority
from core.engine.grounded_state.contracts import canonical_hash
from core.engine.grounded_state.promotion import build_promotion_proposal
from core.engine.grounded_state.promotion_contracts import (
    PromotionDisposition,
    PromotionMaterialV1,
    PromotionMemoryMeaning,
    PromotionOriginMeaning,
    PromotionProposalV1,
    PromotionReceiptV1,
    PromotionReviewV1,
    PromotionTargetKind,
)
from core.engine.grounded_state.promotion_evaluation import load_tp7_config, load_tp7_result
from core.engine.grounded_state.rollout_evaluation import (
    _positive_material,
    load_tp6_config,
)
from core.engine.grounded_state.rollouts import build_reasoning_use_receipt
from core.engine.grounded_state.task_runtime import record_promoted_memory_task_use
from core.engine.product.decision_receipts import build_decision_receipt
from scripts.schema_apply import _split_statements

ROOT = Path(__file__).parents[1]
FROZEN_TP7 = ROOT / "evaluations/fixtures/state_engine_tp7_promotion_feedback_v1.json"


@pytest.mark.asyncio
async def test_production_later_use_bridge_preserves_recorded_matched_comparison(monkeypatch):
    recorded: dict = {}

    class Memory:
        memory_id = "insight:k3-later-use"

    class PromotionServiceDouble:
        def __init__(self, pool):
            assert pool == "pool"

        async def retrieve(self, *, product_id, limit):
            assert product_id == "product:k3-later-use"
            assert limit == 20
            return [Memory()]

        async def record_later_use(self, **kwargs):
            recorded.update(kwargs)
            return {"comparison": kwargs["comparison"]}

    monkeypatch.setattr(
        "core.engine.grounded_state.task_runtime.PromotionService",
        PromotionServiceDouble,
    )
    comparison = {
        "target_intelligence_ids": ["insight:k3-later-use"],
        "with_context": {"decision": {"selected_option": "use"}},
        "without_context": {"decision": {"selected_option": "defer"}},
    }
    result = await record_promoted_memory_task_use(
        pool="pool",
        task_id="task:k3-later-use",
        product_id="product:k3-later-use",
        trace={
            "reflected_ids": ["insight:k3-later-use"],
            "items": [
                {
                    "id": "insight:k3-later-use",
                    "injected": True,
                    "provenance": {"promotion_receipt_id": "grounded_promotion_receipt:k3"},
                }
            ],
            "comparison": comparison,
        },
    )

    assert result == {"comparison": comparison}
    assert recorded["comparison"] == comparison
    assert recorded["injected_ids"] == {"insight:k3-later-use"}
    assert recorded["reflected_ids"] == {"insight:k3-later-use"}


def _proposal_material():
    pack, projection, revision, _, context_pack, _, _, _, rollout = _positive_material(
        "mechanism_supported_transition",
        load_tp6_config(),
    )
    consequence_id = str(rollout.execution_receipts[0].consequences[0].consequence_id)
    use = build_reasoning_use_receipt(
        rollout,
        context_pack=context_pack,
        reflected_item_ids=(consequence_id,),
        matched_control={
            "state": "matched",
            "comparison_id": "comparison:tp7",
            "matched_dimensions": (
                "task_hash",
                "provider",
                "model",
                "configuration",
                "decision_schema",
                "toolset",
            ),
            "treatment_output_hash": canonical_hash("tp7-treatment"),
            "control_output_hash": canonical_hash("tp7-control"),
            "changed_decision_fields": ("selected_option",),
            "material_item_ids": (consequence_id,),
        },
    )
    decision = build_decision_receipt(
        task_id=rollout.task_id,
        product_id=rollout.product_id,
        decision={
            "id": "decision:tp7",
            "selected_option": "Retain the reviewed grounded conclusion.",
            "scope": "State Engine TP7",
            "assumptions": ["Exact TP6 lineage remains immutable"],
            "alternatives": ["Do not promote"],
            "reconsideration_conditions": ["Later correction supersedes the conclusion"],
            "evidence_refs": [str(context_pack.context_pack_id)],
            "originating_actor": "user:tp7",
            "originating_actor_class": "authenticated_user",
            "created_at": pack.as_of,
        },
        route={"provider": "fixture-provider", "model": "fixture-model"},
    )
    task = {
        "id": rollout.task_id,
        "product": rollout.product_id,
        "status": "completed",
        "decision_receipt": decision,
    }
    proposal = build_promotion_proposal(
        task=task,
        material=PromotionMaterialV1(
            target_kind=PromotionTargetKind.DURABLE_CONCLUSION,
            origin_meaning=PromotionOriginMeaning.GROUNDED_REASONING_CONCLUSION,
            memory_meaning=PromotionMemoryMeaning.DURABLE_CONCLUSION,
            content="Disconnecting active cooling increases the bounded thermal-risk state.",
            domain_path="product",
            tags=("state-engine", "thermal-risk"),
        ),
        context_pack=context_pack,
        projection=projection,
        transition_revisions=(revision,),
        rollout=rollout,
        reasoning_use=use,
        proposer_authority=ReviewAuthority.MODEL,
        proposer_ref="model:fixture",
        proposed_at=pack.as_of + timedelta(seconds=1),
        provenance={"route": "tp6_grounded_reasoning", "source_instruction_authority": False},
    )
    return task, context_pack, projection, revision, rollout, use, proposal


def test_frozen_tp7_target_precedes_implementation_and_retains_exact_hashes():
    raw = FROZEN_TP7.read_bytes()
    config = json.loads(raw)
    assert hashlib.sha256(raw).hexdigest() == "d0f3032702557c5d99fabac3257006accf09d745aefd7c23c3818bc489fdfb81"
    assert config["fixture_status"] == "frozen_before_implementation"
    assert config["reference_corpus"]["canonical_hash"] == (
        "4b029bff64564abc226d431b373a3d75cbf971c66aa6bb53e2cf29c7198c4b09"
    )
    assert config["tp6_acceptance"]["outcome_hash"] == (
        "dfeeb1128166b6dc93bfb41a8911b8a9d3fd3a298a6cd85fff7d709783aab915"
    )
    assert config["provider_budget"]["max_model_calls"] == 0
    assert set(config["lifecycle_dispositions"]) == {item.value for item in PromotionDisposition}


def test_recorded_tp7_machine_result_is_exact_provider_free_and_passing():
    config = load_tp7_config()
    result_path = ROOT / "evaluations/results/state_engine_tp7_promotion_feedback_v1.json"
    result = load_tp7_result(result_path)

    assert result.config_hash == config.config_hash()
    assert result.passed is True
    assert result.outcome_hash == "d35a4543f63ac021bd398dbc0c7d76bd0d92632effd321f4d774208ae4a7866f"
    assert result.primary_model_calls == result.input_tokens == result.output_tokens == 0
    assert result.estimated_cost_usd == 0.0
    assert hashlib.sha256(result_path.read_bytes()).hexdigest() == (
        "e1c160058ca8f9989a6fa1881feff58c3e68dde77720463cccf8b78216ee4278"
    )


def test_promotion_contracts_are_immutable_extra_forbid_and_material_derived():
    *_, proposal = _proposal_material()
    assert proposal.proposal_hash == canonical_hash(
        proposal.model_dump(mode="json", exclude={"proposal_id", "proposal_hash"})
    )
    with pytest.raises(ValidationError, match="Extra inputs"):
        PromotionProposalV1.model_validate({**proposal.model_dump(mode="python"), "model_can_accept": True})
    with pytest.raises(ValidationError, match="frozen"):
        proposal.product_id = "product:foreign"  # type: ignore[misc]
    changed = PromotionProposalV1.model_validate(
        {
            **proposal.model_dump(mode="python", exclude={"proposal_id", "proposal_hash"}),
            "proposer_ref": "model:other",
        }
    )
    assert changed.proposal_id != proposal.proposal_id


def test_only_five_typed_memory_meanings_are_eligible_and_simulation_is_never_observation():
    with pytest.raises(ValidationError):
        PromotionMaterialV1(
            target_kind="durable_conclusion",
            origin_meaning="source_claim",
            memory_meaning="durable_conclusion",
            content="A raw extracted claim.",
            domain_path="product",
        )
    with pytest.raises(ValidationError):
        PromotionMaterialV1(
            target_kind="durable_conclusion",
            origin_meaning="grounded_reasoning_conclusion",
            memory_meaning="observed_fact",
            content="A simulated state relabeled as fact.",
            domain_path="product",
        )
    valid = PromotionMaterialV1(
        target_kind="reusable_reasoning_pattern",
        origin_meaning="reusable_reasoning_pattern",
        memory_meaning="pattern",
        content="Challenge action and no-action branches against one frozen state.",
        domain_path="product",
    )
    assert valid.content_hash == canonical_hash({"content": valid.content, "memory_meaning": "pattern"})


def test_proposal_binds_exact_task_decision_evidence_belief_transition_rollout_and_use():
    task, context_pack, projection, revision, rollout, use, proposal = _proposal_material()
    assert proposal.product_id == task["product"] == rollout.product_id
    assert proposal.task_id == task["id"] == rollout.task_id
    assert proposal.context_pack_id == context_pack.context_pack_id
    assert proposal.context_pack_hash == context_pack.context_pack_hash
    assert proposal.evidence_pack_id == context_pack.evidence_pack.pack_id
    assert proposal.evidence_pack_hash == context_pack.evidence_pack.pack_hash
    assert proposal.belief_projection_id == projection.projection_id
    assert proposal.belief_projection_hash == projection.projection_hash
    assert [(item.revision_id, item.revision_hash) for item in proposal.transition_revisions] == [
        (revision.revision_id, revision.revision_hash)
    ]
    assert proposal.rollout_revision_id == rollout.rollout_revision_id
    assert proposal.reasoning_use_receipt_id == use.receipt_id
    assert proposal.source_instruction_authority is proposal.simulated_state_is_observation is False
    assert all(item.source_instruction_authority is False for item in proposal.evidence_versions)


def test_model_can_propose_but_cannot_author_authoritative_review():
    *_, proposal = _proposal_material()
    assert proposal.proposer_authority is ReviewAuthority.MODEL
    with pytest.raises(ValidationError, match="model cannot govern"):
        PromotionReviewV1(
            product_id=proposal.product_id,
            proposal_id=str(proposal.proposal_id),
            proposal_hash=str(proposal.proposal_hash),
            disposition=PromotionDisposition.ACCEPTED,
            authority=ReviewAuthority.MODEL,
            reviewer_ref="model:fixture",
            authority_scope="product_member",
            rationale="Self-authorize.",
            reviewed_at=datetime(2026, 8, 4, tzinfo=UTC),
        )


@pytest.mark.parametrize("disposition", list(PromotionDisposition))
def test_every_required_lifecycle_disposition_is_immutable_and_inspectable(disposition: PromotionDisposition):
    *_, proposal = _proposal_material()
    review = PromotionReviewV1(
        product_id=proposal.product_id,
        proposal_id=str(proposal.proposal_id),
        proposal_hash=str(proposal.proposal_hash),
        disposition=disposition,
        authority=ReviewAuthority.HUMAN,
        reviewer_ref="user:owner",
        authority_scope="product_member",
        rationale=f"Explicit {disposition.value} fixture disposition.",
        reviewed_at=datetime(2026, 8, 4, tzinfo=UTC),
    )
    accepted = disposition is PromotionDisposition.ACCEPTED
    receipt = PromotionReceiptV1(
        product_id=proposal.product_id,
        proposal_id=str(proposal.proposal_id),
        proposal_hash=str(proposal.proposal_hash),
        review_id=str(review.review_id),
        review_hash=str(review.review_hash),
        disposition=disposition,
        memory_id="insight:promotion_fixture" if accepted else None,
        memory_hash=canonical_hash("promotion_fixture") if accepted else None,
        effective_at=review.reviewed_at,
        reasons=(f"fixture:{disposition.value}",),
    )
    assert receipt.disposition is disposition
    assert bool(receipt.memory_id) is accepted
    assert receipt.beneficial_impact_supported is False


def test_nonaccepted_receipt_cannot_smuggle_memory_and_accepted_receipt_requires_it():
    *_, proposal = _proposal_material()
    review = PromotionReviewV1(
        product_id=proposal.product_id,
        proposal_id=str(proposal.proposal_id),
        proposal_hash=str(proposal.proposal_hash),
        disposition="rejected",
        authority="human",
        reviewer_ref="user:owner",
        authority_scope="product_member",
        rationale="Reject.",
        reviewed_at=datetime(2026, 8, 4, tzinfo=UTC),
    )
    common = {
        "product_id": proposal.product_id,
        "proposal_id": proposal.proposal_id,
        "proposal_hash": proposal.proposal_hash,
        "review_id": review.review_id,
        "review_hash": review.review_hash,
        "effective_at": review.reviewed_at,
    }
    with pytest.raises(ValidationError, match="non-accepted promotion"):
        PromotionReceiptV1(**common, disposition="rejected", memory_id="insight:leak", memory_hash="0" * 64)
    with pytest.raises(ValidationError, match="requires exact existing-memory"):
        PromotionReceiptV1(**common, disposition="accepted")


def test_v167_is_the_single_additive_append_only_migration_after_v166():
    migration = ROOT / "core/schema/v167_state_engine_tp7_promotion_feedback.surql"
    assert migration.exists()
    assert not (ROOT / "core/schema/v168_state_engine_tp7_promotion_feedback.surql").exists()
    text = migration.read_text(encoding="utf-8")
    statements = _split_statements(text)
    assert len(statements) >= 60
    assert all(not statement.lstrip().upper().startswith("UPDATE ") for statement in statements)
    assert all(not statement.lstrip().upper().startswith("DELETE ") for statement in statements)
    assert all(not statement.lstrip().upper().startswith("REMOVE ") for statement in statements)
    for table in (
        "grounded_promotion_proposal",
        "grounded_promotion_review",
        "grounded_promotion_receipt",
        "grounded_promotion_memory_lineage",
    ):
        assert f"DEFINE TABLE IF NOT EXISTS {table} SCHEMAFULL" in text
        assert f"ON {table} TYPE record<product>" in text
    assert "FOR update NONE, FOR delete NONE" in text
    assert "promotion_receipt_id ON insight TYPE option<string>" in text
