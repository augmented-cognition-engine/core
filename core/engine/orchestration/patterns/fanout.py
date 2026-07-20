# engine/orchestration/patterns/fanout.py
"""Pattern E: Fan-Out — parallel same-role agents, merged results.

N agents execute the same task concurrently (bounded by
``config.max_concurrent``).  Results are merged once all agents finish.
A single successful agent is enough for the pattern to report success.

This pattern is ideal for tasks that benefit from diverse perspectives
or redundancy (e.g. multiple research angles, voting, or best-of-N
generation).
"""

from __future__ import annotations

import asyncio
import time
from typing import TYPE_CHECKING

from core.engine.orchestration.agent import AgentConfig, AgentResult
from core.engine.orchestration.bus import BusMessage, MessageType
from core.engine.orchestration.patterns.base import PatternConfig, PatternResult, PatternStrategy
from core.engine.orchestration.shell import ComposedShell

if TYPE_CHECKING:
    pass


class FanOutPattern(PatternStrategy):
    """Parallel fan-out with merge.

    All agents receive the same task and run concurrently up to
    ``config.max_concurrent``.  Successful outputs are concatenated
    (or returned directly if only one agent succeeds).
    """

    @property
    def name(self) -> str:
        return "fanout"

    async def execute(
        self,
        task: str,
        config: PatternConfig,
        agent_configs: list[AgentConfig],
    ) -> PatternResult:
        self._validate_config(config)
        start = time.monotonic()

        if not agent_configs:
            return PatternResult(
                run_id=config.run_id,
                pattern_name=self.name,
                status="failed",
                output="Fan-out pattern requires at least 1 agent config",
                duration_ms=0,
            )

        semaphore = asyncio.Semaphore(config.max_concurrent)

        async def run_one(ac: AgentConfig) -> AgentResult:
            async with semaphore:
                shell = ComposedShell(
                    system_prompt=ac.system_prompt,
                    user_prompt=task,
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
                        payload={"role": ac.role},
                    )
                )

                try:
                    return await agent.execute(task, context={"run_id": config.run_id})
                except Exception as exc:
                    return AgentResult(
                        agent_id=agent.agent_id,
                        status="failed",
                        error=str(exc),
                    )

        # Fan out: all agents run concurrently (bounded by semaphore)
        results = await asyncio.gather(*[run_one(ac) for ac in agent_configs])
        agent_results = list(results)

        # Merge: concatenate successful outputs
        successful = [r for r in agent_results if r.status == "completed"]

        if not successful:
            duration = int((time.monotonic() - start) * 1000)
            return PatternResult(
                run_id=config.run_id,
                pattern_name=self.name,
                status="failed",
                output="All agents failed",
                agent_results=agent_results,
                duration_ms=duration,
            )

        # Simple merge: single result used directly; multiple concatenated
        if len(successful) == 1:
            merged = successful[0].output
        else:
            merged = "\n\n---\n\n".join(f"### {r.agent_id}:\n{r.output}" for r in successful)

        duration = int((time.monotonic() - start) * 1000)
        return PatternResult(
            run_id=config.run_id,
            pattern_name=self.name,
            status="completed",
            output=merged,
            agent_results=agent_results,
            duration_ms=duration,
            metadata={
                "total_agents": len(agent_configs),
                "successful": len(successful),
            },
        )
