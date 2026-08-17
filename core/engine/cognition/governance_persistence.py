"""Durable product-scoped persistence for cognition proposals and reviews."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from ace.core.records import (
    AppendOnlyTransactionReceiptV1,
    AppendOnlyTransactionRequestV1,
    ImmutableRecordV1,
    append_only_receipt_id,
)
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
from core.engine.cognition.delegated_activation import (
    DELEGATED_RECORD_SPACE,
    DelegatedCognitionActivationReceiptV1Alpha1,
    DelegatedCognitionApprovalReceiptV1Alpha1,
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


class CognitionDelegatedPreconditionError(CognitionPersistenceError):
    """A governed-state, principal, capability, or head precondition failed."""


DELEGATED_PRECONDITION_THROW = "delegated_governed_state_precondition_failed"
_DELEGATED_APPROVAL_REPLAY_QUERY = (
    "SELECT payload_json, payload FROM cognition_delegated_approval_receipt "
    "WHERE product = $product AND replay_key = $replay_key LIMIT 1"
)
_DELEGATED_ACTIVATION_REPLAY_QUERY = (
    "SELECT payload_json, payload FROM cognition_delegated_activation_receipt "
    "WHERE product = $product AND replay_key = $replay_key LIMIT 1"
)
DELEGATED_GRANT_EXPIRED_THROW = "delegated_grant_expired_at_commit"


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


def _precondition_identity(value: Any) -> tuple[Any, ...]:
    return (
        value.state_kind,
        value.product_id,
        value.state_id,
        value.sequence,
        value.revision_id,
        value.commit_receipt_id,
    )


def _validate_delegated_evidence(
    evidence: AppendOnlyTransactionRequestV1,
    *,
    stage: str,
    product_id: str,
    request_ref: str,
    preconditions: tuple[Any, ...],
) -> AppendOnlyTransactionReceiptV1:
    """Validate the exact evidence bundle that joins one cognition commit."""

    expected_kinds = (
        f"{stage}_capability_use",
        f"{stage}_authority_use",
        f"{stage}_authority_use",
    )
    canonical_preconditions = tuple(sorted(preconditions, key=_precondition_identity))
    if (
        evidence.product_id != product_id
        or evidence.record_space != DELEGATED_RECORD_SPACE
        or evidence.transaction_key != f"delegated_cognition:{stage}:{request_ref}"
        or evidence.governed_state_preconditions != canonical_preconditions
        or len(evidence.records) != 3
        or tuple(record.record_kind for record in evidence.records) != expected_kinds
        or tuple(record.processing_order for record in evidence.records) != (0, 1, 2)
        or any(record.product_id != product_id for record in evidence.records)
        or any(record.record_space != DELEGATED_RECORD_SPACE for record in evidence.records)
    ):
        raise CognitionPersistenceError("delegated evidence does not bind the exact cognition transaction")
    return evidence.receipt()


def _delegated_evidence_statements(
    evidence: AppendOnlyTransactionRequestV1,
    expected: AppendOnlyTransactionReceiptV1,
    *,
    params: dict[str, Any],
) -> list[str]:
    """Inline immutable evidence and its receipt in the caller's transaction."""

    statements: list[str] = []
    for index, record in enumerate(evidence.records):
        params[f"evidence_key_{index}"] = _record_key(str(record.storage_id))
        params[f"evidence_content_{index}"] = {
            "contract_version": record.contract,
            "product": parse_record_id(record.product_id),
            "record_space": record.record_space,
            "record_kind": record.record_kind,
            "record_key": record.record_key,
            "stable_id": record.storage_id,
            "material_hash": record.material_hash,
            "transaction_id": expected.transaction_id,
            "payload_contract": record.payload_contract,
            "as_of": record.as_of,
            "available_at": record.available_at,
            "processing_order": record.processing_order,
            "payload": {},
            "payload_json": canonical_json(record),
            "created_at": expected.committed_at,
        }
        statements.append(
            f"CREATE ONLY type::record('immutable_record', $evidence_key_{index}) CONTENT $evidence_content_{index}"
        )
    params["evidence_receipt_key"] = _record_key(str(expected.receipt_id))
    params["evidence_receipt_content"] = {
        "contract_version": expected.contract,
        "product": parse_record_id(expected.product_id),
        "record_space": expected.record_space,
        "transaction_key": expected.transaction_key,
        "transaction_id": expected.transaction_id,
        "stable_id": expected.receipt_id,
        "request_hash": expected.request_hash,
        "material_hash": expected.receipt_hash,
        "record_ids": [reference.storage_id for reference in expected.records],
        "payload": {},
        "payload_json": canonical_json(expected),
        "created_at": expected.committed_at,
    }
    statements.append(
        "CREATE ONLY type::record('append_only_transaction_receipt', $evidence_receipt_key) "
        "CONTENT $evidence_receipt_content"
    )
    return statements


