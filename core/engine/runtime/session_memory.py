"""Session memory — structured running summary per conversation.

Sections map to ACE's knowledge categories, not Claude Code's template.
Updated incrementally based on token growth. Promoted to graph observations
at session end via promote_to_graph().
"""

from __future__ import annotations

import logging

logger = logging.getLogger(__name__)

MAX_SESSION_MEMORY_CHARS = 12000
MAX_SECTION_CHARS = 2000

# Trigger thresholds — tuned for ACE's intelligence-loaded prompts
# (higher init threshold because ACE prompts include discipline context)
MIN_TOKENS_TO_INIT = 10000
MIN_TOKEN_GROWTH = 5000
MIN_TOOL_CALLS = 3

SECTIONS = {
    "current_state": "Current State",
    "task": "Task Specification",
    "files_modified": "Files Modified",
    "decisions": "Decisions Made",
    "errors": "Errors & Corrections",
    "learnings": "Learnings",
}


class SessionMemory:
    """Structured running summary of the conversation."""

    def __init__(self) -> None:
        self._sections: dict[str, str] = {key: "" for key in SECTIONS}
        self._last_update_tokens: int = 0
        self._last_update_tool_calls: int = 0

    def update_section(self, key: str, content: str) -> None:
        """Update a specific section. Truncates if over cap."""
        if key in self._sections:
            self._sections[key] = content[:MAX_SECTION_CHARS]

    def get_content(self) -> str:
        """Get the full session memory as formatted markdown."""
        parts = []
        for key, title in SECTIONS.items():
            content = self._sections.get(key, "")
            section = f"## {title}\n{content}" if content else f"## {title}\n*No data yet*"
            parts.append(section)
        result = "\n\n".join(parts)
        return result[:MAX_SESSION_MEMORY_CHARS]

    def should_update(self, token_count: int, tool_calls: int) -> bool:
        """Check if session memory should be updated based on thresholds."""
        if token_count < MIN_TOKENS_TO_INIT:
            return False
        token_growth = token_count - self._last_update_tokens
        tool_growth = tool_calls - self._last_update_tool_calls
        if token_growth >= MIN_TOKEN_GROWTH and tool_growth >= MIN_TOOL_CALLS:
            return True
        # Natural break: token threshold met and no tool calls in last turn
        if token_growth >= MIN_TOKEN_GROWTH and tool_growth == 0:
            return True
        return False

    def mark_updated(self, token_count: int, tool_calls: int) -> None:
        """Record that an update was performed."""
        self._last_update_tokens = token_count
        self._last_update_tool_calls = tool_calls

    async def promote_to_graph(self, product_id: str = "product:platform") -> int:
        """Write non-empty sections as graph observations. Called at session end."""
        count = 0
        try:
            from core.engine.core.db import pool

            async with pool.connection() as db:
                for key, content in self._sections.items():
                    if not content or len(content) < 20:
                        continue
                    title = SECTIONS.get(key, key)
                    await db.query(
                        """CREATE observation SET
                            product = <record>$product,
                            content = $content,
                            observation_type = 'session_summary',
                            confidence = 0.8,
                            discipline_hint = 'architecture',
                            source_memory = 'session_memory',
                            synthesized = false,
                            created_at = time::now()""",
                        {"product": product_id, "content": f"[{title}] {content[:2000]}"},
                    )
                    count += 1
        except Exception as exc:
            logger.warning("Failed to promote session memory: %s", exc)
        return count
