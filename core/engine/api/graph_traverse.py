# engine/api/graph_traverse.py
"""Unified graph traversal API — query the knowledge graph from any starting node."""

import logging
from typing import Literal

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel, ValidationError, field_validator

from core.engine.code_intelligence.impact import (
    IMPACT_MAX_PATH_CHARS,
    IMPACT_MAX_REF_CHARS,
    ImpactSelectorRejected,
    bound_fetched_rows,
    capability_query,
    cochange_query,
    function_query,
    impact_payload,
    importer_query,
    merge_cochange_directions,
    project_code_impact,
    validate_impact_selector,
)
from core.engine.core.auth import get_current_user
from core.engine.core.db import parse_one, parse_rows, pool, serialize_record

logger = logging.getLogger(__name__)

router = APIRouter(tags=["graph-traverse"])

# ---------------------------------------------------------------------------
# Schema constants — the 12 node tables and 15 edge tables from v031
# ---------------------------------------------------------------------------

NODE_TYPES = {
    "graph_file",
    "graph_function",
    "graph_decision",
    "graph_insight",
    "graph_task",
    "graph_initiative",
    "graph_idea",
    "graph_specialty",
    "agent_execution",
    "graph_document",
    "graph_user",
    "graph_config",
}

EDGE_TYPES = {
    "depends_on",
    "imports",
    "tests",
    "implements",
    "informed_by",
    "solves",
    "causes",
    "improves",
    "breaks",
    "reverts",
    "decomposes",
    "assigned_to",
    "produced",
    "related_to",
    "evolved_from",
}


# ---------------------------------------------------------------------------
# Request / Response models
# ---------------------------------------------------------------------------


class TraverseRequest(BaseModel):
    start: str  # node ID: "graph_file:engine_core_db_py"
    depth: int = 1  # how many hops (1-3, capped)
    edge_types: list[str] | None = None  # filter: ["imports", "depends_on"]. None = all.
    node_types: list[str] | None = None  # filter: ["graph_file", "graph_decision"]. None = all.
    direction: Literal["out", "in", "both"] = "out"
    graph_id: str = "default"
    limit: int = 50  # max nodes returned

    @field_validator("start")
    @classmethod
    def validate_start(cls, v: str) -> str:
        """Ensure start is a valid node ID of the form table_name:record_id.

        Prevents SurrealQL injection via arbitrary string interpolation in
        `SELECT * FROM {body.start}`.
        """
        import re

        if ":" not in v:
            raise ValueError("start must be a valid node ID (table:record_id)")
        table, _, record = v.partition(":")
        if table not in NODE_TYPES:
            raise ValueError(f"Unknown node type '{table}'. Valid: {sorted(NODE_TYPES)}")
        # Real node IDs are `_slug()` output — word characters only. Admitting
        # `.`, `/`, or `-` lets a record ID reach the SurrealQL start-node
        # SELECT unquoted, where a `--` would comment out the graph_id
        # isolation fence; no legitimate node ID needs them.
        if not record or not re.fullmatch(r"\w+", record):
            raise ValueError("record ID contains invalid characters")
        return v

    @field_validator("graph_id")
    @classmethod
    def validate_graph_id(cls, v: str) -> str:
        """Bound the caller-asserted graph_id before it reaches any query.

        `graph_id` is authorized (not merely shaped) by `traverse_graph` itself
        via `_graph_bound_to_product`, but that authorization check assumes a
        non-empty, bounded string to look up — the same bound the rest of the
        Code contract already uses for a graph selector.
        """
        if not isinstance(v, str) or not v or len(v) > IMPACT_MAX_REF_CHARS:
            raise ValueError(f"graph_id must be a non-empty string of at most {IMPACT_MAX_REF_CHARS} characters")
        return v

    @field_validator("depth")
    @classmethod
    def clamp_depth(cls, v: int) -> int:
        return max(1, min(3, v))

    @field_validator("limit")
    @classmethod
    def clamp_limit(cls, v: int) -> int:
        return max(1, min(100, v))

    @field_validator("edge_types")
    @classmethod
    def validate_edge_types(cls, v: list[str] | None) -> list[str] | None:
        if v is not None:
            invalid = [e for e in v if e not in EDGE_TYPES]
            if invalid:
                raise ValueError(f"Invalid edge types: {invalid}. Valid: {sorted(EDGE_TYPES)}")
        return v

    @field_validator("node_types")
    @classmethod
    def validate_node_types(cls, v: list[str] | None) -> list[str] | None:
        if v is not None:
            invalid = [n for n in v if n not in NODE_TYPES]
            if invalid:
                raise ValueError(f"Invalid node types: {invalid}. Valid: {sorted(NODE_TYPES)}")
        return v


