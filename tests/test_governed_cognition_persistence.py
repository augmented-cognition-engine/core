"""F1 durable cognition concurrency guards and ambiguous-write reconciliation."""

from __future__ import annotations

from contextlib import asynccontextmanager
from datetime import UTC, datetime, timedelta

import pytest

from core.engine.cognition.contracts import (
    RECIPE_BODY_VERSION,
    CognitionHeadV1,
    CognitionIdentityV1,
    CognitionOwnerV1,
    CognitionRevisionV1,
    CognitionScopeV1,
    CognitionSourceV1,
    CognitionType,
    OwnerKind,
    ScopeKind,
    canonical_hash,
)
from core.engine.cognition.governance import (
    ActorClass,
    CognitionProposalV1,
    CognitionReviewReceiptV1,
    ProposalSourceV1,
    ProposalState,
    ReviewActorV1,
    ReviewDisposition,
)
from core.engine.cognition.governance_persistence import (
    CognitionGovernanceStore,
    CognitionPersistenceError,
    CognitionReplayConflict,
)

NOW = datetime(2026, 8, 11, 17, tzinfo=UTC)
PRODUCT = "product:f1-hardening"


def _approval_material():
    identity = CognitionIdentityV1(
        cognition_type=CognitionType.RECIPE,
        owner=CognitionOwnerV1(
            kind=OwnerKind.PRODUCT,
            namespace=PRODUCT,
            provenance="task:f1-hardening",
        ),
        stable_key="f1_hardening",
    )
    scope = CognitionScopeV1(kind=ScopeKind.PRODUCT, product_id=PRODUCT)
    source_hash = canonical_hash({"task": "f1-hardening"})
    proposal = CognitionProposalV1(
        target_identity=identity,
        scope=scope,
        intent="Prove exact durable review reconciliation.",
        sources=(
            ProposalSourceV1(
                source_id="task:f1-hardening",
                source_kind="task",
                content_hash=source_hash,
            ),
        ),
        body_schema_version=RECIPE_BODY_VERSION,
        draft_body={"slug": "f1_hardening", "name": "F1 Hardening"},
        created_by=ReviewActorV1(actor_id="model:teacher", actor_class=ActorClass.MODEL),
        created_at=NOW,
    )
    receipt = CognitionReviewReceiptV1(
        review_request_id="review-request:f1-hardening",
        proposal_id=str(proposal.proposal_id),
        proposal_hash=str(proposal.proposal_hash),
        actor=ReviewActorV1(
            actor_id="user:reviewer",
            actor_class=ActorClass.HUMAN,
            authorities=("cognition-review",),
        ),
        disposition=ReviewDisposition.APPROVE,
        rationale="Exact proposal material reviewed.",
        expected_head_generation=0,
        reviewed_at=NOW + timedelta(seconds=1),
    )
    revision = CognitionRevisionV1(
        identity=identity,
        body_schema_version=proposal.body_schema_version,
        body=proposal.draft_body,
        sources=(
            CognitionSourceV1(
                source_kind="task",
                locator="task:f1-hardening",
                content_hash=source_hash,
            ),
        ),
        approval_receipt_id=str(receipt.receipt_id),
    )
    head = CognitionHeadV1(
        cognition_id=str(identity.cognition_id),
        scope=scope,
        active_revision_id=str(revision.revision_id),
        generation=1,
        authority_receipt_id=str(receipt.receipt_id),
    )
    receipt = receipt.model_copy(
        update={
            "result_revision_id": str(revision.revision_id),
            "result_head_id": str(head.head_id),
        }
    )
    return proposal, receipt, revision, head


class _NoConnectionPool:
    @asynccontextmanager
    async def connection(self):
        raise AssertionError("reconciliation fixture must not use its pool")
        yield


class _ReconciliationStore(CognitionGovernanceStore):
    def __init__(self, *, review, state, revision, head):
        super().__init__(_NoConnectionPool())
        self.review = review
        self.state = state
        self.revision = revision
        self.head = head

    async def load_review(self, *_args, **_kwargs):
        return self.review

    async def load_proposal_state(self, *_args, **_kwargs):
        return self.state

    async def load_revision(self, *_args, **_kwargs):
        return self.revision

    async def load_head(self, *_args, **_kwargs):
        return self.head