class CognitionGovernanceStore:
    """Append-only proposals/reviews with atomic revision and head activation."""

    def __init__(
        self,
        pool: Any,
        *,
        _simulate_delegated_failure_after_evidence: bool = False,
        _simulate_delegated_failure_after_cognition: bool = False,
    ) -> None:
        self.pool = pool
        self._simulate_delegated_failure_after_evidence = _simulate_delegated_failure_after_evidence
        self._simulate_delegated_failure_after_cognition = _simulate_delegated_failure_after_cognition

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

    async def _classify_possible_review_winner(
        self,
        *,
        proposal: CognitionProposalV1,
        receipt: CognitionReviewReceiptV1,
        revision: CognitionRevisionV1 | None,
        head: CognitionHeadV1 | None,
        original: CognitionPersistenceError,
    ) -> CognitionReviewReceiptV1:
        """Accept an ambiguous write only when every exact durable effect reconciles."""

        product_id = _scope_product(proposal.scope)
        try:
            stored = await self.load_review(str(receipt.receipt_id), product_id=product_id)
            if stored is None:
                raise original
            if not _same_review_replay(stored, receipt):
                raise CognitionReplayConflict(
                    f"stable review {receipt.receipt_id} contains different material"
                ) from None
            expected_state = (
                ProposalState.APPROVED
                if receipt.disposition is ReviewDisposition.APPROVE
                else (
                    ProposalState.REJECTED
                    if receipt.disposition is ReviewDisposition.REJECT
                    else ProposalState.CHANGES_REQUESTED
                )
            )
            if await self.load_proposal_state(str(proposal.proposal_id), product_id=product_id) is not expected_state:
                raise CognitionPersistenceError("possible review winner did not reconcile proposal state") from None
            if revision is not None and await self.load_revision(str(revision.revision_id)) != revision:
                raise CognitionPersistenceError("possible review winner did not reconcile exact revision") from None
            if head is not None and await self.load_head(str(head.head_id)) != head:
                raise CognitionPersistenceError("possible review winner did not reconcile exact head") from None
            return stored
        except CognitionReplayConflict:
            raise
        except CognitionPersistenceError:
            raise
        except Exception:
            raise CognitionPersistenceError("possible review winner failed exact durable reconciliation") from None

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

            statements = [
                "BEGIN TRANSACTION",
                "LET $current_proposal_state = SELECT VALUE state FROM ONLY "
                "type::record('cognition_proposal', $proposal_key) WHERE product = $product",
                "IF $current_proposal_state != 'pending' { THROW 'cognition_proposal_state_conflict'; }",
            ]
            params: dict[str, Any] = {
                "proposal_key": proposal_key,
                "review_key": review_key,
                "product": parse_record_id(product_id),
                "expected_generation": receipt.expected_head_generation,
                "expected_current_generation": (
                    None if receipt.expected_head_generation == 0 else receipt.expected_head_generation
                ),
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
                        "LET $transaction_generation = SELECT VALUE generation FROM ONLY "
                        "type::record('cognition_head', $head_key)",
                        "IF $transaction_generation != $expected_current_generation "
                        "{ THROW 'cognition_head_generation_conflict'; }",
                        "CREATE ONLY type::record('cognition_revision', $revision_key) CONTENT $revision_content",
                        "IF $transaction_generation = NONE "
                        "{ CREATE ONLY type::record('cognition_head', $head_key) CONTENT $head_content; } "
                        "ELSE { UPDATE ONLY type::record('cognition_head', $head_key) CONTENT $head_content; }",
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
            try:
                await _query_or_raise(db, ";\n".join(statements) + ";", params)
            except Exception as exc:
                original = (
                    exc
                    if isinstance(exc, CognitionPersistenceError)
                    else CognitionPersistenceError("governed cognition persistence failed")
                )
                return await self._classify_possible_review_winner(
                    proposal=proposal,
                    receipt=receipt,
                    revision=revision,
                    head=head,
                    original=original,
                )
        return receipt

    # ------------------------------------------------------------------
    # Slice 7: delegated headless review and activation (additive).
    # The human write chain above is untouched; these methods add the only
    # non-human path and never issue, mint, widen, renew, or transfer authority.
    # ------------------------------------------------------------------

    async def load_delegated_approval(
        self,
        receipt_id: str,
        *,
        product_id: str,
    ) -> DelegatedCognitionApprovalReceiptV1Alpha1 | None:
        async with self.pool.connection() as db:
            row = parse_one(
                await db.query(
                    "SELECT payload_json, payload FROM ONLY "
                    "type::record('cognition_delegated_approval_receipt', $record_key) "
                    "WHERE product = $product LIMIT 1",
                    {"record_key": _record_key(receipt_id), "product": parse_record_id(product_id)},
                )
            )
        return _validated_payload(row, DelegatedCognitionApprovalReceiptV1Alpha1) if row else None

    async def load_delegated_activation(
        self,
        receipt_id: str,
        *,
        product_id: str,
    ) -> DelegatedCognitionActivationReceiptV1Alpha1 | None:
        async with self.pool.connection() as db:
            row = parse_one(
                await db.query(
                    "SELECT payload_json, payload FROM ONLY "
                    "type::record('cognition_delegated_activation_receipt', $record_key) "
                    "WHERE product = $product LIMIT 1",
                    {"record_key": _record_key(receipt_id), "product": parse_record_id(product_id)},
                )
            )
        return _validated_payload(row, DelegatedCognitionActivationReceiptV1Alpha1) if row else None

    async def _load_delegated_by_replay(
        self,
        query: str,
        contract_type: Any,
        *,
        product_id: str,
        replay_key: str,
    ) -> Any:
        async with self.pool.connection() as db:
            row = parse_one(
                await db.query(
                    query,
                    {"product": parse_record_id(product_id), "replay_key": replay_key},
                )
            )
        return _validated_payload(row, contract_type) if row else None

    @staticmethod
    def _same_delegated_replay(stored: Any, incoming: Any) -> bool:
        return stored is not None and stored.receipt_id == incoming.receipt_id and stored == incoming

    async def _load_exact_delegated_evidence(
        self,
        evidence: AppendOnlyTransactionRequestV1,
    ) -> AppendOnlyTransactionReceiptV1 | None:
        """Return a complete exact evidence winner; reject any partial/divergent state."""

        expected = evidence.receipt()
        async with self.pool.connection() as db:
            receipt_row = parse_one(
                await db.query(
                    "SELECT payload_json FROM ONLY "
                    "type::record('append_only_transaction_receipt', $record_key) "
                    "WHERE product = $product AND record_space = $record_space LIMIT 1",
                    {
                        "record_key": _record_key(str(expected.receipt_id)),
                        "product": parse_record_id(expected.product_id),
                        "record_space": expected.record_space,
                    },
                )
            )
            record_rows = []
            for record in evidence.records:
                record_rows.append(
                    parse_one(
                        await db.query(
                            "SELECT payload_json FROM ONLY type::record('immutable_record', $record_key) "
                            "WHERE product = $product AND record_space = $record_space "
                            "AND record_kind = $record_kind LIMIT 1",
                            {
                                "record_key": _record_key(str(record.storage_id)),
                                "product": parse_record_id(record.product_id),
                                "record_space": record.record_space,
                                "record_kind": record.record_kind,
                            },
                        )
                    )
                )
        present = [receipt_row is not None, *(row is not None for row in record_rows)]
        if not any(present):
            return None
        if not all(present):
            raise CognitionReplayConflict("delegated composite contains partial immutable evidence")
        try:
            stored_receipt = _validated_payload(receipt_row, AppendOnlyTransactionReceiptV1)
            stored_records = tuple(_validated_payload(row, ImmutableRecordV1) for row in record_rows)
        except ValueError as exc:
            raise CognitionReplayConflict("delegated composite contains invalid immutable evidence") from exc
        if stored_receipt != expected or stored_records != evidence.records:
            raise CognitionReplayConflict("delegated composite immutable evidence diverged")
        return stored_receipt

    async def _load_historical_delegated_evidence(
        self,
        *,
        product_id: str,
        stage: str,
        request_ref: str,
    ) -> AppendOnlyTransactionReceiptV1:
        """Reconcile a sealed replay without re-resolving current authority."""

        transaction_key = f"delegated_cognition:{stage}:{request_ref}"
        receipt_id = append_only_receipt_id(
            product_id=product_id,
            record_space=DELEGATED_RECORD_SPACE,
            transaction_key=transaction_key,
        )
        async with self.pool.connection() as db:
            receipt_row = parse_one(
                await db.query(
                    "SELECT payload_json FROM ONLY "
                    "type::record('append_only_transaction_receipt', $record_key) "
                    "WHERE product = $product AND record_space = $record_space LIMIT 1",
                    {
                        "record_key": _record_key(receipt_id),
                        "product": parse_record_id(product_id),
                        "record_space": DELEGATED_RECORD_SPACE,
                    },
                )
            )
            if receipt_row is None:
                raise CognitionReplayConflict("delegated replay is missing its immutable evidence receipt")
            try:
                receipt = _validated_payload(receipt_row, AppendOnlyTransactionReceiptV1)
            except ValueError as exc:
                raise CognitionReplayConflict("delegated replay evidence receipt is invalid") from exc
            if (
                receipt is None
                or receipt.product_id != product_id
                or receipt.record_space != DELEGATED_RECORD_SPACE
                or receipt.transaction_key != transaction_key
                or len(receipt.records) != 3
                or tuple(reference.record_kind for reference in receipt.records)
                != (
                    f"{stage}_capability_use",
                    f"{stage}_authority_use",
                    f"{stage}_authority_use",
                )
            ):
                raise CognitionReplayConflict("delegated replay evidence receipt diverged")
            for reference in receipt.records:
                row = parse_one(
                    await db.query(
                        "SELECT payload_json FROM ONLY type::record('immutable_record', $record_key) "
                        "WHERE product = $product AND record_space = $record_space "
                        "AND record_kind = $record_kind LIMIT 1",
                        {
                            "record_key": _record_key(reference.storage_id),
                            "product": parse_record_id(product_id),
                            "record_space": DELEGATED_RECORD_SPACE,
                            "record_kind": reference.record_kind,
                        },
                    )
                )
                if row is None:
                    raise CognitionReplayConflict("delegated replay contains partial immutable evidence")
                try:
                    record = _validated_payload(row, ImmutableRecordV1)
                except ValueError as exc:
                    raise CognitionReplayConflict("delegated replay immutable evidence is invalid") from exc
                if record is None or record.reference() != reference:
                    raise CognitionReplayConflict("delegated replay immutable evidence diverged")
        return receipt

    async def validate_delegated_approval_history(
        self,
        receipt: DelegatedCognitionApprovalReceiptV1Alpha1,
    ) -> None:
        await self._load_historical_delegated_evidence(
            product_id=receipt.product_id,
            stage="approval",
            request_ref=receipt.request_ref,
        )
        proposal = await self.load_proposal(receipt.proposal_id, product_id=receipt.product_id)
        state = await self.load_proposal_state(receipt.proposal_id, product_id=receipt.product_id)
        if (
            proposal is None
            or proposal.proposal_hash != receipt.proposal_hash
            or state not in {ProposalState.PENDING, ProposalState.APPROVED}
        ):
            raise CognitionReplayConflict("delegated approval history proposal position diverged")

    async def validate_delegated_activation_history(
        self,
        receipt: DelegatedCognitionActivationReceiptV1Alpha1,
    ) -> None:
        await self._load_historical_delegated_evidence(
            product_id=receipt.product_id,
            stage="approval",
            request_ref=receipt.request_ref,
        )
        await self._load_historical_delegated_evidence(
            product_id=receipt.product_id,
            stage="activation",
            request_ref=receipt.request_ref,
        )
        proposal = await self.load_proposal(receipt.proposal_id, product_id=receipt.product_id)
        approval = await self.load_delegated_approval(receipt.approval_receipt_ref, product_id=receipt.product_id)
        review = await self.load_review(receipt.cognition_review_receipt_id, product_id=receipt.product_id)
        revision = await self.load_revision(receipt.result_revision_id)
        state = await self.load_proposal_state(receipt.proposal_id, product_id=receipt.product_id)
        if (
            proposal is None
            or proposal.proposal_hash != receipt.proposal_hash
            or approval is None
            or str(approval.receipt_digest) != receipt.approval_receipt_digest
            or review is None
            or str(review.receipt_id) != receipt.cognition_review_receipt_id
            or revision is None
            or f"sha256:{revision.material_hash}" != receipt.result_material_digest
            or state is not ProposalState.APPROVED
        ):
            raise CognitionReplayConflict("delegated activation history cognition material diverged")
        async with self.pool.connection() as db:
            identity_row = parse_one(
                await db.query(
                    "SELECT payload_json, payload FROM ONLY type::record('cognition', $record_key) LIMIT 1",
                    {"record_key": _record_key(str(revision.identity.cognition_id))},
                )
            )
            event_row = parse_one(
                await db.query(
                    "SELECT active_revision, generation, authority_receipt_id, payload FROM ONLY "
                    "type::record('cognition_activation_event', $record_key) LIMIT 1",
                    {"record_key": _record_key(receipt.activation_event_id)},
                )
            )
        identity = _validated_payload(identity_row, CognitionIdentityV1) if identity_row else None
        if (
            identity != revision.identity
            or not event_row
            or str(event_row.get("active_revision")) != receipt.result_revision_id
            or int(event_row.get("generation", -1)) != receipt.result_head_generation
            or str(event_row.get("authority_receipt_id")) != receipt.cognition_review_receipt_id
            or not isinstance(event_row.get("payload"), dict)
            or str(event_row["payload"].get("head_id")) != receipt.result_head_id
        ):
            raise CognitionReplayConflict("delegated activation history event material diverged")

    async def _classify_delegated_approval_winner(
        self,
        *,
        receipt: DelegatedCognitionApprovalReceiptV1Alpha1,
        evidence: AppendOnlyTransactionRequestV1,
        original: Exception | None,
    ) -> DelegatedCognitionApprovalReceiptV1Alpha1 | None:
        stored = await self.load_delegated_approval(str(receipt.receipt_id), product_id=receipt.product_id)
        stored_evidence = await self._load_exact_delegated_evidence(evidence)
        if stored is None and stored_evidence is None:
            if original is not None:
                raise original
            return None
        if not self._same_delegated_replay(stored, receipt) or stored_evidence is None:
            raise CognitionReplayConflict("delegated approval composite is partial or divergent")
        proposal = await self.load_proposal(receipt.proposal_id, product_id=receipt.product_id)
        state = await self.load_proposal_state(receipt.proposal_id, product_id=receipt.product_id)
        if proposal is None or proposal.proposal_hash != receipt.proposal_hash or state is not ProposalState.PENDING:
            raise CognitionReplayConflict("delegated approval composite proposal position diverged")
        return stored

    async def _classify_delegated_activation_winner(
        self,
        *,
        proposal: CognitionProposalV1,
        review_receipt: CognitionReviewReceiptV1,
        revision: CognitionRevisionV1,
        head: CognitionHeadV1,
        activation_receipt: DelegatedCognitionActivationReceiptV1Alpha1,
        evidence: AppendOnlyTransactionRequestV1,
        original: Exception | None,
    ) -> DelegatedCognitionActivationReceiptV1Alpha1 | None:
        product_id = activation_receipt.product_id
        stored = await self.load_delegated_activation(str(activation_receipt.receipt_id), product_id=product_id)
        stored_evidence = await self._load_exact_delegated_evidence(evidence)
        if stored is None and stored_evidence is None:
            if original is not None:
                raise original
            return None
        if not self._same_delegated_replay(stored, activation_receipt) or stored_evidence is None:
            raise CognitionReplayConflict("delegated activation composite is partial or divergent")
        stored_proposal = await self.load_proposal(str(proposal.proposal_id), product_id=product_id)
        stored_review = await self.load_review(str(review_receipt.receipt_id), product_id=product_id)
        stored_revision = await self.load_revision(str(revision.revision_id))
        state = await self.load_proposal_state(str(proposal.proposal_id), product_id=product_id)
        async with self.pool.connection() as db:
            identity_row = parse_one(
                await db.query(
                    "SELECT payload_json, payload FROM ONLY type::record('cognition', $record_key) LIMIT 1",
                    {"record_key": _record_key(str(revision.identity.cognition_id))},
                )
            )
            event_row = parse_one(
                await db.query(
                    "SELECT active_revision, generation, authority_receipt_id, payload FROM ONLY "
                    "type::record('cognition_activation_event', $record_key) LIMIT 1",
                    {"record_key": _record_key(activation_receipt.activation_event_id)},
                )
            )
        stored_identity = _validated_payload(identity_row, CognitionIdentityV1) if identity_row else None
        event_exact = bool(
            event_row
            and str(event_row.get("active_revision")) == str(revision.revision_id)
            and int(event_row.get("generation", -1)) == head.generation
            and str(event_row.get("authority_receipt_id")) == str(review_receipt.receipt_id)
            and isinstance(event_row.get("payload"), dict)
            and str(event_row["payload"].get("head_id")) == str(head.head_id)
        )
        if (
            stored_proposal != proposal
            or stored_review != review_receipt
            or stored_revision != revision
            or stored_identity != revision.identity
            or state is not ProposalState.APPROVED
            or not event_exact
        ):
            raise CognitionReplayConflict("delegated activation composite cognition material diverged")
        return stored

    async def persist_delegated_approval(
        self,
        *,
        receipt: DelegatedCognitionApprovalReceiptV1Alpha1,
        evidence: AppendOnlyTransactionRequestV1,
        preconditions: tuple[Any, ...],
        grant_expiries: tuple[datetime | None, ...],
    ) -> DelegatedCognitionApprovalReceiptV1Alpha1:
        """Append stage-one approval evidence; no cognition state may move."""

        product_id = receipt.product_id
        _validate_delegated_evidence(
            evidence,
            stage="approval",
            product_id=product_id,
            request_ref=receipt.request_ref,
            preconditions=preconditions,
        )
        existing = await self._load_delegated_by_replay(
            _DELEGATED_APPROVAL_REPLAY_QUERY,
            DelegatedCognitionApprovalReceiptV1Alpha1,
            product_id=product_id,
            replay_key=receipt.replay_key,
        )
        if existing is not None:
            if not self._same_delegated_replay(existing, receipt):
                raise CognitionReplayConflict(
                    f"delegated approval replay {receipt.replay_key} contains different material"
                )
            winner = await self._classify_delegated_approval_winner(
                receipt=receipt,
                evidence=evidence,
                original=None,
            )
            assert winner is not None
            return winner
        winner = await self._classify_delegated_approval_winner(
            receipt=receipt,
            evidence=evidence,
            original=None,
        )
        if winner is not None:
            return winner

        params: dict[str, Any] = {
            "product": parse_record_id(product_id),
            "receipt_key": _record_key(str(receipt.receipt_id)),
            "proposal_key": _record_key(receipt.proposal_id),
            "proposal_hash": receipt.proposal_hash,
            "receipt_content": {
                "contract_version": receipt.contract,
                "product": parse_record_id(product_id),
                "stable_id": receipt.receipt_id,
                "request_ref": receipt.request_ref,
                "request_digest": receipt.request_digest,
                "replay_key": receipt.replay_key,
                "proposal_id": receipt.proposal_id,
                "proposal_hash": receipt.proposal_hash,
                "service_principal_ref": receipt.service_principal.principal_ref,
                "payload": receipt.model_dump(mode="python"),
                "payload_json": canonical_json(receipt),
                "resolved_at": receipt.resolved_at,
            },
        }
        statements = ["BEGIN TRANSACTION"]
        statements.extend(_governed_state_precondition_statements(preconditions, params=params))
        statements.extend(_grant_expiry_statements(grant_expiries, params=params))
        statements.extend(
            [
                "LET $delegated_proposal = SELECT state, proposal_hash FROM ONLY "
                "type::record('cognition_proposal', $proposal_key) WHERE product = $product",
                "IF $delegated_proposal = NONE OR $delegated_proposal.proposal_hash != $proposal_hash "
                "{ THROW 'cognition_proposal_material_conflict'; }",
                "IF $delegated_proposal.state != 'pending' { THROW 'cognition_proposal_state_conflict'; }",
            ]
        )
        evidence_receipt = evidence.receipt()
        statements.extend(_delegated_evidence_statements(evidence, evidence_receipt, params=params))
        if self._simulate_delegated_failure_after_evidence:
            statements.append("THROW 'delegated_simulated_failure_after_evidence'")
        statements.append(
            "CREATE ONLY type::record('cognition_delegated_approval_receipt', $receipt_key) CONTENT $receipt_content"
        )
        if self._simulate_delegated_failure_after_cognition:
            statements.append("THROW 'delegated_simulated_failure_after_cognition'")
        statements.append("COMMIT TRANSACTION")
        async with self.pool.connection() as db:
            try:
                await _query_or_raise(db, ";\n".join(statements) + ";", params)
            except Exception as exc:
                _raise_delegated_failure(exc)
                original = (
                    exc
                    if isinstance(exc, CognitionPersistenceError)
                    else CognitionPersistenceError("delegated approval persistence failed")
                )
                winner = await self._classify_delegated_approval_winner(
                    receipt=receipt,
                    evidence=evidence,
                    original=original,
                )
                assert winner is not None
                return winner
        return receipt

    async def persist_delegated_activation(
        self,
        *,
        proposal: CognitionProposalV1,
        review_receipt: CognitionReviewReceiptV1,
        revision: CognitionRevisionV1,
        head: CognitionHeadV1,
        activation_receipt: DelegatedCognitionActivationReceiptV1Alpha1,
        evidence: AppendOnlyTransactionRequestV1,
        preconditions: tuple[Any, ...],
        grant_expiries: tuple[datetime | None, ...],
    ) -> DelegatedCognitionActivationReceiptV1Alpha1:
        """Commit the delegated activation and its authority preconditions atomically.

        Every governed-state head (both grants, the SERVICE principal lifecycle,
        and the capability state), the exact proposal material and state, and the
        cognition head generation are asserted inside the single transaction that
        writes the revision, head, activation event, review receipt, and this
        delegated receipt.  A revocation, rotation, expiry, or tamper between
        approval and activation therefore loses the race with no partial effect.
        """

        product_id = _scope_product(proposal.scope)
        if activation_receipt.product_id != product_id:
            raise CognitionScopeError("delegated activation crossed its exact product scope")
        if (
            review_receipt.proposal_id != proposal.proposal_id
            or review_receipt.proposal_hash != proposal.proposal_hash
            or review_receipt.disposition is not ReviewDisposition.APPROVE
            or review_receipt.actor.actor_class is not ActorClass.SERVICE
            or revision.identity != proposal.target_identity
            or revision.body != proposal.draft_body
            or revision.approval_receipt_id != review_receipt.receipt_id
            or review_receipt.result_revision_id != revision.revision_id
            or head.active_revision_id != revision.revision_id
            or head.generation != review_receipt.expected_head_generation + 1
            or head.authority_receipt_id != review_receipt.receipt_id
            or review_receipt.result_head_id != head.head_id
        ):
            raise CognitionPersistenceError("delegated activation must bind the exact reviewed proposal material")
        if (
            activation_receipt.proposal_id != proposal.proposal_id
            or activation_receipt.proposal_hash != proposal.proposal_hash
            or activation_receipt.result_revision_id != revision.revision_id
            or activation_receipt.result_material_digest != f"sha256:{revision.material_hash}"
            or activation_receipt.cognition_review_receipt_id != review_receipt.receipt_id
            or activation_receipt.result_head_id != head.head_id
            or activation_receipt.result_head_generation != head.generation
            or activation_receipt.base_revision_id != proposal.base_revision_id
        ):
            raise CognitionPersistenceError("delegated receipt must bind the exact activated cognition material")

        _validate_delegated_evidence(
            evidence,
            stage="activation",
            product_id=product_id,
            request_ref=activation_receipt.request_ref,
            preconditions=preconditions,
        )

        existing = await self._load_delegated_by_replay(
            _DELEGATED_ACTIVATION_REPLAY_QUERY,
            DelegatedCognitionActivationReceiptV1Alpha1,
            product_id=product_id,
            replay_key=activation_receipt.replay_key,
        )
        if existing is not None:
            if not self._same_delegated_replay(existing, activation_receipt):
                raise CognitionReplayConflict(
                    f"delegated activation replay {activation_receipt.replay_key} contains different material"
                )
            winner = await self._classify_delegated_activation_winner(
                proposal=proposal,
                review_receipt=review_receipt,
                revision=revision,
                head=head,
                activation_receipt=activation_receipt,
                evidence=evidence,
                original=None,
            )
            assert winner is not None
            return winner
        winner = await self._classify_delegated_activation_winner(
            proposal=proposal,
            review_receipt=review_receipt,
            revision=revision,
            head=head,
            activation_receipt=activation_receipt,
            evidence=evidence,
            original=None,
        )
        if winner is not None:
            return winner

        identity = revision.identity
        identity_key = _record_key(str(identity.cognition_id))
        revision_key = _record_key(str(revision.revision_id))
        head_key = _record_key(str(head.head_id))
        proposal_key = _record_key(str(proposal.proposal_id))
        review_key = _record_key(str(review_receipt.receipt_id))
        activation_event_id = activation_receipt.activation_event_id
        params: dict[str, Any] = {
            "product": parse_record_id(product_id),
            "proposal_key": proposal_key,
            "proposal_ref": str(proposal.proposal_id),
            "proposal_hash": proposal.proposal_hash,
            "proposal_state": ProposalState.APPROVED.value,
            "approval_key": _record_key(activation_receipt.approval_receipt_ref),
            "approval_ref": activation_receipt.approval_receipt_ref,
            "approval_digest": activation_receipt.approval_receipt_digest,
            "request_ref": activation_receipt.request_ref,
            "request_digest": activation_receipt.request_digest,
            "replay_key": activation_receipt.replay_key,
            "identity_key": identity_key,
            "identity_content": _identity_content(identity),
            "revision_key": revision_key,
            "revision_content": _revision_content(revision),
            "head_key": head_key,
            "head_content": _head_content(head),
            "expected_current_generation": (
                None if review_receipt.expected_head_generation == 0 else review_receipt.expected_head_generation
            ),
            "activation_key": _record_key(activation_event_id),
            "activation_content": {
                "contract_version": head.contract_version,
                "cognition": parse_record_id(str(identity.cognition_id)),
                "scope": head.scope.model_dump(mode="python"),
                "prior_revision": (
                    parse_record_id(proposal.base_revision_id) if proposal.base_revision_id is not None else None
                ),
                "active_revision": parse_record_id(str(revision.revision_id)),
                "generation": head.generation,
                "disposition": "activate",
                "authority_receipt_id": review_receipt.receipt_id,
                "payload": {
                    "head_id": head.head_id,
                    "review_receipt_id": review_receipt.receipt_id,
                    "delegated_activation_receipt_id": activation_receipt.receipt_id,
                },
            },
            "review_key": review_key,
            "review_content": {
                "contract_version": review_receipt.contract_version,
                "product": parse_record_id(product_id),
                "stable_id": review_receipt.receipt_id,
                "proposal_id": review_receipt.proposal_id,
                "proposal_hash": review_receipt.proposal_hash,
                "actor_id": review_receipt.actor.actor_id,
                "actor_class": review_receipt.actor.actor_class.value,
                "disposition": review_receipt.disposition.value,
                "result_revision_id": review_receipt.result_revision_id,
                "result_head_id": review_receipt.result_head_id,
                "payload": review_receipt.model_dump(mode="python"),
                "payload_json": canonical_json(review_receipt),
                "reviewed_at": review_receipt.reviewed_at,
            },
            "delegated_key": _record_key(str(activation_receipt.receipt_id)),
            "delegated_content": {
                "contract_version": activation_receipt.contract,
                "product": parse_record_id(product_id),
                "stable_id": activation_receipt.receipt_id,
                "request_ref": activation_receipt.request_ref,
                "request_digest": activation_receipt.request_digest,
                "approval_receipt_ref": activation_receipt.approval_receipt_ref,
                "replay_key": activation_receipt.replay_key,
                "proposal_id": activation_receipt.proposal_id,
                "proposal_hash": activation_receipt.proposal_hash,
                "service_principal_ref": activation_receipt.service_principal.principal_ref,
                "result_revision_id": activation_receipt.result_revision_id,
                "result_head_id": activation_receipt.result_head_id,
                "result_head_generation": activation_receipt.result_head_generation,
                "payload": activation_receipt.model_dump(mode="python"),
                "payload_json": canonical_json(activation_receipt),
                "activated_at": activation_receipt.activated_at,
            },
        }

        async with self.pool.connection() as db:
            existing_identity = parse_one(
                await db.query(
                    "SELECT payload_json, payload FROM ONLY type::record('cognition', $record_key) LIMIT 1",
                    {"record_key": identity_key},
                )
            )
            create_identity = True
            if existing_identity:
                stored_identity = _validated_payload(existing_identity, CognitionIdentityV1)
                if stored_identity != identity:
                    raise CognitionReplayConflict("stable cognition identity contains different material")
                create_identity = False
            existing_revision = parse_one(
                await db.query(
                    "SELECT material_hash FROM ONLY type::record('cognition_revision', $record_key) LIMIT 1",
                    {"record_key": revision_key},
                )
            )
            if existing_revision:
                raise CognitionReplayConflict("delegated revision exists without its delegated activation receipt")

            statements = ["BEGIN TRANSACTION"]
            statements.extend(_governed_state_precondition_statements(preconditions, params=params))
            statements.extend(_grant_expiry_statements(grant_expiries, params=params))
            statements.extend(
                [
                    "LET $delegated_proposal = SELECT state, proposal_hash FROM ONLY "
                    "type::record('cognition_proposal', $proposal_key) WHERE product = $product",
                    "IF $delegated_proposal = NONE OR $delegated_proposal.proposal_hash != $proposal_hash "
                    "{ THROW 'cognition_proposal_material_conflict'; }",
                    "IF $delegated_proposal.state != 'pending' { THROW 'cognition_proposal_state_conflict'; }",
                    "LET $delegated_approval = SELECT stable_id, request_ref, request_digest, replay_key, "
                    "proposal_id, proposal_hash, payload FROM ONLY "
                    "type::record('cognition_delegated_approval_receipt', $approval_key) "
                    "WHERE product = $product",
                    "IF $delegated_approval = NONE OR $delegated_approval.stable_id != $approval_ref "
                    "OR $delegated_approval.request_ref != $request_ref "
                    "OR $delegated_approval.request_digest != $request_digest "
                    "OR $delegated_approval.replay_key != $replay_key "
                    "OR $delegated_approval.proposal_id != $proposal_ref "
                    "OR $delegated_approval.proposal_hash != $proposal_hash "
                    "OR $delegated_approval.payload.receipt_digest != $approval_digest "
                    "{ THROW 'cognition_delegated_approval_conflict'; }",
                    "LET $transaction_generation = SELECT VALUE generation FROM ONLY "
                    "type::record('cognition_head', $head_key)",
                    "IF $transaction_generation != $expected_current_generation "
                    "{ THROW 'cognition_head_generation_conflict'; }",
                ]
            )
            evidence_receipt = evidence.receipt()
            statements.extend(_delegated_evidence_statements(evidence, evidence_receipt, params=params))
            if self._simulate_delegated_failure_after_evidence:
                statements.append("THROW 'delegated_simulated_failure_after_evidence'")
            if create_identity:
                statements.append("CREATE ONLY type::record('cognition', $identity_key) CONTENT $identity_content")
            statements.extend(
                [
                    "CREATE ONLY type::record('cognition_revision', $revision_key) CONTENT $revision_content",
                    "IF $transaction_generation = NONE "
                    "{ CREATE ONLY type::record('cognition_head', $head_key) CONTENT $head_content; } "
                    "ELSE { UPDATE ONLY type::record('cognition_head', $head_key) CONTENT $head_content; }",
                    "CREATE ONLY type::record('cognition_activation_event', $activation_key) "
                    "CONTENT $activation_content",
                    "CREATE ONLY type::record('cognition_review_receipt', $review_key) CONTENT $review_content",
                    "CREATE ONLY type::record('cognition_delegated_activation_receipt', $delegated_key) "
                    "CONTENT $delegated_content",
                    "UPDATE ONLY type::record('cognition_proposal', $proposal_key) SET state = $proposal_state",
                ]
            )
            if self._simulate_delegated_failure_after_cognition:
                statements.append("THROW 'delegated_simulated_failure_after_cognition'")
            statements.append("COMMIT TRANSACTION")
            try:
                await _query_or_raise(db, ";\n".join(statements) + ";", params)
            except Exception as exc:
                _raise_delegated_failure(exc)
                original = (
                    exc
                    if isinstance(exc, CognitionPersistenceError)
                    else CognitionPersistenceError("delegated activation persistence failed")
                )
                winner = await self._classify_delegated_activation_winner(
                    proposal=proposal,
                    review_receipt=review_receipt,
                    revision=revision,
                    head=head,
                    activation_receipt=activation_receipt,
                    evidence=evidence,
                    original=original,
                )
                assert winner is not None
                return winner
        return activation_receipt


def _governed_state_precondition_statements(
    preconditions: tuple[Any, ...],
    *,
    params: dict[str, Any],
) -> list[str]:
    """Return in-transaction assertions that every named head is still current.

    This mirrors the proven ``SurrealImmutableRecordStore.append`` precondition
    shape so grant, principal-lifecycle, and capability heads participate in the
    same commit boundary as the cognition revision, head, and activation event.
    """

    statements: list[str] = []
    for index, precondition in enumerate(preconditions):
        params[f"gs_key_{index}"] = _record_key(
            stable_id(
                "governed_state_head",
                {
                    "state_kind": precondition.state_kind,
                    "product_id": precondition.product_id,
                    "state_id": precondition.state_id,
                },
            )
        )
        params[f"gs_product_{index}"] = parse_record_id(precondition.product_id)
        params[f"gs_kind_{index}"] = precondition.state_kind
        params[f"gs_state_{index}"] = precondition.state_id
        params[f"gs_sequence_{index}"] = precondition.sequence
        params[f"gs_revision_{index}"] = precondition.revision_id
        params[f"gs_receipt_{index}"] = precondition.commit_receipt_id
        statements.extend(
            (
                f"LET $governed_head_{index} = SELECT sequence, revision_id, commit_receipt_id "
                f"FROM ONLY type::record('governed_state_head', $gs_key_{index}) "
                f"WHERE product = $gs_product_{index} "
                f"AND state_kind = $gs_kind_{index} AND state_id = $gs_state_{index}",
                f"IF $governed_head_{index} = NONE "
                f"OR $governed_head_{index}.sequence != $gs_sequence_{index} "
                f"OR $governed_head_{index}.revision_id != $gs_revision_{index} "
                f"OR $governed_head_{index}.commit_receipt_id != $gs_receipt_{index} "
                f"{{ THROW '{DELEGATED_PRECONDITION_THROW}'; }}",
            )
        )
    return statements


def _grant_expiry_statements(
    expiries: tuple[datetime | None, ...],
    *,
    params: dict[str, Any],
) -> list[str]:
    """Assert wall-clock grant validity with server time inside the commit.

    Expiry alone never moves a governed-state head, so head preconditions cannot
    observe it.  The head preconditions above pin the exact stored grant, which
    is what makes comparing its ``expires_at`` against SurrealDB ``time::now()``
    an honest durable check rather than a client-side assertion.
    """

    statements: list[str] = []
    for index, expires_at in enumerate(expiries):
        if expires_at is None:
            continue
        params[f"grant_expiry_{index}"] = expires_at
        statements.append(f"IF $grant_expiry_{index} <= time::now() {{ THROW '{DELEGATED_GRANT_EXPIRED_THROW}'; }}")
    return statements


def _raise_delegated_failure(exc: Exception) -> None:
    detail = str(exc)
    if DELEGATED_PRECONDITION_THROW in detail or DELEGATED_GRANT_EXPIRED_THROW in detail:
        raise CognitionDelegatedPreconditionError(
            DELEGATED_GRANT_EXPIRED_THROW if DELEGATED_GRANT_EXPIRED_THROW in detail else DELEGATED_PRECONDITION_THROW
        ) from exc


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
