# engine/orchestration/agent.py
"""Agent abstractions: config, result, and the AgentShell protocol.

AgentShell is the contract every shell implementation must satisfy.
It is runtime-checkable so patterns can assert compliance without
importing concrete classes.
"""

from __future__ import annotations

from collections.abc import AsyncIterator
from dataclasses import dataclass, field
from typing import Any, Protocol, runtime_checkable


@dataclass
class AgentConfig:
    """Everything needed to build an agent shell."""

    role: str
    system_prompt: str = ""
    model: str | None = None
    tools: list[str] | None = None
    use_agent_sdk: bool = False
    timeout_s: int = 300
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass
class AgentResult:
    """Outcome of a single agent execution."""

    agent_id: str
    status: str  # "completed" | "failed" | "timeout"
    output: str = ""
    duration_ms: int = 0
    error: str | None = None
    structured_output: dict[str, Any] | None = None


@runtime_checkable
class AgentShell(Protocol):
    """Protocol that all agent shell implementations must satisfy.

    Each shell wraps one execution backend (direct LLM, Agent SDK, mock)
    and exposes a uniform interface to the pattern strategies.
    """

    @property
    def agent_id(self) -> str: ...

    async def execute(self, task: str, context: dict[str, Any] | None = None) -> AgentResult: ...

    async def execute_streaming(self, task: str, context: dict[str, Any] | None = None) -> AsyncIterator[str]: ...

    async def inject_message(self, message: Any) -> None:
        """Inject a BusMessage into the agent's context.

        Uses ``Any`` to avoid circular imports with bus.py.
        """
        ...

    async def cancel(self) -> None: ...