@pytest.mark.asyncio
async def test_ambiguous_review_write_accepts_only_exact_reconciled_durable_winner() -> None:
    proposal, receipt, revision, head = _approval_material()
    stored = receipt.model_copy(update={"reviewed_at": receipt.reviewed_at + timedelta(seconds=1)})
    store = _ReconciliationStore(
        review=stored,
        state=ProposalState.APPROVED,
        revision=revision,
        head=head,
    )

    reconciled = await store._classify_possible_review_winner(
        proposal=proposal,
        receipt=receipt,
        revision=revision,
        head=head,
        original=CognitionPersistenceError("ambiguous transaction failure"),
    )

    assert reconciled == stored


@pytest.mark.asyncio
@pytest.mark.parametrize("failure_kind", ("missing", "divergent", "proposal", "revision", "head"))
async def test_ambiguous_review_write_fails_closed_without_exact_reconciliation(failure_kind: str) -> None:
    proposal, receipt, revision, head = _approval_material()
    review = receipt
    state = ProposalState.APPROVED
    stored_revision = revision
    stored_head = head
    if failure_kind == "missing":
        review = None
    elif failure_kind == "divergent":
        review = receipt.model_copy(update={"result_revision_id": "cognition_revision:different"})
    elif failure_kind == "proposal":
        state = ProposalState.PENDING
    elif failure_kind == "revision":
        stored_revision = None
    else:
        stored_head = None
    store = _ReconciliationStore(
        review=review,
        state=state,
        revision=stored_revision,
        head=stored_head,
    )

    failure = CognitionReplayConflict if failure_kind == "divergent" else CognitionPersistenceError
    with pytest.raises(failure):
        await store._classify_possible_review_winner(
            proposal=proposal,
            receipt=receipt,
            revision=revision,
            head=head,
            original=CognitionPersistenceError("ambiguous transaction failure"),
        )


class _TransactionConnection:
    def __init__(self, proposal, revision):
        self.proposal = proposal
        self.revision = revision
        self.raw_query = None
        self.raw_params = None

    async def query(self, query, _params):
        if "cognition_review_receipt" in query:
            return []
        if "cognition_proposal" in query:
            return {"proposal_hash": self.proposal.proposal_hash, "state": ProposalState.PENDING.value}
        if "type::record('cognition'," in query:
            return {"payload": self.proposal.target_identity.model_dump(mode="python")}
        if "cognition_revision" in query:
            return []
        if "cognition_head" in query:
            return []
        raise AssertionError(f"unexpected query: {query}")

    async def query_raw(self, query, params):
        self.raw_query = query
        self.raw_params = params
        return {"result": [{"status": "OK", "result": []}]}


class _TransactionPool:
    def __init__(self, connection):
        self._connection = connection

    @asynccontextmanager
    async def connection(self):
        yield self._connection


@pytest.mark.asyncio
async def test_review_transaction_rechecks_proposal_and_generation_before_any_effect() -> None:
    proposal, receipt, revision, head = _approval_material()
    connection = _TransactionConnection(proposal, revision)
    store = CognitionGovernanceStore(_TransactionPool(connection))

    assert (
        await store.persist_disposition(
            proposal=proposal,
            receipt=receipt,
            revision=revision,
            head=head,
        )
        == receipt
    )

    assert connection.raw_query is not None
    proposal_guard = connection.raw_query.index("LET $current_proposal_state")
    generation_guard = connection.raw_query.index("LET $transaction_generation")
    revision_write = connection.raw_query.index("CREATE ONLY type::record('cognition_revision'")
    assert proposal_guard < generation_guard < revision_write
    assert "THROW 'cognition_proposal_state_conflict'" in connection.raw_query
    assert "THROW 'cognition_head_generation_conflict'" in connection.raw_query
    assert connection.raw_params["expected_current_generation"] is None
