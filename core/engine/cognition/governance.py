"""Sourced proposals, semantic diffs, and human-only cognition review."""

from __future__ import annotations

import asyncio
from datetime import datetime, timezone
from enum import StrEnum
from typing import Annotated, Any, Self

from pydantic import Field, field_validator, model_validator

from core.engine.cognition.contracts import (
    MAX_BODY_BYTES,
    CognitionDependencyV1,
    CognitionHeadV1,
    CognitionIdentityV1,
    CognitionRevisionV1,
    CognitionScopeV1,
    CognitionSourceV1,
    FrozenContract,
    canonical_hash,
    canonical_json,
    stable_id,
)
from core.engine.cognition.store import InMemoryCognitionStore

COGNITION_PROPOSAL_VERSION = "ace.cognition.proposal/v1"
COGNITION_REVIEW_VERSION = "ace.cognition.review/v1"
COGNITION_DIFF_VERSION = "ace.cognition.semantic-diff/v1"
COGNITION_PROPOSAL_POLICY = "ace.cognition.proposal-policy/v1"
COGNITION_REVIEW_POLICY = "ace.cognition.review-policy/v1"

MAX_PROPOSAL_SOURCES = 200
MAX_DIFF_CHANGES = 500
AuthorityToken = Annotated[
    str,
    Field(min_length=1, max_length=120, pattern=r"^[A-Za-z0-9][A-Za-z0-9._:-]{0,119}$"),
]


def _aware(value: datetime, name: str) -> datetime:
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError(f"{name} must include a timezone")
    return value


class ActorClass(StrEnum):
    HUMAN = "human"
    MODEL = "model"
    SYSTEM = "system"
    # Additive: an authenticated, registered, product-scoped SERVICE principal
    # acting under pre-existing delegated grants. It is never coerced to HUMAN
    # and never satisfies the human-authority check below.
    SERVICE = "service"


class ProposalState(StrEnum):
    PENDING = "pending"
    APPROVED = "approved"
    REJECTED = "rejected"
    CHANGES_REQUESTED = "changes_requested"
    SUPERSEDED = "superseded"


class ReviewDisposition(StrEnum):
    APPROVE = "approve"
    REJECT = "reject"
    REQUEST_CHANGES = "request_changes"


class ReviewActorV1(FrozenContract):
    actor_id: str = Field(min_length=1, max_length=240)
    actor_class: ActorClass
    authorities: tuple[AuthorityToken, ...] = Field(default_factory=tuple, max_length=50)


class ProposalSourceV1(FrozenContract):
    source_id: str = Field(min_length=1, max_length=240)
    source_kind: str = Field(min_length=1, max_length=80)
    content_hash: str = Field(pattern=r"^[a-f0-9]{64}$")
    relation: str = Field(default="supports", min_length=1, max_length=80)


class CognitionProposalV1(FrozenContract):
    contract_version: str = COGNITION_PROPOSAL_VERSION
    proposal_id: str | None = None
    proposal_hash: str | None = None
    target_identity: CognitionIdentityV1
    scope: CognitionScopeV1
    intent: str = Field(min_length=1, max_length=2_000)
    sources: tuple[ProposalSourceV1, ...] = Field(min_length=1, max_length=MAX_PROPOSAL_SOURCES)
    base_revision_id: str | None = Field(default=None, max_length=240)
    body_schema_version: str = Field(min_length=1, max_length=120)
    draft_body: dict[str, Any]
    dependencies: tuple[CognitionDependencyV1, ...] = Field(default_factory=tuple, max_length=512)
    created_by: ReviewActorV1
    policy_version: str = COGNITION_PROPOSAL_POLICY
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))

    @field_validator("created_at")
    @classmethod
    def validate_time(cls, value: datetime) -> datetime:
        return _aware(value, "created_at")

    @field_validator("draft_body")
    @classmethod
    def validate_body(cls, value: dict[str, Any]) -> dict[str, Any]:
        if len(canonical_json(value).encode("utf-8")) > MAX_BODY_BYTES:
            raise ValueError("proposal draft exceeds the cognition body bound")
        return value

    @model_validator(mode="after")
    def derive_identity(self) -> Self:
        material = {
            "contract_version": self.contract_version,
            "target_identity": self.target_identity.model_dump(mode="json"),
            "scope": self.scope.model_dump(mode="json"),
            "intent": self.intent,
            "sources": [item.model_dump(mode="json") for item in self.sources],
            "base_revision_id": self.base_revision_id,
            "body_schema_version": self.body_schema_version,
            "draft_body": self.draft_body,
            "dependencies": [item.model_dump(mode="json") for item in self.dependencies],
            "created_by": self.created_by.model_dump(mode="json"),
            "policy_version": self.policy_version,
        }
        digest = canonical_hash(material)
        expected = f"cognition_proposal:{digest[:32]}"
        if self.proposal_hash is not None and self.proposal_hash != digest:
            raise ValueError("proposal hash does not match exact proposal material")
        if self.proposal_id is not None and self.proposal_id != expected:
            raise ValueError("proposal identity does not match exact proposal material")
        object.__setattr__(self, "proposal_hash", digest)
        object.__setattr__(self, "proposal_id", expected)
        return self