class TraverseResponse(BaseModel):
    nodes: list[dict] = []
    edges: list[dict] = []
    start_node: dict | None = None
    stats: dict = {}


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _serialize_node(node: dict) -> dict:
    """Convert a raw SurrealDB row to a JSON-serializable dict."""
    return serialize_record(node)


def _node_type_from_id(node_id: str) -> str:
    """Extract table name from a node ID string like 'graph_file:slug'."""
    if ":" in node_id:
        return node_id.split(":")[0]
    return ""


def _build_hop_query(
    start_id: str,
    edge_types: list[str] | None,
    node_types: list[str] | None,
    direction: str,
    graph_id: str,
) -> tuple[str, dict]:
    """Build a SurrealQL query for one traversal hop.

    Returns (query_string, params).
    """
    edges = edge_types or sorted(EDGE_TYPES)

    # Build sub-queries for each edge type, then UNION them via array::union
    parts = []
    for edge in edges:
        if direction == "out":
            parts.append(f"->{edge}->?")
        elif direction == "in":
            parts.append(f"<-{edge}<-?")

    if direction == "both":
        for edge in edges:
            parts.append(f"->{edge}->?")
            parts.append(f"<-{edge}<-?")

    # Build individual SELECT for each traversal path, union results
    selects = []
    for part in parts:
        selects.append(f"$start{part}")

    query = f"SELECT * FROM array::flatten([{', '.join(selects)}]) WHERE graph_id = $graph_id"

    # Filter by node types if specified
    if node_types:
        type_checks = " OR ".join(f"record::tb(id) = '{nt}'" for nt in node_types)
        query += f" AND ({type_checks})"

    params = {"start": start_id, "graph_id": graph_id}
    return query, params


async def _traverse_one_hop(
    db,
    node_ids: list[str],
    edge_types: list[str] | None,
    node_types: list[str] | None,
    direction: str,
    graph_id: str,
    visited: set[str],
    limit: int,
) -> tuple[list[dict], list[dict]]:
    """Single hop from a set of nodes. Returns (connected_nodes, edges).

    Uses SurrealQL graph traversal syntax.
    """
    edges = edge_types or sorted(EDGE_TYPES)
    all_nodes = []
    all_edges = []

    for node_id in node_ids:
        if len(all_nodes) >= limit:
            break

        # Build traversal queries per edge type
        directions = []
        if direction in ("out", "both"):
            directions.append("out")
        if direction in ("in", "both"):
            directions.append("in")

        for d in directions:
            for edge in edges:
                if len(all_nodes) >= limit:
                    break

                if d == "out":
                    traversal_query = (
                        f"SELECT id, *, record::tb(id) AS _type FROM ({node_id})->{edge}->? WHERE graph_id = $graph_id"
                    )
                else:
                    traversal_query = (
                        f"SELECT id, *, record::tb(id) AS _type FROM ({node_id})<-{edge}<-? WHERE graph_id = $graph_id"
                    )

                # Add node type filter
                if node_types:
                    type_checks = " OR ".join(f"record::tb(id) = '{nt}'" for nt in node_types)
                    traversal_query += f" AND ({type_checks})"

                traversal_query += f" LIMIT {limit}"

                try:
                    result = await db.query(traversal_query, {"graph_id": graph_id})
                    rows = parse_rows(result)

                    for row in rows:
                        row_id = str(serialize_record(row.get("id", "")))
                        if row_id in visited:
                            continue
                        visited.add(row_id)

                        node_data = _serialize_node(row)
                        node_data.setdefault("_type", _node_type_from_id(row_id))
                        all_nodes.append(node_data)

                        # Build edge record
                        if d == "out":
                            edge_record = {
                                "from": node_id,
                                "to": row_id,
                                "type": edge,
                            }
                        else:
                            edge_record = {
                                "from": row_id,
                                "to": node_id,
                                "type": edge,
                            }
                        all_edges.append(edge_record)

                        if len(all_nodes) >= limit:
                            break
                except Exception as exc:
                    logger.debug("Hop query failed for %s via %s: %s", node_id, edge, exc)
                    continue

    return all_nodes, all_edges


