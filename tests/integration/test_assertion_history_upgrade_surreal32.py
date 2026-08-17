from __future__ import annotations

import os
from datetime import UTC, datetime

import pytest
from surrealdb import AsyncSurreal

from core.engine.core.config import settings
from core.engine.core.db import parse_record_id, parse_rows
from core.engine.graph.assertion_history_upgrade import (
    apply_assertion_history_upgrade,
    build_assertion_history_inventory,
    load_assertion_history_inventory,
)
from core.engine.graph.assertions import RelationshipProposal, resolve_proposals

pytestmark = [pytest.mark.integration, pytest.mark.asyncio]


@pytest.mark.skipif(
    os.environ.get("ACE_RUN_SURREAL32_UPGRADE_ACCEPTANCE") != "1",
    reason="requires an explicitly disposable SurrealDB 3.2 database",
)
async def test_legacy_assertion_upgrade_is_product_scoped_inert_and_restart_replayable():
    assert settings.surreal_db.startswith("ace_v179"), "refusing to mutate a non-disposable database"
    db = AsyncSurreal(settings.surreal_url)
    await db.connect()
    await db.signin({"username": settings.surreal_user, "password": settings.surreal_pass})
    await db.use(settings.surreal_ns, settings.surreal_db)
    await db.query("UPSERT product:platform SET name = 'Upgrade acceptance', tenant = tenant:default")

    proposal = RelationshipProposal(
        product_id="product:platform",
        subject="insight:upgrade_acceptance_subject",
        predicate="depends_on",
        object="insight:upgrade_acceptance_object",
        evidence_refs=["observation:upgrade_acceptance"],
        origin_type="human",
    )
    canonical = resolve_proposals([proposal])[0]
    proposal_content = proposal.model_dump(mode="json")
    proposal_content.pop("product_id")
    assertion_content = canonical.model_dump(mode="json")
    assertion_content.pop("id")
    assertion_content.pop("product_id")
    assertion_content["proposal_ids"] = ["relationship_proposal:upgrade_acceptance_legacy"]
    assertion_content["updated_at"] = datetime.now(UTC)

    await db.query(
        "UPSERT relationship_proposal:upgrade_acceptance_legacy CONTENT $content",
        {"content": proposal_content},
    )
    await db.query(
        "UPSERT relationship_assertion:upgrade_acceptance_legacy CONTENT $content",
        {"content": assertion_content},
    )
    await db.query(
        "UPSERT assertion_event:upgrade_acceptance_legacy SET "
        "assertion_id = relationship_assertion:upgrade_acceptance_legacy, "
        "event_type = 'resolution', actor = 'legacy-resolver', rationale = 'upgrade acceptance'",
    )
    await db.query("DELETE assertion_dependency:upgrade_acceptance_legacy")
    await db.query(
        "RELATE relationship_assertion:upgrade_acceptance_legacy"
        "->assertion_dependency:upgrade_acceptance_legacy"
        "->relationship_assertion:upgrade_acceptance_legacy "
        "SET dependency_type = 'derives_from'",
    )

    inventory, rows = await load_assertion_history_inventory(db)
    component = next(
        item
        for item in inventory.components
        if "relationship_proposal:upgrade_acceptance_legacy" in item.legacy_row_ids
    )
    mapped = build_assertion_history_inventory(
        rows,
        mappings={component.component_id: "product:platform"},
        unavailable_tables=inventory.unavailable_tables,
    )
    report = await apply_assertion_history_upgrade(db, inventory=mapped, rows_by_table=rows)
    assert component.component_id in report.applied_components + report.replayed_components

    receipt = parse_rows(
        await db.query(
            "SELECT * FROM assertion_history_upgrade_receipt WHERE component_id = $component LIMIT 1",
            {"component": component.component_id},
        )
    )[0]
    target_assertion = str(receipt["assertion_id_map"]["relationship_assertion:upgrade_acceptance_legacy"])
    copied = parse_rows(await db.query("SELECT * FROM ONLY $id LIMIT 1", {"id": parse_record_id(target_assertion)}))[0]
    source = parse_rows(
        await db.query("SELECT product FROM ONLY relationship_assertion:upgrade_acceptance_legacy LIMIT 1")
    )[0]
    assert str(copied["product"]) == "product:platform"
    assert copied["projection_eligible"] is False
    assert copied["status"] == "provisional"
    assert source.get("product") is None
    await db.close()

    restarted = AsyncSurreal(settings.surreal_url)
    await restarted.connect()
    await restarted.signin({"username": settings.surreal_user, "password": settings.surreal_pass})
    await restarted.use(settings.surreal_ns, settings.surreal_db)
    replay = await apply_assertion_history_upgrade(restarted, inventory=mapped, rows_by_table=rows)
    assert replay.replayed_components == (component.component_id,)
    assert replay.copied_rows == 0
    await restarted.close()
