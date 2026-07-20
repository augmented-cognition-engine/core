# tests/canvas/test_ledger_bridge.py
import pytest

from core.engine.canvas.ledger_bridge import bridge_decision_to_ledger

pytestmark = pytest.mark.e2e


@pytest.mark.asyncio
async def test_canvas_decision_lands_in_decision_table_with_surface_field(db_pool):
    """Bridge persists a canvas decision via create_decision, then UPDATEs
    the resulting record with canvas_session_id and surface='canvas'."""
    from core.engine.core.db import parse_one, pool

    session_id = "canvas_session:bridge_test"
    async with pool.connection() as db:
        await db.query(
            f"CREATE {session_id} SET project_id = 'product:p1', title = 't', "
            f"created_at = time::now(), updated_at = time::now();"
        )
    decision_id = await bridge_decision_to_ledger(
        session_id=session_id,
        product_id="product:p1",
        title="Use Postgres",
        rationale="ACID required for billing",
        cited_artifact_ids=["canvas_artifact:a1"],
        framework_kind="trade_off_matrix",
    )
    async with pool.connection() as db:
        result = await db.query(f"SELECT surface, canvas_session_id, title, source FROM {decision_id};")
    row = parse_one(result)
    assert row["surface"] == "canvas"
    assert row["source"] == "canvas"
    assert row["title"] == "Use Postgres"
    # canvas_session_id stored as record reference
    assert str(row["canvas_session_id"]) == session_id


@pytest.mark.asyncio
async def test_bridge_invokes_canonical_create_decision(db_pool, monkeypatch):
    """§A4 invariant: bridge MUST call engine.product.decisions.create_decision
    (the canonical entrypoint that runs similarity-check, edge-creation, and the
    downstream synthesizer hooks). Loud-fail if the symbol moves.

    NOTE: monkeypatch DOES NOT use raising=False — if create_decision is missing,
    the test must error loudly, not vacuously pass."""
    called = []

    async def fake_create_decision(**kwargs):
        called.append(kwargs)
        return {"id": "decision:canvas_test_id"}

    # Patch where the bridge imports from. raising=True (default) ensures
    # this fails if the symbol moves.
    monkeypatch.setattr(
        "core.engine.canvas.ledger_bridge.create_decision",
        fake_create_decision,
    )

    from core.engine.core.db import pool

    session_id = "canvas_session:bridge_pipeline"
    async with pool.connection() as db:
        await db.query(
            f"CREATE {session_id} SET project_id = 'product:p1', title = 't', "
            f"created_at = time::now(), updated_at = time::now();"
        )

    await bridge_decision_to_ledger(
        session_id=session_id,
        product_id="product:p1",
        title="t",
        rationale="r",
        cited_artifact_ids=[],
        framework_kind=None,
    )

    assert len(called) == 1, "bridge MUST invoke create_decision exactly once"
    assert called[0]["title"] == "t"
    assert called[0]["source"] == "canvas"
    assert called[0]["product_id"] == "product:p1"
