"""Append-only product-scoped persistence for TP4 belief-state material."""

from __future__ import annotations

from collections.abc import Iterable
from typing import Any, TypeVar

from pydantic import BaseModel

from core.engine.core.db import parse_one, parse_record_id, parse_rows
from core.engine.grounded_state.belief_contracts import (
    AssertionReviewV1,
    BeliefStateProjectionV1,
    BoundedEvidencePackV1,
    CounterevidenceSearchReceiptV1,
    EpistemicAssertionProposalV1,
    EpistemicAssertionV1,
    ExternalWorldInsightV1,
    IncrementalReprojectionReceiptV1,
    InferenceReceiptV1,
)
from core.engine.grounded_state.contracts import canonical_hash


class BeliefStateReplayConflict(RuntimeError):
    """A stable TP4 identity was replayed with different immutable material."""


class BeliefStateProductScopeError(RuntimeError):
    """TP4 material was unavailable in the requested product scope."""


TP4Model = (
    EpistemicAssertionProposalV1
    | AssertionReviewV1
    | EpistemicAssertionV1
    | CounterevidenceSearchReceiptV1
    | BoundedEvidencePackV1
    | BeliefStateProjectionV1
    | ExternalWorldInsightV1
    | InferenceReceiptV1
    | IncrementalReprojectionReceiptV1
)
ModelT = TypeVar("ModelT", bound=BaseModel)


_MODEL_TABLE: dict[type[BaseModel], str] = {
    EpistemicAssertionProposalV1: "grounded_epistemic_proposal",
    AssertionReviewV1: "grounded_assertion_review_v1",
    EpistemicAssertionV1: "grounded_epistemic_assertion_revision",
    CounterevidenceSearchReceiptV1: "grounded_counterevidence_search",
    BoundedEvidencePackV1: "grounded_evidence_pack",
    BeliefStateProjectionV1: "grounded_belief_projection",
    ExternalWorldInsightV1: "grounded_external_insight",
    InferenceReceiptV1: "grounded_inference_receipt",
    IncrementalReprojectionReceiptV1: "grounded_reprojection_receipt",
}


def _stable_id(record: TP4Model) -> str:
    if isinstance(record, EpistemicAssertionProposalV1):
        return str(record.proposal_id)
    if isinstance(record, AssertionReviewV1):
        return str(record.review_id)
    if isinstance(record, EpistemicAssertionV1):
        return str(record.revision_id)
    if isinstance(record, CounterevidenceSearchReceiptV1):
        return str(record.receipt_id)
    if isinstance(record, BoundedEvidencePackV1):
        return str(record.pack_id)
    if isinstance(record, BeliefStateProjectionV1):
        return str(record.projection_id)
    if isinstance(record, ExternalWorldInsightV1):
        return str(record.insight_id)
    if isinstance(record, (InferenceReceiptV1, IncrementalReprojectionReceiptV1)):
        return str(record.receipt_id)
    raise TypeError(f"unsupported TP4 stable identity: {type(record).__name__}")


def _material_hash(record: TP4Model) -> str:
    for name in ("material_hash", "receipt_hash", "pack_hash", "projection_hash"):
        value = getattr(record, name, None)
        if value:
            return str(value)
    return canonical_hash(record)


def _record_key(stable_id: str) -> str:
    _, separator, key = stable_id.partition(":")
    if not separator or not key:
        raise ValueError("TP4 records require a bounded table-prefixed stable identity")
    return key


def _specific_fields(record: TP4Model) -> dict[str, Any]:
    if isinstance(record, EpistemicAssertionProposalV1):
        return {
            "assertion_id": record.assertion_id(),
            "evidence_refs": list(record.supporting_evidence_refs),
        }
    if isinstance(record, AssertionReviewV1):
        return {
            "assertion_id": record.assertion_id,
            "disposition": record.disposition.value,
            "authority": record.authority.value,
        }
    if isinstance(record, EpistemicAssertionV1):
        dependencies = sorted(
            {
                record.subject.record_id,
                record.object.record_id,
                record.evidence_pack_id,
                *record.supporting_evidence_refs,
                *record.contrary_evidence_refs,
                *record.source_origin_ids,
            }
        )
        return {
            "assertion_id": record.assertion_id,
            "revision": record.revision,
            "disposition": record.disposition.value,
            "dependency_refs": dependencies,
            "prior_revision_ref": record.prior_revision_id,
        }
    if isinstance(record, CounterevidenceSearchReceiptV1):
        return {
            "assertion_material_hash": record.assertion_material_hash,
            "completed": record.completed,
        }
    if isinstance(record, BoundedEvidencePackV1):
        return {
            "as_of": record.as_of,
            "candidate_receipt_id": record.candidate_receipt_id,
            "evidence_refs": [item.endpoint.record_id for item in record.items],
        }
    if isinstance(record, BeliefStateProjectionV1):
        return {
            "as_of": record.as_of,
            "revision": record.revision,
            "evidence_pack_id": record.evidence_pack_id,
            "assertion_refs": list(record.assertion_revision_refs),
        }
    if isinstance(record, ExternalWorldInsightV1):
        return {
            "as_of": record.as_of,
            "evidence_pack_id": record.evidence_pack_id,
            "inference_receipt_id": record.inference_receipt_id,
        }
    if isinstance(record, InferenceReceiptV1):
        return {
            "evidence_pack_id": record.evidence_pack_id,
            "assertion_refs": list(record.supporting_assertion_refs),
        }
    if isinstance(record, IncrementalReprojectionReceiptV1):
        return {
            "prior_projection_id": record.prior_projection_id,
            "resulting_projection_id": record.resulting_projection_id,
            "affected_assertion_refs": list(record.affected_assertion_refs),
        }
    raise TypeError(f"unsupported TP4 persistence model: {type(record).__name__}")