# ---------------------------------------------------------------------------
# Main traversal endpoint
# ---------------------------------------------------------------------------


@router.post("/graph/traverse", response_model=TraverseResponse)
async def traverse_graph(body: TraverseRequest, user: dict = Depends(get_current_user)):
    """Traverse the knowledge graph from a starting node.

    Builds a subgraph by expanding from the start node through connected edges,
    up to the requested depth. Returns all discovered nodes and edges.

    `graph_id` is a caller assertion, exactly like it is on every shortcut that
    builds a request for this function. Every node table in this schema is
    partitioned by `graph_id` alone, so this is the one shared boundary that
    protects a direct `POST /graph/traverse` and every shortcut built on top of
    it (`get_impact`, `get_history`, `get_related`) — not just the endpoints
    that happened to add their own check. Before any node or edge of the named
    graph is read: the authenticated principal must carry a product binding,
    and the requested graph must be bound to that product through the same
    `graph` record the capability mapper's product→graph lookup already uses.
    An unknown or cross-product graph is refused with a non-confirming 404,
    before the start node — or any hop — is ever read. The start-node read
    itself is also scoped to the authorized graph: a record whose ID matches
    but whose actual `graph_id` names a different (e.g. competitor) graph is
    never returned, closing the crosswire where a caller authorized for one
    graph could otherwise reach a same-named record living in another.
    """
    product_ref = _bound_product_to_principal("", user)

    async with pool.connection() as db:
        graph_id = await _graph_bound_to_product(db, body.graph_id, product_ref)

        # Step 1: Fetch the start node, scoped to the authorized graph — a
        # record whose ID matches `body.start` but whose own `graph_id` names
        # a different graph must not be returned.
        start_result = await db.query(
            f"SELECT * FROM {body.start} WHERE graph_id = $graph_id",
            {"graph_id": graph_id},
        )
        start_row = parse_one(start_result)

        if not start_row:
            return TraverseResponse(
                nodes=[],
                edges=[],
                start_node=None,
                stats={"node_count": 0, "edge_count": 0, "depth_reached": 0},
            )

        start_node = _serialize_node(start_row)
        start_id = body.start

        # Track visited nodes to avoid cycles
        visited: set[str] = {start_id}
        all_nodes: list[dict] = []
        all_edges: list[dict] = []

        # Step 2: BFS — expand depth levels
        frontier = [start_id]
        depth_reached = 0

        for hop in range(body.depth):
            if not frontier:
                break
            if len(all_nodes) >= body.limit:
                break

            remaining = body.limit - len(all_nodes)
            new_nodes, new_edges = await _traverse_one_hop(
                db,
                frontier,
                body.edge_types,
                body.node_types,
                body.direction,
                graph_id,
                visited,
                remaining,
            )

            all_nodes.extend(new_nodes)
            all_edges.extend(new_edges)
            depth_reached = hop + 1

            # Next frontier: the newly discovered node IDs
            frontier = []
            for n in new_nodes:
                nid = n.get("id", "")
                if isinstance(nid, str) and ":" in nid:
                    frontier.append(nid)

        return TraverseResponse(
            nodes=all_nodes,
            edges=all_edges,
            start_node=start_node,
            stats={
                "node_count": len(all_nodes),
                "edge_count": len(all_edges),
                "depth_reached": depth_reached,
            },
        )


