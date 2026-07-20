"""ACE self-tools — Layer 2 wiring for runtime graph access.

Each tool calls engine.mcp.tools functions directly (no HTTP roundtrip).
All tools are scoped to a product_id supplied at construction time.

Tool list:
  Read-only (run in parallel):
    ace_graph_search      — semantic search of intelligence graph
    ace_graph_load        — load intelligence for a topic
    ace_product_context   — current capabilities, quality scores, active gaps

  Write (exclusive):
    ace_graph_capture     — write observation immediately
    ace_graph_decision    — write decision with rationale + alternatives
    ace_graph_idea        — capture idea before it's lost
    ace_graph_error       — flag something broken — feeds sentinel
    ace_spawn_agent       — spawn focused sub-agent with scoped tools + context
    ace_session_flush     — force observer run on current session summary
"""

from __future__ import annotations

import json
import logging
from typing import Any

from core.engine.runtime.tools import RuntimeTool

logger = logging.getLogger(__name__)


def _fmt(result: Any) -> str:
    """Format a result dict or string for tool output."""
    if isinstance(result, dict):
        return json.dumps(result, indent=2, default=str)
    return str(result)


# ---------------------------------------------------------------------------
# Read-only tools
# ---------------------------------------------------------------------------


class AceGraphSearchTool(RuntimeTool):
    """Semantic search of the ACE intelligence graph."""

    name: str = "ace_graph_search"
    description: str = (
        "Search the ACE intelligence graph for insights, patterns, corrections, and preferences. "
        "Use this before making decisions to check what ACE already knows about a topic."
    )
    is_read_only: bool = True

    def __init__(self, product_id: str) -> None:
        self._product_id = product_id

    def get_input_schema(self) -> dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "query": {
                    "type": "string",
                    "description": "What to search for — use natural language or keywords.",
                },
                "knowledge_type": {
                    "type": "string",
                    "description": (
                        "Optional filter. One of: correction, decision, preference, pattern, learning, error."
                    ),
                },
            },
            "required": ["query"],
        }

    async def execute(self, input: dict[str, Any]) -> str:
        from core.engine.mcp.tools import ace_search

        query: str = input["query"]
        knowledge_type: str | None = input.get("knowledge_type")
        try:
            result = await ace_search(query=query, product_id=self._product_id, knowledge_type=knowledge_type)
            return _fmt(result)
        except Exception as exc:
            logger.warning("ace_graph_search failed: %s", exc)
            return f"Search error: {exc}"


class AceGraphLoadTool(RuntimeTool):
    """Load accumulated intelligence for a topic or capability."""

    name: str = "ace_graph_load"
    description: str = (
        "Load all intelligence ACE has accumulated for a topic — insights, corrections, preferences, decisions. "
        "Call at session start or before working on a specific capability."
    )
    is_read_only: bool = True

    def __init__(self, product_id: str) -> None:
        self._product_id = product_id

    def get_input_schema(self) -> dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "topic": {
                    "type": "string",
                    "description": "Topic or capability to load intelligence for (e.g. 'auth', 'api_design', 'testing').",
                },
            },
            "required": ["topic"],
        }

    async def execute(self, input: dict[str, Any]) -> str:
        from core.engine.mcp.tools import ace_load

        topic: str = input["topic"]
        try:
            result = await ace_load(topic=topic, product_id=self._product_id)
            return _fmt(result)
        except Exception as exc:
            logger.warning("ace_graph_load failed: %s", exc)
            return f"Load error: {exc}"


class AceProductContextTool(RuntimeTool):
    """Get current product context — capabilities, quality scores, active gaps."""

    name: str = "ace_product_context"
    description: str = (
        "Get a full picture of the current product state: capabilities mapped, quality scores "
        "across 18 disciplines, active gaps, and recent decisions. Useful for understanding "
        "what exists before proposing changes."
    )
    is_read_only: bool = True

    def __init__(self, product_id: str) -> None:
        self._product_id = product_id

    def get_input_schema(self) -> dict[str, Any]:
        return {
            "type": "object",
            "properties": {},
            "required": [],
        }

    async def execute(self, input: dict[str, Any]) -> str:
        from core.engine.mcp.tools import ace_context

        try:
            result = await ace_context(product_id=self._product_id)
            return _fmt(result)
        except Exception as exc:
            logger.warning("ace_product_context failed: %s", exc)
            return f"Context error: {exc}"


# ---------------------------------------------------------------------------
# Write tools
# ---------------------------------------------------------------------------


