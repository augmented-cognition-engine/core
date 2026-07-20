"""Progress indicators — tool summaries and agent status.

Tool use summaries: one-line descriptions of completed tool batches.
Agent progress: 3-5 word present-tense status updates.

Modeled on Claude Code's toolUseSummaryGenerator and agentSummary.
"""

from __future__ import annotations


class ProgressTracker:
    """Tracks tool execution and agent progress for display."""

    def __init__(self) -> None:
        self._tool_history: list[dict[str, str]] = []
        self._agent_status: str = ""

    def record_tool(self, name: str, summary: str) -> None:
        self._tool_history.append({"name": name, "summary": summary})

    def tool_summary(self) -> str:
        if not self._tool_history:
            return ""
        recent = self._tool_history[-5:]
        return " → ".join(f"{t['name']}: {t['summary'][:40]}" for t in recent)

    def set_agent_status(self, status: str) -> None:
        self._agent_status = status

    @property
    def agent_status(self) -> str:
        return self._agent_status

    def reset(self) -> None:
        self._tool_history.clear()
        self._agent_status = ""
