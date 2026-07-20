# engine/orchestration/patterns/base.py
"""Base abstractions for pattern strategies.

Every pattern (independent, team, pipeline, adversarial, fanout) extends
``PatternStrategy`` and implements ``execute()``.  The orchestrator picks
the right strategy at plan time and delegates execution.
"""

from __future__ import annotations

import logging
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any

from core.engine.core.exceptions import ValidationError

logger = logging.getLogger(__name__)

if TYPE_CHECKING:
    from core.engine.orchestration.agent import AgentConfig, AgentResult
    from core.engine.orchestration.bus import OrchestrationBus
    from core.engine.orchestration.factory import AgentFactory


@dataclass
class PatternConfig:
    """Execution parameters shared across all patterns."""

    run_id: str
    product_id: str
    workspace_id: str = "workspace:default"
    user_id: str = "user:system"
    intel_context: str = ""
    timeout_seconds: int = 600
    max_concurrent: int = 5
    stream_tokens: bool = False
    event_bus: Any = None  # EventBus instance, optional — used for AgentToken events
    conversation_messages: list[dict[str, Any]] | None = None
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass
class PatternResult:
    """Aggregate result returned by a pattern strategy."""

    run_id: str
    pattern_name: str
    status: str  # "completed" | "failed" | "timeout"
    output: str = ""
    agent_results: list[AgentResult] = field(default_factory=list)
    duration_ms: int = 0
    metadata: dict[str, Any] = field(default_factory=dict)


class PatternStrategy(ABC):
    """Abstract base for all orchestration pattern strategies.

    Subclasses are instantiated with a shared ``OrchestrationBus`` and an
    ``AgentFactory`` that can spawn ``AgentShell`` instances on demand.
    """

    def __init__(self, bus: OrchestrationBus, factory: AgentFactory) -> None:
        self.bus = bus
        self.factory = factory

    def _validate_config(self, config: PatternConfig) -> None:
        """Validate a PatternConfig before pattern execution begins.

        Raises ValidationError for out-of-range timeout or concurrency values
        that would cause the pattern to either timeout immediately or spawn an
        unbounded number of agents.
        """
        if not config.product_id or ":" not in config.product_id:
            raise ValidationError(f"Invalid product_id in PatternConfig: {config.product_id!r}")
        if config.timeout_seconds <= 0:
            raise ValidationError(f"timeout_seconds must be positive, got {config.timeout_seconds}")
        if config.max_concurrent < 1:
            raise ValidationError(f"max_concurrent must be >= 1, got {config.max_concurrent}")

    @property
    @abstractmethod
    def name(self) -> str:
        """Short identifier for this pattern (e.g. ``"independent"``)."""
        ...

    @abstractmethod
    async def execute(
        self,
        task: str,
        config: PatternConfig,
        agent_configs: list[AgentConfig],
    ) -> PatternResult:
        """Run the pattern to completion and return aggregated results.

        Raises:
            OrchestrationError: If the pattern cannot execute (e.g. no agents,
                timeout exceeded, dependency cycle detected).
        """
        ...
