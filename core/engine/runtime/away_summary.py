"""Away summary — session reconnection recap via ACE's orchestrator.

Routes through the orchestrator as a documentation task with reactive mode,
so it gets classified, intelligence-loaded, and recorded like every other task.
"""

from __future__ import annotations

import logging

from core.engine.runtime.models import AssistantMessage, Message, UserMessage

logger = logging.getLogger(__name__)

RECENT_WINDOW = 30


class AwaySummary:
    """Generates a session reconnection recap."""

    def build_context(self, messages: list[Message], session_memory: str | None = None) -> str:
        recent = messages[-RECENT_WINDOW:]
        parts = []
        if session_memory:
            parts.append(f"Session memory:\n{session_memory}")
        for msg in recent:
            if isinstance(msg, UserMessage):
                parts.append(f"User: {msg.content[:200]}")
            elif isinstance(msg, AssistantMessage):
                parts.append(f"Assistant: {msg.content[:200]}")
        return "\n".join(parts)

    async def generate(
        self, messages: list[Message], session_memory: str | None = None, product_id: str = "product:platform"
    ) -> str:
        context = self.build_context(messages, session_memory)
        return await self._generate_via_orchestrator(context, product_id)

    async def _generate_via_orchestrator(self, context: str, product_id: str) -> str:
        """Route through the orchestrator for proper classification and recording."""
        try:
            from core.engine.orchestrator.executor import execute_task

            result = await execute_task(
                description=f"Generate a 1-3 sentence session recap. The user stepped away and is coming back. State the high-level task, then the concrete next step.\n\nContext:\n{context}",
                product_id=product_id,
                workspace_id="workspace:default",
                user_id="user:system",
            )
            return result.get("output", "")
        except Exception as exc:
            logger.warning("Away summary via orchestrator failed, falling back to direct LLM: %s", exc)
            return await self._fallback_direct(context)

    async def _fallback_direct(self, context: str) -> str:
        """Fallback if orchestrator is unavailable."""
        try:
            from core.engine.core.llm import get_llm

            llm = get_llm()
            return await llm.complete(
                f"Write 1-3 sentences. State the high-level task, then the next step.\n\n{context}",
            )
        except Exception as exc:
            logger.warning("Away summary direct fallback failed: %s", exc)
            return ""

    # Backward compat alias used by tests
    async def _call_llm(self, context: str) -> str:
        """Backward compat: delegates to _generate_via_orchestrator."""
        return await self._generate_via_orchestrator(context, "product:platform")
