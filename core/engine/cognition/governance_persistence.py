"""Durable product-scoped persistence for cognition proposals and reviews."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from core.engine.cognition.contracts import (
    CognitionHeadV1,
    CognitionIdentityV1,
    CognitionRevisionV1,
    CognitionScopeV1,
    CognitionSourceV1,
    ScopeKind,
    canonical_hash,
    canonical_json,
    stable_id,
)
from core.engine.cognition.governance import (
    ActorClass,
    CognitionProposalV1,
    CognitionReviewReceiptV1,
    ProposalState,
    ReviewActorV1,
    ReviewDisposition,
)
from core.engine.core.db import parse_one, parse_record_id


class CognitionPersistenceError(RuntimeError):
    """A governed-cognition durable write failed closed."""


class CognitionReplayConflict(CognitionPersistenceError):
    """A stable record identity was replayed with different material."""


class CognitionScopeError(CognitionPersistenceError):
    """A record was not available in the requested product scope."""


def _record_key(stable_id_value: str) -> str:
    _, separator, key = stable_id_value.partition(":")
    if not separator or not key:
        raise ValueError("cognition records require table-prefixed stable identities")
    return key


def _scope_product(scope: CognitionScopeV1) -> str:
    if scope.kind not in {ScopeKind.PRODUCT, ScopeKind.WORKSPACE, ScopeKind.USER} or scope.product_id is None:
        raise CognitionScopeError("durable proposal/review requires explicit product scope")
    return scope.product_id


def _same_review_replay(
    stored: CognitionReviewReceiptV1,
    incoming: CognitionReviewReceiptV1,
) -> bool:
    """Ignore only the nondeterministic timestamp on an otherwise exact retry."""
    return stored.model_dump(mode="json", exclude={"reviewed_at"}) == incoming.model_dump(
        mode="json",
        exclude={"reviewed_at"},
    )


def _validated_payload(row: dict[str, Any], contract_type: Any) -> Any:
    """Restore exact contract bytes when available, with pre-v176 compatibility."""
    payload_json = row.get("payload_json")
    if isinstance(payload_json, str):
        return contract_type.model_validate_json(payload_json)
    payload = row.get("payload")
    return contract_type.model_validate(payload) if isinstance(payload, dict) else None


async def _query_or_raise(db: Any, query: str, params: dict[str, Any]) -> Any:
    if ";" in query and hasattr(db, "query_raw"):
        response = await db.query_raw(query, params)
        result = response.get("result") if isinstance(response, dict) else response
    else:
        result = await db.query(query, params)
    errors: list[str] = []
    if isinstance(result, str):
        errors.append(result)
    elif isinstance(result, list):
        for item in result:
            if isinstance(item, str):
                errors.append(item)
            elif isinstance(item, dict) and str(item.get("status", "")).upper() == "ERR":
                errors.append(str(item.get("result") or item.get("detail") or item))
    if errors:
        detail = " | ".join(errors)
        raise CognitionPersistenceError(f"governed cognition persistence failed: {detail[:1000]}")
    return result


class CognitionGovernanceStore:
    """Append-only proposals/reviews with atomic revision and head activation."""

    def __init__(self, pool: Any) -> None:
        self.pool = pool

    async def persist_proposal(self, proposal: CognitionProposalV1) -> CognitionProposalV1:
        product_id = _scope_product(proposal.scope)
        key = _record_key(str(proposal.proposal_id))
        async with self.pool.connection() as db:
            existing = parse_one(
                await db.query(
                    "SELECT proposal_hash, payload_json, payload FROM ONLY "
                    "type::record('cognition_proposal', $record_key) "
                    "WHERE product = $product LIMIT 1",
                    {"record_key": key, "product": parse_record_id(product_id)},
                )
            )
            if existing:
                stored = _validated_payload(existing, CognitionProposalV1)
                if (
                    stored is not None
                    and str(existing.get("proposal_hash")) == proposal.proposal_hash
                    and canonical_hash(stored.model_dump(mode="json", exclude={"created_at"}))
                    == canonical_hash(proposal.model_dump(mode="json", exclude={"created_at"}))
                ):
                    return stored
                raise CognitionReplayConflict(f"stable proposal {proposal.proposal_id} contains different material")
            content = {
                "contract_version": proposal.contract_version,
                "product": parse_record_id(product_id),
                "stable_id": proposal.proposal_id,
                "proposal_hash": proposal.proposal_hash,
                "target_cognition_id": proposal.target_identity.cognition_id,
                "scope": proposal.scope.model_dump(mode="python"),
                "base_revision_id": proposal.base_revision_id,
                "state": ProposalState.PENDING.value,
                "payload": proposal.model_dump(mode="python"),
                "payload_json": canonical_json(proposal),
                "created_at": proposal.created_at,
            }
            await _query_or_raise(
                db,
                "CREATE ONLY type::record('cognition_proposal', $record_key) CONTENT $content",
                {"record_key": key, "content": content},
            )
        return proposal

    async def load_proposal(self, proposal_id: str, *, product_id: str) -> CognitionProposalV1 | None:
        async with self.pool.connection() as db:
            row = parse_one(
                await db.query(
                    "SELECT payload_json, payload FROM ONLY type::record('cognition_proposal', $record_key) "
                    "WHERE product = $product LIMIT 1",
                    {"record_key": _record_key(proposal_id), "product": parse_record_id(product_id)},
                )
            )
        return _validated_payload(row, CognitionProposalV1) if row else None

    async def load_review(self, receipt_id: str, *, product_id: str) -> CognitionReviewReceiptV1 | None:
        async with self.pool.connection() as db:
            row = parse_one(
                await db.query(
                    "SELECT payload_json, payload FROM ONLY "
                    "type::record('cognition_review_receipt', $record_key) "
                    "WHERE product = $product LIMIT 1",
                    {"record_key": _record_key(receipt_id), "product": parse_record_id(product_id)},
                )
            )
        return _validated_payload(row, CognitionReviewReceiptV1) if row else None

    async def load_proposal_state(self, proposal_id: str, *, product_id: str) -> ProposalState | None:
        async with self.pool.connection() as db:
            row = parse_one(
                await db.query(
                    "SELECT state FROM ONLY type::record('cognition_proposal', $record_key) "
                    "WHERE product = $product LIMIT 1",
                    {"record_key": _record_key(proposal_id), "product": parse_record_id(product_id)},
                )
            )
        return ProposalState(str(row["state"])) if row and row.get("state") is not None else None

    async def load_revision(self, revision_id: str) -> CognitionRevisionV1 | None:
        async with self.pool.connection() as db:
            row = parse_one(
                await db.query(
                    "SELECT payload_json, payload FROM ONLY type::record('cognition_revision', $record_key) LIMIT 1",
                    {"record_key": _record_key(revision_id)},
                )
            )
        return _validated_payload(row, CognitionRevisionV1) if row else None

    async def load_head(self, head_id: str) -> CognitionHeadV1 | None:
        async with self.pool.connection() as db:
            row = parse_one(
                await db.query(
                    "SELECT payload_json, payload FROM ONLY type::record('cognition_head', $record_key) LIMIT 1",
                    {"record_key": _record_key(head_id)},
                )
            )
        return _validated_payload(row, CognitionHeadV1) if row else None

    async def persist_disposition(
        self,
        *,
        proposal: CognitionProposalV1,
        receipt: CognitionReviewReceiptV1,
        revision: CognitionRevisionV1 | None,
        head: CognitionHeadV1 | None,
    ) -> CognitionReviewReceiptV1:
        product_id = _scope_product(proposal.scope)
        approving = receipt.disposition is ReviewDisposition.APPROVE
        if approving != (revision is not None and head is not None):
            raise CognitionPersistenceError("approval requires revision and head; non-approval forbids them")
        if receipt.proposal_id != proposal.proposal_id or receipt.proposal_hash != proposal.proposal_hash:
            raise CognitionPersistenceError("review must bind the exact proposal material")
        if revision is not None and (
            revision.identity != proposal.target_identity
            or revision.body != proposal.draft_body
            or revision.approval_receipt_id != receipt.receipt_id
            or receipt.result_revision_id != revision.revision_id
        ):
            raise CognitionPersistenceError("approved revision must equal the reviewed proposal material")
        if head is not None and (
            head.active_revision_id != revision.revision_id
            or head.generation != receipt.expected_head_generation + 1
            or head.authority_receipt_id != receipt.receipt_id
            or receipt.result_head_id != head.head_id
        ):
            raise CognitionPersistenceError("active head must bind the approved revision and review")

        review_key = _record_key(str(receipt.receipt_id))
        proposal_key = _record_key(str(proposal.proposal_id))
        async with self.pool.connection() as db:
            existing_review = parse_one(
                await db.query(
                    "SELECT payload_json, payload FROM ONLY "
                    "type::record('cognition_review_receipt', $record_key) "
                    "WHERE product = $product LIMIT 1",
                    {"record_key": review_key, "product": parse_record_id(product_id)},
                )
            )
            if existing_review:
                stored = _validated_payload(existing_review, CognitionReviewReceiptV1)
                if _same_review_replay(stored, receipt):
                    return stored
                raise CognitionReplayConflict(f"stable review {receipt.receipt_id} contains different material")

            proposal_row = parse_one(
                await db.query(
                    "SELECT proposal_hash, state, payload FROM ONLY "
                    "type::record('cognition_proposal', $record_key) "
                    "WHERE product = $product LIMIT 1",
                    {"record_key": proposal_key, "product": parse_record_id(product_id)},
                )
            )
            if not proposal_row or str(proposal_row.get("proposal_hash")) != proposal.proposal_hash:
                raise CognitionScopeError("review requires the exact persisted product-scoped proposal")
            if proposal_row.get("state") != ProposalState.PENDING.value:
                raise CognitionPersistenceError("proposal is not pending")

            statements = ["BEGIN TRANSACTION"]
            params: dict[str, Any] = {
                "proposal_key": proposal_key,
                "review_key": review_key,
                "product": parse_record_id(product_id),
                "expected_generation": receipt.expected_head_generation,
                "proposal_state": (
                    ProposalState.APPROVED.value
                    if receipt.disposition is ReviewDisposition.APPROVE
                    else (
                        ProposalState.REJECTED.value
                        if receipt.disposition is ReviewDisposition.REJECT
                        else ProposalState.CHANGES_REQUESTED.value
                    )
                ),
                "review_content": {
                    "contract_version": receipt.contract_version,
                    "product": parse_record_id(product_id),
                    "stable_id": receipt.receipt_id,
                    "proposal_id": receipt.proposal_id,
                    "proposal_hash": receipt.proposal_hash,
                    "actor_id": receipt.actor.actor_id,
                    "actor_class": receipt.actor.actor_class.value,
                    "disposition": receipt.disposition.value,
                    "result_revision_id": receipt.result_revision_id,
                    "result_head_id": receipt.result_head_id,
                    "payload": receipt.model_dump(mode="python"),
                    "payload_json": canonical_json(receipt),
                    "reviewed_at": receipt.reviewed_at,
                },
            }
            if approving and revision is not None and head is not None:
                identity = revision.identity
                identity_key = _record_key(str(identity.cognition_id))
                revision_key = _record_key(str(revision.revision_id))
                head_key = _record_key(str(head.head_id))
                activation_id = stable_id(
                    "cognition_activation",
                    {"head_id": head.head_id, "generation": head.generation, "review": receipt.receipt_id},
                )
                params.update(
                    {
                        "identity_key": identity_key,
                        "revision_key": revision_key,
                        "head_key": head_key,
                        "activation_key": _record_key(activation_id),
                        "identity_content": _identity_content(identity),
                        "revision_content": _revision_content(revision),
                        "head_content": _head_content(head),
                        "activation_content": {
                            "contract_version": head.contract_version,
                            "cognition": parse_record_id(str(identity.cognition_id)),
                            "scope": head.scope.model_dump(mode="python"),
                            "prior_revision": None,
                            "active_revision": parse_record_id(str(revision.revision_id)),
                            "generation": head.generation,
                            "disposition": "activate",
                            "authority_receipt_id": receipt.receipt_id,
                            "payload": {
                                "head_id": head.head_id,
                                "review_receipt_id": receipt.receipt_id,
                            },
                        },
                    }
                )
                existing_identity = parse_one(
                    await db.query(
                        "SELECT payload_json, payload FROM ONLY type::record('cognition', $record_key) LIMIT 1",
                        {"record_key": identity_key},
                    )
                )
                if existing_identity:
                    stored_identity = _validated_payload(existing_identity, CognitionIdentityV1)
                    if stored_identity != identity:
                        raise CognitionReplayConflict("stable cognition identity contains different material")
                else:
                    statements.append("CREATE ONLY type::record('cognition', $identity_key) CONTENT $identity_content")
                existing_revision = parse_one(
                    await db.query(
                        "SELECT material_hash, payload FROM ONLY "
                        "type::record('cognition_revision', $record_key) LIMIT 1",
                        {"record_key": revision_key},
                    )
                )
                if existing_revision:
                    raise CognitionReplayConflict("partial approval revision exists without its review receipt")

                current_head = parse_one(
                    await db.query(
                        "SELECT generation, payload FROM ONLY type::record('cognition_head', $record_key) LIMIT 1",
                        {"record_key": head_key},
                    )
                )
                actual_generation = int(current_head.get("generation", 0)) if current_head else 0
                if actual_generation != receipt.expected_head_generation:
                    raise CognitionPersistenceError(
                        f"cognition_head_generation_conflict:expected={receipt.expected_head_generation}:"
                        f"actual={actual_generation}"
                    )
                statements.extend(
                    [
                        "CREATE ONLY type::record('cognition_revision', $revision_key) CONTENT $revision_content",
                        (
                            "CREATE ONLY type::record('cognition_head', $head_key) CONTENT $head_content"
                            if current_head is None
                            else "UPDATE ONLY type::record('cognition_head', $head_key) CONTENT $head_content"
                        ),
                        "CREATE ONLY type::record('cognition_activation_event', $activation_key) "
                        "CONTENT $activation_content",
                    ]
                )
            statements.extend(
                [
                    "CREATE ONLY type::record('cognition_review_receipt', $review_key) CONTENT $review_content",
                    "UPDATE ONLY type::record('cognition_proposal', $proposal_key) SET state = $proposal_state",
                    "COMMIT TRANSACTION",
                ]
            )
            await _query_or_raise(db, ";\n".join(statements) + ";", params)
        return receipt


def _identity_content(identity: CognitionIdentityV1) -> dict[str, Any]:
    return {
        "contract_version": identity.contract_version,
        "cognition_type": identity.cognition_type.value,
        "owner": identity.owner.model_dump(mode="python"),
        "stable_key": identity.stable_key,
        "payload": identity.model_dump(mode="python"),
        "payload_json": canonical_json(identity),
    }


def _revision_content(revision: CognitionRevisionV1) -> dict[str, Any]:
    return {
        "contract_version": revision.contract_version,
        "cognition": parse_record_id(str(revision.identity.cognition_id)),
        "body_schema_version": revision.body_schema_version,
        "body": revision.body,
        "dependencies": [item.model_dump(mode="python") for item in revision.dependencies],
        "sources": [item.model_dump(mode="python") for item in revision.sources],
        "material_hash": revision.material_hash,
        "approval_receipt_id": revision.approval_receipt_id,
        "payload": revision.model_dump(mode="python"),
        "payload_json": canonical_json(revision),
    }


def _head_content(head: CognitionHeadV1) -> dict[str, Any]:
    content = {
        "contract_version": head.contract_version,
        "cognition": parse_record_id(head.cognition_id),
        "scope": head.scope.model_dump(mode="python"),
        "active_revision": parse_record_id(head.active_revision_id),
        "generation": head.generation,
        "lifecycle": head.lifecycle,
        "authority_receipt_id": head.authority_receipt_id,
        "expires_at": head.expires_at,
        "payload": head.model_dump(mode="python"),
        "payload_json": canonical_json(head),
    }
    content["effective_at"] = head.effective_at or datetime.now(timezone.utc)
    return content


class DurableCognitionGovernanceService:
    """Product-scoped proposal/review facade whose write chain is durable."""

    def __init__(self, store: CognitionGovernanceStore) -> None:
        self.store = store

    async def propose(self, proposal: CognitionProposalV1) -> CognitionProposalV1:
        return await self.store.persist_proposal(proposal)

    async def review(
        self,
        *,
        proposal_id: str,
        product_id: str,
        review_request_id: str,
        actor: ReviewActorV1,
        disposition: ReviewDisposition,
        rationale: str,
        expected_head_generation: int,
    ) -> CognitionReviewReceiptV1:
        if actor.actor_class is not ActorClass.HUMAN or "cognition-review" not in actor.authorities:
            raise PermissionError("human_authority_required")
        proposal = await self.store.load_proposal(proposal_id, product_id=product_id)
        if proposal is None:
            raise CognitionScopeError("proposal is unavailable in product scope")
        receipt = CognitionReviewReceiptV1(
            review_request_id=review_request_id,
            proposal_id=proposal_id,
            proposal_hash=str(proposal.proposal_hash),
            actor=actor,
            disposition=disposition,
            rationale=rationale,
            expected_head_generation=expected_head_generation,
        )
        revision = None
        head = None
        if disposition is ReviewDisposition.APPROVE:
            revision = CognitionRevisionV1(
                identity=proposal.target_identity,
                body_schema_version=proposal.body_schema_version,
                body=proposal.draft_body,
                dependencies=proposal.dependencies,
                sources=tuple(
                    # Proposal sources are immutable content identities; review
                    # grants lifecycle authority but never changes provenance.
                    CognitionSourceV1(
                        source_kind=item.source_kind,
                        locator=item.source_id,
                        content_hash=item.content_hash,
                    )
                    for item in proposal.sources
                ),
                approval_receipt_id=str(receipt.receipt_id),
            )
            head = CognitionHeadV1(
                cognition_id=str(proposal.target_identity.cognition_id),
                scope=proposal.scope,
                active_revision_id=str(revision.revision_id),
                generation=expected_head_generation + 1,
                authority_receipt_id=str(receipt.receipt_id),
            )
            receipt = receipt.model_copy(
                update={
                    "result_revision_id": str(revision.revision_id),
                    "result_head_id": str(head.head_id),
                }
            )
        return await self.store.persist_disposition(
            proposal=proposal,
            receipt=receipt,
            revision=revision,
            head=head,
        )
