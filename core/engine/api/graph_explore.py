# engine/api/graph_explore.py
"""Graph explorer API — overview, node expansion, and Mermaid diagram endpoints."""

from __future__ import annotations

import logging
import re

from fastapi import APIRouter, Depends, HTTPException

from core.engine.core.auth import get_current_user
from core.engine.core.db import parse_one, parse_rows, pool, serialize_record

logger = logging.getLogger(__name__)

router = APIRouter(tags=["graph-explore"])

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

_LAYER_MAP = {
    "graph_file": "code",
    "graph_function": "code",
    "graph_decision": "code",
    "capability": "product",
    "capability_quality": "product",
    "insight": "product",
    "decision": "product",
    "product_vision": "product",
    "idea": "work",
    "initiative": "work",
    "milestone": "work",
    "work_item": "work",
    "task": "work",
    "agent_spec": "work",
    "agent_session": "live",
    "active_edit": "live",
}

_EDGE_TABLES = [
    "inspired_by",
    "became",
    "specified_by",
    "fulfills",
    "led_to",
    "affected",
    "derived_from",
    "supersedes",
    "loaded",
    "quality_delta",
    "targets",
    "blocked_by",
    "realizes",
    "depends_on",
    "improves",
]


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _node_layer(node_id: str) -> str:
    """Return the layer for a node based on its table prefix."""
    table = node_id.split(":")[0] if ":" in node_id else ""
    return _LAYER_MAP.get(table, "unknown")


def _serialize(row: dict) -> dict:
    """Serialize a raw SurrealDB row to a JSON-safe dict."""
    data = serialize_record(row)
    node_id = data.get("id", "")
    if isinstance(node_id, str):
        data.setdefault("layer", _node_layer(node_id))
        # Derive a label from name/title/slug for frontend display
        if "label" not in data:
            data["label"] = (
                data.get("name")
                or data.get("title")
                or data.get("slug")
                or (node_id.split(":")[-1] if ":" in node_id else node_id)
            )
        # Set node type from table prefix
        if "type" not in data:
            table = node_id.split(":")[0] if ":" in node_id else ""
            if table:
                data["type"] = table
    return data


def _serialize_edge(row: dict, table: str) -> dict:
    """Serialize a SurrealDB edge row, mapping in/out → from/to and _table → type."""
    data = serialize_record(row)
    from_id = str(data.pop("in", ""))
    to_id = str(data.pop("out", ""))
    data["from"] = from_id
    data["to"] = to_id
    data["type"] = table
    return data


def _edge_key(edge: dict) -> str:
    return f"{edge.get('from', edge.get('in', ''))}|{edge.get('to', edge.get('out', ''))}|{edge.get('type', edge.get('_table', ''))}"


def _node_key(node: dict) -> str:
    return str(node.get("id", ""))


# ---------------------------------------------------------------------------
# GET /graph/overview
# ---------------------------------------------------------------------------


@router.get("/graph/overview")
async def graph_overview(user: dict = Depends(get_current_user)):
    """Initial graph load: top 20 capabilities + connected files + active initiatives + live sessions.

    Returns a deduplicated set of nodes and edges, capped at 200 nodes.
    """
    product_id = user.get("product", "")

    nodes: list[dict] = []
    edges: list[dict] = []
    seen_nodes: set[str] = set()
    seen_edges: set[str] = set()

    def _add_node(row: dict) -> None:
        data = _serialize(row)
        key = _node_key(data)
        if key and key not in seen_nodes:
            seen_nodes.add(key)
            nodes.append(data)

    def _add_edge(row: dict, table: str) -> None:
        data = _serialize_edge(row, table)
        key = _edge_key(data)
        if key not in seen_edges:
            seen_edges.add(key)
            edges.append(data)

    async with pool.connection() as db:
        # 1. Top 20 capabilities
        cap_result = await db.query(
            "SELECT * FROM capability WHERE product = <record>$product AND status != 'deprecated' ORDER BY priority LIMIT 20",
            {"product": product_id},
        )
        for row in parse_rows(cap_result):
            _add_node(row)

        # 2. Files linked via realizes edges
        realizes_result = await db.query(
            {"product": product_id},
        )
        for row in parse_rows(realizes_result):
            edge_data = _serialize_edge(row, "realizes")
            key = _edge_key(edge_data)
            if key not in seen_edges:
                seen_edges.add(key)
                edges.append(edge_data)
            # Collect the file nodes referenced by these edges
            out_id = edge_data.get("to", "")
            if out_id and out_id not in seen_nodes and len(nodes) < 200:
                try:
                    file_result = await db.query(
                        "SELECT * FROM <record>$id",
                        {"id": str(out_id)},
                    )
                    file_row = parse_one(file_result)
                    if file_row:
                        _add_node(file_row)
                except Exception as exc:
                    logger.debug("Could not fetch file node %s: %s", out_id, exc)

        # 3. Active initiatives
        init_result = await db.query(
            "SELECT * FROM initiative WHERE product = <record>$product AND status IN ['active', 'ready', 'decomposing', 'review'] LIMIT 10",
            {"product": product_id},
        )
        for row in parse_rows(init_result):
            _add_node(row)

        # 4. Active sessions
        session_result = await db.query(
            "SELECT * FROM agent_session WHERE product = <record>$product AND state IN ['starting', 'active', 'blocked'] LIMIT 10",
            {"product": product_id},
        )
        for row in parse_rows(session_result):
            _add_node(row)

    # Cap at 200 nodes
    nodes = nodes[:200]

    return {
        "nodes": nodes,
        "edges": edges,
        "node_count": len(nodes),
        "edge_count": len(edges),
    }


