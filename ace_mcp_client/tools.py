# ace_mcp_client/tools.py
"""11 MCP tool implementations — pure HTTP calls to the ACE API.

Zero engine imports. Each function calls the REST API and returns formatted results.
"""

from __future__ import annotations

import re

from .client import AceClient

_client: AceClient | None = None


def _get_client() -> AceClient:
    """Lazy-init the shared HTTP client."""
    global _client
    if _client is None:
        _client = AceClient()
    return _client


def _slugify_path(file_path: str) -> str:
    """Convert a file path to a SurrealDB slug: engine/core/db.py -> engine_core_db_py."""
    slug = re.sub(r"[^a-z0-9]", "_", file_path.lower())
    slug = re.sub(r"_+", "_", slug).strip("_")
    return slug


# ---------------------------------------------------------------------------
# 1. ace_start — session pre-flight
# ---------------------------------------------------------------------------


async def ace_start(product_id: str = "product:default") -> dict:
    """Pre-flight: health check + session context."""
    c = _get_client()
    try:
        health = await c.get("/health")
    except Exception:
        health = {"status": "unreachable"}

    try:
        pulse = await c.get("/portal/attention", params={"product": product_id})
    except Exception:
        pulse = {}

    try:
        briefing = await c.get("/briefings/latest", params={"product": product_id})
        briefing_available = True
        last_briefing_date = str(briefing.get("created_at", ""))
    except Exception:
        briefing_available = False
        last_briefing_date = None

    return {
        "status": health.get("status", "unknown"),
        "briefing_available": briefing_available,
        "last_briefing_date": last_briefing_date,
        "attention_items": pulse.get("items", []),
    }


# ---------------------------------------------------------------------------
# 2. ace_load — load intelligence for a domain
# ---------------------------------------------------------------------------


async def ace_load(topic: str, product_id: str = "product:default") -> dict:
    """Load accumulated intelligence for a domain."""
    c = _get_client()
    r = await c.get("/intel/context", params={"q": topic, "product": product_id})

    return {
        "domain_path": r.get("domain_path", ""),
        "insights": r.get("insights", []),
        "corrections": r.get("corrections", []),
        "preferences": r.get("preferences", []),
        "framework_recommendation": r.get("framework_recommendation"),
        "total_count": r.get("total_count", 0),
    }


# ---------------------------------------------------------------------------
# 3. ace_capture — record an observation
# ---------------------------------------------------------------------------


async def ace_capture(
    observation_type: str,
    content: str,
    domain_path: str,
    confidence: float = 0.7,
    product_id: str = "product:default",
    affected_decision_id: str | None = None,
    affected_task_id: str | None = None,
    lifecycle_state: str = "active",
    supersedes_correction_id: str | None = None,
    invalidates_correction_id: str | None = None,
    contests_correction_id: str | None = None,
    expires_at: str | None = None,
) -> dict:
    """Record an observation from the session."""
    c = _get_client()
    body = {
        "observation_type": observation_type,
        "content": content,
        "domain_path": domain_path,
        "confidence": confidence,
        "source_surface": "thin_mcp",
    }
    optional = {
        "affected_decision_id": affected_decision_id,
        "affected_task_id": affected_task_id,
        "supersedes_correction_id": supersedes_correction_id,
        "invalidates_correction_id": invalidates_correction_id,
        "contests_correction_id": contests_correction_id,
        "expires_at": expires_at,
    }
    body.update({key: value for key, value in optional.items() if value is not None})
    if observation_type == "correction":
        body["lifecycle_state"] = lifecycle_state
    r = await c.post("/observations", json=body)
    return r


# ---------------------------------------------------------------------------
# 4. ace_task — run task through orchestrator
# ---------------------------------------------------------------------------


