# engine/orchestration/patterns/adversarial.py
"""Pattern D: Adversarial — independent positions, challenge, synthesis.

Three-phase execution:

1. **Independent** — every agent produces output in isolation.
2. **Challenge** — each agent reviews the others' positions and critiques.
   Supports multiple rounds via ``config.metadata["rounds"]``.
3. **Synthesis** — a dedicated synthesizer merges all positions and
   challenges into a single balanced result.

This pattern replaces the hard-coded generator/evaluator logic in
``engine/evolution/experiment.py`` with a reusable strategy that the
orchestrator can select at plan time.
"""

from __future__ import annotations

import asyncio
import logging
import time
from dataclasses import replace
from typing import TYPE_CHECKING

from core.engine.orchestration.agent import AgentConfig, AgentResult
from core.engine.orchestration.bus import BusMessage, MessageType
from core.engine.orchestration.patterns.base import PatternConfig, PatternResult, PatternStrategy
from core.engine.orchestration.shell import ComposedShell

if TYPE_CHECKING:
    pass

logger = logging.getLogger(__name__)

CONVERGE_ACTIONS = {"AGREE", "CONCEDE"}


def _check_convergence(challenge_outputs: list[dict], threshold: float = 0.8) -> bool:
    """Check if >threshold of agents chose AGREE or CONCEDE actions."""
    if not challenge_outputs:
        return False
    converged = 0
    for co in challenge_outputs:
        first_line = co["output"].strip().split("\n")[0].upper()
        action = first_line.strip().rstrip(".:!")
        if action in CONVERGE_ACTIONS:
            converged += 1
    return (converged / len(challenge_outputs)) >= threshold


