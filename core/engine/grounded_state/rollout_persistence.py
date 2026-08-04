"""Append-only product-scoped persistence for TP6 rollout and reasoning records."""

from __future__ import annotations

from collections.abc import Iterable
from typing import Any, TypeVar

from pydantic import BaseModel

from core.engine.core.db import parse_one, parse_record_id, parse_rows
from core.engine.grounded_state.contracts import canonical_hash
from core.engine.grounded_state.rollout_contracts import (
    ConsequenceRolloutRevisionV1,
    EvidenceQueryV1,
    ModelBranchProposalReceiptV1,
    ReasoningContextUseReceiptV1,
    ReasoningEvidencePackV1,
    RolloutChallengeReceiptV1,
    RolloutOutcomeObservationV1,
    RolloutProposalV1,
    RolloutReconciliationReceiptV1,
    TransitionExecutionReceiptV1,
)


class RolloutReplayConflict(RuntimeError):
    """A stable TP6 identity was replayed with different immutable material."""


class RolloutProductScopeError(RuntimeError):
    """TP6 material was unavailable in the requested product scope."""


TP6Model = (
    EvidenceQueryV1
    | ReasoningEvidencePackV1
    | RolloutProposalV1
    | TransitionExecutionReceiptV1
    | ModelBranchProposalReceiptV1
    | RolloutChallengeReceiptV1
    | ConsequenceRolloutRevisionV1
    | ReasoningContextUseReceiptV1
    | RolloutOutcomeObservationV1
    | RolloutReconciliationReceiptV1
)
ModelT = TypeVar("ModelT", bound=BaseModel)

_MODEL_TABLE: dict[type[BaseModel], str] = {
    EvidenceQueryV1: "grounded_evidence_query",
    ReasoningEvidencePackV1: "grounded_reasoning_evidence_pack",
    RolloutProposalV1: "grounded_rollout_proposal",
    TransitionExecutionReceiptV1: "grounded_rollout_execution",
    ModelBranchProposalReceiptV1: "grounded_model_branch_proposal",
    RolloutChallengeReceiptV1: "grounded_rollout_challenge",
    ConsequenceRolloutRevisionV1: "grounded_consequence_rollout",
    ReasoningContextUseReceiptV1: "grounded_rollout_reasoning_use",
    RolloutOutcomeObservationV1: "grounded_rollout_outcome",
    RolloutReconciliationReceiptV1: "grounded_rollout_reconciliation",
}


def _stable_id(record: TP6Model) -> str:
    if isinstance(record, EvidenceQueryV1):
        return str(record.query_id)
    if isinstance(record, ReasoningEvidencePackV1):
        return str(record.context_pack_id)
    if isinstance(record, RolloutProposalV1):
        return str(record.proposal_id)
    if isinstance(record, TransitionExecutionReceiptV1):
        return str(record.receipt_id)
    if isinstance(record, ModelBranchProposalReceiptV1):
        return str(record.receipt_id)
    if isinstance(record, RolloutChallengeReceiptV1):
        return str(record.receipt_id)
    if isinstance(record, ConsequenceRolloutRevisionV1):
        return str(record.rollout_revision_id)
    if isinstance(record, ReasoningContextUseReceiptV1):
        return str(record.receipt_id)
    if isinstance(record, RolloutOutcomeObservationV1):
        return str(record.observation_id)
    if isinstance(record, RolloutReconciliationReceiptV1):
        return str(record.receipt_id)
    raise TypeError(f"unsupported TP6 stable identity: {type(record).__name__}")


def _material_hash(record: TP6Model) -> str:
    for name in (
        "query_hash",
        "context_pack_hash",
        "proposal_hash",
        "rollout_revision_hash",
        "observation_hash",
        "receipt_hash",
    ):
        value = getattr(record, name, None)
        if value:
            return str(value)
    return canonical_hash(record)


def _record_key(stable_id: str) -> str:
    _, separator, key = stable_id.partition(":")
    if not separator or not key:
        raise ValueError("TP6 records require a bounded table-prefixed stable identity")
    return key