async def ace_task(
    description: str,
    product_id: str = "product:default",
    workspace_id: str = "workspace:default",
    skill_hint: str | None = None,
    frameworks_hint: list[str] | None = None,
    request_id: str | None = None,
    decision: dict | None = None,
) -> dict:
    """Submit work to the orchestrator and return a durable receipt or fast result."""
    c = _get_client()
    body: dict = {
        "description": description,
        "workspace_id": workspace_id,
    }
    if skill_hint:
        body["force_skill"] = skill_hint
    if frameworks_hint:
        body["frameworks_hint"] = frameworks_hint
    if request_id:
        body["idempotency_key"] = request_id
    if decision:
        body["decision"] = decision

    r = await c.submit_task(body)
    return r


# ---------------------------------------------------------------------------
# 5. ace_status — check autonomous work status
# ---------------------------------------------------------------------------


async def ace_status(
    product_id: str = "product:default",
    filter: str | None = None,
    task_id: str | None = None,
) -> dict:
    """Retrieve a durable task or check broader autonomous-work status."""
    c = _get_client()

    requested_task = task_id or (filter if filter and filter.startswith("task:") else None)
    if requested_task:
        task = await c.get(f"/tasks/{requested_task}")
        return {"status": task.get("status", "degraded"), "task": task}

    try:
        runner = await c.get("/runner/status")
    except Exception:
        runner = {"status": "unavailable"}

    try:
        attention = await c.get("/portal/attention", params={"product": product_id})
    except Exception:
        attention = {"items": []}

    return {
        "runner": runner,
        "attention_items": attention.get("items", []),
    }


# ---------------------------------------------------------------------------
# 6. ace_capture_idea — send idea to incubator
# ---------------------------------------------------------------------------


async def ace_capture_idea(
    raw_idea: str,
    product_id: str = "product:default",
    context: str | None = None,
) -> dict:
    """Send idea to incubator."""
    full_input = f"{raw_idea}\n\nContext: {context}" if context else raw_idea
    c = _get_client()
    r = await c.post("/ideas", json={"raw_input": full_input})
    return r


# ---------------------------------------------------------------------------
# 7. ace_search — search the intelligence graph
# ---------------------------------------------------------------------------


async def ace_search(
    query: str,
    product_id: str = "product:default",
    knowledge_type: str | None = None,
) -> dict:
    """Search the intelligence graph."""
    c = _get_client()
    params: dict = {"q": query, "product": product_id}
    r = await c.get("/intel/search", params=params)
    # Client-side filter by knowledge_type if provided
    results = r.get("results", [])
    if knowledge_type:
        results = [i for i in results if i.get("insight_type") == knowledge_type]
    return {"results": results, "count": len(results)}


# ---------------------------------------------------------------------------
# 8. ace_briefing — retrieve latest briefing
# ---------------------------------------------------------------------------


async def ace_briefing(
    product_id: str = "product:default",
    date: str | None = None,
) -> dict:
    """Retrieve morning briefing."""
    c = _get_client()
    try:
        if date:
            # List briefings and find matching date
            r = await c.get("/briefings", params={"product": product_id, "limit": 30})
            briefings = r.get("briefings", [])
            for b in briefings:
                if str(b.get("created_at", "")).startswith(date):
                    return {
                        "content": b.get("content", ""),
                        "period": b.get("period", ""),
                        "created_at": str(b.get("created_at", "")),
                        "metrics": b.get("metrics", {}),
                        "available": True,
                    }
            return {"content": None, "period": "", "created_at": "", "metrics": {}, "available": False}
        else:
            r = await c.get("/briefings/latest", params={"product": product_id})
            return {
                "content": r.get("content", ""),
                "period": r.get("period", ""),
                "created_at": str(r.get("created_at", "")),
                "metrics": r.get("metrics", {}),
                "available": True,
            }
    except Exception:
        return {"content": None, "period": "", "created_at": "", "metrics": {}, "available": False}


# ---------------------------------------------------------------------------
# 9. ace_impact — what breaks if you change this file?
# ---------------------------------------------------------------------------