# ---------------------------------------------------------------------------
# Shortcut endpoints
# ---------------------------------------------------------------------------


@router.get("/graph/impact/{node_id:path}", response_model=TraverseResponse)
async def get_impact(
    node_id: str,
    graph_id: str = Query("default"),
    user: dict = Depends(get_current_user),
):
    """What does changing this node affect?

    Traverses depends_on, tests, breaks edges inward (who depends on me?)
    plus improves edges outward (what did changes to me improve?).

    `graph_id` is a caller assertion exactly like it is on
    `/graph/impact-by-path`, and `traverse_graph` now authorizes it at the
    shared traversal boundary before any node or edge of that graph is read:
    the authenticated principal must carry a product binding, and the
    requested graph must be bound to that product through the same `graph`
    record the capability mapper's product→graph lookup already uses. An
    unknown or cross-product graph is refused with a non-confirming 404,
    before the start node — or any hop — is ever read.

    This endpoint still bounds `node_id` and `graph_id` to the shared Code
    contract's limits, and still refuses a principal with no product binding,
    before `traverse_graph` is ever called — both selectors and the product
    check are input validation this endpoint owns regardless of which layer
    performs the graph↔product authorization. The mapping lookup itself is
    not repeated here: `traverse_graph`'s is the first database query this
    endpoint's call chain issues.
    """
    node_id = _admit_impact_selector(node_id, "node_id", IMPACT_MAX_PATH_CHARS)
    graph_id = _admit_impact_selector(graph_id, "graph_id", IMPACT_MAX_REF_CHARS)
    _bound_product_to_principal("", user)

    body = _admitted_traverse_request(
        start=node_id,
        depth=2,
        edge_types=["depends_on", "tests", "breaks", "imports"],
        direction="in",
        graph_id=graph_id,
        limit=50,
    )
    return await traverse_graph(body, user)


def _bound_product_to_principal(requested: str, user: dict) -> str:
    """Resolve the product this request may read, from the authenticated principal.

    The `product` query parameter is a caller *assertion*, never an authorization.
    Capability rows are product-scoped, so a request that names a product other
    than the principal's own would be arbitrary cross-product read access. The
    principal's claim wins; a mismatch is refused, and a principal with no
    product binding has no product to read and is refused too.
    """
    principal_product = str(user.get("product") or "")
    if not principal_product:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Authenticated principal has no product binding",
        )
    if requested and requested != principal_product:
        # 404, not 403 — matching `verify_ownership`, so a refusal never
        # confirms that some other product's capability exists.
        raise HTTPException(status_code=404, detail="Not found")
    return principal_product


_TRAVERSE_FIELD_DETAIL = {
    "start": "node_id must be a valid node reference of the form table:record_id",
    "graph_id": "graph_id must be a non-empty, bounded graph identifier",
}


def _admitted_traverse_request(**kwargs) -> TraverseRequest:
    """Build a TraverseRequest from caller-supplied selectors.

    The shortcut endpoints construct the request themselves, so `TraverseRequest`
    validation failures there are caller errors, not server faults — refused with
    422, never surfaced as a 500. The refusal names the field that actually
    failed (node_id or graph_id), without echoing the value.
    """
    try:
        return TraverseRequest(**kwargs)
    except ValidationError as exc:
        loc = exc.errors()[0].get("loc") if exc.errors() else ()
        field = loc[0] if loc else ""
        detail = _TRAVERSE_FIELD_DETAIL.get(field, "request contains an invalid node_id or graph_id selector")
        raise HTTPException(status_code=422, detail=detail) from exc


def _admit_impact_selector(value: str, field: str, limit: int, *, allow_empty: bool = False) -> str:
    """Bound one caller-supplied selector before a connection is ever opened.

    FastAPI already enforces these lengths for an HTTP request, but this
    endpoint is also called directly, and the bound that matters is the shared
    Code contract's — not whatever a route signature happens to repeat. The
    refusal names the field and its limit and never echoes the value.
    """

    try:
        return validate_impact_selector(value, field=field, limit=limit, allow_empty=allow_empty)
    except ImpactSelectorRejected as exc:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_CONTENT, detail=str(exc)) from exc


