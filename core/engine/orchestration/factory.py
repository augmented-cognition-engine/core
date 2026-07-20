# engine/orchestration/factory.py
"""AgentFactory — creates concrete shell instances from AgentConfig.

The factory inspects ``config.use_agent_sdk`` to decide between LLMShell
(direct LLM calls) and AgentSDKShell (Claude Agent SDK with tool use).
Shell imports are deferred so the factory module stays lightweight.
"""

from __future__ import annotations

import uuid

from core.engine.orchestration.agent import AgentConfig, AgentShell
from core.engine.orchestration.bus import OrchestrationBus
from core.engine.orchestration.shell import ComposedShell


class AgentFactory:
    """Creates AgentShell instances from AgentConfig."""

    def __init__(self, llm_provider, bus: OrchestrationBus) -> None:  # noqa: ANN001
        self._llm = llm_provider
        self._bus = bus

    def create(self, config: AgentConfig, shell: ComposedShell | None = None) -> AgentShell:
        """Create an agent shell from config.

        If config.use_agent_sdk is True, creates AgentSDKShell.
        Otherwise creates LLMShell.
        """
        agent_id = f"{config.role}_{uuid.uuid4().hex[:8]}"

        if config.use_agent_sdk:
            from core.engine.orchestration.shells.agent_sdk_shell import AgentSDKShell

            return AgentSDKShell(
                agent_id=agent_id,
                config=config,
                shell=shell,
                bus=self._bus,
            )
        else:
            from core.engine.orchestration.shells.llm_shell import LLMShell

            return LLMShell(
                agent_id=agent_id,
                config=config,
                shell=shell,
                llm=self._llm,
                bus=self._bus,
            )
