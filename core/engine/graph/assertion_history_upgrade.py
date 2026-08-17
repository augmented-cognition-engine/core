"""Explicit product assignment for pre-v164 relational assertion history.

Legacy rows remain inert until an operator maps each whole connected component
to an existing product.  The upgrade copies validated history to current,
product-bound identities and leaves source rows unchanged for backup/rollback.
Copied assertions are deliberately non-operational until the current resolver
replays their proposals under current review policy.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import asdict, dataclass
from typing import Any, Literal, Mapping

from core.engine.core.db import parse_record_id, parse_rows
from core.engine.graph.assertions import (
    AssertionReview,
    RelationshipProposal,
    _semantic_key,
    _stable_id,
)
from core.engine.graph.ontology import RELATIONSHIPS, normalize_predicate

ASSERTION_HISTORY_INVENTORY_CONTRACT = "ace.assertion-history-inventory/v1"
ASSERTION_HISTORY_RECEIPT_CONTRACT = "ace.assertion-history-upgrade-receipt/v1"
ASSERTION_HISTORY_QUARANTINE_CONTRACT = "ace.assertion-history-quarantine/v1"

HISTORY_TABLES = (
    "relationship_proposal",
    "relationship_assertion",
    "assertion_review",
    "assertion_event",
    "assertion_dependency",
)


class AssertionHistoryUpgradeError(RuntimeError):
    """The legacy assertion-history upgrade could not proceed safely."""


async def _query_or_raise(db, query: str, params: dict[str, Any] | None = None):
    """Normalize SDK variants that return statement failures as strings."""

    result = await db.query(query, params or {})
    if isinstance(result, str):
        raise AssertionHistoryUpgradeError(result)
    return result


@dataclass(frozen=True, slots=True)
class HistoryComponent:
    component_id: str
    row_ids: tuple[str, ...]
    legacy_row_ids: tuple[str, ...]
    existing_products: tuple[str, ...]
    target_product: str | None
    status: Literal["awaiting_mapping", "ready", "quarantined"]
    reasons: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class AssertionHistoryInventory:
    contract: str
    source_tables: tuple[str, ...]
    unavailable_tables: tuple[str, ...]
    components: tuple[HistoryComponent, ...]
    row_count: int
    legacy_row_count: int

    def as_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True, slots=True)
class AssertionHistoryApplyReport:
    contract: str
    applied_components: tuple[str, ...]
    replayed_components: tuple[str, ...]
    quarantined_components: tuple[str, ...]
    copied_rows: int

    def as_dict(self) -> dict[str, Any]:
        return asdict(self)


def _record_id(row: Mapping[str, Any]) -> str:
    value = str(row.get("id", ""))
    if ":" not in value or any(character.isspace() for character in value):
        raise ValueError("missing or invalid record id")
    return value


def _product(row: Mapping[str, Any]) -> str | None:
    value = row.get("product")
    if value is None or str(value).upper() == "NONE":
        return None
    product = str(value)
    if not product.startswith("product:") or any(character.isspace() for character in product):
        raise ValueError(f"invalid product identity {product!r}")
    return product


def _component_id(legacy_ids: list[str]) -> str:
    digest = hashlib.sha256("\n".join(sorted(legacy_ids)).encode()).hexdigest()[:32]
    return f"assertion_history_component:{digest}"


def _references(table: str, row: Mapping[str, Any]) -> tuple[str, ...]:
    if table == "relationship_assertion":
        return tuple(
            str(item)
            for field in ("proposal_ids", "supporting_assertions", "contradicting_assertions")
            for item in row.get(field, []) or []
        )
    if table == "assertion_review":
        return (str(row.get("target_assertion", "")),)
    if table == "assertion_event":
        return (str(row.get("assertion_id", "")),)
    if table == "assertion_dependency":
        return (str(row.get("in", "")), str(row.get("out", "")))
    return ()


def _validate_row(table: str, row: Mapping[str, Any]) -> list[str]:
    reasons: list[str] = []
    try:
        _record_id(row)
        _product(row)
    except ValueError as exc:
        reasons.append(str(exc))
    required: dict[str, tuple[str, ...]] = {
        "relationship_proposal": ("subject", "predicate", "object", "polarity", "scope"),
        "relationship_assertion": (
            "subject",
            "predicate",
            "object",
            "polarity",
            "scope",
            "status",
            "projection_eligible",
        ),
        "assertion_review": ("target_assertion", "verdict", "reviewer_role"),
        "assertion_event": ("assertion_id", "event_type", "actor", "rationale"),
        "assertion_dependency": ("in", "out", "dependency_type"),
    }
    missing = [field for field in required[table] if row.get(field) is None]
    if missing:
        reasons.append(f"{table} missing typed fields: {', '.join(missing)}")
    for reference in _references(table, row):
        if ":" not in reference or any(character.isspace() for character in reference):
            reasons.append(f"{table} has invalid record reference {reference!r}")
    return reasons


def build_assertion_history_inventory(
    rows_by_table: Mapping[str, list[dict[str, Any]]],
    *,
    mappings: Mapping[str, str] | None = None,
    unavailable_tables: tuple[str, ...] = (),
) -> AssertionHistoryInventory:
    """Build deterministic connected components and validate explicit mappings."""

    mappings = mappings or {}
    nodes: dict[str, tuple[str, dict[str, Any]]] = {}
    reverse_references: dict[str, set[str]] = {}
    invalid_by_id: dict[str, list[str]] = {}

    for table in HISTORY_TABLES:
        for row in rows_by_table.get(table, []):
            try:
                row_id = _record_id(row)
            except ValueError as exc:
                synthetic = f"{table}:invalid:{len(invalid_by_id)}"
                invalid_by_id[synthetic] = [str(exc)]
                nodes[synthetic] = (table, row)
                continue
            if row_id in nodes:
                invalid_by_id.setdefault(row_id, []).append("duplicate record id across history inventory")
                continue
            nodes[row_id] = (table, row)
            invalid_by_id[row_id] = _validate_row(table, row)
            for reference in _references(table, row):
                reverse_references.setdefault(reference, set()).add(row_id)

    def inventory_product(row: Mapping[str, Any]) -> str | None:
        try:
            return _product(row)
        except ValueError:
            return None

    legacy_ids = sorted(row_id for row_id, (_, row) in nodes.items() if inventory_product(row) is None)
    visited: set[str] = set()
    components: list[HistoryComponent] = []
    known_component_ids: set[str] = set()

    for seed in legacy_ids:
        if seed in visited:
            continue
        pending = [seed]
        member_ids: set[str] = set()
        while pending:
            row_id = pending.pop()
            if row_id in visited or row_id not in nodes:
                continue
            visited.add(row_id)
            member_ids.add(row_id)
            table, row = nodes[row_id]
            linked = set(_references(table, row)) | reverse_references.get(row_id, set())
            pending.extend(sorted(linked - visited))

        member_legacy = sorted(row_id for row_id in member_ids if inventory_product(nodes[row_id][1]) is None)
        component_id = _component_id(member_legacy)
        known_component_ids.add(component_id)
        reasons: list[str] = []
        for row_id in sorted(member_ids):
            reasons.extend(f"{row_id}: {reason}" for reason in invalid_by_id.get(row_id, []))
            table, row = nodes[row_id]
            for reference in _references(table, row):
                if reference not in nodes:
                    reasons.append(f"{row_id}: dangling reference {reference}")

        products = sorted(
            {product for row_id in member_ids if (product := inventory_product(nodes[row_id][1])) is not None}
        )
        target = mappings.get(component_id)
        if len(products) > 1:
            reasons.append("component crosses multiple existing products")
        if target is not None and (
            not target.startswith("product:") or any(character.isspace() for character in target)
        ):
            reasons.append("mapping target is not a valid product record identity")
        if target is not None and products and target not in products:
            reasons.append("mapping conflicts with the component's existing product")

        status: Literal["awaiting_mapping", "ready", "quarantined"]
        if reasons:
            status = "quarantined"
        elif target is None:
            status = "awaiting_mapping"
        else:
            status = "ready"
        components.append(
            HistoryComponent(
                component_id=component_id,
                row_ids=tuple(sorted(member_ids)),
                legacy_row_ids=tuple(member_legacy),
                existing_products=tuple(products),
                target_product=target,
                status=status,
                reasons=tuple(sorted(set(reasons))),
            )
        )

    unknown_mappings = sorted(set(mappings) - known_component_ids)
    if unknown_mappings:
        raise AssertionHistoryUpgradeError(
            "mapping file contains unknown component ids: " + ", ".join(unknown_mappings)
        )
    return AssertionHistoryInventory(
        contract=ASSERTION_HISTORY_INVENTORY_CONTRACT,
        source_tables=tuple(table for table in HISTORY_TABLES if table not in unavailable_tables),
        unavailable_tables=tuple(sorted(unavailable_tables)),
        components=tuple(sorted(components, key=lambda item: item.component_id)),
        row_count=len(nodes),
        legacy_row_count=len(legacy_ids),
    )


async def load_assertion_history_inventory(
    db,
    *,
    mappings: Mapping[str, str] | None = None,
    max_rows_per_table: int = 10_000,
) -> tuple[AssertionHistoryInventory, dict[str, list[dict[str, Any]]]]:
    """Load a bounded inventory, tolerating pre-v142 tables as unavailable."""

    if max_rows_per_table < 1:
        raise ValueError("max_rows_per_table must be positive")
    info_value = await _query_or_raise(db, "INFO FOR DB")
    while isinstance(info_value, list) and len(info_value) == 1:
        info_value = info_value[0]
    info = info_value if isinstance(info_value, dict) else {}
    table_info = info.get("tables", {})
    available = set(table_info) if isinstance(table_info, dict) else set()
    rows_by_table: dict[str, list[dict[str, Any]]] = {}
    unavailable: list[str] = []
    for table in HISTORY_TABLES:
        if table not in available:
            unavailable.append(table)
            rows_by_table[table] = []
            continue
        rows = parse_rows(await _query_or_raise(db, f"SELECT * FROM {table} LIMIT {max_rows_per_table + 1}"))
        if len(rows) > max_rows_per_table:
            raise AssertionHistoryUpgradeError(
                f"{table} exceeds the bounded inventory limit of {max_rows_per_table} rows"
            )
        rows_by_table[table] = rows
    return (
        build_assertion_history_inventory(
            rows_by_table,
            mappings=mappings,
            unavailable_tables=tuple(unavailable),
        ),
        rows_by_table,
    )


def _canonical_assertion_id(row: Mapping[str, Any], product: str) -> str:
    predicate = str(row["predicate"])
    subject = str(row["subject"])
    object_ = str(row["object"])
    normalized = normalize_predicate(predicate)
    if normalized is not None:
        predicate, swap = normalized
        if swap:
            subject, object_ = object_, subject
        contract = RELATIONSHIPS[predicate]
        if contract.symmetric and object_ < subject:
            subject, object_ = object_, subject
    key = _semantic_key(
        product,
        subject,
        predicate,
        object_,
        str(row["polarity"]),
        dict(row.get("scope") or {}),
        row.get("valid_from"),
        row.get("valid_to"),
    )
    return _stable_id("relationship_assertion", key)


def _copy_content(row: Mapping[str, Any], *, excluded: set[str]) -> dict[str, Any]:
    return {key: value for key, value in row.items() if key not in excluded}


async def apply_assertion_history_upgrade(
    db,
    *,
    inventory: AssertionHistoryInventory,
    rows_by_table: Mapping[str, list[dict[str, Any]]],
) -> AssertionHistoryApplyReport:
    """Copy mapped components to current identities; quarantine invalid ones.

    The operation is restart-safe: every target identity and final receipt is
    deterministic.  Source rows are never updated or deleted.  A completed
    component receipt turns subsequent applies into exact replays.
    """

    if any(component.status == "awaiting_mapping" for component in inventory.components):
        raise AssertionHistoryUpgradeError("every legacy component requires an explicit mapping before apply")
    products = sorted(
        {
            component.target_product
            for component in inventory.components
            if component.status == "ready" and component.target_product is not None
        }
    )
    for product in products:
        result = parse_rows(
            await _query_or_raise(
                db,
                "SELECT id FROM product WHERE id = <record>$product LIMIT 1",
                {"product": product},
            )
        )
        if not result:
            raise AssertionHistoryUpgradeError(f"mapped target product does not exist: {product}")

    indexed = {
        str(row["id"]): (table, row)
        for table in HISTORY_TABLES
        for row in rows_by_table.get(table, [])
        if row.get("id") is not None
    }
    applied: list[str] = []
    replayed: list[str] = []
    quarantined: list[str] = []
    copied_rows = 0

    for component in inventory.components:
        receipt_id = component.component_id.replace("assertion_history_component:", "")
        if component.status == "quarantined":
            quarantine_id = parse_record_id(f"assertion_history_upgrade_quarantine:{receipt_id}")
            existing_quarantine = parse_rows(
                await _query_or_raise(db, "SELECT id FROM ONLY $id LIMIT 1", {"id": quarantine_id})
            )
            if not existing_quarantine:
                await _query_or_raise(
                    db,
                    "CREATE $id CONTENT $content",
                    {
                        "id": quarantine_id,
                        "content": {
                            "contract": ASSERTION_HISTORY_QUARANTINE_CONTRACT,
                            "component_id": component.component_id,
                            "target_product": (
                                parse_record_id(component.target_product) if component.target_product else None
                            ),
                            "source_row_ids": list(component.legacy_row_ids),
                            "reasons": list(component.reasons),
                        },
                    },
                )
            quarantined.append(component.component_id)
            continue

        assert component.target_product is not None
        target_product = component.target_product
        receipt_record = parse_record_id(f"assertion_history_upgrade_receipt:{receipt_id}")
        existing = parse_rows(await _query_or_raise(db, "SELECT id FROM ONLY $id LIMIT 1", {"id": receipt_record}))
        if existing:
            replayed.append(component.component_id)
            continue

        proposal_map: dict[str, str] = {
            source_id: source_id
            for source_id in component.row_ids
            if indexed[source_id][0] == "relationship_proposal" and _product(indexed[source_id][1]) is not None
        }
        assertion_map: dict[str, str] = {
            source_id: source_id
            for source_id in component.row_ids
            if indexed[source_id][0] == "relationship_assertion" and _product(indexed[source_id][1]) is not None
        }
        review_map: dict[str, str] = {
            source_id: source_id
            for source_id in component.row_ids
            if indexed[source_id][0] == "assertion_review" and _product(indexed[source_id][1]) is not None
        }
        created_ids: list[str] = []

        for source_id in component.row_ids:
            table, row = indexed[source_id]
            if table == "relationship_proposal" and _product(row) is None:
                material = {
                    field: row[field]
                    for field in RelationshipProposal.model_fields
                    if field != "product_id" and field in row
                }
                material["product_id"] = target_product
                proposal = RelationshipProposal.model_validate(material)
                target_id = proposal.event_id()
                proposal_map[source_id] = target_id
                content = proposal.model_dump(mode="json")
                content.pop("product_id")
                content["product"] = parse_record_id(target_product)
                await _query_or_raise(
                    db,
                    "UPSERT $id CONTENT $content",
                    {"id": parse_record_id(target_id), "content": content},
                )
                created_ids.append(target_id)
                copied_rows += 1

        for source_id in component.row_ids:
            table, row = indexed[source_id]
            if table == "relationship_assertion" and _product(row) is None:
                target_id = _canonical_assertion_id(row, target_product)
                assertion_map[source_id] = target_id

        for source_id in component.row_ids:
            table, row = indexed[source_id]
            if table == "relationship_assertion" and _product(row) is None:
                target_id = assertion_map[source_id]
                content = _copy_content(row, excluded={"id", "product", "created_at"})
                content["product"] = parse_record_id(target_product)
                content["proposal_ids"] = [
                    proposal_map.get(str(item), str(item)) for item in row.get("proposal_ids", [])
                ]
                content["supporting_assertions"] = [
                    assertion_map.get(str(item), str(item)) for item in row.get("supporting_assertions", [])
                ]
                content["contradicting_assertions"] = [
                    assertion_map.get(str(item), str(item)) for item in row.get("contradicting_assertions", [])
                ]
                # Reviews are copied and remain inspectable through their target.
                # Current policy replay reconstructs the authoritative review_refs.
                content["review_refs"] = []
                content["status"] = "provisional" if row.get("status") not in {"rejected", "retired"} else row["status"]
                content["projection_eligible"] = False
                content["degraded_reason"] = "legacy_history_requires_current_policy_replay"
                content["explanation"] = (
                    "Imported legacy history is non-operational until replayed by the current resolver. "
                    + str(row.get("explanation", ""))
                ).strip()
                await _query_or_raise(
                    db,
                    "UPSERT $id CONTENT $content",
                    {"id": parse_record_id(target_id), "content": content},
                )
                created_ids.append(target_id)
                copied_rows += 1

        for source_id in component.row_ids:
            table, row = indexed[source_id]
            if table == "assertion_review" and _product(row) is None:
                old_target = str(row["target_assertion"])
                material = {
                    field: row[field]
                    for field in AssertionReview.model_fields
                    if field != "product_id" and field in row
                }
                material["product_id"] = target_product
                material["target_assertion"] = assertion_map[old_target]
                review = AssertionReview.model_validate(material)
                target_id = review.review_id()
                review_map[source_id] = target_id
                content = review.model_dump(mode="json")
                content.pop("product_id")
                content["product"] = parse_record_id(target_product)
                content["target_assertion"] = parse_record_id(review.target_assertion)
                await _query_or_raise(
                    db,
                    "UPSERT $id CONTENT $content",
                    {"id": parse_record_id(target_id), "content": content},
                )
                created_ids.append(target_id)
                copied_rows += 1

        for source_id in component.row_ids:
            table, row = indexed[source_id]
            if _product(row) is not None:
                continue
            if table == "assertion_event":
                content = _copy_content(row, excluded={"id", "product"})
                content["product"] = parse_record_id(target_product)
                content["assertion_id"] = parse_record_id(assertion_map[str(row["assertion_id"])])
                target_id = _stable_id(
                    "assertion_event",
                    {"legacy_event": source_id, "product": target_product, "assertion": str(content["assertion_id"])},
                )
                await _query_or_raise(
                    db,
                    "UPSERT $id CONTENT $content",
                    {"id": parse_record_id(target_id), "content": content},
                )
                created_ids.append(target_id)
                copied_rows += 1
            elif table == "assertion_dependency":
                content = _copy_content(row, excluded={"id", "product", "in", "out"})
                content["product"] = parse_record_id(target_product)
                content["in"] = parse_record_id(assertion_map[str(row["in"])])
                content["out"] = parse_record_id(assertion_map[str(row["out"])])
                target_id = _stable_id(
                    "assertion_dependency",
                    {
                        "product": target_product,
                        "in": str(content["in"]),
                        "out": str(content["out"]),
                        "dependency_type": row["dependency_type"],
                    },
                )
                edge = parse_record_id(target_id)
                existing_edge = parse_rows(await _query_or_raise(db, "SELECT id FROM ONLY $id LIMIT 1", {"id": edge}))
                if not existing_edge:
                    await _query_or_raise(
                        db,
                        "RELATE $in -> $edge -> $out CONTENT $content",
                        {
                            "in": content["in"],
                            "edge": edge,
                            "out": content["out"],
                            "content": content,
                        },
                    )
                created_ids.append(target_id)
                copied_rows += 1

        await _query_or_raise(
            db,
            "CREATE $id CONTENT $content",
            {
                "id": receipt_record,
                "content": {
                    "contract": ASSERTION_HISTORY_RECEIPT_CONTRACT,
                    "component_id": component.component_id,
                    "target_product": parse_record_id(target_product),
                    "source_row_ids": list(component.legacy_row_ids),
                    "created_row_ids": sorted(set(created_ids)),
                    "proposal_id_map": proposal_map,
                    "assertion_id_map": assertion_map,
                    "review_id_map": review_map,
                    "operational": False,
                },
            },
        )
        applied.append(component.component_id)

    return AssertionHistoryApplyReport(
        contract=ASSERTION_HISTORY_RECEIPT_CONTRACT,
        applied_components=tuple(applied),
        replayed_components=tuple(replayed),
        quarantined_components=tuple(quarantined),
        copied_rows=copied_rows,
    )


def load_mapping_document(payload: Mapping[str, Any]) -> dict[str, str]:
    """Validate the small, explicit component-to-product mapping document."""

    if payload.get("contract") != "ace.assertion-history-product-map/v1":
        raise AssertionHistoryUpgradeError("unsupported assertion-history mapping contract")
    mappings = payload.get("components")
    if not isinstance(mappings, dict) or not mappings:
        raise AssertionHistoryUpgradeError("mapping document must contain a non-empty components object")
    return {str(component): str(product) for component, product in mappings.items()}


def mapping_digest(mappings: Mapping[str, str]) -> str:
    material = json.dumps(dict(sorted(mappings.items())), sort_keys=True, separators=(",", ":"))
    return f"sha256:{hashlib.sha256(material.encode()).hexdigest()}"
