"""Append-only product-scoped persistence for TP5 transition material."""

from __future__ import annotations

from collections.abc import Iterable
from typing import Any, TypeVar

from pydantic import BaseModel

from core.engine.core.db import parse_one, parse_record_id, parse_rows
from core.engine.grounded_state.contracts import canonical_hash
from core.engine.grounded_state.transition_contracts import (
    ObservedTransitionOutcomeV1,
    TransitionBranchInputV1,
    TransitionCalibrationReceiptV1,
    TransitionChallengeReceiptV1,
    TransitionHypothesisProposalV1,
    TransitionHypothesisRevisionV1,
    TransitionReviewV1,
)


class TransitionReplayConflict(RuntimeError):
    """A stable TP5 identity was replayed with different immutable material."""


class TransitionProductScopeError(RuntimeError):
    """TP5 material was unavailable in the requested product scope."""


TP5Model = (
    TransitionHypothesisProposalV1
    | TransitionChallengeReceiptV1
    | TransitionReviewV1
    | TransitionHypothesisRevisionV1
    | TransitionBranchInputV1
    | ObservedTransitionOutcomeV1
    | TransitionCalibrationReceiptV1
)
ModelT = TypeVar("ModelT", bound=BaseModel)

_MODEL_TABLE: dict[type[BaseModel], str] = {
    TransitionHypothesisProposalV1: "grounded_transition_proposal",
    TransitionChallengeReceiptV1: "grounded_transition_challenge",
    TransitionReviewV1: "grounded_transition_review",
    TransitionHypothesisRevisionV1: "grounded_transition_revision",
    TransitionBranchInputV1: "grounded_transition_branch_input",
    ObservedTransitionOutcomeV1: "grounded_transition_outcome",
    TransitionCalibrationReceiptV1: "grounded_transition_calibration",
}


def _stable_id(record: TP5Model) -> str:
    if isinstance(record, TransitionHypothesisProposalV1):
        return str(record.proposal_id)
    if isinstance(record, TransitionChallengeReceiptV1):
        return str(record.receipt_id)
    if isinstance(record, TransitionReviewV1):
        return str(record.review_id)
    if isinstance(record, TransitionHypothesisRevisionV1):
        return str(record.revision_id)
    if isinstance(record, TransitionBranchInputV1):
        return str(record.input_id)
    if isinstance(record, ObservedTransitionOutcomeV1):
        return str(record.outcome_id)
    if isinstance(record, TransitionCalibrationReceiptV1):
        return str(record.receipt_id)
    raise TypeError(f"unsupported TP5 stable identity: {type(record).__name__}")


def _material_hash(record: TP5Model) -> str:
    for name in ("revision_hash", "receipt_hash", "input_hash", "outcome_hash"):
        value = getattr(record, name, None)
        if value:
            return str(value)
    if isinstance(record, TransitionHypothesisProposalV1):
        return record.review_material_hash()
    return canonical_hash(record)


def _record_key(stable_id: str) -> str:
    _, separator, key = stable_id.partition(":")
    if not separator or not key:
        raise ValueError("TP5 records require a bounded table-prefixed stable identity")
    return key


def _specific_fields(record: TP5Model) -> dict[str, Any]:
    if isinstance(record, TransitionHypothesisProposalV1):
        return {
            "hypothesis_id": record.hypothesis_id(),
            "projection_id": record.projection_id,
            "evidence_pack_id": record.evidence_pack_id,
            "evidence_refs": list(record.supporting_evidence_refs + record.contrary_evidence_refs),
        }
    if isinstance(record, TransitionChallengeReceiptV1):
        return {
            "hypothesis_id": record.hypothesis_id,
            "proposal_id": record.proposal_id,
            "completed": record.completed,
            "evidence_refs": list(record.searched_evidence_refs),
        }
    if isinstance(record, TransitionReviewV1):
        return {
            "hypothesis_id": record.hypothesis_id,
            "proposal_id": record.proposal_id,
            "disposition": record.disposition.value,
            "authority": record.authority.value,
        }
    if isinstance(record, TransitionHypothesisRevisionV1):
        dependencies = sorted(
            {
                record.projection_id,
                record.evidence_pack_id,
                record.challenge_receipt_id,
                record.review_id,
                *record.projection_entry_refs,
                *record.supporting_evidence_refs,
                *record.contrary_evidence_refs,
                *record.supporting_assertion_refs,
            }
        )
        return {
            "hypothesis_id": record.hypothesis_id,
            "revision": record.revision,
            "review_state": record.review_state.value,
            "rollout_eligible": record.rollout_eligible,
            "prior_revision_id": record.prior_revision_id,
            "dependency_refs": dependencies,
        }
    if isinstance(record, TransitionBranchInputV1):
        return {
            "hypothesis_id": record.hypothesis_id,
            "transition_revision_id": record.transition_revision_id,
            "projection_id": record.starting_projection_id,
            "applicable": record.applicable,
        }
    if isinstance(record, ObservedTransitionOutcomeV1):
        return {
            "hypothesis_id": record.hypothesis_id,
            "transition_revision_id": record.transition_revision_id,
            "disposition": record.disposition.value,
            "observed_at": record.observed_at,
            "evidence_refs": list(record.evidence_refs),
            "forecast_ref": record.forecast_ref,
            "forecast_resolution_ref": record.forecast_resolution_ref,
        }
    if isinstance(record, TransitionCalibrationReceiptV1):
        return {
            "hypothesis_id": record.hypothesis_id,
            "transition_revision_id": record.transition_revision_id,
            "outcome_refs": list(record.outcome_refs),
            "calibrated_at": record.calibrated_at,
        }
    raise TypeError(f"unsupported TP5 persistence model: {type(record).__name__}")