# ---------------------------------------------------------------------------
# GET /graph/explore/{node_id:path}
# ---------------------------------------------------------------------------


_NODE_ID_RE = re.compile(r"^[a-zA-Z0-9_]+:[a-zA-Z0-9_\-]+$")


@router.get("/graph/explore/{node_id:path}")
async def explore_node(node_id: str, user: dict = Depends(get_current_user)):
    """Expand a node: return node + all connected edges + connected nodes (depth 1).

    Scans all 15 edge tables for connections to the given node.
    """
    if not _NODE_ID_RE.match(node_id):
        raise HTTPException(status_code=400, detail="Invalid node_id format. Expected 'table:id'.")
    async with pool.connection() as db:
        # 1. Fetch the node itself
        node_result = await db.query(
            "SELECT * FROM <record>$id",
            {"id": node_id},
        )
        node_row = parse_one(node_result)
        if not node_row:
            raise HTTPException(status_code=404, detail=f"Node '{node_id}' not found")

        node = _serialize(node_row)

        # 2. Scan each edge table for connections
        edges: list[dict] = []
        connected_ids: set[str] = set()
        seen_edges: set[str] = set()

        for table in _EDGE_TABLES:
            try:
                edge_result = await db.query(
                    f"SELECT * FROM {table} WHERE in = <record>$id OR out = <record>$id LIMIT 50",
                    {"id": node_id},
                )
                for row in parse_rows(edge_result):
                    data = _serialize_edge(row, table)
                    key = _edge_key(data)
                    if key not in seen_edges:
                        seen_edges.add(key)
                        edges.append(data)

                    # Collect connected node IDs (both from and to)
                    for cid in (data["from"], data["to"]):
                        if cid and cid != node_id and cid != "None":
                            connected_ids.add(cid)
            except Exception as exc:
                logger.debug("Edge query failed for table %s on node %s: %s", table, node_id, exc)

        # 3. Fetch up to 50 connected nodes
        connected: list[dict] = []
        for cid in list(connected_ids)[:50]:
            try:
                c_result = await db.query(
                    "SELECT * FROM <record>$id",
                    {"id": cid},
                )
                c_row = parse_one(c_result)
                if c_row:
                    connected.append(_serialize(c_row))
            except Exception as exc:
                logger.debug("Could not fetch connected node %s: %s", cid, exc)

    return {
        "node": node,
        "edges": edges,
        "connected": connected,
    }


# ---------------------------------------------------------------------------
# GET /graph/diagram/{query_type}/{node_id:path}
# ---------------------------------------------------------------------------

_VALID_DIAGRAM_TYPES = {"capability_architecture", "decision_tree", "initiative_flow"}


