# engine/orchestration/shells/llm_shell.py
"""LLMShell — model-agnostic agent shell using the LLMProvider protocol.

Wraps ``complete()`` / ``stream()`` / ``stream_messages()`` from
engine.core.llm so that pattern strategies never touch the LLM directly.
"""

from __future__ import annotations

import asyncio
import time
from collections.abc import AsyncIterator
from typing import Any

from core.engine.orchestration.agent import AgentConfig, AgentResult
from core.engine.orchestration.bus import BusMessage, MessageType, OrchestrationBus
from core.engine.orchestration.shell import ComposedShell


class LLMShell:
    """Model-agnostic agent shell using LLMProvider protocol."""

    def __init__(
        self,
        agent_id: str,
        config: AgentConfig,
        shell: ComposedShell | None,
        llm,  # noqa: ANN001 — LLMProvider protocol
        bus: OrchestrationBus,
    ) -> None:
        self._agent_id = agent_id
        self._config = config
        self._shell = shell
        self._llm = llm
        self._bus = bus
        self._cancelled = False
        self._inbox: asyncio.Queue[BusMessage] = asyncio.Queue()

    @property
    def agent_id(self) -> str:
        return self._agent_id

    async def execute(self, task: str, context: dict[str, Any] | None = None) -> AgentResult:
        """Run agent to completion via llm.complete()."""
        start = time.monotonic()
        try:
            shell = self._shell or ComposedShell(system_prompt="", user_prompt=task)
            system_prompt = shell.resolved_system_prompt()

            # Pass system prompt properly via system= parameter
            output = await self._llm.complete(
                shell.user_prompt,
                system=system_prompt or None,
                model=shell.model or self._config.model,
            )

            duration = int((time.monotonic() - start) * 1000)

            await self._bus.publish(
                BusMessage(
                    type=MessageType.AGENT_COMPLETED,
                    source_agent_id=self._agent_id,
                    run_id=context.get("run_id", "") if context else "",
                    payload={"output_length": len(output)},
                )
            )

            return AgentResult(
                agent_id=self._agent_id,
                status="completed",
                output=output,
                duration_ms=duration,
            )
        except Exception as e:
            duration = int((time.monotonic() - start) * 1000)
            return AgentResult(
                agent_id=self._agent_id,
                status="failed",
                error=str(e),
                duration_ms=duration,
            )

    async def execute_streaming(self, task: str, context: dict[str, Any] | None = None) -> AsyncIterator[str]:
        """Run agent, yielding tokens."""
        shell = self._shell or ComposedShell(system_prompt="", user_prompt=task)
        system_prompt = shell.resolved_system_prompt()

        if shell.messages:
            messages = list(shell.messages) + [{"role": "user", "content": shell.user_prompt}]
            async for token in self._llm.stream_messages(
                system=system_prompt,
                messages=messages,
                model=shell.model or self._config.model,
            ):
                yield token
        else:
            prompt = f"{system_prompt}\n\nTask: {shell.user_prompt}" if system_prompt else shell.user_prompt
            async for token in self._llm.stream(
                prompt,
                model=shell.model or self._config.model,
            ):
                yield token

    async def inject_message(self, message: Any) -> None:
        await self._inbox.put(message)

    async def cancel(self) -> None:
        self._cancelled = True