async def _query_or_raise(db, query: str, params: dict[str, Any]) -> Any:
    result = await db.query(query, params)
    if isinstance(result, str):
        raise TransitionReplayConflict(f"TP5 persistence failed closed: {result[:240]}")
    return result


class TransitionStore:
    """Durable append-only store for frozen TP5 contracts."""

    def __init__(self, pool) -> None:
        self.pool = pool

    async def persist(self, record: TP5Model, *, db=None) -> TP5Model:
        table = _MODEL_TABLE[type(record)]
        stable_id = _stable_id(record)
        product_id = str(record.product_id)
        material_hash = _material_hash(record)

        async def write(connection):
            existing = parse_one(
                await connection.query(
                    f"SELECT material_hash, payload FROM ONLY type::record('{table}', $record_key) "
                    "WHERE product = $product LIMIT 1",
                    {"record_key": _record_key(stable_id), "product": parse_record_id(product_id)},
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
                raise TransitionReplayConflict(f"stable TP5 identity {stable_id} contains different material")
            content = {
                "contract_version": record.contract_version,
                "product": parse_record_id(product_id),
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

    async def persist_all(self, records: Iterable[TP5Model]) -> tuple[TP5Model, ...]:
        normalized = tuple(sorted(records, key=_stable_id))
        if not normalized:
            return ()
        if len({record.product_id for record in normalized}) != 1:
            raise TransitionProductScopeError("one TP5 persistence batch cannot cross product scope")
        async with self.pool.connection() as db:
            missing: list[TP5Model] = []
            for record in normalized:
                table = _MODEL_TABLE[type(record)]
                stable_id = _stable_id(record)
                existing = parse_one(
                    await db.query(
                        f"SELECT material_hash, payload FROM ONLY type::record('{table}', $record_key) "
                        "WHERE product = $product LIMIT 1",
                        {"record_key": _record_key(stable_id), "product": parse_record_id(record.product_id)},
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
                    raise TransitionReplayConflict(f"stable TP5 identity {stable_id} contains different material")
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
                        f"CREATE ONLY type::record('{_MODEL_TABLE[type(record)]}', ${record_key}) CONTENT ${content_key}"
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
                    {"record_key": _record_key(stable_id), "product": parse_record_id(product_id)},
                )
            )
        if not row or not isinstance(row.get("payload"), dict):
            return None
        return model.model_validate(row["payload"])

    async def require(self, model: type[ModelT], stable_id: str, *, product_id: str) -> ModelT:
        record = await self.load(model, stable_id, product_id=product_id)
        if record is None:
            raise TransitionProductScopeError(f"TP5 record is unavailable in product scope: {stable_id}")
        return record

    async def list_revisions(self, *, product_id: str) -> list[TransitionHypothesisRevisionV1]:
        async with self.pool.connection() as db:
            rows = parse_rows(
                await db.query(
                    "SELECT payload, hypothesis_id, revision, stable_id FROM grounded_transition_revision "
                    "WHERE product = $product ORDER BY hypothesis_id, revision, stable_id",
                    {"product": parse_record_id(product_id)},
                )
            )
        return [
            TransitionHypothesisRevisionV1.model_validate(row["payload"])
            for row in rows
            if isinstance(row.get("payload"), dict)
        ]

    async def latest_revisions(self, *, product_id: str) -> list[TransitionHypothesisRevisionV1]:
        latest: dict[str, TransitionHypothesisRevisionV1] = {}
        for revision in await self.list_revisions(product_id=product_id):
            current = latest.get(revision.hypothesis_id)
            if current is None or revision.revision > current.revision:
                latest[revision.hypothesis_id] = revision
        return [latest[key] for key in sorted(latest)]

    async def list_outcomes(
        self,
        *,
        product_id: str,
        transition_revision_id: str,
    ) -> list[ObservedTransitionOutcomeV1]:
        async with self.pool.connection() as db:
            rows = parse_rows(
                await db.query(
                    "SELECT payload, observed_at, stable_id FROM grounded_transition_outcome "
                    "WHERE product = $product AND transition_revision_id = $revision "
                    "ORDER BY observed_at, stable_id",
                    {"product": parse_record_id(product_id), "revision": transition_revision_id},
                )
            )
        return [
            ObservedTransitionOutcomeV1.model_validate(row["payload"])
            for row in rows
            if isinstance(row.get("payload"), dict)
        ]