class SemanticDiffChangeV1(FrozenContract):
    path: str = Field(min_length=1, max_length=500)
    operation: str = Field(pattern=r"^(add|remove|replace)$")
    before: Any = None
    after: Any = None


class CognitionSemanticDiffV1(FrozenContract):
    contract_version: str = COGNITION_DIFF_VERSION
    proposal_id: str
    base_revision_id: str | None = None
    base_material_hash: str | None = None
    draft_material_hash: str
    changes: tuple[SemanticDiffChangeV1, ...] = Field(max_length=MAX_DIFF_CHANGES)


class CognitionReviewReceiptV1(FrozenContract):
    contract_version: str = COGNITION_REVIEW_VERSION
    receipt_id: str | None = None
    review_request_id: str = Field(min_length=1, max_length=240)
    proposal_id: str = Field(min_length=1, max_length=240)
    proposal_hash: str = Field(pattern=r"^[a-f0-9]{64}$")
    actor: ReviewActorV1
    disposition: ReviewDisposition
    rationale: str = Field(min_length=1, max_length=4_000)
    policy_version: str = COGNITION_REVIEW_POLICY
    expected_head_generation: int = Field(ge=0)
    result_revision_id: str | None = Field(default=None, max_length=240)
    result_head_id: str | None = Field(default=None, max_length=240)
    reviewed_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))

    @field_validator("reviewed_at")
    @classmethod
    def validate_time(cls, value: datetime) -> datetime:
        return _aware(value, "reviewed_at")

    @model_validator(mode="after")
    def derive_identity(self) -> Self:
        material = {
            "contract_version": self.contract_version,
            "review_request_id": self.review_request_id,
            "proposal_id": self.proposal_id,
            "proposal_hash": self.proposal_hash,
            "actor": self.actor.model_dump(mode="json"),
            "disposition": self.disposition,
            "rationale": self.rationale,
            "policy_version": self.policy_version,
            "expected_head_generation": self.expected_head_generation,
        }
        expected = stable_id("cognition_review", material)
        if self.receipt_id is not None and self.receipt_id != expected:
            raise ValueError("review receipt identity does not match exact review request")
        object.__setattr__(self, "receipt_id", expected)
        return self


def _semantic_changes(before: Any, after: Any, path: str = "$") -> list[SemanticDiffChangeV1]:
    if before == after:
        return []
    if isinstance(before, dict) and isinstance(after, dict):
        out: list[SemanticDiffChangeV1] = []
        for key in sorted(set(before) | set(after)):
            child = f"{path}.{key}"
            if key not in before:
                out.append(SemanticDiffChangeV1(path=child, operation="add", after=after[key]))
            elif key not in after:
                out.append(SemanticDiffChangeV1(path=child, operation="remove", before=before[key]))
            else:
                out.extend(_semantic_changes(before[key], after[key], child))
        return out
    if isinstance(before, list) and isinstance(after, list):
        out = []
        for index in range(max(len(before), len(after))):
            child = f"{path}[{index}]"
            if index >= len(before):
                out.append(SemanticDiffChangeV1(path=child, operation="add", after=after[index]))
            elif index >= len(after):
                out.append(SemanticDiffChangeV1(path=child, operation="remove", before=before[index]))
            else:
                out.extend(_semantic_changes(before[index], after[index], child))
        return out
    return [SemanticDiffChangeV1(path=path, operation="replace", before=before, after=after)]


def build_semantic_diff(
    proposal: CognitionProposalV1,
    *,
    base_revision: CognitionRevisionV1 | None,
) -> CognitionSemanticDiffV1:
    if proposal.base_revision_id is None and base_revision is not None:
        raise RuntimeError("cognition_unexpected_base_revision")
    if proposal.base_revision_id is not None:
        if base_revision is None or base_revision.revision_id != proposal.base_revision_id:
            raise RuntimeError(f"cognition_base_revision_unavailable:{proposal.base_revision_id}")
        if base_revision.identity.cognition_id != proposal.target_identity.cognition_id:
            raise RuntimeError("cognition_base_revision_identity_mismatch")
    before = base_revision.body if base_revision is not None else {}
    changes = tuple(_semantic_changes(before, proposal.draft_body))
    if len(changes) > MAX_DIFF_CHANGES:
        raise RuntimeError("cognition_semantic_diff_exceeds_bound")
    return CognitionSemanticDiffV1(
        proposal_id=str(proposal.proposal_id),
        base_revision_id=proposal.base_revision_id,
        base_material_hash=base_revision.material_hash if base_revision is not None else None,
        draft_material_hash=canonical_hash(proposal.draft_body),
        changes=changes,
    )