class AceGraphCaptureTool(RuntimeTool):
    """Write an observation to the ACE intelligence graph immediately."""

    name: str = "ace_graph_capture"
    description: str = (
        "Record an observation (pattern, correction, preference, learning) to the ACE intelligence graph. "
        "Observations are processed by the capture pipeline and become durable insights. "
        "Call this whenever you notice something worth remembering."
    )
    is_read_only: bool = False

    def __init__(self, product_id: str) -> None:
        self._product_id = product_id

    def get_input_schema(self) -> dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "observation_type": {
                    "type": "string",
                    "description": "Type of observation. One of: correction, decision, preference, pattern, learning, error.",
                },
                "content": {
                    "type": "string",
                    "description": "The observation content — be specific and actionable.",
                },
                "domain_path": {
                    "type": "string",
                    "description": "Discipline or area this applies to (e.g. 'testing', 'api_design', 'security').",
                },
                "confidence": {
                    "type": "number",
                    "description": "Confidence level 0.0-1.0. Defaults to 0.7.",
                },
            },
            "required": ["observation_type", "content", "domain_path"],
        }

    async def execute(self, input: dict[str, Any]) -> str:
        from core.engine.mcp.tools import ace_capture

        try:
            result = await ace_capture(
                observation_type=input["observation_type"],
                content=input["content"],
                domain_path=input["domain_path"],
                confidence=float(input.get("confidence", 0.7)),
                product_id=self._product_id,
            )
            return _fmt(result)
        except Exception as exc:
            logger.warning("ace_graph_capture failed: %s", exc)
            return f"Capture error: {exc}"


class AceGraphDecisionTool(RuntimeTool):
    """Record an architectural decision with rationale and alternatives."""

    name: str = "ace_graph_decision"
    description: str = (
        "Record an architectural or design decision with full rationale and alternatives considered. "
        "Call proactively whenever you choose an approach over alternatives — this prevents revisiting "
        "settled decisions and builds institutional knowledge."
    )
    is_read_only: bool = False

    def __init__(self, product_id: str) -> None:
        self._product_id = product_id

    def get_input_schema(self) -> dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "title": {
                    "type": "string",
                    "description": "Short title for the decision.",
                },
                "decision_type": {
                    "type": "string",
                    "description": "Category: architecture, api_design, data_modeling, technology, process.",
                },
                "rationale": {
                    "type": "string",
                    "description": "Why this decision was made.",
                },
                "alternatives": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "Alternatives that were considered and rejected.",
                },
                "affected_capabilities": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "Capability slugs this decision affects.",
                },
            },
            "required": ["title", "decision_type", "rationale"],
        }

    async def execute(self, input: dict[str, Any]) -> str:
        from core.engine.mcp.tools import ace_capture_decision

        try:
            result = await ace_capture_decision(
                title=input["title"],
                decision_type=input["decision_type"],
                rationale=input["rationale"],
                alternatives=input.get("alternatives"),
                affected_capabilities=input.get("affected_capabilities"),
                product_id=self._product_id,
            )
            return _fmt(result)
        except Exception as exc:
            logger.warning("ace_graph_decision failed: %s", exc)
            return f"Decision capture error: {exc}"


class AceGraphIdeaTool(RuntimeTool):
    """Capture an idea before it's lost — sends to the idea incubator."""

    name: str = "ace_graph_idea"
    description: str = (
        "Capture a product or technical idea immediately. "
        "Ideas go to the incubator where ACE researches them overnight and generates a brief. "
        "Use when the user says 'what if...', 'we should...', or 'remind me to think about...'."
    )
    is_read_only: bool = False

    def __init__(self, product_id: str) -> None:
        self._product_id = product_id

    def get_input_schema(self) -> dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "raw_idea": {
                    "type": "string",
                    "description": "The idea as stated — raw is fine, ACE will refine it.",
                },
                "context": {
                    "type": "string",
                    "description": "Optional context about why this idea came up.",
                },
            },
            "required": ["raw_idea"],
        }

    async def execute(self, input: dict[str, Any]) -> str:
        from core.engine.mcp.tools import ace_capture_idea

        try:
            result = await ace_capture_idea(
                raw_idea=input["raw_idea"],
                product_id=self._product_id,
                context=input.get("context"),
            )
            return _fmt(result)
        except Exception as exc:
            logger.warning("ace_graph_idea failed: %s", exc)
            return f"Idea capture error: {exc}"