async def _query_or_raise(db, query: str, params: dict[str, Any]) -> Any:
    result = await db.query(query, params)
    if isinstance(result, str):
        raise BeliefStateReplayConflict(f"TP4 persistence failed closed: {result[:240]}")
    return result


class BeliefStateStore:
    """Durable append-only store for frozen TP4 contracts."""

    def __init__(self, pool) -> None:
        self.pool = pool

    async def persist(self, record: TP4Model, *, db=None) -> TP4Model:
        table = _MODEL_TABLE[type(record)]
        stable_id = _stable_id(record)
        product_id = str(getattr(record, "product_id"))
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
                raise BeliefStateReplayConflict(f"stable TP4 identity {stable_id} contains different material")
            content = {
                "contract_version": str(getattr(record, "contract_version")),
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
            raise BeliefStateProductScopeError(f"TP4 record is unavailable in product scope: {stable_id}")
        return record

    async def list_assertion_revisions(self, *, product_id: str) -> list[EpistemicAssertionV1]:
        async with self.pool.connection() as db:
            rows = parse_rows(
                await db.query(
                    "SELECT payload, assertion_id, revision, stable_id FROM grounded_epistemic_assertion_revision "
                    "WHERE product = $product ORDER BY assertion_id, revision, stable_id",
                    {"product": parse_record_id(product_id)},
                )
            )
        return [
            EpistemicAssertionV1.model_validate(row["payload"]) for row in rows if isinstance(row.get("payload"), dict)
        ]

    async def affected_assertions(
        self,
        changed_input_refs: Iterable[str],
        *,
        product_id: str,
    ) -> list[EpistemicAssertionV1]:
        changed = sorted(set(changed_input_refs))
        if not changed:
            return []
        async with self.pool.connection() as db:
            rows = parse_rows(
                await db.query(
                    "SELECT payload, assertion_id, revision, stable_id FROM grounded_epistemic_assertion_revision "
                    "WHERE product = $product AND dependency_refs CONTAINSANY $changed "
                    "ORDER BY assertion_id, revision DESC, stable_id",
                    {"product": parse_record_id(product_id), "changed": changed},
                )
            )
        latest: dict[str, EpistemicAssertionV1] = {}
        for row in rows:
            if not isinstance(row.get("payload"), dict):
                continue
            assertion = EpistemicAssertionV1.model_validate(row["payload"])
            latest.setdefault(assertion.assertion_id, assertion)
        return [latest[key] for key in sorted(latest)]

    async def persist_all(self, records: Iterable[TP4Model]) -> tuple[TP4Model, ...]:
        normalized = tuple(sorted(records, key=_stable_id))
        if not normalized:
            return ()
        products = {str(getattr(record, "product_id")) for record in normalized}
        if len(products) > 1:
            raise BeliefStateProductScopeError("one TP4 persistence batch cannot cross product scope")
        async with self.pool.connection() as db:
            missing: list[TP4Model] = []
            for record in normalized:
                table = _MODEL_TABLE[type(record)]
                stable_id = _stable_id(record)
                product_id = str(getattr(record, "product_id"))
                material_hash = _material_hash(record)
                existing = parse_one(
                    await db.query(
                        f"SELECT material_hash, payload FROM ONLY type::record('{table}', $record_key) "
                        "WHERE product = $product LIMIT 1",
                        {"record_key": _record_key(stable_id), "product": parse_record_id(product_id)},
                    )
                )
                if not existing:
                    missing.append(record)
                    continue
                payload = existing.get("payload")
                stored = type(record).model_validate(payload) if isinstance(payload, dict) else None
                if (
                    str(existing.get("material_hash")) != material_hash
                    or stored is None
                    or canonical_hash(stored) != canonical_hash(record)
                ):
                    raise BeliefStateReplayConflict(f"stable TP4 identity {stable_id} contains different material")
            if missing:
                statements = ["BEGIN TRANSACTION"]
                params: dict[str, Any] = {}
                for index, record in enumerate(missing):
                    table = _MODEL_TABLE[type(record)]
                    stable_id = _stable_id(record)
                    record_key = f"record_key_{index}"
                    content_key = f"content_{index}"
                    params[record_key] = _record_key(stable_id)
                    params[content_key] = {
                        "contract_version": str(getattr(record, "contract_version")),
                        "product": parse_record_id(str(getattr(record, "product_id"))),
                        "stable_id": stable_id,
                        "material_hash": _material_hash(record),
                        "payload": record.model_dump(mode="python"),
                        **_specific_fields(record),
                    }
                    statements.append(f"CREATE ONLY type::record('{table}', ${record_key}) CONTENT ${content_key}")
                statements.append("COMMIT TRANSACTION")
                await _query_or_raise(db, ";\n".join(statements) + ";", params)
        return normalized
