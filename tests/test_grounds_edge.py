"""E2E tests for the `grounds` edge — ACE's node↔canvas join (v136).

The `grounds` edge is the substrate contract's one "before it hardens" schema
addition: it joins a reasoning node (the mind) to a canvas object (its
projection). These tests exercise the REAL SurrealDB (marked e2e) because the
reverse-lookup correctness is the substrate's named reliability frontier
(11-SUBSTRATE §9.1) — a false reverse match would make the metabolism
re-evaluate the WRONG beliefs, and a mock accepts every query the real engine
would reject.

Spec: docs/superpowers/specs/2026-07-14-grounds-edge-design.md
"""

from __future__ import annotations

import pytest

from core.engine.core.db import parse_one, parse_record_id, parse_rows

pytestmark = pytest.mark.e2e


# --------------------------------------------------------------------------- #
# helpers — real reasoning nodes (insight) and canvas objects (canvas_artifact)
# --------------------------------------------------------------------------- #
async def _mk_insight(db, content: str = "grounds-test belief") -> str:
    """A minimal SCHEMAFULL insight. `product` is required (non-option); the
    db_pool fixture seeds product:test. `org` was widened to option by v113."""
    r = await db.query(
        "CREATE insight SET content = $c, insight_type = 'pattern', tier = 'domain', "
        "confidence = 0.5, source_domain = 'grounds-test', product = product:test",
        {"c": content},
    )
    return str(parse_one(r)["id"])


async def _mk_artifact(db) -> str:
    r = await db.query("CREATE canvas_artifact SET shape_kind = 'sticky', author = 'ai', payload = {}")
    return str(parse_one(r)["id"])


async def _cleanup(db, ids: list[str]) -> None:
    for i in ids:
        try:
            await db.query("DELETE grounds WHERE in = $r OR out = $r", {"r": parse_record_id(i)})
            await db.query(f"DELETE {i}")
        except Exception:
            pass


# --------------------------------------------------------------------------- #
# ground() — create + idempotency
# --------------------------------------------------------------------------- #
async def test_ground_creates_edge_and_grounded_in_reads_it(db_health, db_pool):
    from core.engine.graph.grounding import ground, grounded_in

    async with db_pool.connection() as db:
        node = await _mk_insight(db)
        obj = await _mk_artifact(db)
    try:
        edge_id = await ground(node, obj, pool=db_pool)
        assert edge_id  # an edge was created

        grounds = await grounded_in(node, pool=db_pool)
        assert grounds == [{"plane": "artifact", "objectIds": [obj]}]
    finally:
        async with db_pool.connection() as db:
            await _cleanup(db, [node, obj])


async def test_ground_is_idempotent_and_flips_role_and_primary(db_health, db_pool):
    """A second ground() on the same (in, out) updates role/primary in place —
    it must NOT create a duplicate edge."""
    from core.engine.graph.grounding import ground

    async with db_pool.connection() as db:
        node = await _mk_insight(db)
        obj = await _mk_artifact(db)
    try:
        e1 = await ground(node, obj, role="about", primary=False, pool=db_pool)
        e2 = await ground(node, obj, role="originates", primary=True, pool=db_pool)
        assert e1 == e2  # same edge id — no duplicate

        async with db_pool.connection() as db:
            rows = parse_rows(
                await db.query(
                    "SELECT * FROM grounds WHERE in = $n AND out = $o",
                    {"n": parse_record_id(node), "o": parse_record_id(obj)},
                )
            )
        assert len(rows) == 1
        assert rows[0]["role"] == "originates"
        assert rows[0]["primary"] is True
    finally:
        async with db_pool.connection() as db:
            await _cleanup(db, [node, obj])


async def test_at_most_one_primary_per_node(db_health, db_pool):
    """The single-primary invariant: marking a new grounding primary clears the
    previous one (enforced in the write path, not the schema)."""
    from core.engine.graph.grounding import ground

    async with db_pool.connection() as db:
        node = await _mk_insight(db)
        x = await _mk_artifact(db)
        y = await _mk_artifact(db)
    try:
        await ground(node, x, primary=True, pool=db_pool)
        await ground(node, y, primary=True, pool=db_pool)

        async with db_pool.connection() as db:
            rows = parse_rows(
                await db.query(
                    "SELECT out, primary FROM grounds WHERE in = $n",
                    {"n": parse_record_id(node)},
                )
            )
        primaries = {str(r["out"]): r["primary"] for r in rows}
        assert primaries[x] is False  # cleared when y became primary
        assert primaries[y] is True
    finally:
        async with db_pool.connection() as db:
            await _cleanup(db, [node, x, y])