@router.get("/graph/diagram/{query_type}/{node_id:path}")
async def graph_diagram(
    query_type: str,
    node_id: str,
    user: dict = Depends(get_current_user),
):
    """Generate a Mermaid diagram from graph traversal.

    query_type options:
    - capability_architecture: capability → files (realizes) + quality gaps
    - decision_tree: decision → led_to + supersedes
    - initiative_flow: initiative ← became (from idea) + quality_delta
    """
    if query_type not in _VALID_DIAGRAM_TYPES:
        raise HTTPException(
            status_code=400,
            detail=f"Invalid query_type '{query_type}'. Valid: {sorted(_VALID_DIAGRAM_TYPES)}",
        )
    if not _NODE_ID_RE.match(node_id):
        raise HTTPException(status_code=400, detail="Invalid node_id format. Expected 'table:id'.")

    # Map query_type → table name for slug lookups
    _TABLE_MAP = {
        "capability_architecture": "capability",
        "decision_tree": "decision",
        "initiative_flow": "initiative",
    }

    async with pool.connection() as db:
        root_row = None

        # If node_id is a bare slug (no ":"), resolve it via the appropriate table
        if ":" not in node_id:
            table = _TABLE_MAP.get(query_type, "")
            if table:
                slug_result = await db.query(
                    f"SELECT * FROM {table} WHERE slug = <string>$slug LIMIT 1",
                    {"slug": node_id},
                )
                root_row = parse_one(slug_result)
                if root_row:
                    # Update node_id to the real record ID for edge queries
                    real_id = serialize_record(root_row.get("id", ""))
                    node_id = str(real_id) if real_id else node_id

        # Fallback: direct record ID lookup
        if not root_row:
            root_result = await db.query(
                "SELECT * FROM <record>$id",
                {"id": node_id},
            )
            root_row = parse_one(root_result)

        if not root_row:
            raise HTTPException(status_code=404, detail=f"Node '{node_id}' not found")

        root = _serialize(root_row)

        if query_type == "capability_architecture":
            return await _diagram_capability_architecture(db, root, node_id)
        elif query_type == "decision_tree":
            return await _diagram_decision_tree(db, root, node_id)
        else:  # initiative_flow
            return await _diagram_initiative_flow(db, root, node_id)


# ---------------------------------------------------------------------------
# Diagram builders
# ---------------------------------------------------------------------------


def _safe_label(node: dict, fallback: str = "") -> str:
    """Return a Mermaid-safe label for a node."""
    label = node.get("name") or node.get("title") or node.get("slug") or fallback
    # Escape double-quotes and square brackets that break Mermaid
    return str(label).replace('"', "'").replace("[", "(").replace("]", ")")


def _mermaid_id(node_id: str) -> str:
    """Convert a SurrealDB record ID to a valid Mermaid node ID."""
    return node_id.replace(":", "_").replace("-", "_").replace("/", "_").replace(".", "_")


async def _diagram_capability_architecture(db, root: dict, node_id: str) -> dict:
    """Capability → files via realizes + quality gaps."""
    lines = ["flowchart TD"]
    root_mid = _mermaid_id(node_id)
    root_label = _safe_label(root, node_id)
    lines.append(f'    {root_mid}["{root_label}"]')

    # Fetch realizes edges (capability → files)
    try:
        realizes_result = await db.query(
            "SELECT * FROM realizes WHERE in = <record>$id LIMIT 30",
            {"id": node_id},
        )
        for edge_row in parse_rows(realizes_result):
            out_id = str(serialize_record(edge_row.get("out", "")))
            if not out_id or out_id == "None":
                continue
            try:
                file_result = await db.query("SELECT * FROM <record>$id", {"id": out_id})
                file_row = parse_one(file_result)
                if file_row:
                    file_data = _serialize(file_row)
                    file_mid = _mermaid_id(out_id)
                    file_label = _safe_label(file_data, out_id)
                    lines.append(f'    {file_mid}["{file_label}"]')
                    lines.append(f"    {root_mid} -->|realizes| {file_mid}")
            except Exception as exc:
                logger.debug("Could not fetch realized file %s: %s", out_id, exc)
    except Exception as exc:
        logger.debug("realizes query failed for %s: %s", node_id, exc)

    # Fetch quality gaps (capability_quality nodes)
    try:
        quality_result = await db.query(
            "SELECT * FROM capability_quality WHERE capability = <record>$id LIMIT 10",
            {"id": node_id},
        )
        for qrow in parse_rows(quality_result):
            qdata = _serialize(qrow)
            q_id = str(qdata.get("id", ""))
            if not q_id or q_id == "None":
                continue
            q_mid = _mermaid_id(q_id)
            discipline = qdata.get("discipline", "quality")
            score = qdata.get("score", "?")
            lines.append(f'    {q_mid}(["gap: {discipline} {score}"])')
            lines.append(f"    {root_mid} -.->|quality| {q_mid}")
    except Exception as exc:
        logger.debug("capability_quality query failed for %s: %s", node_id, exc)

    title = f"Architecture: {_safe_label(root, node_id)}"
    return {"mermaid": "\n".join(lines), "title": title}