async def ace_impact(file_path: str, graph_id: str = "default") -> str:
    """Analyze the impact of changing a file.

    Returns dependents, functions, decisions, fragility score — formatted as markdown.
    """
    c = _get_client()
    slug = _slugify_path(file_path)
    node_id = f"graph_file:{slug}"

    try:
        r = await c.get(f"/graph/impact/{node_id}", params={"graph_id": graph_id})
    except Exception as exc:
        return f"**Error analyzing impact:** {exc}"

    return _format_traverse_result(r, file_path, "Impact Analysis")


# ---------------------------------------------------------------------------
# 10. ace_history — why was this file built this way?
# ---------------------------------------------------------------------------


async def ace_history(file_path: str, graph_id: str = "default") -> str:
    """Get the decision history for a file.

    Shows why things were built this way — decisions, outcomes, timestamps.
    """
    c = _get_client()
    slug = _slugify_path(file_path)
    node_id = f"graph_file:{slug}"

    try:
        r = await c.get(f"/graph/history/{node_id}", params={"graph_id": graph_id})
    except Exception as exc:
        return f"**Error loading history:** {exc}"

    return _format_traverse_result(r, file_path, "Decision History")


# ---------------------------------------------------------------------------
# 11. ace_related — what's connected to this file?
# ---------------------------------------------------------------------------


async def ace_related(file_path: str, graph_id: str = "default") -> str:
    """Find everything connected to a file.

    Returns imports, importers, co-changed peers, and decisions — 1-2 hops.
    """
    c = _get_client()
    slug = _slugify_path(file_path)
    node_id = f"graph_file:{slug}"

    try:
        r = await c.get(f"/graph/related/{node_id}", params={"graph_id": graph_id})
    except Exception as exc:
        return f"**Error finding related nodes:** {exc}"

    return _format_traverse_result(r, file_path, "Connected Graph")


# ---------------------------------------------------------------------------
# Formatting helpers
# ---------------------------------------------------------------------------


def _format_traverse_result(data: dict, file_path: str, title: str) -> str:
    """Format a TraverseResponse into readable markdown."""
    nodes = data.get("nodes", [])
    _ = data.get("edges", [])  # available for future use
    start_node = data.get("start_node")
    stats = data.get("stats", {})

    if not start_node:
        return (
            f"**File not found in graph:** `{file_path}`\n\n"
            "No graph node exists for this path. Has the graph been built for this repo?"
        )

    lines = [
        f"## {title}: `{file_path}`",
        "",
        f"**{stats.get('node_count', 0)} connected nodes** | "
        f"**{stats.get('edge_count', 0)} edges** | "
        f"**Depth:** {stats.get('depth_reached', 0)}",
        "",
    ]

    # Group nodes by type
    by_type: dict[str, list[dict]] = {}
    for node in nodes:
        ntype = node.get("_type", "unknown")
        by_type.setdefault(ntype, []).append(node)

    type_labels = {
        "graph_file": "Files",
        "graph_function": "Functions",
        "graph_decision": "Decisions",
        "graph_insight": "Insights",
        "graph_task": "Tasks",
        "graph_initiative": "Initiatives",
        "graph_idea": "Ideas",
    }

    for ntype, label in type_labels.items():
        group = by_type.get(ntype, [])
        if not group:
            continue
        lines.append(f"### {label} ({len(group)})")
        for node in group[:20]:
            name = node.get("path") or node.get("title") or node.get("name") or node.get("id", "?")
            lines.append(f"- `{name}`")
        if len(group) > 20:
            lines.append(f"- ...and {len(group) - 20} more")
        lines.append("")

    # Show remaining types not in the label map
    for ntype, group in by_type.items():
        if ntype in type_labels:
            continue
        lines.append(f"### {ntype} ({len(group)})")
        for node in group[:10]:
            name = node.get("name") or node.get("title") or node.get("id", "?")
            lines.append(f"- `{name}`")
        lines.append("")

    if not nodes:
        lines.append("_No connections found. This file may be isolated or the graph may need updating._")

    return "\n".join(lines)