# --------------------------------------------------------------------------- #
# grounds_of() — the reverse lookup the metabolism depends on
# --------------------------------------------------------------------------- #
async def test_grounds_of_isolates_by_object(db_health, db_pool):
    """LOAD-BEARING: the reverse lookup must return the nodes grounded in THIS
    object and NOT nodes grounded in a different object. A false match would
    re-derive the wrong beliefs when an unrelated object changes."""
    from core.engine.graph.grounding import ground, grounds_of

    async with db_pool.connection() as db:
        a1 = await _mk_insight(db, "belief about x")
        a2 = await _mk_insight(db, "belief about y")
        x = await _mk_artifact(db)
        y = await _mk_artifact(db)
    try:
        await ground(a1, x, pool=db_pool)
        await ground(a2, y, pool=db_pool)

        nodes_x = await grounds_of(x, pool=db_pool)
        assert a1 in nodes_x
        assert a2 not in nodes_x  # the isolation guarantee
    finally:
        async with db_pool.connection() as db:
            await _cleanup(db, [a1, a2, x, y])


async def test_grounds_of_returns_all_nodes_for_shared_object(db_health, db_pool):
    from core.engine.graph.grounding import ground, grounds_of

    async with db_pool.connection() as db:
        a1 = await _mk_insight(db)
        a2 = await _mk_insight(db)
        obj = await _mk_artifact(db)
    try:
        await ground(a1, obj, pool=db_pool)
        await ground(a2, obj, pool=db_pool)

        nodes = await grounds_of(obj, pool=db_pool)
        assert set(nodes) >= {a1, a2}
    finally:
        async with db_pool.connection() as db:
            await _cleanup(db, [a1, a2, obj])


# --------------------------------------------------------------------------- #
# grounded_in() — the membrane shape + error handling
# --------------------------------------------------------------------------- #
async def test_grounded_in_membrane_shape_groups_by_plane(db_health, db_pool):
    from core.engine.graph.grounding import ground, grounded_in

    async with db_pool.connection() as db:
        node = await _mk_insight(db)
        x = await _mk_artifact(db)
        y = await _mk_artifact(db)
    try:
        await ground(node, x, pool=db_pool)
        await ground(node, y, pool=db_pool)

        grounds = await grounded_in(node, pool=db_pool)
        assert len(grounds) == 1  # one entry per plane
        assert grounds[0]["plane"] == "artifact"
        assert set(grounds[0]["objectIds"]) == {x, y}
    finally:
        async with db_pool.connection() as db:
            await _cleanup(db, [node, x, y])


async def test_grounded_in_ungrounded_node_returns_empty(db_health, db_pool):
    from core.engine.graph.grounding import grounded_in

    async with db_pool.connection() as db:
        node = await _mk_insight(db)
    try:
        assert await grounded_in(node, pool=db_pool) == []
    finally:
        async with db_pool.connection() as db:
            await _cleanup(db, [node])


async def test_grounded_in_omits_dangling_target(db_health, db_pool):
    """A canvas object can be deleted while nodes still ground in it. The node is
    NEVER deleted for losing its ground; grounded_in filters the dead target and
    does not raise."""
    from core.engine.graph.grounding import ground, grounded_in

    async with db_pool.connection() as db:
        node = await _mk_insight(db)
        obj = await _mk_artifact(db)
    try:
        await ground(node, obj, pool=db_pool)
        async with db_pool.connection() as db:
            await db.query(f"DELETE {obj}")  # target gone; edge now dangles

        grounds = await grounded_in(node, pool=db_pool)  # must not raise
        ids = [o for g in grounds for o in g.get("objectIds", [])]
        assert obj not in ids
    finally:
        async with db_pool.connection() as db:
            await _cleanup(db, [node, obj])


async def test_ground_rejects_reasoning_node_target(db_health, db_pool):
    """`grounds` is node→canvas only. Grounding into another reasoning node is an
    `edges` relation, not a `grounds` one, and must raise."""
    from core.engine.graph.grounding import ground

    async with db_pool.connection() as db:
        a = await _mk_insight(db)
        b = await _mk_insight(db)  # a reasoning node, NOT a canvas object
    try:
        with pytest.raises(ValueError):
            await ground(a, b, pool=db_pool)
    finally:
        async with db_pool.connection() as db:
            await _cleanup(db, [a, b])


# --------------------------------------------------------------------------- #
# backfill — decision.cited_artifact_ids becomes the first population
# --------------------------------------------------------------------------- #
async def test_backfill_cited_artifacts_creates_grounds_and_keeps_field(db_health, db_pool):
    from core.engine.graph.grounding import backfill_cited_artifacts, grounded_in

    async with db_pool.connection() as db:
        x = await _mk_artifact(db)
        y = await _mk_artifact(db)
        r = await db.query(
            "CREATE decision SET title = 'grounds backfill', decision_type = 'direction', "
            "rationale = 'r', product = product:test, cited_artifact_ids = [$x, $y]",
            {"x": x, "y": y},
        )
        did = str(parse_one(r)["id"])
    try:
        n = await backfill_cited_artifacts(pool=db_pool)
        assert n >= 1

        grounds = await grounded_in(did, pool=db_pool)
        ids = {o for g in grounds for o in g.get("objectIds", [])}
        assert {x, y} <= ids

        # idempotent: a second backfill does not duplicate edges
        await backfill_cited_artifacts(pool=db_pool)
        grounds2 = await grounded_in(did, pool=db_pool)
        ids2 = [o for g in grounds2 for o in g.get("objectIds", [])]
        assert sorted(ids2) == sorted({x, y})

        # the deprecated field is retained (readable), not dropped
        async with db_pool.connection() as db:
            row = parse_one(await db.query("SELECT * FROM $d", {"d": parse_record_id(did)}))
        assert set(row.get("cited_artifact_ids") or []) == {x, y}
    finally:
        async with db_pool.connection() as db:
            await _cleanup(db, [did, x, y])