async def _graph_bound_to_product(db, graph_id: str, product_ref: str) -> str:
    """Resolve the requested graph only if it is bound to the principal's product.

    `graph_id` is a caller *assertion* exactly like `product` is. Every node
    table in this schema is partitioned by `graph_id` alone, so a request that
    names another product's graph and passes only the product fence would read
    that graph's files, imports, functions, and co-change edges in full — the
    product fence would still be intact, and entirely beside the point.

    The binding is the one this repository already keeps: a `graph` record
    carries its `graph_id` and a `product` record link, written when a product
    is initialised and read the same way by the capability mapper's
    product→graph lookup. This asks that mapping directly, for this product
    only, and there is no rule anywhere that makes a graph readable by every
    product — an unmapped graph is refused like any other.

    A graph that is unknown, unmapped, or mapped elsewhere is refused with 404
    like `verify_ownership`, so the refusal never distinguishes "no such graph"
    from "someone else's graph", and it is raised before any graph_file,
    import, function, or co-change row is read.
    """

    result = await db.query(
        "SELECT graph_id FROM graph WHERE graph_id = $gid AND product = <record>$product LIMIT 1",
        {"gid": graph_id, "product": product_ref},
    )
    row = parse_one(result)
    if not row or str(serialize_record(row.get("graph_id", ""))) != graph_id:
        raise HTTPException(status_code=404, detail="Not found")
    return graph_id


@router.get("/graph/impact-by-path")
async def impact_by_path(
    path: str = Query(
        ...,
        description="File path like 'engine/core/auth.py'",
        min_length=1,
        max_length=IMPACT_MAX_PATH_CHARS,
    ),
    graph_id: str = Query("default", min_length=1, max_length=IMPACT_MAX_REF_CHARS),
    product: str = Query(
        "product:platform",
        description="Product record id (e.g. product:platform); must match the authenticated principal",
        max_length=IMPACT_MAX_REF_CHARS,
    ),
    user: dict = Depends(get_current_user),
):
    """Bounded observed dependent graph for one file path, within one product.

    Accepts a file path (not a node ID). Returns the files observed to import
    it, the functions it is observed to define, its recorded co-change
    partners, and the capabilities of the authenticated principal's product
    that declare it.

    This does not assess what breaks, how fragile the file is, or whether it is
    safe to delete — every collection is a bounded traversal of one graph
    revision, and each one discloses its own truncation.
    """
    # Shape first, then authorization: an unusable selector is refused before a
    # connection is opened, and neither refusal echoes what the caller sent.
    path = _admit_impact_selector(path, "path", IMPACT_MAX_PATH_CHARS)
    graph_id = _admit_impact_selector(graph_id, "graph_id", IMPACT_MAX_REF_CHARS)
    product = _admit_impact_selector(product, "product", IMPACT_MAX_REF_CHARS, allow_empty=True)
    product_ref = _bound_product_to_principal(product, user)

    async with pool.connection() as db:
        # The requested graph must be bound to this principal's product before
        # anything in it is read — including the graph_file lookup below, which
        # is itself a read of the named graph. The compatibility default graph
        # is not exempt; it passes this same check or it is refused.
        graph_id = await _graph_bound_to_product(db, graph_id, product_ref)

        # Resolve path to node ID
        file_result = await db.query(
            "SELECT id, path, name, language, change_frequency FROM graph_file WHERE path = $path AND graph_id = $gid LIMIT 1",
            {"path": path, "gid": graph_id},
        )
        file_node = parse_one(file_result)
        if not file_node:
            return {"error": f"File '{path}' not found in graph", "importers": [], "dependents": [], "tests": []}

        file_id = str(serialize_record(file_node["id"]))

        # Every query below is bounded at `LIMIT bound + 1` by the shared Code
        # contract, so no branch of this endpoint can serialize an unbounded
        # number of database rows.
        import_result = await db.query(importer_query(file_id), {"gid": graph_id})
        importer_rows = bound_fetched_rows([_serialize_node(r) for r in parse_rows(import_result)], "importers")

        func_result = await db.query(function_query(file_id), {"gid": graph_id})
        function_rows = bound_fetched_rows([_serialize_node(r) for r in parse_rows(func_result)], "functions")

        # Co-change partners (files recorded as changing alongside this one).
        # Each direction is its own bound+1 query, so their concatenation can
        # be up to twice that — merged, deduped by partner identity, and
        # re-bounded to one row past the bound before the strict central
        # projection ever sees it.
        cochange_out = await db.query(cochange_query(file_id, "out"), {"gid": graph_id})
        cochange_in = await db.query(cochange_query(file_id, "in"), {"gid": graph_id})
        cochange_rows = merge_cochange_directions(
            [_serialize_node(r) for r in parse_rows(cochange_out)],
            [_serialize_node(r) for r in parse_rows(cochange_in)],
        )

        # What capability does this file belong to?
        # decision:zlinw5b2kx09j8k2s00l — schema rename residue. The prior query
        # filtered `org = <record>"org:platform"` which (a) used a stale "org:" prefix
        # that doesn't match any product record, and (b) targeted the `org` field
        # whose data was migrated to `product` in v054. Smoke-verified: the old
        # shape returned 0 rows for any file; the new shape returns the matching
        # capability rows correctly. The product is the principal's own, resolved
        # above — it is never taken from the query string unchecked.
        cap_result = await db.query(capability_query(), {"path": path, "product": product_ref})
        capability_rows = bound_fetched_rows([_serialize_node(r) for r in parse_rows(cap_result)], "capabilities")

    observation = project_code_impact(
        graph_id=graph_id,
        product_ref=product_ref,
        target_path=path,
        target_node_id=file_id,
        importer_rows=importer_rows,
        function_rows=function_rows,
        cochange_rows=cochange_rows,
        capability_rows=capability_rows,
        cochange_observed=True,
    )
    # `file` stays the serialized start node this endpoint has always returned.
    return {"file": _serialize_node(file_node), **impact_payload(observation)}


