"""E1-B deterministic legacy inventory and quarantine acceptance tests."""

from __future__ import annotations

import pytest

from core.engine.cognition import composer as composer_module
from core.engine.cognition.catalog import build_default_catalog
from core.engine.cognition.legacy_import import (
    LEGACY_COMPLETE_INVENTORY_QUERIES,
    LEGACY_INVENTORY_QUERIES,
    LegacyDisposition,
    collect_complete_legacy_rows,
    collect_legacy_rows,
    inventory_rows,
    map_framework_row,
    map_historical_row,
    map_meta_skill_row,
    map_proposal_row,
    map_skill_row,
    persist_import_receipts,
    verify_persisted_import_receipts,
)


def _job() -> dict:
    return {
        "name": "Frame",
        "archetype": "analyst",
        "mode": "deliberative",
        "frameworks": ["first-principles"],
        "output_format": "structured",
        "description": "Frame the decision.",
    }


def _skill(product: str | None = "product:alpha") -> dict:
    return {
        "id": "skill:example",
        "product": product,
        "slug": "example_skill",
        "name": "Example",
        "description": "Example legacy skill.",
        "domain_path": "architecture",
        "tier": "custom",
        "jobs": [_job()],
        "activation_signals": ["example"],
    }


def test_product_skill_maps_to_review_required_recipe_draft() -> None:
    receipt = map_skill_row(_skill())
    assert receipt.disposition is LegacyDisposition.MAPPED_REVIEW_REQUIRED
    assert receipt.target_identity is not None
    assert receipt.target_identity.cognition_type.value == "recipe"
    assert receipt.target_scope is not None
    assert receipt.target_scope.product_id == "product:alpha"
    assert receipt.normalized_body["phases"][0]["slots"][0]["frameworks"] == ["first-principles"]
    assert receipt.target_revision_id is None


def test_null_product_skill_is_quarantined_not_promoted_global() -> None:
    receipt = map_skill_row(_skill(product=None))
    assert receipt.disposition is LegacyDisposition.QUARANTINED
    assert "null_product_is_not_global" in receipt.diagnostics
    assert receipt.target_identity is None


def test_unsupported_skill_transition_is_quarantined() -> None:
    row = _skill()
    row["jobs"] = []
    row["phases"] = [
        {
            "name": "Loop",
            "pattern": "iterative",
            "slots": [
                {
                    "archetype": "analyst",
                    "mode": "deliberative",
                    "frameworks": [],
                    "specialties": [],
                }
            ],
            "termination": "convergence",
        }
    ]
    receipt = map_skill_row(row)
    assert receipt.disposition is LegacyDisposition.QUARANTINED
    assert "unsupported_pattern:iterative" in receipt.diagnostics
    assert "unsupported_termination:convergence" in receipt.diagnostics


def test_product_framework_maps_without_becoming_active() -> None:
    receipt = map_framework_row(
        {
            "id": "framework:custom",
            "product": "product:alpha",
            "slug": "custom-frame",
            "name": "Custom Frame",
            "family": "diagnostic",
            "tier": "custom",
            "description": "A custom frame.",
            "system_prompt": "Inspect constraints.",
            "activation_signals": ["constraints"],
            "archetype_affinity": {},
            "mode_affinity": {},
            "task_type_affinity": {},
            "composability": {},
        }
    )
    assert receipt.disposition is LegacyDisposition.MAPPED_REVIEW_REQUIRED
    assert receipt.target_identity is not None
    assert receipt.target_identity.cognition_type.value == "framework"
    assert receipt.target_revision_id is None


def test_exact_meta_skill_seed_snapshot_links_active_revision() -> None:
    catalog = build_default_catalog(core_yaml=composer_module._RECIPE_YAML)
    revision = catalog.recipe_revision("coding_intelligence")
    body = revision.body
    row = {
        "id": "meta_skill:coding",
        "slug": body["slug"],
        "name": body["name"],
        "description": body["description"],
        "domain_intelligences": body["domain_intelligences"],
        "recipe": {
            "phases": [
                {
                    "cognitive_function": phase["cognitive_function"],
                    "instruments": [
                        {
                            "slug": item["slug"],
                            "family_hint": item["family_hint"],
                            "fallback_slug": item["fallback_slug"],
                            "task_affinity": item["task_affinity"],
                        }
                        for item in phase["instruments"]
                    ],
                    "min_depth": phase["min_depth"],
                    "output_schema": phase["output_schema"],
                    "pattern": phase["pattern"],
                }
                for phase in body["recipe"]["phases"]
            ]
        },
    }
    receipt = map_meta_skill_row(row, catalog)
    assert receipt.disposition is LegacyDisposition.MATCHED_ACTIVE_REVISION
    assert receipt.target_revision_id == revision.revision_id

    row["description"] = "mutated snapshot"
    conflict = map_meta_skill_row(row, catalog)
    assert conflict.disposition is LegacyDisposition.QUARANTINED
    assert conflict.diagnostics == ("legacy_snapshot_conflict",)


