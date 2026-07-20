# engine/orchestration/patterns/team.py
"""Pattern B: Agent Team — concurrent agents with live coordination.

Multiple agents run as concurrent asyncio tasks.  When any agent publishes
a ``DISCOVERY`` on the ``OrchestrationBus``, the pattern forwards it to
every *other* running agent via ``inject_message()``.  After all agents
complete, a synthesis agent merges results into a unified output.

This is the most complex pattern because it introduces real-time
cross-agent communication during execution rather than the sequential
handoff used by Pipeline (Pattern C) or the phased structure of
Adversarial (Pattern D).
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


class TeamPattern(PatternStrategy):
    """Pattern B: Multiple agents with live coordination via message bus.

    Agents run concurrently.  ``DISCOVERY`` messages are forwarded to all
    other running agents via ``inject_message()``.  After all complete, a
    synthesizer merges results.
    """

    @property
    def name(self) -> str:
        return "team"

    async def execute(
        self,
        task: str,
        config: PatternConfig,
        agent_configs: list[AgentConfig],
    ) -> PatternResult:
        self._validate_config(config)
        start = time.monotonic()

        if len(agent_configs) < 2:
            return PatternResult(
                run_id=config.run_id,
                pattern_name=self.name,
                status="failed",
                output="Team pattern requires at least 2 agents",
                duration_ms=0,
            )

        semaphore = asyncio.Semaphore(config.max_concurrent)

        # ------------------------------------------------------------------
        # Create all agents up front so the discovery-forwarding callback
        # can reference the complete roster.
        # ------------------------------------------------------------------
        agents: dict[str, object] = {}  # agent_id -> AgentShell
        agent_config_map: dict[str, AgentConfig] = {}  # agent_id -> AgentConfig

        for ac in agent_configs:
            shell = ComposedShell(
                system_prompt=ac.system_prompt,
                user_prompt=task,
                model=ac.model,
                tools=ac.tools,
                intel_context=config.intel_context,
            )
            agent = self.factory.create(ac, shell)
            agents[agent.agent_id] = agent
            agent_config_map[agent.agent_id] = ac

        # ------------------------------------------------------------------
        # Discovery forwarding: when any agent publishes DISCOVERY, inject
        # the message into every OTHER running agent.  Best-effort — if an
        # agent has already finished or rejects the injection, we skip it.
        # ------------------------------------------------------------------
        async def forward_discoveries(message: BusMessage) -> None:
            if message.type != MessageType.DISCOVERY:
                return
            if message.run_id != config.run_id:
                return  # isolate: only forward discoveries within this run
            for aid, agent in agents.items():
                if aid != message.source_agent_id:
                    try:
                        await agent.inject_message(message)
                    except Exception:
                        pass  # best effort

        self.bus.subscribe_global(forward_discoveries)

        # ------------------------------------------------------------------
        # Run all agents concurrently, bounded by the semaphore
        # ------------------------------------------------------------------
        async def run_agent(agent, ac: AgentConfig) -> AgentResult:
            async with semaphore:
                await self.bus.publish(
                    BusMessage(
                        type=MessageType.AGENT_SPAWNED,
                        source_agent_id=agent.agent_id,
                        run_id=config.run_id,
                        payload={"role": ac.role, "team_size": len(agents)},
                    )
                )
                try:
                    return await agent.execute(
                        task,
                        context={
                            "run_id": config.run_id,
                            "intel": config.intel_context,
                            "team_size": len(agents),
                        },
                    )
                except Exception as exc:
                    return AgentResult(
                        agent_id=agent.agent_id,
                        status="failed",
                        error=str(exc),
                    )

        agent_ids = list(agents.keys())
        results = await asyncio.gather(
            *[run_agent(agents[aid], agent_config_map[aid]) for aid in agent_ids],
            return_exceptions=False,
        )
        agent_results: list[AgentResult] = list(results)

        # Clean up per-agent subscriptions
        for aid in agent_ids:
            self.bus.unsubscribe(aid)

        # ------------------------------------------------------------------
        # Early exit if every agent failed
        # ------------------------------------------------------------------
        successful = [r for r in agent_results if r.status == "completed"]
        if not successful:
            duration = int((time.monotonic() - start) * 1000)
            return PatternResult(
                run_id=config.run_id,
                pattern_name=self.name,
                status="failed",
                output="All team agents failed",
                agent_results=agent_results,
                duration_ms=duration,
            )

        # ------------------------------------------------------------------
        # Skip synthesis if requested (e.g., parallel WIs in unrelated disciplines)
        # ------------------------------------------------------------------
        if config.metadata.get("skip_synthesis"):
            agent_outputs = "\n\n---\n\n".join(r.output for r in agent_results if r.output)
            duration = int((time.monotonic() - start) * 1000)
            return PatternResult(
                run_id=config.run_id,
                pattern_name=self.name,
                status="completed",
                output=agent_outputs,
                agent_results=agent_results,
                duration_ms=duration,
                metadata={
                    "team_size": len(agent_configs),
                    "successful": len(successful),
                    "synthesis_skipped": True,
                },
            )

        # ------------------------------------------------------------------
        # Synthesis: merge all agent outputs into a unified result
        # ------------------------------------------------------------------
        agent_outputs = "\n\n".join(
            f"### Agent {r.agent_id} ({r.status}):\n{r.output}" for r in agent_results if r.output
        )
        synthesis_prompt = (
            f"Synthesize these team member outputs for the task:\n"
            f"{task}\n\n{agent_outputs}\n\n"
            f"Produce a unified, coherent result that incorporates the "
            f"best from each perspective."
        )

        synthesis_config = AgentConfig(
            role="synthesizer",
            system_prompt="You synthesize multiple agent outputs into a coherent, balanced result.",
        )
        synthesis_shell = ComposedShell(
            system_prompt=synthesis_config.system_prompt,
            user_prompt=synthesis_prompt,
        )
        synth_agent = self.factory.create(synthesis_config, synthesis_shell)

        await self.bus.publish(
            BusMessage(
                type=MessageType.AGENT_SPAWNED,
                source_agent_id=synth_agent.agent_id,
                run_id=config.run_id,
                payload={"role": "synthesizer", "phase": "synthesis"},
            )
        )

        try:
            synth_result = await synth_agent.execute(
                synthesis_prompt,
                context={"run_id": config.run_id},
            )
        except Exception as exc:
            synth_result = AgentResult(
                agent_id=synth_agent.agent_id,
                status="failed",
                error=str(exc),
            )

        agent_results.append(synth_result)

        duration = int((time.monotonic() - start) * 1000)
        final_status = "completed" if synth_result.status == "completed" else "failed"
        return PatternResult(
            run_id=config.run_id,
            pattern_name=self.name,
            status=final_status,
            output=synth_result.output,
            agent_results=agent_results,
            duration_ms=duration,
            metadata={
                "team_size": len(agent_configs),
                "successful": len(successful),
            },
        )