@router.get("/graph/history/{node_id:path}", response_model=TraverseResponse)
async def get_history(
    node_id: str,
    graph_id: str = Query("default"),
    user: dict = Depends(get_current_user),
):
    """Why was this node created or changed?

    Traverses informed_by, produced, improves edges in both directions.
    """
    body = _admitted_traverse_request(
        start=node_id,
        depth=2,
        edge_types=["informed_by", "produced", "improves"],
        direction="both",
        graph_id=graph_id,
        limit=50,
    )
    return await traverse_graph(body, user)


@router.get("/graph/related/{node_id:path}", response_model=TraverseResponse)
async def get_related(
    node_id: str,
    graph_id: str = Query("default"),
    user: dict = Depends(get_current_user),
):
    """What is connected to this node? All edge types, depth 1."""
    body = _admitted_traverse_request(
        start=node_id,
        depth=1,
        edge_types=None,  # all edges
        direction="both",
        graph_id=graph_id,
        limit=50,
    )
    return await traverse_graph(body, user)


# ---------------------------------------------------------------------------
# Stats endpoint
# ---------------------------------------------------------------------------


# Real table counterparts for shadow tables (Phase 2 migration)
_REAL_TABLE_MAP = {
    "graph_insight": "insight",
    "graph_task": "task",
    "graph_initiative": "initiative",
    "graph_idea": "idea",
    "graph_specialty": "specialty",
    "graph_agent": "agent_execution",
    "graph_document": "document",
    "graph_user": "user",
}