def test_approved_legacy_proposal_never_synthesizes_review_authority() -> None:
    receipt = map_proposal_row(
        {
            "id": "self_optimizer_proposal:old",
            "product": "product:alpha",
            "type": "skill",
            "status": "approved",
            "name": "Old proposal",
            "draft": {},
            "source_tasks": [],
            "source_insights": [],
        }
    )
    assert receipt.disposition is LegacyDisposition.HISTORICAL_EVIDENCE
    assert "legacy_approval_provenance_missing" in receipt.diagnostics
    assert receipt.target_revision_id is None


def test_confidence_telemetry_is_not_effectiveness() -> None:
    receipt = map_historical_row(
        "instrument_perf",
        {"id": "instrument_perf:x", "product": "product:alpha", "outcome_score": 0.99},
    )
    assert receipt.disposition is LegacyDisposition.HISTORICAL_EVIDENCE
    assert "confidence_is_not_effectiveness" in receipt.diagnostics


def test_inventory_is_deterministic_and_product_id_changes_target_identity() -> None:
    catalog = build_default_catalog(core_yaml=composer_module._RECIPE_YAML)
    alpha = _skill("product:alpha")
    beta = _skill("product:beta")
    first = inventory_rows({"skill": [alpha], "instrument_perf": []}, catalog=catalog)
    second = inventory_rows({"instrument_perf": [], "skill": [alpha]}, catalog=catalog)
    assert first == second
    beta_receipt = map_skill_row(beta)
    assert first[0].target_identity.cognition_id != beta_receipt.target_identity.cognition_id


async def test_collect_inventory_reads_every_declared_source_kind() -> None:
    class FakeDB:
        def __init__(self) -> None:
            self.queries = []

        async def query(self, query, params):
            self.queries.append((query, params))
            return [[]]

    db = FakeDB()
    rows = await collect_legacy_rows(db, product_id="product:alpha")
    assert set(rows) == set(LEGACY_INVENTORY_QUERIES)
    assert len(db.queries) == len(LEGACY_INVENTORY_QUERIES)
    assert all(params == {"product": "product:alpha"} for _, params in db.queries)


async def test_inventory_query_failure_is_not_silently_skipped() -> None:
    class FailingDB:
        async def query(self, query, params):
            raise OSError("unavailable")

    with pytest.raises(RuntimeError, match="legacy_inventory_query_failed:skill"):
        await collect_legacy_rows(FailingDB(), product_id="product:alpha")


async def test_persist_import_receipts_writes_every_disposition_idempotently() -> None:
    class FakeDB:
        def __init__(self) -> None:
            self.params = []

        async def query(self, query, params):
            self.params.append(params)
            return []

    receipts = (map_skill_row(_skill()), map_skill_row(_skill(product=None)))
    db = FakeDB()
    await persist_import_receipts(db, receipts)
    assert len(db.params) == 2
    assert {item["disposition"] for item in db.params} == {
        "mapped_review_required",
        "quarantined",
    }
    assert all(len(item["record_key"]) == 32 for item in db.params)


async def test_complete_inventory_pages_every_source_without_product_filter() -> None:
    class FakeDB:
        def __init__(self) -> None:
            self.queries = []
            self.skills = [_skill("product:alpha"), _skill(None), _skill("product:beta")]

        async def query(self, query, params):
            self.queries.append((query, params))
            rows = self.skills if "FROM skill ORDER BY id" in query else []
            start = params["offset"]
            return [rows[start : start + params["limit"]]]

    db = FakeDB()
    rows = await collect_complete_legacy_rows(db, page_size=2, max_rows_per_source=10)
    assert set(rows) == set(LEGACY_COMPLETE_INVENTORY_QUERIES)
    assert rows["skill"] == db.skills
    assert all("ORDER BY id" in query and "LIMIT $limit START $offset" in query for query, _ in db.queries)
    assert all("product" not in params for _, params in db.queries)


async def test_complete_inventory_fails_closed_at_row_ceiling() -> None:
    class FakeDB:
        async def query(self, query, params):
            rows = [_skill("product:alpha"), _skill("product:beta"), _skill(None)]
            start = params["offset"]
            return [rows[start : start + params["limit"]]] if "FROM skill ORDER BY id" in query else [[]]

    with pytest.raises(RuntimeError, match="legacy_complete_inventory_row_limit:skill"):
        await collect_complete_legacy_rows(FakeDB(), page_size=2, max_rows_per_source=2)


async def test_persisted_receipts_are_read_verified_one_for_one() -> None:
    receipt = map_skill_row(_skill())

    class FakeDB:
        async def query(self, query, params):
            assert params["record_key"] == str(receipt.receipt_id).split(":", 1)[1]
            return [
                [
                    {
                        "source_hash": receipt.source_hash,
                        "disposition": receipt.disposition.value,
                        "receipt": receipt.model_dump(mode="json"),
                    }
                ]
            ]

    assert await verify_persisted_import_receipts(FakeDB(), (receipt,)) == 1
