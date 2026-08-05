"""E1-C proposal, diff, human review, and atomic head acceptance tests."""

from __future__ import annotations

import asyncio
import copy
from datetime import timedelta

import pytest

from core.engine.cognition import composer as composer_module
from core.engine.cognition.catalog import build_default_catalog
from core.engine.cognition.contracts import canonical_hash
from core.engine.cognition.governance import (
    ActorClass,
    CognitionGovernanceService,
    CognitionProposalV1,
    CognitionReviewReceiptV1,
    ProposalSourceV1,
    ProposalState,
    ReviewActorV1,
    ReviewDisposition,
)
from core.engine.cognition.governance_persistence import _same_review_replay
from core.engine.cognition.store import CognitionHeadConflict


def _human() -> ReviewActorV1:
    return ReviewActorV1(
        actor_id="user:maintainer",
        actor_class=ActorClass.HUMAN,
        authorities=("cognition-review",),
    )


def _proposal(catalog, *, suffix: str = "improve framing") -> CognitionProposalV1:
    revision = catalog.recipe_revision("coding_intelligence")
    body = copy.deepcopy(revision.body)
    body["description"] = f"{body['description']} {suffix}"
    return CognitionProposalV1(
        target_identity=revision.identity,
        scope=next(head.scope for head in catalog.store.heads() if head.cognition_id == revision.identity.cognition_id),
        intent=suffix,
        sources=(
            ProposalSourceV1(
                source_id="task:teach-example",
                source_kind="task",
                content_hash=canonical_hash({"task": "teach-example"}),
            ),
        ),
        base_revision_id=str(revision.revision_id),
        body_schema_version=revision.body_schema_version,
        draft_body=body,
        dependencies=revision.dependencies,
        created_by=ReviewActorV1(
            actor_id="model:teacher",
            actor_class=ActorClass.MODEL,
            authorities=(),
        ),
    )


def test_durable_review_retry_ignores_only_review_timestamp() -> None:
    receipt = CognitionReviewReceiptV1(
        review_request_id="review-request:retry",
        proposal_id="cognition_proposal:test",
        proposal_hash="a" * 64,
        actor=_human(),
        disposition=ReviewDisposition.APPROVE,
        rationale="Exact material reviewed.",
        expected_head_generation=0,
    )
    timestamp_retry = receipt.model_copy(update={"reviewed_at": receipt.reviewed_at + timedelta(seconds=1)})
    changed_result = timestamp_retry.model_copy(update={"result_revision_id": "cognition_revision:different"})
    assert _same_review_replay(receipt, timestamp_retry)
    assert not _same_review_replay(receipt, changed_result)


async def test_proposal_is_idempotent_and_never_selectable_before_review() -> None:
    catalog = build_default_catalog(core_yaml=composer_module._RECIPE_YAML)
    service = CognitionGovernanceService(catalog.store)
    proposal = _proposal(catalog)
    await service.propose(proposal)
    assert service.proposal_state(str(proposal.proposal_id)) is ProposalState.PENDING
    assert catalog.recipe_revision("coding_intelligence").revision_id == proposal.base_revision_id
    assert all(item.revision_id != proposal.proposal_id for item in catalog.store.revisions())


async def test_semantic_diff_is_exact_and_inspectable() -> None:
    catalog = build_default_catalog(core_yaml=composer_module._RECIPE_YAML)
    service = CognitionGovernanceService(catalog.store)
    proposal = await service.propose(_proposal(catalog))
    diff = service.semantic_diff(str(proposal.proposal_id))
    assert diff.base_revision_id == proposal.base_revision_id
    assert diff.draft_material_hash == canonical_hash(proposal.draft_body)
    assert [(item.path, item.operation) for item in diff.changes] == [("$.description", "replace")]


async def test_model_cannot_approve_or_activate() -> None:
    catalog = build_default_catalog(core_yaml=composer_module._RECIPE_YAML)
    service = CognitionGovernanceService(catalog.store)
    proposal = await service.propose(_proposal(catalog))
    before = catalog.store.revisions()
    with pytest.raises(PermissionError, match="human_authority_required"):
        await service.review(
            proposal_id=str(proposal.proposal_id),
            review_request_id="review-request:model",
            actor=ReviewActorV1(actor_id="model:reviewer", actor_class=ActorClass.MODEL),
            disposition=ReviewDisposition.APPROVE,
            rationale="I approve myself.",
            expected_head_generation=1,
            runtime_view=catalog.recipe("coding_intelligence"),
        )
    assert catalog.store.revisions() == before
    assert service.proposal_state(str(proposal.proposal_id)) is ProposalState.PENDING


