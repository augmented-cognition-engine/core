# engine/orchestration/shells/agent_sdk_shell.py
"""AgentSDKShell — agent shell using Claude Agent SDK query() for tool use.

Replaces the bespoke ``create_evolution_agent()`` in engine/evolution/agents.py
with a shell that satisfies the AgentShell protocol and integrates with the
orchestration bus.
"""

from __future__ import annotations

import time
from collections.abc import AsyncIterator
from typing import Any

from core.engine.orchestration.agent import AgentConfig, AgentResult
from core.engine.orchestration.bus import BusMessage, MessageType, OrchestrationBus
from core.engine.orchestration.shell import ComposedShell


class AgentSDKShell:
    """Agent shell using Claude Agent SDK query() for tool-using agents."""

    def __init__(
        self,
        agent_id: str,
        config: AgentConfig,
        shell: ComposedShell | None,
        bus: OrchestrationBus,
    ) -> None:
        self._agent_id = agent_id
        self._config = config
        self._shell = shell
        self._bus = bus
        self._cancelled = False

    @property
    def agent_id(self) -> str:
        return self._agent_id

    async def execute(self, task: str, context: dict[str, Any] | None = None) -> AgentResult:
        """Run agent via Claude Agent SDK query()."""
        start = time.monotonic()
        try:
            from pathlib import Path

            from claude_agent_sdk import ClaudeAgentOptions, query

            shell = self._shell or ComposedShell(system_prompt="", user_prompt=task)
            default_root = str(Path(__file__).resolve().parent.parent.parent.parent)
            cwd = self._config.metadata.get("cwd", default_root)
            system_prompt = shell.resolved_system_prompt()
            artifact_kind = str(self._config.metadata.get("i2_artifact_kind") or "")
            if artifact_kind:
                from core.engine.product.deliberation import attribution_instruction

                system_prompt += attribution_instruction(
                    artifact_kind,
                    contributor_ids=list(self._config.metadata.get("i2_contributor_ids") or []),
                )

            options = ClaudeAgentOptions(
                system_prompt=system_prompt,
                allowed_tools=shell.tools or self._config.tools or [],
                permission_mode="acceptEdits",
                cwd=cwd,
            )

            collected_text = ""
            async for message in query(prompt=shell.user_prompt, options=options):
                if hasattr(message, "content"):
                    for block in message.content:
                        if hasattr(block, "text"):
                            collected_text = block.text

            duration = int((time.monotonic() - start) * 1000)
            structured_output = None
            if artifact_kind:
                from core.engine.product.deliberation import extract_attribution_artifact

                collected_text, structured_output = extract_attribution_artifact(collected_text)

            await self._bus.publish(
                BusMessage(
                    type=MessageType.AGENT_COMPLETED,
                    source_agent_id=self._agent_id,
                    run_id=context.get("run_id", "") if context else "",
                    payload={"output_length": len(collected_text)},
                )
            )

            return AgentResult(
                agent_id=self._agent_id,
                status="completed",
                output=collected_text,
                duration_ms=duration,
                structured_output=structured_output,
                metadata={
                    "i2_artifact_kind": artifact_kind,
                    "i2_phase": self._config.metadata.get("i2_phase") or "execution",
                }
                if artifact_kind
                else {},
            )
        except Exception as e:
            duration = int((time.monotonic() - start) * 1000)
            return AgentResult(
                agent_id=self._agent_id,
                status="failed",
                error=str(e),
                duration_ms=duration,
                metadata={
                    "i2_artifact_kind": str(self._config.metadata.get("i2_artifact_kind") or "contribution"),
                    "i2_phase": self._config.metadata.get("i2_phase") or "execution",
                },
            )

    async def execute_streaming(self, task: str, context: dict[str, Any] | None = None) -> AsyncIterator[str]:
        """Streaming not fully supported for Agent SDK -- yields complete output."""
        result = await self.execute(task, context)
        yield result.output

    async def inject_message(self, message: Any) -> None:
        pass  # Agent SDK sessions don't support mid-execution injection

    async def cancel(self) -> None:
        self._cancelled = True