async def _diagram_decision_tree(db, root: dict, node_id: str) -> dict:
    """Decision → led_to + supersedes."""
    lines = ["flowchart TD"]
    root_mid = _mermaid_id(node_id)
    root_label = _safe_label(root, node_id)
    lines.append(f'    {root_mid}["{root_label}"]')

    # led_to edges (outgoing)
    try:
        led_to_result = await db.query(
            "SELECT * FROM led_to WHERE in = <record>$id LIMIT 20",
            {"id": node_id},
        )
        for edge_row in parse_rows(led_to_result):
            out_id = str(serialize_record(edge_row.get("out", "")))
            if not out_id or out_id == "None":
                continue
            try:
                target_result = await db.query("SELECT * FROM <record>$id", {"id": out_id})
                target_row = parse_one(target_result)
                if target_row:
                    target = _serialize(target_row)
                    t_mid = _mermaid_id(out_id)
                    t_label = _safe_label(target, out_id)
                    lines.append(f'    {t_mid}["{t_label}"]')
                    lines.append(f"    {root_mid} -->|led to| {t_mid}")
            except Exception as exc:
                logger.debug("Could not fetch led_to target %s: %s", out_id, exc)
    except Exception as exc:
        logger.debug("led_to query failed for %s: %s", node_id, exc)

    # supersedes edges (outgoing — this decision supersedes older ones)
    try:
        supersedes_result = await db.query(
            "SELECT * FROM supersedes WHERE in = <record>$id LIMIT 10",
            {"id": node_id},
        )
        for edge_row in parse_rows(supersedes_result):
            out_id = str(serialize_record(edge_row.get("out", "")))
            if not out_id or out_id == "None":
                continue
            try:
                old_result = await db.query("SELECT * FROM <record>$id", {"id": out_id})
                old_row = parse_one(old_result)
                if old_row:
                    old = _serialize(old_row)
                    o_mid = _mermaid_id(out_id)
                    o_label = _safe_label(old, out_id)
                    lines.append(f'    {o_mid}["{o_label}"]')
                    lines.append(f"    {root_mid} -->|supersedes| {o_mid}")
            except Exception as exc:
                logger.debug("Could not fetch superseded node %s: %s", out_id, exc)
    except Exception as exc:
        logger.debug("supersedes query failed for %s: %s", node_id, exc)

    title = f"Decision Tree: {_safe_label(root, node_id)}"
    return {"mermaid": "\n".join(lines), "title": title}


async def _diagram_initiative_flow(db, root: dict, node_id: str) -> dict:
    """Initiative ← became (from idea) + quality_delta edges."""
    lines = ["flowchart TD"]
    root_mid = _mermaid_id(node_id)
    root_label = _safe_label(root, node_id)
    lines.append(f'    {root_mid}["{root_label}"]')

    # became edges (incoming — idea became this initiative)
    try:
        became_result = await db.query(
            "SELECT * FROM became WHERE out = <record>$id LIMIT 10",
            {"id": node_id},
        )
        for edge_row in parse_rows(became_result):
            in_id = str(serialize_record(edge_row.get("in", "")))
            if not in_id or in_id == "None":
                continue
            try:
                idea_result = await db.query("SELECT * FROM <record>$id", {"id": in_id})
                idea_row = parse_one(idea_result)
                if idea_row:
                    idea = _serialize(idea_row)
                    i_mid = _mermaid_id(in_id)
                    i_label = _safe_label(idea, in_id)
                    lines.append(f'    {i_mid}["{i_label}"]')
                    lines.append(f"    {i_mid} -->|became| {root_mid}")
            except Exception as exc:
                logger.debug("Could not fetch idea %s: %s", in_id, exc)
    except Exception as exc:
        logger.debug("became query failed for %s: %s", node_id, exc)

    # quality_delta edges (outgoing — initiative affects quality)
    try:
        qd_result = await db.query(
            "SELECT * FROM quality_delta WHERE in = <record>$id LIMIT 10",
            {"id": node_id},
        )
        for edge_row in parse_rows(qd_result):
            edge = _serialize(edge_row)
            out_id = str(serialize_record(edge_row.get("out", "")))
            if not out_id or out_id == "None":
                continue
            try:
                target_result = await db.query("SELECT * FROM <record>$id", {"id": out_id})
                target_row = parse_one(target_result)
                if target_row:
                    target = _serialize(target_row)
                    t_mid = _mermaid_id(out_id)
                    t_label = _safe_label(target, out_id)
                    delta = edge.get("delta", "")
                    lines.append(f'    {t_mid}["{t_label}"]')
                    lines.append(f'    {root_mid} -->|"quality Δ {delta}"| {t_mid}')
            except Exception as exc:
                logger.debug("Could not fetch quality_delta target %s: %s", out_id, exc)
    except Exception as exc:
        logger.debug("quality_delta query failed for %s: %s", node_id, exc)

    title = f"Initiative Flow: {_safe_label(root, node_id)}"
    return {"mermaid": "\n".join(lines), "title": title}