class AceGraphErrorTool(RuntimeTool):
    """Flag something broken — feeds the sentinel for monitoring."""

    name: str = "ace_graph_error"
    description: str = (
        "Flag a bug, broken integration, or quality issue. "
        "Errors feed the sentinel engine which tracks patterns and alerts on recurring issues. "
        "Use when you find something broken that should be tracked."
    )
    is_read_only: bool = False

    def __init__(self, product_id: str) -> None:
        self._product_id = product_id

    def get_input_schema(self) -> dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "content": {
                    "type": "string",
                    "description": "Description of what is broken and where.",
                },
                "domain_path": {
                    "type": "string",
                    "description": "Discipline or area affected (e.g. 'testing', 'api_design', 'security').",
                },
                "confidence": {
                    "type": "number",
                    "description": "How certain you are this is a real issue (0.0-1.0). Defaults to 0.9.",
                },
            },
            "required": ["content", "domain_path"],
        }

    async def execute(self, input: dict[str, Any]) -> str:
        from core.engine.mcp.tools import ace_capture

        try:
            result = await ace_capture(
                observation_type="error",
                content=input["content"],
                domain_path=input["domain_path"],
                confidence=float(input.get("confidence", 0.9)),
                product_id=self._product_id,
            )
            return _fmt(result)
        except Exception as exc:
            logger.warning("ace_graph_error failed: %s", exc)
            return f"Error capture failed: {exc}"


class AceSpawnAgentTool(RuntimeTool):
    """Spawn a focused sub-agent with scoped tools and context."""

    name: str = "ace_spawn_agent"
    description: str = (
        "Spawn a focused sub-agent to handle a self-contained task. "
        "The sub-agent gets a clean context with only the tools it needs. "
        "Results are returned when the sub-agent completes. "
        "Use for parallel work that shouldn't pollute the current context."
    )
    is_read_only: bool = False

    def __init__(self, product_id: str, model: str = "claude-sonnet-4-6") -> None:
        self._product_id = product_id
        self._model = model

    def get_input_schema(self) -> dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "task": {
                    "type": "string",
                    "description": "The task for the sub-agent to complete.",
                },
                "context": {
                    "type": "string",
                    "description": "Optional system prompt addition — extra context the sub-agent needs.",
                },
                "scoped_tools": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": (
                        "Tool names the sub-agent can use. "
                        "If omitted, sub-agent gets all tools. "
                        "Example: ['read', 'grep', 'ace_graph_search']"
                    ),
                },
                "max_turns": {
                    "type": "integer",
                    "description": "Maximum turns for the sub-agent. Defaults to 20.",
                },
            },
            "required": ["task"],
        }

    async def execute(self, input: dict[str, Any]) -> str:
        from core.engine.runtime.runtime import Runtime

        task: str = input["task"]
        context: str | None = input.get("context")
        scoped_tools: list[str] | None = input.get("scoped_tools")
        max_turns: int = int(input.get("max_turns", 20))

        system = "You are a focused sub-agent. Complete only the task given. Report your results clearly when done."
        if context:
            system = f"{system}\n\n{context}"

        try:
            child = Runtime(
                model=self._model,
                system=system,
                max_turns=max_turns,
                enable_intelligence=False,  # sub-agent skips intelligence load
                product_id=self._product_id,
            )

            # Remove tools not in scoped_tools if list was provided
            if scoped_tools is not None:
                allowed = set(scoped_tools)
                to_remove = [name for name in child.tool_names if name not in allowed]
                for name in to_remove:
                    child._registry._tools.pop(name, None)

            # Re-register ACE tools the sub-agent requested
            if scoped_tools:
                ace_tool_map = _make_ace_tools(self._product_id, self._model)
                for tool_name in scoped_tools:
                    if tool_name in ace_tool_map and tool_name not in child.tool_names:
                        child._registry.register(ace_tool_map[tool_name])

            # Run the task
            result_parts: list[str] = []
            from core.engine.runtime.models import AssistantMessage

            async for msg in child.chat(task):
                if isinstance(msg, AssistantMessage) and msg.content:
                    result_parts.append(msg.content)

            return "\n\n".join(result_parts) if result_parts else "(sub-agent completed with no output)"
        except Exception as exc:
            logger.warning("ace_spawn_agent failed: %s", exc)
            return f"Sub-agent error: {exc}"


