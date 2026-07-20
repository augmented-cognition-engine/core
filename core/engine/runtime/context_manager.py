# engine/runtime/context_manager.py
"""Context manager — graph-backed context rotation for the ACE Runtime.

Unlike Claude Code (which LLM-summarizes and discards), ACE rotates context:
intelligence is already in the graph via auto-extract, so compaction is just
dropping stale working data and re-loading fresh context from the graph.

Three tiers, from cheapest to most aggressive:

Tier 1: Microcompact — clear old tool results with [Cleared]
Tier 2: Drop + Reload — drop old messages, re-inject relevant graph intelligence
Tier 3: Emergency — session memory swap (last resort, zero API calls)

Key insight: nothing is LOST during compaction. The auto-extract pipeline
already captured observations to the graph. Compaction is context rotation,
not context loss.

Circuit breaker: stops after 3 consecutive failures.
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

from core.engine.runtime.models import (
    Message,
    ToolResultMessage,
    UserMessage,
)

if TYPE_CHECKING:
    from core.engine.runtime.intelligence import IntelligenceLayer
    from core.engine.runtime.session_memory import SessionMemory

logger = logging.getLogger(__name__)

MAX_CONSECUTIVE_FAILURES = 3


class ContextManager:
    """Manages context window size through graph-backed context rotation."""

    def __init__(self) -> None:
        self._consecutive_failures = 0
        self._compaction_count = 0

    @property
    def compaction_count(self) -> int:
        return self._compaction_count

    def compact(
        self,
        messages: list[Message],
        intelligence: "IntelligenceLayer | None" = None,
        session_memory: "SessionMemory | None" = None,
        current_query: str = "",
    ) -> list[Message]:
        """Run the compaction pipeline. Tries each tier in order.

        Returns compacted messages. The graph ensures nothing is truly lost.
        """
        if self._consecutive_failures >= MAX_CONSECUTIVE_FAILURES:
            logger.warning("Compaction circuit breaker tripped (%d failures)", self._consecutive_failures)
            return messages

        try:
            # Tier 1: Always run microcompact first (cheapest)
            result = self.microcompact(messages)

            # If still too many messages, try drop + reload
            if len(result) > 40:
                result = self.drop_and_reload(
                    result,
                    intelligence=intelligence,
                    session_memory=session_memory,
                    current_query=current_query,
                )

            # If STILL too many, emergency session memory swap
            if len(result) > 40 and session_memory:
                result = self.emergency_compact(result, session_memory)

            self._consecutive_failures = 0
            self._compaction_count += 1
            return result

        except Exception:
            self._consecutive_failures += 1
            logger.exception("Compaction failed (attempt %d)", self._consecutive_failures)
            return messages

    # ------------------------------------------------------------------
    # Tier 1: Microcompact — clear old tool results
    # ------------------------------------------------------------------

    def microcompact(
        self,
        messages: list[Message],
        keep_recent: int = 5,
    ) -> list[Message]:
        """Clear old tool results, keeping the N most recent.

        Replaces old ToolResultMessage content with '[Cleared]'.
        Cheapest compaction — no API calls, no information loss
        (auto-extract already captured anything important).
        """
        tool_result_indices = [i for i, m in enumerate(messages) if isinstance(m, ToolResultMessage)]

        if len(tool_result_indices) <= keep_recent:
            return messages

        to_clear = set(tool_result_indices[:-keep_recent])

        result = []
        for i, msg in enumerate(messages):
            if i in to_clear and isinstance(msg, ToolResultMessage):
                result.append(
                    ToolResultMessage(
                        tool_use_id=msg.tool_use_id,
                        content="[Cleared]",
                        is_error=msg.is_error,
                    )
                )
            else:
                result.append(msg)
        return result

    # ------------------------------------------------------------------
    # Tier 2: Drop + Reload — the ACE-native approach
    # ------------------------------------------------------------------

    def drop_and_reload(
        self,
        messages: list[Message],
        intelligence: "IntelligenceLayer | None" = None,
        session_memory: "SessionMemory | None" = None,
        current_query: str = "",
        keep_recent_exchanges: int = 5,
    ) -> list[Message]:
        """Drop old messages, re-inject graph intelligence.

        This is ACE's unique advantage over Claude Code:
        - Claude Code summarizes and discards (lossy)
        - ACE drops and reloads from graph (lossless)

        The auto-extract pipeline already captured important observations.
        We just keep recent exchanges and re-inject relevant intelligence.
        """
        # Find exchange boundaries (each user message starts an exchange)
        user_indices = [i for i, m in enumerate(messages) if isinstance(m, UserMessage) and not m.is_meta]

        if len(user_indices) <= keep_recent_exchanges:
            return messages  # not enough to drop

        # Keep the last N exchanges
        keep_from = user_indices[-keep_recent_exchanges]
        recent_messages = messages[keep_from:]

        # Build the reload context
        reload_parts: list[str] = []

        # 1. Session memory (structured summary of what happened)
        if session_memory:
            memory_content = session_memory.get_content()
            # Check if at least one section has real content (not all "No data yet")
            section_count = memory_content.count("##")
            empty_count = memory_content.count("No data yet")
            if memory_content and empty_count < section_count:
                reload_parts.append(f"<session-context>\n{memory_content}\n</session-context>")

        # 2. Cached graph intelligence (already loaded, zero cost)
        if intelligence and intelligence.last_classification:
            cached = intelligence.get_cached(intelligence.last_classification.get("discipline", ""))
            if cached:
                reload_parts.append(f"<intelligence-context>\n{cached}\n</intelligence-context>")

        # 3. Summary of what was dropped
        dropped_count = keep_from
        dropped_user_msgs = [m for m in messages[:keep_from] if isinstance(m, UserMessage) and not m.is_meta]
        if dropped_user_msgs:
            topics = [m.content[:80] for m in dropped_user_msgs[-3:]]
            reload_parts.append(
                f"<dropped-context>\n"
                f"Earlier conversation ({dropped_count} messages) covered:\n"
                + "\n".join(f"- {t}" for t in topics)
                + "\nFull intelligence is preserved in the graph.\n"
                "</dropped-context>"
            )

        # Build the reload message
        if reload_parts:
            reload_msg = UserMessage(
                content="\n\n".join(reload_parts) + "\n\nThe conversation continues:",
                is_meta=True,
            )
            return [reload_msg] + recent_messages

        return recent_messages

    # ------------------------------------------------------------------
    # Tier 3: Emergency — session memory swap
    # ------------------------------------------------------------------

    def emergency_compact(
        self,
        messages: list[Message],
        session_memory: "SessionMemory",
        keep_recent: int = 2,
    ) -> list[Message]:
        """Last resort: replace everything with session memory.

        Only used when Tier 1 + Tier 2 aren't enough. Zero API calls.
        """
        memory_content = session_memory.get_content()

        user_indices = [i for i, m in enumerate(messages) if isinstance(m, UserMessage) and not m.is_meta]
        keep_from = user_indices[-keep_recent] if len(user_indices) > keep_recent else 0

        summary_msg = UserMessage(
            content=(
                f"<emergency-compact>\n"
                f"Previous conversation was compacted. Session summary:\n\n"
                f"{memory_content}\n"
                f"</emergency-compact>\n\n"
                f"Continue from here:"
            ),
            is_meta=True,
        )
        return [summary_msg] + messages[keep_from:]
