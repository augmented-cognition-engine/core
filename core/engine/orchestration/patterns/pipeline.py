# engine/orchestration/patterns/pipeline.py
"""Pattern C: Pipeline — sequential specialists with handoffs.

Each agent in the pipeline receives the original task plus the accumulated
output from all prior steps.  If any step fails the pipeline halts and
reports the failure.  ``HANDOFF`` events are emitted between steps so the
bus can track progression.

This pattern generalises the existing skill executor's Job chain into a
first-class orchestration strategy.
"""

from __future__ import annotations

import time
from typing import TYPE_CHECKING

from core.engine.orchestration.agent import AgentConfig
from core.engine.orchestration.bus import BusMessage, MessageType
from core.engine.orchestration.patterns.base import PatternConfig, PatternResult, PatternStrategy
from core.engine.orchestration.shell import ComposedShell

if TYPE_CHECKING:
    pass


class PipelinePattern(PatternStrategy):
    """Sequential specialist chain.

    Agents execute one at a time.  Each step's output is appended to a
    growing context block that subsequent agents receive alongside the
    original task.
    """

    @property
    def name(self) -> str:
        return "pipeline"

    async def execute(
        self,
        task: str,
        config: PatternConfig,
        agent_configs: list[AgentConfig],
    ) -> PatternResult:
        self._validate_config(config)
        start = time.monotonic()
        accumulated_context = ""
        agent_results: list = []
        last_output = ""

        if not agent_configs:
            return PatternResult(
                run_id=config.run_id,
                pattern_name=self.name,
                status="failed",
                output="Pipeline pattern requires at least 1 agent config",
                duration_ms=0,
            )

        for i, ac in enumerate(agent_configs):
            # Build shell with accumulated context from prior steps
            step_prompt = task if i == 0 else f"{task}\n\n## Prior Steps Output\n{accumulated_context}"

            # Pass conversation context only to the first step; subsequent steps
            # build on accumulated pipeline output rather than the chat history.
            messages = config.conversation_messages if i == 0 else None

            shell = ComposedShell(
                system_prompt=ac.system_prompt,
                user_prompt=step_prompt,
                messages=messages,
                model=ac.model,
                tools=ac.tools,
                intel_context=config.intel_context,
            )

            agent = self.factory.create(ac, shell)

            await self.bus.publish(
                BusMessage(
                    type=MessageType.AGENT_SPAWNED,
                    source_agent_id=agent.agent_id,
                    run_id=config.run_id,
                    payload={
                        "role": ac.role,
                        "step": i + 1,
                        "total_steps": len(agent_configs),
                    },
                )
            )

            try:
                result = await agent.execute(
                    step_prompt,
                    context={
                        "run_id": config.run_id,
                        "intel": config.intel_context,
                        "conversation": config.conversation_messages,
                    },
                )
            except Exception as exc:
                from core.engine.orchestration.agent import AgentResult

                result = AgentResult(
                    agent_id=agent.agent_id,
                    status="failed",
                    error=str(exc),
                )

            agent_results.append(result)

            if result.status == "failed":
                duration = int((time.monotonic() - start) * 1000)
                return PatternResult(
                    run_id=config.run_id,
                    pattern_name=self.name,
                    status="failed",
                    output=f"Step {i + 1} ({ac.role}) failed: {result.error}",
                    agent_results=agent_results,
                    duration_ms=duration,
                )

            last_output = result.output
            accumulated_context += f"\n### Step {i + 1}: {ac.role}\n{result.output}\n"

            # Emit handoff event (except for last step)
            if i < len(agent_configs) - 1:
                next_role = agent_configs[i + 1].role
                await self.bus.publish(
                    BusMessage(
                        type=MessageType.HANDOFF,
                        source_agent_id=agent.agent_id,
                        run_id=config.run_id,
                        payload={
                            "from_role": ac.role,
                            "to_role": next_role,
                            "context_summary": result.output[:200],
                        },
                    )
                )

        duration = int((time.monotonic() - start) * 1000)
        return PatternResult(
            run_id=config.run_id,
            pattern_name=self.name,
            status="completed",
            output=last_output,
            agent_results=agent_results,
            duration_ms=duration,
        )