class AceSessionFlushTool(RuntimeTool):
    """Force the capture pipeline to process the current session summary."""

    name: str = "ace_session_flush"
    description: str = (
        "Immediately emit the current session's work to the capture pipeline for processing. "
        "Normally happens at session end — call this mid-session to make insights available "
        "to other agents or the next turn without waiting."
    )
    is_read_only: bool = False

    def __init__(self, product_id: str) -> None:
        self._product_id = product_id

    def get_input_schema(self) -> dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "summary": {
                    "type": "string",
                    "description": "Brief summary of what has happened this session — what was built, decided, or learned.",
                },
            },
            "required": ["summary"],
        }

    async def execute(self, input: dict[str, Any]) -> str:
        summary: str = input["summary"]

        try:
            from core.engine.events.bus import bus as event_bus

            await event_bus.emit(
                "runtime.turn_for_capture",
                {
                    "product_id": self._product_id,
                    "turn_text": summary,
                    "message_count": 1,
                    "source": "ace_session_flush",
                },
            )
            return json.dumps({"status": "flushed", "source": "ace_session_flush"})
        except Exception as exc:
            logger.warning("ace_session_flush failed: %s", exc)
            return f"Flush error: {exc}"


# ---------------------------------------------------------------------------
# Graph intelligence tools (Stream 8) — read-only, chain reaction detection
# ---------------------------------------------------------------------------


class AceBlastRadiusTool(RuntimeTool):
    """Find everything affected if a file or symbol changes."""

    name: str = "ace_blast_radius"
    description: str = (
        "Find the full blast radius of changing a file or symbol — all direct and transitive dependents. "
        "Call this BEFORE modifying any file to understand what else may need updating. "
        "Returns affected files, risk score, and critical path count."
    )
    is_read_only: bool = True

    def __init__(self, product_id: str) -> None:
        self._product_id = product_id

    def get_input_schema(self) -> dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "target": {
                    "type": "string",
                    "description": "File path or symbol name to analyze (e.g. 'engine/runtime/runtime.py' or 'Runtime').",
                },
            },
            "required": ["target"],
        }

    async def execute(self, input: dict[str, Any]) -> str:
        from core.engine.mcp.tools import ace_blast_radius

        try:
            result = await ace_blast_radius(target=input["target"], product_id=self._product_id)
            return _fmt(result)
        except Exception as exc:
            logger.warning("ace_blast_radius failed: %s", exc)
            return f"Blast radius error: {exc}"


class AceCodeContextTool(RuntimeTool):
    """Graph-grounded code context for a natural language query."""

    name: str = "ace_code_context"
    description: str = (
        "Get graph-grounded code context for a query — finds the most relevant files and symbols "
        "by traversing actual dependency relationships, not keyword search. "
        "Better than grep for 'what code is relevant to authentication?'"
    )
    is_read_only: bool = True

    def __init__(self, product_id: str) -> None:
        self._product_id = product_id

    def get_input_schema(self) -> dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "query": {
                    "type": "string",
                    "description": "Natural language query (e.g. 'authentication flow', 'database connection pooling').",
                },
            },
            "required": ["query"],
        }

    async def execute(self, input: dict[str, Any]) -> str:
        from core.engine.mcp.tools import ace_code_context

        try:
            result = await ace_code_context(query=input["query"], product_id=self._product_id)
            return _fmt(result)
        except Exception as exc:
            logger.warning("ace_code_context failed: %s", exc)
            return f"Code context error: {exc}"


class AceSymbolImportanceTool(RuntimeTool):
    """Rank files and symbols by architectural centrality."""

    name: str = "ace_symbol_importance"
    description: str = (
        "Get the most architecturally important files ranked by graph centrality (PageRank). "
        "High-centrality files are the load-bearing walls — changes to them ripple widely. "
        "Useful for identifying where to focus code review or testing effort."
    )
    is_read_only: bool = True

    def __init__(self, product_id: str) -> None:
        self._product_id = product_id

    def get_input_schema(self) -> dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "limit": {
                    "type": "integer",
                    "description": "Number of top symbols to return. Defaults to 20.",
                },
            },
            "required": [],
        }

    async def execute(self, input: dict[str, Any]) -> str:
        from core.engine.mcp.tools import ace_symbol_importance

        try:
            result = await ace_symbol_importance(
                limit=int(input.get("limit", 20)),
                product_id=self._product_id,
            )
            return _fmt(result)
        except Exception as exc:
            logger.warning("ace_symbol_importance failed: %s", exc)
            return f"Symbol importance error: {exc}"