@router.get("/graph/stats")
async def graph_stats(
    graph_id: str = Query("default"),
    user: dict = Depends(get_current_user),
):
    """Return graph statistics: node counts per type, edge counts per type, top connected nodes."""
    async with pool.connection() as db:
        # Count nodes per type (read from real tables where available)
        node_counts = {}
        for nt in sorted(NODE_TYPES):
            table = _REAL_TABLE_MAP.get(nt, nt)
            result = await db.query(
                f"SELECT count() AS count FROM {table} WHERE graph_id = $gid GROUP ALL",
                {"gid": graph_id},
            )
            row = parse_one(result)
            node_counts[nt] = row.get("count", 0) if row else 0

        # Count edges per type
        edge_counts = {}
        for et in sorted(EDGE_TYPES):
            result = await db.query(
                f"SELECT count() AS count FROM {et} GROUP ALL",
            )
            row = parse_one(result)
            edge_counts[et] = row.get("count", 0) if row else 0

        total_nodes = sum(node_counts.values())
        total_edges = sum(edge_counts.values())

        # Top connected nodes by change_frequency (proxy for connectivity)
        top_result = await db.query(
            """
            SELECT id, path, name, change_frequency
            FROM graph_file
            WHERE graph_id = $gid
            ORDER BY change_frequency DESC
            LIMIT 10
            """,
            {"gid": graph_id},
        )
        top_nodes = [_serialize_node(r) for r in parse_rows(top_result)]

    return {
        "graph_id": graph_id,
        "nodes": node_counts,
        "edges": edge_counts,
        "total_nodes": total_nodes,
        "total_edges": total_edges,
        "top_connected": top_nodes,
    }


# ---------------------------------------------------------------------------
# Top files endpoint — initial graph view
# ---------------------------------------------------------------------------


@router.get("/graph/top-files")
async def top_files(
    graph_id: str = Query("default"),
    limit: int = Query(30, ge=1, le=100),
    user: dict = Depends(get_current_user),
):
    """Return the most important files with their import connections.

    Used by the code graph explorer to build the initial view.
    Returns top files by change_frequency and all import edges between them.
    """
    async with pool.connection() as db:
        # Fetch top files
        file_result = await db.query(
            """
            SELECT id, path, name, change_frequency, language
            FROM graph_file
            WHERE graph_id = $gid
            ORDER BY change_frequency DESC
            LIMIT $lim
            """,
            {"gid": graph_id, "lim": limit},
        )
        files = [_serialize_node(r) for r in parse_rows(file_result)]
        file_ids = {f["id"] for f in files}

        # Fetch functions for each file (aggregated count + list)
        func_counts: dict[str, list[dict]] = {}
        for f in files:
            fid = f["id"]
            func_result = await db.query(
                f"SELECT id, name FROM ({fid})->depends_on->graph_function WHERE graph_id = $gid LIMIT 50",
                {"gid": graph_id},
            )
            funcs = [_serialize_node(r) for r in parse_rows(func_result)]
            if funcs:
                func_counts[fid] = funcs

        # Fetch import edges between these top files
        edges = []
        for f in files:
            fid = f["id"]
            # Outgoing imports
            import_result = await db.query(
                f"SELECT id, *, record::tb(id) AS _type FROM ({fid})->imports->graph_file WHERE graph_id = $gid",
                {"gid": graph_id},
            )
            for row in parse_rows(import_result):
                target = _serialize_node(row)
                target_id = target.get("id", "")
                if target_id in file_ids:
                    edges.append({"from": fid, "to": target_id, "type": "imports"})

            # Incoming imports
            import_in_result = await db.query(
                f"SELECT id, *, record::tb(id) AS _type FROM ({fid})<-imports<-graph_file WHERE graph_id = $gid",
                {"gid": graph_id},
            )
            for row in parse_rows(import_in_result):
                source = _serialize_node(row)
                source_id = source.get("id", "")
                if source_id in file_ids:
                    edges.append({"from": source_id, "to": fid, "type": "imports"})

        # Deduplicate edges
        seen_edges = set()
        unique_edges = []
        for e in edges:
            key = f"{e['from']}->{e['to']}"
            if key not in seen_edges:
                seen_edges.add(key)
                unique_edges.append(e)

        # Attach function counts to files
        for f in files:
            fid = f["id"]
            funcs = func_counts.get(fid, [])
            f["functions"] = funcs
            f["function_count"] = len(funcs)
            f["import_count"] = sum(1 for e in unique_edges if e["to"] == fid)

    return {
        "files": files,
        "edges": unique_edges,
        "total": len(files),
    }