class AdversarialPattern(PatternStrategy):
    """Multi-agent adversarial pattern with challenge and synthesis phases.

    Requires at least two agent configs.  A third synthesizer agent is
    created internally unless one of the supplied configs has role
    ``"synthesizer"``.

    Optional metadata fields (via ``PatternConfig.metadata``):
    - ``rounds`` (int, default 1): number of challenge rounds to run.
    - ``constrained_actions`` (bool, default False): if True, agents must
      begin their challenge response with a vocabulary action word, and
      convergence (>= 80% AGREE/CONCEDE) triggers early exit.
    """

    @property
    def name(self) -> str:
        return "adversarial"

    async def execute(
        self,
        task: str,
        config: PatternConfig,
        agent_configs: list[AgentConfig],
    ) -> PatternResult:
        self._validate_config(config)
        start = time.monotonic()
        rounds = config.metadata.get("rounds", 1)
        constrained_actions = config.metadata.get("constrained_actions", False)
        agent_results: list[AgentResult] = []

        if len(agent_configs) < 2:
            return PatternResult(
                run_id=config.run_id,
                pattern_name=self.name,
                status="failed",
                output="Adversarial pattern requires at least 2 agents",
                duration_ms=0,
            )

        # ------------------------------------------------------------------
        # Phase 1: Independent execution (parallel — agents don't see
        # each other's output until the challenge phase)
        # ------------------------------------------------------------------
        independent_outputs: list[dict] = []

        async def _run_independent(ac: AgentConfig) -> tuple[AgentConfig, AgentResult]:
            ac = replace(
                ac,
                metadata={
                    **ac.metadata,
                    "i2_artifact_kind": "contribution",
                    "i2_phase": "adversarial_position",
                },
            )
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
                    payload={"role": ac.role, "phase": "independent"},
                )
            )

            try:
                result = await agent.execute(task, context={"run_id": config.run_id})
            except Exception as exc:
                result = AgentResult(
                    agent_id=agent.agent_id,
                    status="failed",
                    error=str(exc),
                )

            result.metadata = {
                **result.metadata,
                "i2_artifact_kind": "contribution",
                "i2_phase": "adversarial_position",
            }

            await self.bus.publish(
                BusMessage(
                    type=MessageType.POSITION_SUBMITTED,
                    source_agent_id=agent.agent_id,
                    run_id=config.run_id,
                    payload={"role": ac.role, "output_length": len(result.output)},
                )
            )
            return ac, result

        phase1_results = await asyncio.gather(
            *[_run_independent(ac) for ac in agent_configs],
            return_exceptions=False,
        )

        for ac, result in phase1_results:
            agent_results.append(result)
            independent_outputs.append(
                {
                    "role": ac.role,
                    "output": result.output,
                    "agent_id": result.agent_id,
                }
            )

        # Bail out early if all independent outputs failed
        if all(r.status == "failed" for r in agent_results):
            duration = int((time.monotonic() - start) * 1000)
            return PatternResult(
                run_id=config.run_id,
                pattern_name=self.name,
                status="failed",
                output="All agents failed in the independent phase",
                agent_results=agent_results,
                duration_ms=duration,
            )

        # ------------------------------------------------------------------
        # Phase 2: Challenge — multi-round, each agent critiques the others
        # ------------------------------------------------------------------
        all_challenge_outputs: list[list[dict]] = []
        current_positions = independent_outputs[:]

        for round_num in range(1, rounds + 1):
            round_challenge_outputs: list[dict] = []

            for i, ac in enumerate(agent_configs):
                ac = replace(
                    ac,
                    metadata={
                        **ac.metadata,
                        "i2_artifact_kind": "challenge",
                        "i2_phase": f"challenge_round_{round_num}",
                        "i2_contributor_ids": [item["agent_id"] for item in independent_outputs],
                    },
                )
                others = [o for j, o in enumerate(current_positions) if j != i]
                others_text = "\n\n".join(
                    f"### Contributor {o.get('agent_id', 'unreported')} ({o['role']}):\n{o['output']}" for o in others
                )
                challenge_prompt = (
                    f"You previously produced this output:\n"
                    f"{current_positions[i]['output']}\n\n"
                    f"Here are the other perspectives:\n{others_text}\n\n"
                    f"Now challenge these other perspectives. What did they miss? "
                    f"What did they get wrong? What would you change in your own "
                    f"position after seeing theirs?"
                )

                if constrained_actions:
                    challenge_prompt += (
                        "\n\nYou MUST begin your response by choosing one action: "
                        "AGREE, CHALLENGE, REFINE, PROPOSE_ALTERNATIVE, or CONCEDE"
                    )

                shell = ComposedShell(
                    system_prompt=ac.system_prompt,
                    user_prompt=challenge_prompt,
                    model=ac.model,
                    tools=ac.tools,
                )
                agent = self.factory.create(ac, shell)

                await self.bus.publish(
                    BusMessage(
                        type=MessageType.CHALLENGE_ISSUED,
                        source_agent_id=agent.agent_id,
                        run_id=config.run_id,
                        payload={"role": ac.role, "phase": "challenge", "round": round_num},
                    )
                )

                try:
                    result = await agent.execute(challenge_prompt, context={"run_id": config.run_id})
                except Exception as exc:
                    result = AgentResult(
                        agent_id=agent.agent_id,
                        status="failed",
                        error=str(exc),
                    )

                result.metadata = {
                    **result.metadata,
                    "i2_artifact_kind": "challenge",
                    "i2_phase": f"challenge_round_{round_num}",
                }

                agent_results.append(result)
                round_challenge_outputs.append(
                    {
                        "role": ac.role,
                        "output": result.output,
                        "agent_id": independent_outputs[i]["agent_id"],
                    }
                )

            all_challenge_outputs.append(round_challenge_outputs)
            # Update current_positions to the outputs from this round
            current_positions = round_challenge_outputs

            # Early exit if constrained actions and convergence detected
            if constrained_actions and _check_convergence(round_challenge_outputs):
                logger.info(
                    "Adversarial convergence detected after round %d — stopping early",
                    round_num,
                )
                break

        # ------------------------------------------------------------------
        # Phase 3: Synthesis — incorporates all challenge rounds
        # ------------------------------------------------------------------
        all_text = "\n\n".join(
            f"### Contributor {o['agent_id']} ({o['role']}, position):\n{o['output']}" for o in independent_outputs
        )
        for round_idx, round_outputs in enumerate(all_challenge_outputs, start=1):
            all_text += f"\n\n---\n\n## Round {round_idx} Challenges\n\n"
            all_text += "\n\n".join(
                f"### {o['role']} (challenge round {round_idx}):\n{o['output']}" for o in round_outputs
            )

        synthesis_prompt = (
            f"Synthesize these positions and challenges into a unified, "
            f"balanced output for the task:\n\n{task}\n\n{all_text}\n\n"
            f"Produce a final synthesis that accounts for all perspectives "
            f"and challenges."
        )

        synthesis_config = AgentConfig(
            role="synthesizer",
            system_prompt=("You synthesize multiple agent outputs into a coherent, balanced result."),
            metadata={
                "i2_artifact_kind": "synthesis",
                "i2_phase": "synthesis",
                "i2_contributor_ids": [item["agent_id"] for item in independent_outputs],
            },
        )
        shell = ComposedShell(
            system_prompt=synthesis_config.system_prompt,
            user_prompt=synthesis_prompt,
        )
        synth_agent = self.factory.create(synthesis_config, shell)

        await self.bus.publish(
            BusMessage(
                type=MessageType.AGENT_SPAWNED,
                source_agent_id=synth_agent.agent_id,
                run_id=config.run_id,
                payload={"role": "synthesizer", "phase": "synthesis"},
            )
        )

        try:
            synth_result = await synth_agent.execute(synthesis_prompt, context={"run_id": config.run_id})
        except Exception as exc:
            synth_result = AgentResult(
                agent_id=synth_agent.agent_id,
                status="failed",
                error=str(exc),
            )

        synth_result.metadata = {
            **synth_result.metadata,
            "i2_artifact_kind": "synthesis",
            "i2_phase": "synthesis",
        }

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
                "positions": len(independent_outputs),
                "challenges": sum(len(rc) for rc in all_challenge_outputs),
                "rounds": len(all_challenge_outputs),
            },
        )
