# engine/orchestration/patterns/independent.py
"""Pattern A: Independent — single agent, single task.

The simplest pattern.  One agent receives the task, executes it, and
returns the result.  Useful for straightforward requests that don't
benefit from multi-agent coordination.
"""

from __future__ import annotations

import time
from typing import TYPE_CHECKING

from core.engine.orchestration.agent import AgentConfig, AgentResult
from core.engine.orchestration.bus import BusMessage, MessageType
from core.engine.orchestration.patterns.base import PatternConfig, PatternResult, PatternStrategy
from core.engine.orchestration.shell import ComposedShell

if TYPE_CHECKING:
    pass


class IndependentPattern(PatternStrategy):
    """Single-agent execution pattern.

    Takes the first ``AgentConfig`` (or creates a default executor) and
    runs the task to completion.  Emits an ``AGENT_SPAWNED`` event on
    the bus so observers can track execution.
    """

    @property
    def name(self) -> str:
        return "independent"

    async def execute(
        self,
        task: str,
        config: PatternConfig,
        agent_configs: list[AgentConfig],
    ) -> PatternResult:
        self._validate_config(config)
        start = time.monotonic()
        ac = agent_configs[0] if agent_configs else AgentConfig(role="executor")

        # Compose shell if system_prompt provided
        shell = (
            ComposedShell(
                system_prompt=ac.system_prompt,
                user_prompt=task,
                model=ac.model,
                tools=ac.tools,
                intel_context=config.intel_context,
            )
            if ac.system_prompt
            else None
        )

        agent = self.factory.create(ac, shell)

        await self.bus.publish(
            BusMessage(
                type=MessageType.AGENT_SPAWNED,
                source_agent_id=agent.agent_id,
                run_id=config.run_id,
                payload={"role": ac.role},
            )
        )

        try:
            if config.stream_tokens:
                result = await self._execute_streaming(agent, task, config)
            else:
                result = await agent.execute(task, context={"run_id": config.run_id, "intel": config.intel_context})
        except Exception as exc:
            duration = int((time.monotonic() - start) * 1000)
            failed_result = AgentResult(
                agent_id=agent.agent_id,
                status="failed",
                error=str(exc),
            )
            return PatternResult(
                run_id=config.run_id,
                pattern_name=self.name,
                status="failed",
                output=f"Agent execution failed: {exc}",
                agent_results=[failed_result],
                duration_ms=duration,
            )

        duration = int((time.monotonic() - start) * 1000)
        return PatternResult(
            run_id=config.run_id,
            pattern_name=self.name,
            status=result.status,
            output=result.output,
            agent_results=[result],
            duration_ms=duration,
        )

    async def _execute_streaming(
        self,
        agent,
        task: str,
        config: PatternConfig,
    ) -> AgentResult:
        """Execute with streaming — emit AgentToken events, accumulate output."""
        from core.engine.orchestration.events import AgentToken

        start = time.monotonic()
        full_output = ""

        try:
            async for token in agent.execute_streaming(
                task, context={"run_id": config.run_id, "intel": config.intel_context}
            ):
                full_output += token
                if config.event_bus:
                    await config.event_bus.emit(
                        AgentToken(
                            run_id=config.run_id,
                            product_id=config.product_id,
                            agent_id=agent.agent_id,
                            text=token,
                        )
                    )

            duration = int((time.monotonic() - start) * 1000)
            return AgentResult(
                agent_id=agent.agent_id,
                status="completed",
                output=full_output,
                duration_ms=duration,
            )
        except Exception as exc:
            duration = int((time.monotonic() - start) * 1000)
            return AgentResult(
                agent_id=agent.agent_id,
                status="failed",
                output=full_output,
                error=str(exc),
                duration_ms=duration,
            )
