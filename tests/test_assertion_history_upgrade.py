from __future__ import annotations

import pytest

from core.engine.graph.assertion_history_upgrade import (
    ASSERTION_HISTORY_RECEIPT_CONTRACT,
    AssertionHistoryUpgradeError,
    apply_assertion_history_upgrade,
    build_assertion_history_inventory,
    load_mapping_document,
)

pytestmark = pytest.mark.unit


def _history_rows(*, conflicting_product: str | None = None):
    proposal = {
        "id": "relationship_proposal:legacy-p1",
        "product": None,
        "subject": "insight:subject",
        "predicate": "depends_on",
        "object": "insight:object",
        "polarity": "positive",
        "scope": {},
    }
    assertion = {
        "id": "relationship_assertion:legacy-a1",
        "product": conflicting_product,
        "subject": "insight:subject",
        "predicate": "depends_on",
        "object": "insight:object",
        "polarity": "positive",
        "scope": {},
        "status": "accepted",
        "projection_eligible": True,
        "proposal_ids": [proposal["id"]],
        "explanation": "accepted by the historical resolver",
    }
    return {
        "relationship_proposal": [proposal],
        "relationship_assertion": [assertion],
        "assertion_review": [
            {
                "id": "assertion_review:legacy-r1",
                "product": None,
                "target_assertion": assertion["id"],
                "reviewer_role": "critic",
                "verdict": "object",
            }
        ],
        "assertion_event": [
            {
                "id": "assertion_event:legacy-e1",
                "product": None,
                "assertion_id": assertion["id"],
                "event_type": "resolution",
                "actor": "resolver",
                "rationale": "historical",
            }
        ],
        "assertion_dependency": [],
    }


def test_inventory_requires_explicit_whole_component_mapping_and_is_deterministic():
    rows = _history_rows()
    first = build_assertion_history_inventory(rows)
    second = build_assertion_history_inventory(
        {table: list(reversed(values)) for table, values in reversed(rows.items())}
    )

    assert first.components == second.components
    assert len(first.components) == 1
    component = first.components[0]
    assert component.status == "awaiting_mapping"
    assert component.legacy_row_ids == tuple(sorted(component.row_ids))

    mapped = build_assertion_history_inventory(rows, mappings={component.component_id: "product:platform"})
    assert mapped.components[0].status == "ready"
    assert mapped.components[0].target_product == "product:platform"


def test_inventory_quarantines_cross_product_and_dangling_material():
    rows = _history_rows(conflicting_product="product:other")
    component_id = build_assertion_history_inventory(rows).components[0].component_id
    mapped = build_assertion_history_inventory(rows, mappings={component_id: "product:platform"})

    component = mapped.components[0]
    assert component.status == "quarantined"
    assert any("conflicts" in reason for reason in component.reasons)

    rows["assertion_event"][0]["assertion_id"] = "relationship_assertion:missing"
    dangling = build_assertion_history_inventory(rows)
    assert any("dangling reference" in reason for component in dangling.components for reason in component.reasons)


def test_mapping_document_is_versioned_and_nonempty():
    assert load_mapping_document(
        {
            "contract": "ace.assertion-history-product-map/v1",
            "components": {"assertion_history_component:abc": "product:platform"},
        }
    ) == {"assertion_history_component:abc": "product:platform"}
    with pytest.raises(AssertionHistoryUpgradeError, match="unsupported"):
        load_mapping_document({"contract": "unknown", "components": {"a": "product:p"}})


def test_inventory_quarantines_malformed_row_instead_of_dropping_it():
    rows = {table: [] for table in _history_rows()}
    rows["relationship_proposal"] = [
        {
            "product": None,
            "subject": "insight:a",
            "predicate": "depends_on",
            "object": "insight:b",
            "polarity": "positive",
            "scope": {},
        }
    ]
    inventory = build_assertion_history_inventory(rows)
    assert inventory.legacy_row_count == 1
    assert inventory.components[0].status == "quarantined"
    assert any("record id" in reason for reason in inventory.components[0].reasons)


class FakeApplyDB:
    def __init__(self):
        self.receipts: set[str] = set()
        self.writes: list[tuple[str, dict]] = []

    async def query(self, statement: str, params=None):
        params = params or {}
        if statement.startswith("SELECT id FROM product"):
            return [{"id": params["product"]}]
        if statement == "SELECT id FROM ONLY $id LIMIT 1":
            return [{"id": params["id"]}] if str(params["id"]) in self.receipts else []
        if statement.startswith("CREATE $id"):
            self.receipts.add(str(params["id"]))
            self.writes.append((statement, params))
            return [params["content"]]
        if statement.startswith("UPSERT $id"):
            self.writes.append((statement, params))
            return [params["content"]]
        raise AssertionError(statement)


@pytest.mark.asyncio
async def test_apply_copies_to_product_bound_nonoperational_ids_and_replays_without_writes():
    rows = _history_rows()
    component_id = build_assertion_history_inventory(rows).components[0].component_id
    inventory = build_assertion_history_inventory(rows, mappings={component_id: "product:platform"})
    db = FakeApplyDB()

    first = await apply_assertion_history_upgrade(db, inventory=inventory, rows_by_table=rows)
    writes_after_first = len(db.writes)
    second = await apply_assertion_history_upgrade(db, inventory=inventory, rows_by_table=rows)

    assert first.contract == ASSERTION_HISTORY_RECEIPT_CONTRACT
    assert first.applied_components == (component_id,)
    assert first.copied_rows == 4
    assert second.replayed_components == (component_id,)
    assert len(db.writes) == writes_after_first
    assertion_writes = [
        params["content"]
        for statement, params in db.writes
        if statement.startswith("UPSERT") and str(params["id"]).startswith("relationship_assertion:")
    ]
    assert str(assertion_writes[0]["product"]) == "product:platform"
    assert assertion_writes[0]["projection_eligible"] is False
    assert assertion_writes[0]["status"] == "provisional"


@pytest.mark.asyncio
async def test_apply_refuses_any_unmapped_component_before_writing():
    rows = _history_rows()
    inventory = build_assertion_history_inventory(rows)
    db = FakeApplyDB()
    with pytest.raises(AssertionHistoryUpgradeError, match="explicit mapping"):
        await apply_assertion_history_upgrade(db, inventory=inventory, rows_by_table=rows)
    assert db.writes == []


@pytest.mark.asyncio
async def test_quarantine_receipt_is_append_only_and_restart_idempotent():
    rows = _history_rows(conflicting_product="product:other")
    component_id = build_assertion_history_inventory(rows).components[0].component_id
    inventory = build_assertion_history_inventory(rows, mappings={component_id: "product:platform"})
    db = FakeApplyDB()

    first = await apply_assertion_history_upgrade(db, inventory=inventory, rows_by_table=rows)
    write_count = len(db.writes)
    second = await apply_assertion_history_upgrade(db, inventory=inventory, rows_by_table=rows)

    assert first.quarantined_components == (component_id,)
    assert second.quarantined_components == (component_id,)
    assert len(db.writes) == write_count
