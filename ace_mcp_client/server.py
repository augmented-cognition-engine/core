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
        "Intelligence that compounds. Load knowledge, capture observations, "
        "run tasks through ACE's full orchestrator. "
        "This is a thin client — all intelligence lives in the ACE API."
    ),
)


@mcp.tool(name="ace_start")
async def ace_start_tool() -> dict:
    """Pre-flight check. Returns session context: API health, briefing availability, attention items. Call this at the start of every session."""
    return await ace_start()


@mcp.tool(name="ace_load")
async def ace_load_tool(topic: str) -> dict:
    """Load accumulated intelligence for a domain topic. Returns insights, corrections, preferences, and framework recommendation. Always call this before starting work in a domain. Do not attempt to help without loading organizational intelligence first."""
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
) -> dict:
    """Record an observation from this session. Types: correction, decision, preference, pattern, learning, error. Call when user corrects output ("that's wrong", "use X not Y"), makes a decision, states a preference, or when you discover a useful fact. ACE processes these into durable intelligence."""
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
    """Search the intelligence graph. Optional filter by knowledge_type: insight, correction, preference."""
    return await ace_search(query=query, knowledge_type=knowledge_type)


@mcp.tool(name="ace_briefing")
async def ace_briefing_tool(date: str | None = None) -> dict:
    """Retrieve the intelligence briefing. Defaults to latest. Shows what ACE learned, what needs attention, ideas ready."""
    return await ace_briefing(date=date)


@mcp.tool(name="ace_impact")
async def ace_impact_tool(file_path: str, graph_id: str = "default") -> str:
    """What breaks if you change this file? Returns dependents (who imports it), functions defined, recent decisions, and a fragility score. Call this before refactoring or deleting a file to understand blast radius."""
    return await ace_impact(file_path=file_path, graph_id=graph_id)


@mcp.tool(name="ace_history")
async def ace_history_tool(file_path: str, graph_id: str = "default") -> str:
    """Why was this file built this way? Returns the decision trail — what decisions were made, what was tried, what succeeded. Call this when you encounter code that seems odd or over-engineered."""
    return await ace_history(file_path=file_path, graph_id=graph_id)


@mcp.tool(name="ace_related")
async def ace_related_tool(file_path: str, graph_id: str = "default") -> str:
    """What's connected to this file? Returns imports (outgoing), importers (incoming), co-changed files, and related decisions — everything 1-2 hops away in the knowledge graph."""
    return await ace_related(file_path=file_path, graph_id=graph_id)


def main():
    """Entry point for ace-mcp-client script."""
    mcp.run()


if __name__ == "__main__":
    main()