def _specific_fields(record: TP6Model) -> dict[str, Any]:
    if isinstance(record, EvidenceQueryV1):
        return {
            "task_id": record.task_id,
            "invocation_id": record.invocation_id,
            "as_of": record.as_of,
        }
    if isinstance(record, ReasoningEvidencePackV1):
        return {
            "task_id": record.task_id,
            "invocation_id": record.invocation_id,
            "query_id": record.query_id,
            "evidence_pack_id": record.evidence_pack.pack_id,
            "evidence_refs": list(record.selected_record_refs),
        }
    if isinstance(record, RolloutProposalV1):
        return {
            "task_id": record.task_id,
            "invocation_id": record.invocation_id,
            "rollout_id": record.request.rollout_id(),
            "projection_id": record.request.starting_state_id,
            "transition_revision_ids": list(record.transition_revision_ids),
        }
    if isinstance(record, TransitionExecutionReceiptV1):
        return {
            "proposal_id": record.proposal_id,
            "branch_id": record.branch_id,
            "branch_kind": record.branch_kind.value,
            "projection_id": record.starting_projection_id,
            "transition_revision_ids": list(record.transition_revision_hashes),
        }
    if isinstance(record, ModelBranchProposalReceiptV1):
        return {
            "proposal_id": record.rollout_proposal_id,
            "branch_ids": list(record.branch_ids),
        }
    if isinstance(record, RolloutChallengeReceiptV1):
        return {
            "proposal_id": record.proposal_id,
            "completed": record.completed,
            "transition_revision_ids": list(record.checked_transition_refs),
        }
    if isinstance(record, ConsequenceRolloutRevisionV1):
        return {
            "task_id": record.task_id,
            "invocation_id": record.invocation_id,
            "rollout_id": record.rollout_id,
            "revision": record.revision,
            "projection_id": record.starting_projection_id,
            "disposition": record.disposition.value,
            "transition_revision_ids": list(record.transition_revision_ids),
        }
    if isinstance(record, ReasoningContextUseReceiptV1):
        return {
            "task_id": record.task_id,
            "invocation_id": record.invocation_id,
            "rollout_revision_id": record.rollout_revision_id,
            "comparison_state": record.comparison_state,
        }
    if isinstance(record, RolloutOutcomeObservationV1):
        return {
            "rollout_revision_id": record.rollout_revision_id,
            "predicted_outcome_id": record.predicted_outcome_id,
            "branch_id": record.branch_id,
            "observed_at": record.observed_at,
            "evidence_pack_id": record.evidence_pack_id,
        }
    if isinstance(record, RolloutReconciliationReceiptV1):
        return {
            "rollout_revision_id": record.rollout_revision_id,
            "predicted_outcome_id": record.predicted_outcome_id,
            "observation_id": record.observation_id,
            "branch_id": record.branch_id,
            "disposition": record.disposition.value,
            "reconciled_at": record.reconciled_at,
        }
    raise TypeError(f"unsupported TP6 persistence model: {type(record).__name__}")


async def _query_or_raise(db, query: str, params: dict[str, Any]) -> Any:
    # The SurrealDB SDK's high-level ``query`` helper can flatten a failed
    # multi-statement transaction to an empty list.  That made an aborted TP6
    # batch look successful until an immediate replay could not find its final
    # revision.  Preserve the per-statement statuses and fail at the write
    # boundary instead.
    raw = await db.query_raw(query, params)
    errors: list[object] = []
    if isinstance(raw, dict):
        if raw.get("error") is not None:
            errors.append(raw["error"])
        errors.extend(
            item.get("result")
            for item in (raw.get("result", ()) or ())
            if isinstance(item, dict) and item.get("status") == "ERR"
        )
    if errors:
        messages = [item.get("message", item) if isinstance(item, dict) else item for item in errors]
        detail = " | ".join(dict.fromkeys(str(item) for item in messages))
        raise RolloutReplayConflict(f"TP6 persistence failed closed: {detail[:1_000]}")
    return raw


