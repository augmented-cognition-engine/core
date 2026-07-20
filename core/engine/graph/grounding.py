# engine/graph/grounding.py
"""The `grounds` edge — ACE's node<->canvas join (the substrate's grounding).

A reasoning node (insight, decision, conflict, product_question, graph_insight,
...) is `grounds`-related to a canvas target (today: canvas_artifact). This
module is the thin engine surface over that edge — pure graph reads/writes, no
LLM, no organ calls:

  ground(node, target)  — create/update the edge, idempotent on (in, out)
  grounded_in(node)     — forward: node -> its canvas targets, shaped as the
                          ProjectableNode.grounding array the projector emits
  grounds_of(object)    — reverse: canvas object -> the reasoning nodes about it,
                          the lookup the metabolism walks when an object changes

The edge (not a field array on the node) exists BECAUSE of grounds_of. SurrealDB
answers both <-grounds<- and ->grounds-> natively, so the reverse question the
re-evaluation loop asks — "which beliefs ground in this changed object?" — is an
indexed lookup, not a full-table scan. That reverse correctness is load-bearing:
a false match would re-derive the WRONG beliefs (11-SUBSTRATE §9.1).

`grounded_in` is the membrane function: nothing else in the engine needs to know
grounding is stored as an edge. Spec:
docs/superpowers/specs/2026-07-14-grounds-edge-design.md
"""

from __future__ import annotations

import logging

from core.engine.core.db import parse_record_id, parse_record_ids, parse_rows

logger = logging.getLogger(__name__)

# Canvas target tables `grounds` may point at. Today only canvas_artifact (v103)
# exists; scratch/discourse/sheet get their tables with the canvas build and are
# added here then (the plane/role enums are already declared ready in v136). A
# target outside this set is a reasoning node — that link is an `edges` relation,
# not a `grounds` one, and ground() raises on it.
CANVAS_TABLES = {"canvas_artifact"}

# Which CanvasGround key a plane projects its target ids under at the membrane.
# artifact/scratch carry a list (objectIds); discourse/sheet carry a single id.
_PLANE_KEY = {
    "artifact": "objectIds",
    "scratch": "objectIds",
    "discourse": "markId",
    "sheet": "sheetId",
}
_SINGLE_TARGET_PLANES = {"discourse", "sheet"}


def _table_of(record_id: str) -> str:
    return record_id.split(":", 1)[0] if ":" in record_id else record_id


def _resolve_pool(pool):
    if pool is None:
        from core.engine.core.db import pool as default_pool

        return default_pool
    return pool


async def _alive_ids(pool, ids: list[str]) -> set[str]:
    """The subset of `ids` whose records still resolve. Used to filter dangling
    edge endpoints — a canvas object (or reasoning node) can be deleted while
    grounds edges still point at it."""
    if not ids:
        return set()
    async with pool.connection() as db:
        rows = parse_rows(await db.query("SELECT id FROM $ids", {"ids": parse_record_ids(ids)}))
    return {str(r["id"]) for r in rows}


async def ground(
    node_id: str,
    target_id: str,
    *,
    plane: str = "artifact",
    role: str = "about",
    primary: bool = False,
    source: str = "engine",
    pool=None,
) -> str | None:
    """Ground a reasoning node in a canvas target. Idempotent on (in, out).

    A second call for the same (node, target) updates plane/role/primary/source
    in place rather than duplicating the edge. Marking `primary` first clears any
    other primary grounding on the same node (at most one primary per node —
    enforced here, not in the schema).

    Raises ValueError if `target_id` is not a known canvas table: a reasoning
    node must not `grounds` into another reasoning node (that is an `edges`
    relation). Returns the edge id, or None if the write did not land.
    """
    target_table = _table_of(target_id)
    if target_table not in CANVAS_TABLES:
        raise ValueError(
            f"grounds target must be a canvas object {sorted(CANVAS_TABLES)}, got "
            f"{target_table!r} ({target_id}) — reasoning-node links are `edges`, not `grounds`"
        )

    pool = _resolve_pool(pool)
    node_rec = parse_record_id(node_id)
    target_rec = parse_record_id(target_id)

    async with pool.connection() as db:
        # Single-primary invariant: clear other primaries on this node first, so
        # the new primary is the only one — even across a re-ground of a sibling.
        if primary:
            await db.query(
                "UPDATE grounds SET primary = false WHERE in = $n AND out != $o",
                {"n": node_rec, "o": target_rec},
            )

        existing = parse_rows(
            await db.query(
                "SELECT id FROM grounds WHERE in = $n AND out = $o LIMIT 1",
                {"n": node_rec, "o": target_rec},
            )
        )
        if existing:
            edge_id = str(existing[0]["id"])
            await db.query(
                "UPDATE $eid SET plane = $plane, role = $role, primary = $primary, source = $source",
                {
                    "eid": parse_record_id(edge_id),
                    "plane": plane,
                    "role": role,
                    "primary": primary,
                    "source": source,
                },
            )
            return edge_id

        # RELATE endpoints MUST be bound RecordID objects with no <record> cast —
        # v3 rejects `RELATE <record>$x` (parse error) and won't coerce strings,
        # so a cast/string endpoint silently no-ops the edge (see edge_writer.py).
        created = parse_rows(
            await db.query(
                "RELATE $n -> grounds -> $o SET plane = $plane, role = $role, "
                "primary = $primary, source = $source, created_at = time::now()",
                {
                    "n": node_rec,
                    "o": target_rec,
                    "plane": plane,
                    "role": role,
                    "primary": primary,
                    "source": source,
                },
            )
        )
        return str(created[0]["id"]) if created else None


