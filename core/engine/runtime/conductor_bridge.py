# engine/runtime/conductor_bridge.py
"""Conductor bridge — conductor uses Runtime for execution.

The conductor (autonomous PM) switches from external harness to
ACE's own Runtime. Enforces the synthesis mandate: implementation-ready
specs with file paths, never lazy delegation.

Usage:
    bridge = ConductorBridge(product_id="product:platform")
    result = await bridge.execute_task("Fix the null pointer in auth.py:42")
    # Returns {"status": "complete", "output": "...", "messages": [...]}
"""

from __future__ import annotations

import logging
from typing import Any

logger = logging.getLogger(__name__)

LAZY_PHRASES = [
    "based on your findings",
    "based on the research",
    "based on what you found",
    "look into this",
    "investigate and fix",
]


class ConductorBridge:
    """Bridges the conductor to the Runtime for autonomous execution."""

    def __init__(
        self,
        product_id: str = "product:platform",
        model: str = "claude-sonnet-4-6",
    ) -> None:
        self._org_id = product_id
        self._model = model

    async def execute_task(self, description: str, **kwargs: Any) -> dict:
        """Execute a task through the ACE Runtime.

        Creates a Runtime instance, sends the task, collects all messages.
        Returns a result dict compatible with the conductor action system.
        """
        from core.engine.runtime.models import AssistantMessage
        from core.engine.runtime.runtime import Runtime

        runtime = Runtime(
            model=self._model,
            thinking="disabled",
            enable_intelligence=True,
            product_id=self._org_id,
        )

        output_parts: list[str] = []
        all_messages = []

        try:
            async for msg in runtime.chat(description):
                all_messages.append(msg)
                if isinstance(msg, AssistantMessage) and msg.content:
                    output_parts.append(msg.content)

            return {
                "status": "complete",
                "output": "\n".join(output_parts),
                "message_count": len(all_messages),
                "tokens": runtime.token_tracker.summary(),
            }
        except Exception as exc:
            logger.exception("ConductorBridge execution failed")
            return {
                "status": "error",
                "error": str(exc),
                "message_count": len(all_messages),
            }

    async def execute_spec(self, description: str) -> dict:
        """Execute a spec through the Runtime. Alias for execute_task."""
        return await self.execute_task(description)

    def build_worker_prompt(self, task: str, findings: str = "") -> str:
        """Build a worker prompt enforcing the synthesis mandate.

        The prompt must be self-contained with specific file paths
        and line numbers. Never delegate understanding.
        """
        parts = [task]
        if findings:
            parts.append(f"\nContext from research:\n{findings}")
        parts.append("\nCommit your changes and report the commit hash when done. Run relevant tests to verify.")
        return "\n".join(parts)

    def validate_prompt(self, prompt: str) -> list[str]:
        """Check prompt for lazy delegation phrases. Returns violations."""
        violations = []
        prompt_lower = prompt.lower()
        for phrase in LAZY_PHRASES:
            if phrase in prompt_lower:
                violations.append(f"Lazy delegation: '{phrase}'")
        return violations