async def test_rejection_creates_receipt_without_revision_or_head_change() -> None:
    catalog = build_default_catalog(core_yaml=composer_module._RECIPE_YAML)
    service = CognitionGovernanceService(catalog.store)
    proposal = await service.propose(_proposal(catalog))
    revisions_before = catalog.store.revisions()
    heads_before = catalog.store.heads()
    receipt = await service.review(
        proposal_id=str(proposal.proposal_id),
        review_request_id="review-request:reject",
        actor=_human(),
        disposition=ReviewDisposition.REJECT,
        rationale="The change is not grounded enough.",
        expected_head_generation=1,
        runtime_view=None,
    )
    assert receipt.result_revision_id is None
    assert service.proposal_state(str(proposal.proposal_id)) is ProposalState.REJECTED
    assert catalog.store.revisions() == revisions_before
    assert catalog.store.heads() == heads_before


async def test_human_approval_creates_immutable_revision_and_cas_head_atomically() -> None:
    catalog = build_default_catalog(core_yaml=composer_module._RECIPE_YAML)
    service = CognitionGovernanceService(catalog.store)
    proposal = await service.propose(_proposal(catalog))
    runtime = copy.deepcopy(catalog.recipe("coding_intelligence"))
    runtime.description = proposal.draft_body["description"]
    receipt = await service.review(
        proposal_id=str(proposal.proposal_id),
        review_request_id="review-request:approve",
        actor=_human(),
        disposition=ReviewDisposition.APPROVE,
        rationale="Exact diff reviewed and accepted.",
        expected_head_generation=1,
        runtime_view=runtime,
    )
    revision = catalog.store.revision(receipt.result_revision_id)
    head = catalog.store.head(receipt.result_head_id)
    assert revision is not None
    assert revision.approval_receipt_id == receipt.receipt_id
    assert revision.body == proposal.draft_body
    assert head is not None
    assert head.active_revision_id == revision.revision_id
    assert head.generation == 2
    assert service.proposal_state(str(proposal.proposal_id)) is ProposalState.APPROVED

    replay = await service.review(
        proposal_id=str(proposal.proposal_id),
        review_request_id="review-request:approve",
        actor=_human(),
        disposition=ReviewDisposition.APPROVE,
        rationale="Exact diff reviewed and accepted.",
        expected_head_generation=1,
        runtime_view=runtime,
    )
    assert replay == receipt


async def test_generation_conflict_leaves_no_partial_revision() -> None:
    catalog = build_default_catalog(core_yaml=composer_module._RECIPE_YAML)
    service = CognitionGovernanceService(catalog.store)
    proposal = await service.propose(_proposal(catalog))
    before = catalog.store.revisions()
    with pytest.raises(CognitionHeadConflict, match="generation_conflict"):
        await service.review(
            proposal_id=str(proposal.proposal_id),
            review_request_id="review-request:stale",
            actor=_human(),
            disposition=ReviewDisposition.APPROVE,
            rationale="Stale client review.",
            expected_head_generation=0,
            runtime_view=catalog.recipe("coding_intelligence"),
        )
    assert catalog.store.revisions() == before
    assert service.proposal_state(str(proposal.proposal_id)) is ProposalState.PENDING


async def test_concurrent_reviews_have_one_winner() -> None:
    catalog = build_default_catalog(core_yaml=composer_module._RECIPE_YAML)
    service = CognitionGovernanceService(catalog.store)
    proposal = await service.propose(_proposal(catalog))

    async def approve(request_id: str):
        return await service.review(
            proposal_id=str(proposal.proposal_id),
            review_request_id=request_id,
            actor=_human(),
            disposition=ReviewDisposition.APPROVE,
            rationale=f"Review {request_id}.",
            expected_head_generation=1,
            runtime_view=catalog.recipe("coding_intelligence"),
        )

    results = await asyncio.gather(approve("review-request:a"), approve("review-request:b"), return_exceptions=True)
    assert sum(not isinstance(item, Exception) for item in results) == 1
    assert sum(isinstance(item, RuntimeError) for item in results) == 1