class AceFindDeadCodeTool(RuntimeTool):
    """Identify unreferenced symbols and files."""

    name: str = "ace_find_dead_code"
    description: str = (
        "Find symbols and files that nothing in the codebase references. "
        "Dead code that can be safely removed or that indicates a broken import chain."
    )
    is_read_only: bool = True

    def __init__(self, product_id: str) -> None:
        self._product_id = product_id

    def get_input_schema(self) -> dict[str, Any]:
        return {
            "type": "object",
            "properties": {},
            "required": [],
        }

    async def execute(self, input: dict[str, Any]) -> str:
        from core.engine.mcp.tools import ace_find_dead_code

        try:
            result = await ace_find_dead_code(product_id=self._product_id)
            return _fmt(result)
        except Exception as exc:
            logger.warning("ace_find_dead_code failed: %s", exc)
            return f"Dead code search error: {exc}"


class AceDependencyChainTool(RuntimeTool):
    """Find the shortest dependency path between two files."""

    name: str = "ace_dependency_chain"
    description: str = (
        "Find the shortest dependency path between two files in the call graph. "
        "Useful for understanding why file A indirectly depends on file B, "
        "or tracing how a change propagates across modules."
    )
    is_read_only: bool = True

    def __init__(self, product_id: str) -> None:
        self._product_id = product_id

    def get_input_schema(self) -> dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "from_file": {
                    "type": "string",
                    "description": "Starting file path.",
                },
                "to_file": {
                    "type": "string",
                    "description": "Target file path.",
                },
            },
            "required": ["from_file", "to_file"],
        }

    async def execute(self, input: dict[str, Any]) -> str:
        from core.engine.mcp.tools import ace_dependency_chain

        try:
            result = await ace_dependency_chain(
                from_file=input["from_file"],
                to_file=input["to_file"],
                product_id=self._product_id,
            )
            return _fmt(result)
        except Exception as exc:
            logger.warning("ace_dependency_chain failed: %s", exc)
            return f"Dependency chain error: {exc}"


class AceModuleCouplingTool(RuntimeTool):
    """Measure coupling between two modules or directories."""

    name: str = "ace_module_coupling"
    description: str = (
        "Measure how tightly coupled two modules or directories are. "
        "High coupling means they tend to change together — a refactor signal. "
        "Returns coupling score and shared dependency count."
    )
    is_read_only: bool = True

    def __init__(self, product_id: str) -> None:
        self._product_id = product_id

    def get_input_schema(self) -> dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "module_a": {
                    "type": "string",
                    "description": "First module or directory path.",
                },
                "module_b": {
                    "type": "string",
                    "description": "Second module or directory path.",
                },
            },
            "required": ["module_a", "module_b"],
        }

    async def execute(self, input: dict[str, Any]) -> str:
        from core.engine.mcp.tools import ace_module_coupling

        try:
            result = await ace_module_coupling(
                module_a=input["module_a"],
                module_b=input["module_b"],
                product_id=self._product_id,
            )
            return _fmt(result)
        except Exception as exc:
            logger.warning("ace_module_coupling failed: %s", exc)
            return f"Module coupling error: {exc}"


# ---------------------------------------------------------------------------
# Factory helper
# ---------------------------------------------------------------------------


def _make_ace_tools(product_id: str, model: str = "claude-sonnet-4-6") -> dict[str, RuntimeTool]:
    """Return a dict of name → ACE tool instance for the given product."""
    tools: list[RuntimeTool] = [
        # Graph read/write
        AceGraphSearchTool(product_id),
        AceGraphLoadTool(product_id),
        AceProductContextTool(product_id),
        AceGraphCaptureTool(product_id),
        AceGraphDecisionTool(product_id),
        AceGraphIdeaTool(product_id),
        AceGraphErrorTool(product_id),
        AceSpawnAgentTool(product_id, model),
        AceSessionFlushTool(product_id),
        # Graph intelligence (Stream 8) — chain reaction detection
        AceBlastRadiusTool(product_id),
        AceCodeContextTool(product_id),
        AceSymbolImportanceTool(product_id),
        AceFindDeadCodeTool(product_id),
        AceDependencyChainTool(product_id),
        AceModuleCouplingTool(product_id),
    ]
    return {t.name: t for t in tools}


def make_ace_tools(product_id: str, model: str = "claude-sonnet-4-6") -> list[RuntimeTool]:
    """Return all ACE self-tools for the given product, ready to register."""
    return list(_make_ace_tools(product_id, model).values())