# --------------------------------------------------------------------------- #
# bundled hygiene fix — freshness fields must actually persist
# --------------------------------------------------------------------------- #
async def test_freshness_recompute_all_persists_through_the_real_writer(db_health, db_pool):
    """The bundled fix's real goal: the freshness SCORER's output persists. The
    v136 schema declaration is necessary but NOT sufficient — recompute_all() is
    the actual writer, and it must target the record correctly. v3 refuses a bare
    string as an UPDATE target and returns the error as a result string (not a
    raise), so the write is silently dropped and count is still incremented. This
    test drives the real writer, unlike the schema test below which uses a
    RecordID and so cannot catch a broken writer target."""
    from core.engine.capture.freshness import FreshnessDecay

    async with db_pool.connection() as db:
        iid = str(
            parse_one(
                await db.query(
                    "CREATE insight SET content = 'recompute writer', insight_type = 'pattern', "
                    "tier = 'domain', confidence = 0.5, source_domain = 'grounds-test', product = product:test"
                )
            )["id"]
        )
    try:
        await FreshnessDecay().recompute_all(db_pool, "product:test")
        async with db_pool.connection() as db:
            row = parse_one(await db.query("SELECT freshness_score FROM $r", {"r": parse_record_id(iid)}))
        assert row.get("freshness_score") is not None  # the real writer persisted it
    finally:
        async with db_pool.connection() as db:
            await db.query(f"DELETE {iid}")


async def test_freshness_fields_declared_on_schemafull_insight(db_health, db_pool):
    """v136 declares the four freshness fields (undeclared before, so silently
    dropped on the SCHEMAFULL insight table). option<> types so the ~15.6k legacy
    rows survive. This pins the SCHEMA declaration; the writer path is pinned by
    test_freshness_recompute_all_persists_through_the_real_writer above."""
    async with db_pool.connection() as db:
        r = await db.query(
            "CREATE insight SET content = 'freshness persist', insight_type = 'pattern', "
            "tier = 'domain', confidence = 0.5, source_domain = 'grounds-test', product = product:test"
        )
        iid = str(parse_one(r)["id"])
        try:
            await db.query(
                "UPDATE $id SET freshness_score = 0.73, freshness_last_computed = time::now(), "
                "governed_files = ['a.py', 'b.py'], contradiction_count = 2",
                {"id": parse_record_id(iid)},
            )
            row = parse_one(await db.query("SELECT * FROM $id", {"id": parse_record_id(iid)}))
        finally:
            await db.query(f"DELETE {iid}")

    assert row.get("freshness_score") == 0.73
    assert row.get("freshness_last_computed") is not None
    assert row.get("governed_files") == ["a.py", "b.py"]
    assert row.get("contradiction_count") == 2


# --------------------------------------------------------------------------- #
# write-path repoint — the canvas ledger bridge grounds via the edge
# --------------------------------------------------------------------------- #
async def test_ledger_bridge_writes_grounds_edges(db_health, db_pool, monkeypatch):
    """A canvas decision bridged with cited artifacts writes `grounds` edges (the
    new source of truth) while keeping cited_artifact_ids readable (deprecated)."""
    from core.engine.canvas import ledger_bridge
    from core.engine.graph.grounding import grounded_in

    async def _noop(*a, **k):  # skip the background LLM prediction call
        return None

    monkeypatch.setattr("core.engine.foresight.forecaster.attach_prediction", _noop)

    async with db_pool.connection() as db:
        x = await _mk_artifact(db)
        y = await _mk_artifact(db)

    did = await ledger_bridge.bridge_decision_to_ledger(
        session_id="canvas_session:grounds_test",
        product_id="product:test",
        title="grounds bridge",
        rationale="r",
        cited_artifact_ids=[x, y],
        framework_kind="trade_off_matrix",
    )
    try:
        grounds = await grounded_in(did, pool=db_pool)
        ids = {o for g in grounds for o in g.get("objectIds", [])}
        assert {x, y} <= ids  # bridge wrote grounds edges

        async with db_pool.connection() as db:  # deprecated field still readable
            row = parse_one(await db.query("SELECT * FROM $d", {"d": parse_record_id(did)}))
        assert set(row.get("cited_artifact_ids") or []) == {x, y}
    finally:
        async with db_pool.connection() as db:
            await _cleanup(db, [did, x, y])