async def grounded_in(node_id: str, *, pool=None) -> list[dict]:
    """Forward: the node's canvas targets, shaped as the ProjectableNode.grounding
    array the projector emits.

    Groups edges by plane; within a plane, primary targets sort first so the
    projector can anchor on objectIds[0]. Filters targets that no longer resolve
    (a dangling grounding degrades to its spatial ghost — the node is NEVER
    dropped for losing its ground). Returns [] for an ungrounded node; the
    ungrounded and dangling cases never raise (a genuine DB/connection error
    still propagates — the projector must not render a readable-but-unreachable
    graph as "no grounding", which silently drops the anchor).
    """
    pool = _resolve_pool(pool)
    node_rec = parse_record_id(node_id)
    async with pool.connection() as db:
        edges = parse_rows(
            await db.query(
                "SELECT out, plane, primary FROM grounds WHERE in = $n",
                {"n": node_rec},
            )
        )
    if not edges:
        return []

    alive = await _alive_ids(pool, [str(e["out"]) for e in edges])

    # primary first, so the projector's anchor is objectIds[0].
    by_plane: dict[str, list[str]] = {}
    for e in sorted(edges, key=lambda e: not e.get("primary")):
        oid = str(e["out"])
        if oid not in alive:
            continue  # dangling target — omit; the node itself survives
        ids = by_plane.setdefault(e.get("plane") or "artifact", [])
        if oid not in ids:
            ids.append(oid)

    result: list[dict] = []
    for plane, ids in by_plane.items():
        if plane in _SINGLE_TARGET_PLANES:
            result.append({"plane": plane, _PLANE_KEY[plane]: ids[0]})
        else:
            result.append({"plane": plane, "objectIds": ids})
    return result


async def grounds_of(object_id: str, *, pool=None) -> list[str]:
    """Reverse: the reasoning nodes grounded in a canvas object — the lookup the
    metabolism walks when a grounded object changes, to schedule the beliefs that
    ground there for re-derivation.

    Returns only nodes that still resolve (a deleted reasoning node is not
    surfaced), deduped, and never the nodes grounded in a DIFFERENT object.
    Returns [] if nothing grounds there; the empty and dangling cases never
    raise (a genuine DB/connection error still propagates rather than masquerade
    as "nothing grounds here", which would skip a real re-evaluation).
    """
    pool = _resolve_pool(pool)
    obj_rec = parse_record_id(object_id)
    async with pool.connection() as db:
        edges = parse_rows(await db.query("SELECT in FROM grounds WHERE out = $o", {"o": obj_rec}))
    if not edges:
        return []

    seen: set[str] = set()
    in_ids: list[str] = []
    for e in edges:
        nid = str(e["in"])
        if nid not in seen:
            seen.add(nid)
            in_ids.append(nid)

    alive = await _alive_ids(pool, in_ids)
    return [i for i in in_ids if i in alive]


async def backfill_cited_artifacts(*, pool=None) -> int:
    """Generalize the crude decision-only citation into `grounds`.

    For every decision with a non-empty cited_artifact_ids, create
    decision -grounds-> canvas_artifact edges (role='about', source='migration').
    Idempotent via ground() (re-running refreshes, never duplicates). The
    cited_artifact_ids field is left in place — deprecated, derive from the edge.

    Returns the number of grounds edges created or refreshed. Skips (and logs)
    any citation whose id is not a known canvas table, so a stray non-artifact
    id in the legacy array never aborts the backfill.
    """
    pool = _resolve_pool(pool)
    async with pool.connection() as db:
        rows = parse_rows(
            await db.query("SELECT id, cited_artifact_ids FROM decision WHERE cited_artifact_ids != NONE")
        )

    grounded = 0
    for row in rows:
        did = str(row["id"])
        for aid in row.get("cited_artifact_ids") or []:
            aid = str(aid)
            if _table_of(aid) not in CANVAS_TABLES:
                logger.debug("backfill_cited_artifacts: skipping non-canvas citation %s on %s", aid, did)
                continue
            try:
                if await ground(did, aid, role="about", source="migration", pool=pool):
                    grounded += 1
            except ValueError:
                continue
    return grounded