class CognitionGovernanceService:
    """In-process governance service with atomic revision/head application."""

    def __init__(self, store: InMemoryCognitionStore) -> None:
        self.store = store
        self._proposals: dict[str, CognitionProposalV1] = {}
        self._states: dict[str, ProposalState] = {}
        self._reviews: dict[str, CognitionReviewReceiptV1] = {}
        self._lock = asyncio.Lock()

    async def propose(self, proposal: CognitionProposalV1) -> CognitionProposalV1:
        proposal_id = str(proposal.proposal_id)
        existing = self._proposals.get(proposal_id)
        if existing is not None:
            if existing.proposal_hash != proposal.proposal_hash:
                raise RuntimeError(f"cognition_proposal_conflict:{proposal_id}")
            return existing
        self._proposals[proposal_id] = proposal
        self._states.setdefault(proposal_id, ProposalState.PENDING)
        return proposal

    def proposal(self, proposal_id: str) -> CognitionProposalV1 | None:
        return self._proposals.get(proposal_id)

    def proposal_state(self, proposal_id: str) -> ProposalState | None:
        return self._states.get(proposal_id)

    def semantic_diff(self, proposal_id: str) -> CognitionSemanticDiffV1:
        proposal = self._proposals.get(proposal_id)
        if proposal is None:
            raise KeyError(f"cognition_proposal_not_found:{proposal_id}")
        base = None
        if proposal.base_revision_id is not None:
            base = self.store.revision(proposal.base_revision_id)
        return build_semantic_diff(proposal, base_revision=base)

    @staticmethod
    def _require_human_authority(actor: ReviewActorV1) -> None:
        if actor.actor_class is not ActorClass.HUMAN or "cognition-review" not in actor.authorities:
            raise PermissionError("human_authority_required")

    async def review(
        self,
        *,
        proposal_id: str,
        review_request_id: str,
        actor: ReviewActorV1,
        disposition: ReviewDisposition,
        rationale: str,
        expected_head_generation: int,
        runtime_view: Any,
    ) -> CognitionReviewReceiptV1:
        self._require_human_authority(actor)
        async with self._lock:
            proposal = self._proposals.get(proposal_id)
            if proposal is None:
                raise KeyError(f"cognition_proposal_not_found:{proposal_id}")
            if self._states.get(proposal_id) is not ProposalState.PENDING:
                existing = next(
                    (
                        item
                        for item in self._reviews.values()
                        if item.review_request_id == review_request_id and item.proposal_id == proposal_id
                    ),
                    None,
                )
                if existing is not None:
                    return existing
                raise RuntimeError(f"cognition_proposal_not_pending:{proposal_id}")
            receipt = CognitionReviewReceiptV1(
                review_request_id=review_request_id,
                proposal_id=proposal_id,
                proposal_hash=str(proposal.proposal_hash),
                actor=actor,
                disposition=disposition,
                rationale=rationale,
                expected_head_generation=expected_head_generation,
            )
            receipt_id = str(receipt.receipt_id)
            if disposition is ReviewDisposition.REJECT:
                self._states[proposal_id] = ProposalState.REJECTED
                self._reviews[receipt_id] = receipt
                return receipt
            if disposition is ReviewDisposition.REQUEST_CHANGES:
                self._states[proposal_id] = ProposalState.CHANGES_REQUESTED
                self._reviews[receipt_id] = receipt
                return receipt

            sources = tuple(
                CognitionSourceV1(
                    source_kind=item.source_kind,
                    locator=item.source_id,
                    content_hash=item.content_hash,
                )
                for item in proposal.sources
            )
            revision = CognitionRevisionV1(
                identity=proposal.target_identity,
                body_schema_version=proposal.body_schema_version,
                body=proposal.draft_body,
                dependencies=proposal.dependencies,
                sources=sources,
                approval_receipt_id=receipt_id,
            )
            head = CognitionHeadV1(
                cognition_id=str(proposal.target_identity.cognition_id),
                scope=proposal.scope,
                active_revision_id=str(revision.revision_id),
                generation=expected_head_generation + 1,
                authority_receipt_id=receipt_id,
            )
            final_receipt = receipt.model_copy(
                update={
                    "result_revision_id": str(revision.revision_id),
                    "result_head_id": str(head.head_id),
                }
            )
            self.store.commit_revision_and_head(
                revision,
                runtime_view=runtime_view,
                head=head,
                expected_generation=expected_head_generation,
            )
            self._states[proposal_id] = ProposalState.APPROVED
            self._reviews[receipt_id] = final_receipt
            return final_receipt
