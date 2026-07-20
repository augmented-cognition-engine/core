# engine/orchestration/composition.py
"""ComposedAgentShell -- wraps a PatternStrategy as an AgentShell.

The key insight: any ``PatternStrategy`` can be wrapped so it appears as
a single ``AgentShell``.  This enables infinite nesting:

- A Pipeline step can internally be a Team (Pattern B).
- An Adversarial pair can be one step in a Pipeline (Pattern C).
- A Team member can itself be a Pipeline.

The outer pattern sees this as a single agent with ``execute()``,
``inject_message()``, and ``cancel()``.  Internally it orchestrates
multiple agents via its own pattern strategy and bus.
"""

from __future__ import annotations

import logging
from collections.abc import AsyncIterator
from typing import Any

from core.engine.orchestration.agent import AgentConfig, AgentResult
from core.engine.orchestration.bus import BusMessage
from core.engine.orchestration.patterns.base import PatternConfig, PatternResult, PatternStrategy

logger = logging.getLogger(__name__)


class ComposedAgentShell:
    """Wraps a PatternStrategy as an AgentShell for pattern composition.

    Satisfies the ``AgentShell`` protocol so patterns can use it anywhere
    a regular agent is expected.  The ``execute()`` call delegates to the
    inner pattern's ``execute()``, maps the ``PatternResult`` back to an
    ``AgentResult``, and returns it.
    """

    def __init__(
        self,
        config: AgentConfig,
        inner_pattern: PatternStrategy,
        inner_config: PatternConfig,
        inner_agent_configs: list[AgentConfig],
    ) -> None:
        self._config = config
        self._inner_pattern = inner_pattern
        self._inner_config = inner_config
        self._inner_agent_configs = inner_agent_configs
        self._id = f"composed_{config.role}_{id(self)}"

    # -- AgentShell protocol -------------------------------------------------

    @property
    def agent_id(self) -> str:
        return self._id

    async def execute(
        self,
        task: str,
        context: dict[str, Any] | None = None,
    ) -> AgentResult:
        """Execute the inner pattern and return result as a single AgentResult."""
        # Propagate intel context from the outer pattern if available
        if context and "intel" in context:
            self._inner_config.intel_context = context["intel"]

        logger.debug(
            "ComposedAgentShell.execute: id=%s pattern=%s",
            self.agent_id,
            type(self._inner_pattern).__name__,
        )
        try:
            pattern_result: PatternResult = await self._inner_pattern.execute(
                task,
                self._inner_config,
                self._inner_agent_configs,
            )

            logger.debug(
                "ComposedAgentShell complete: id=%s status=%s agents=%d",
                self.agent_id,
                pattern_result.status,
                len(pattern_result.agent_results),
            )
            nested_error = None
            if pattern_result.status == "failed":
                nested_error = next(
                    (result.error for result in pattern_result.agent_results if result.error),
                    None,
                ) or (pattern_result.output or None)
            return AgentResult(
                agent_id=self.agent_id,
                status=pattern_result.status,
                output=pattern_result.output,
                error=nested_error,
                duration_ms=pattern_result.duration_ms,
                structured_output={
                    "inner_pattern": pattern_result.pattern_name,
                    "inner_agents": len(pattern_result.agent_results),
                    "inner_metadata": pattern_result.metadata,
                },
            )
        except Exception as exc:
            logger.warning("ComposedAgentShell.execute failed: id=%s error=%s", self.agent_id, exc)
            return AgentResult(
                agent_id=self.agent_id,
                status="failed",
                error=str(exc),
            )

    async def execute_streaming(
        self,
        task: str,
        context: dict[str, Any] | None = None,
    ) -> AsyncIterator[str]:
        """Streaming not supported for composed patterns -- yields final output.

        Composed patterns orchestrate multiple inner agents and only
        produce a meaningful output after all of them complete, so
        true token-level streaming is not possible.  We execute fully
        and yield the final output as a single chunk.
        """
        result = await self.execute(task, context)
        yield result.output or ""

    async def inject_message(self, message: BusMessage) -> None:
        """Forward message to inner pattern's bus.

        This allows the outer pattern (e.g. a Team) to push discovery
        messages into the nested pattern's bus, where they propagate
        to inner agents.
        """
        await self._inner_pattern.bus.publish(message)

    async def cancel(self) -> None:
        """Cancel the inner pattern.

        Currently a no-op -- inner patterns run to completion once
        started.  Future implementations may track inner tasks and
        cancel them.
        """
        pass