class RolloutStore:
    """Durable append-only store for frozen TP6 contracts."""

    def __init__(self, pool) -> None:
        self.pool = pool

    async def persist(self, record: TP6Model, *, db=None) -> TP6Model:
        table = _MODEL_TABLE[type(record)]
        stable_id = _stable_id(record)
        material_hash = _material_hash(record)

        async def write(connection):
            existing = parse_one(
                await connection.query(
                    f"SELECT material_hash, payload FROM ONLY type::record('{table}', $record_key) "
                    "WHERE product = $product LIMIT 1",
                    {
                        "record_key": _record_key(stable_id),
                        "product": parse_record_id(record.product_id),
                    },
                )
            )
            if existing:
                payload = existing.get("payload")
                stored = type(record).model_validate(payload) if isinstance(payload, dict) else None
                if (
                    str(existing.get("material_hash")) == material_hash
                    and stored is not None
                    and canonical_hash(stored) == canonical_hash(record)
                ):
                    return record
                raise RolloutReplayConflict(f"stable TP6 identity {stable_id} contains different material")
            content = {
                "contract_version": record.contract_version,
                "product": parse_record_id(record.product_id),
                "stable_id": stable_id,
                "material_hash": material_hash,
                "payload": record.model_dump(mode="python"),
                **_specific_fields(record),
            }
            await _query_or_raise(
                connection,
                f"CREATE ONLY type::record('{table}', $record_key) CONTENT $content",
                {"record_key": _record_key(stable_id), "content": content},
            )
            return record

        if db is not None:
            return await write(db)
        async with self.pool.connection() as connection:
            return await write(connection)

    async def persist_all(self, records: Iterable[TP6Model]) -> tuple[TP6Model, ...]:
        normalized = tuple(sorted(records, key=_stable_id))
        if not normalized:
            return ()
        if len({record.product_id for record in normalized}) != 1:
            raise RolloutProductScopeError("one TP6 persistence batch cannot cross product scope")
        async with self.pool.connection() as db:
            missing: list[TP6Model] = []
            for record in normalized:
                table = _MODEL_TABLE[type(record)]
                stable_id = _stable_id(record)
                existing = parse_one(
                    await db.query(
                        f"SELECT material_hash, payload FROM ONLY type::record('{table}', $record_key) "
                        "WHERE product = $product LIMIT 1",
                        {
                            "record_key": _record_key(stable_id),
                            "product": parse_record_id(record.product_id),
                        },
                    )
                )
                if not existing:
                    missing.append(record)
                    continue
                payload = existing.get("payload")
                stored = type(record).model_validate(payload) if isinstance(payload, dict) else None
                if (
                    str(existing.get("material_hash")) != _material_hash(record)
                    or stored is None
                    or canonical_hash(stored) != canonical_hash(record)
                ):
                    raise RolloutReplayConflict(f"stable TP6 identity {stable_id} contains different material")
            if missing:
                statements = ["BEGIN TRANSACTION"]
                params: dict[str, Any] = {}
                for index, record in enumerate(missing):
                    stable_id = _stable_id(record)
                    record_key = f"record_key_{index}"
                    content_key = f"content_{index}"
                    params[record_key] = _record_key(stable_id)
                    params[content_key] = {
                        "contract_version": record.contract_version,
                        "product": parse_record_id(record.product_id),
                        "stable_id": stable_id,
                        "material_hash": _material_hash(record),
                        "payload": record.model_dump(mode="python"),
                        **_specific_fields(record),
                    }
                    statements.append(
                        f"CREATE ONLY type::record('{_MODEL_TABLE[type(record)]}', ${record_key}) "
                        f"CONTENT ${content_key}"
                    )
                statements.append("COMMIT TRANSACTION")
                await _query_or_raise(db, ";\n".join(statements) + ";", params)
        return normalized

    async def load(self, model: type[ModelT], stable_id: str, *, product_id: str) -> ModelT | None:
        table = _MODEL_TABLE[model]
        async with self.pool.connection() as db:
            row = parse_one(
                await db.query(
                    f"SELECT payload FROM ONLY type::record('{table}', $record_key) WHERE product = $product LIMIT 1",
                    {
                        "record_key": _record_key(stable_id),
                        "product": parse_record_id(product_id),
                    },
                )
            )
        if not row or not isinstance(row.get("payload"), dict):
            return None
        return model.model_validate(row["payload"])

    async def require(self, model: type[ModelT], stable_id: str, *, product_id: str) -> ModelT:
        record = await self.load(model, stable_id, product_id=product_id)
        if record is None:
            raise RolloutProductScopeError(f"TP6 record is unavailable in product scope: {stable_id}")
        return record

    async def list_rollouts(self, *, product_id: str) -> list[ConsequenceRolloutRevisionV1]:
        async with self.pool.connection() as db:
            rows = parse_rows(
                await db.query(
                    "SELECT payload, rollout_id, revision, stable_id FROM grounded_consequence_rollout "
                    "WHERE product = $product ORDER BY rollout_id, revision, stable_id",
                    {"product": parse_record_id(product_id)},
                )
            )
        return [
            ConsequenceRolloutRevisionV1.model_validate(row["payload"])
            for row in rows
            if isinstance(row.get("payload"), dict)
        ]

    async def latest_rollout(
        self,
        *,
        product_id: str,
        rollout_id: str,
    ) -> ConsequenceRolloutRevisionV1 | None:
        """Load the latest immutable revision for one logical rollout series."""
        async with self.pool.connection() as db:
            row = parse_one(
                await db.query(
                    "SELECT payload, revision, stable_id FROM grounded_consequence_rollout "
                    "WHERE product = $product AND rollout_id = $rollout_id "
                    "ORDER BY revision DESC, stable_id DESC LIMIT 1",
                    {
                        "product": parse_record_id(product_id),
                        "rollout_id": rollout_id,
                    },
                )
            )
        if not row or not isinstance(row.get("payload"), dict):
            return None
        return ConsequenceRolloutRevisionV1.model_validate(row["payload"])

    async def list_reconciliations(
        self,
        *,
        product_id: str,
        rollout_revision_id: str,
    ) -> list[RolloutReconciliationReceiptV1]:
        async with self.pool.connection() as db:
            rows = parse_rows(
                await db.query(
                    "SELECT payload, reconciled_at, stable_id FROM grounded_rollout_reconciliation "
                    "WHERE product = $product AND rollout_revision_id = $rollout_revision_id "
                    "ORDER BY reconciled_at, stable_id",
                    {
                        "product": parse_record_id(product_id),
                        "rollout_revision_id": rollout_revision_id,
                    },
                )
            )
        return [
            RolloutReconciliationReceiptV1.model_validate(row["payload"])
            for row in rows
            if isinstance(row.get("payload"), dict)
        ]
