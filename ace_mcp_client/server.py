# ace_mcp_client/server.py
"""ACE MCP thin client server — exposes 11 tools over MCP protocol.

Zero engine imports. All intelligence comes from HTTP calls to the ACE API.

Run: ace-mcp-client (or: python -m ace_mcp_client.server)
"""

from __future__ import annotations

from fastmcp import FastMCP

from .tools import (
    ace_briefing,
    ace_capture,
    ace_capture_idea,
    ace_history,
    ace_impact,
    ace_load,
    ace_related,
    ace_search,
    ace_start,
    ace_status,
    ace_task,
)

mcp = FastMCP(
    "ACE Intelligence Engine",
    instructions=(
        "ACE serves this project's accumulated, governed intelligence: a pre-scanned "
        "code graph (files, functions, imports, tests, co-change history) plus "
        "captured decisions, corrections, and preferences.\n"
        "Use it as the first move in a code task, not as a last resort:\n"
        "1. Call ace_start once at session start (health, briefing, attention items).\n"
        "2. Entering an unfamiliar area of the codebase? ace_search the topic or "
        "symbol and ace_load the domain before manual exploration — one call often "
        "replaces several rounds of grep/glob orientation.\n"
        "3. Before modifying, moving, or deleting a file: ace_impact (observed "
        "dependents) and ace_related (import neighborhood, co-changed files).\n"
        "4. Code that looks odd or over-engineered? ace_history for its decision "
        "and co-change trail before you change it.\n"
        "5. When you learn or correct something, ace_capture it so the next session "
        "starts smarter.\n"
        "Results come from observed, governed records; each tool names its limits "
        "and never claims more than what was scanned or captured. This is a thin "
        "client — all intelligence lives in the ACE API."
    ),
)


@mcp.tool(name="ace_start")
async def ace_start_tool() -> dict:
    """Pre-flight check — call once at the start of every session, before other tools and before exploring the codebase by hand. Returns session context: API health, briefing availability, and attention items, so you know what accumulated intelligence exists for this project."""
    return await ace_start()


@mcp.tool(name="ace_load")
async def ace_load_tool(topic: str) -> dict:
    """Load accumulated intelligence for a domain topic before working in that area of the codebase — prior insights, corrections, preferences, and a framework recommendation from earlier sessions. One call orients you faster than re-deriving the same context by reading files. Call it with the area you are about to work in (e.g. topic='intelligence contracts', 'feedback admission')."""
    return await ace_load(topic=topic)


@mcp.tool(name="ace_capture")
async def ace_capture_tool(
    observation_type: str,
    content: str,
    domain_path: str,
    confidence: float = 0.7,
    affected_decision_id: str | None = None,
    affected_task_id: str | None = None,
    lifecycle_state: str = "active",
    supersedes_correction_id: str | None = None,
    invalidates_correction_id: str | None = None,
    contests_correction_id: str | None = None,
    expires_at: str | None = None,
    intervention: dict | None = None,
    indicator: dict | None = None,
    comparator: dict | None = None,
    measurement: dict | None = None,
) -> dict:
    """Record an observation the moment you learn, decide, or correct something in this session — don't wait for session end. Types include correction, decision, preference, pattern, learning, error, intervention, forecast_indicator, forecast_comparator, and forecast_measurement. Supply the corresponding structured payload for foresight evidence. ACE processes ordinary observations into durable intelligence and keeps foresight observations as separate evidence."""
    return await ace_capture(
        observation_type=observation_type,
        content=content,
        domain_path=domain_path,
        confidence=confidence,
        affected_decision_id=affected_decision_id,
        affected_task_id=affected_task_id,
        lifecycle_state=lifecycle_state,
        supersedes_correction_id=supersedes_correction_id,
        invalidates_correction_id=invalidates_correction_id,
        contests_correction_id=contests_correction_id,
        expires_at=expires_at,
        intervention=intervention,
        indicator=indicator,
        comparator=comparator,
        measurement=measurement,
    )


@mcp.tool(name="ace_task")
async def ace_task_tool(
    description: str,
    skill_hint: str | None = None,
    frameworks_hint: str | None = None,
    request_id: str | None = None,
    decision: dict | None = None,
) -> dict:
    """Submit a task through ACE's full orchestrator. Returns either a completed result or a durable pending/running receipt that remains retrievable with ace_status. Reuse request_id when retrying the same submission; use a new value for an intentional rerun."""
    fw_list = frameworks_hint.split(",") if frameworks_hint else None
    return await ace_task(
        description=description,
        skill_hint=skill_hint,
        frameworks_hint=fw_list,
        request_id=request_id,
        decision=decision,
    )


@mcp.tool(name="ace_status")
async def ace_status_tool(filter: str | None = None, task_id: str | None = None) -> dict:
    """Retrieve a task receipt/result by task_id (or filter='task:…'), or check broader autonomous work status."""
    return await ace_status(filter=filter, task_id=task_id)


@mcp.tool(name="ace_capture_idea")
async def ace_capture_idea_tool(raw_idea: str, context: str | None = None) -> dict:
    """Drop an idea into ACE's incubator. Call when user says 'what if...', 'I want to explore...', 'remind me to think about...'. ACE will enrich it overnight: generate brief, find connections, identify gaps, qualify feasibility."""
    return await ace_capture_idea(raw_idea=raw_idea, context=context)


@mcp.tool(name="ace_search")
async def ace_search_tool(query: str, knowledge_type: str | None = None) -> dict:
    """Search the accumulated intelligence graph for a topic, symbol, or file name — use this before manual grep/glob exploration of unfamiliar code, since it returns what prior sessions already learned (insights, corrections, preferences) instead of raw text matches. Optional filter by knowledge_type: insight, correction, preference."""
    return await ace_search(query=query, knowledge_type=knowledge_type)


@mcp.tool(name="ace_briefing")
async def ace_briefing_tool(date: str | None = None) -> dict:
    """Retrieve the intelligence briefing. Defaults to latest. Shows what ACE learned, what needs attention, ideas ready."""
    return await ace_briefing(date=date)


@mcp.tool(name="ace_impact")
async def ace_impact_tool(file_path: str, graph_id: str = "default") -> str:
    """Before modifying, moving, or deleting a file in a scanned repository, call this to see what is observed to depend on it — faster and more complete than hand-tracing importers with grep. Returns a bounded traversal of the dependent graph: the nodes reachable inward from this file through depends_on, tests, breaks, and imports edges, up to a fixed depth and node limit. This is an observed subgraph, not an assessment: it does not establish what breaks, how fragile the file is, whether it is safe to delete, or which recent decisions touched it."""
    return await ace_impact(file_path=file_path, graph_id=graph_id)


@mcp.tool(name="ace_history")
async def ace_history_tool(file_path: str, graph_id: str = "default") -> str:
    """Encountered code that seems odd, over-engineered, or surprising? Call this before changing it. Returns the file's recorded decision trail and git co-change history from the scanned graph — what was decided, what was tried, and which files historically changed together with it."""
    return await ace_history(file_path=file_path, graph_id=graph_id)


@mcp.tool(name="ace_related")
async def ace_related_tool(file_path: str, graph_id: str = "default") -> str:
    """Map a file's neighborhood before working in it — instead of hand-tracing imports with grep. Returns imports (outgoing), importers (incoming), co-changed files, and related decisions: everything observed 1-2 hops away in the scanned knowledge graph."""
    return await ace_related(file_path=file_path, graph_id=graph_id)


def main():
    """Entry point for ace-mcp-client script."""
    mcp.run()


if __name__ == "__main__":
    main()
