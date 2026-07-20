# engine/orchestration/testing.py
"""Test helpers for the orchestration layer.

Provides deterministic mocks and collectors that make it easy to write
fast, isolated tests for patterns and agents without hitting real LLMs
or databases.
"""

from __future__ import annotations

import asyncio
import json
from collections.abc import AsyncIterator
from typing import Any

from core.engine.orchestration.agent import AgentResult
from core.engine.orchestration.bus import BusMessage
from core.engine.orchestration.events import EventBus, OrchestratorEvent


class MockLLMProvider:
    """Deterministic LLM for testing. Returns canned responses."""

    def __init__(
        self,
        responses: dict[str, str] | None = None,
        default: str = "Mock response",
    ) -> None:
        self._responses = responses or {}
        self._default = default
        self.calls: list[dict[str, Any]] = []

    async def complete(
        self,
        prompt: str,
        model: str | None = None,
        max_tokens: int = 4096,
        system: str | list[dict] | None = None,
    ) -> str:
        self.calls.append({"method": "complete", "prompt": prompt, "model": model, "system": system})
        for key, response in self._responses.items():
            if key in prompt:
                return response
        return self._default

    async def complete_json(
        self, prompt: str, model: str | None = None, max_tokens: int = 4096, system: str | list[dict] | None = None
    ) -> dict:
        self.calls.append({"method": "complete_json", "prompt": prompt, "model": model})
        for key, response in self._responses.items():
            if key in prompt:
                return json.loads(response) if isinstance(response, str) else response
        return {}

    async def complete_structured(self, prompt: str, schema: type, model: str | None = None):
        self.calls.append({"method": "complete_structured", "prompt": prompt, "model": model})
        return schema()  # Return empty instance

    async def stream(self, prompt: str, model: str | None = None, max_tokens: int = 4096) -> AsyncIterator[str]:
        self.calls.append({"method": "stream", "prompt": prompt, "model": model})
        response = self._default
        for key, resp in self._responses.items():
            if key in prompt:
                response = resp
                break
        # Yield word by word
        for word in response.split():
            yield word + " "

    async def stream_messages(
        self,
        system: str,
        messages: list[dict],
        model: str | None = None,
        max_tokens: int = 4096,
    ) -> AsyncIterator[str]:
        self.calls.append({"method": "stream_messages", "system": system, "model": model})
        for word in self._default.split():
            yield word + " "


class EventCollector:
    """Collects events from an EventBus for test assertions."""

    def __init__(self, bus: EventBus) -> None:
        self._events: list[OrchestratorEvent] = []
        self._bus = bus
        self._task: asyncio.Task | None = None

    async def start(self) -> None:
        """Start collecting events in background."""

        async def _collect():
            async for event in self._bus.subscribe():
                self._events.append(event)

        self._task = asyncio.create_task(_collect())

    def stop(self) -> None:
        """Stop the background collection task."""
        if self._task:
            self._task.cancel()

    @property
    def events(self) -> list[OrchestratorEvent]:
        """Return a copy of all collected events."""
        return list(self._events)

    def of_type(self, event_type: str) -> list[OrchestratorEvent]:
        """Return only events matching *event_type*."""
        return [e for e in self._events if e.event_type == event_type]

    def assert_sequence(self, *event_types: str) -> None:
        """Assert the collected events match the given type sequence exactly."""
        actual = [e.event_type for e in self._events]
        assert actual == list(event_types), f"Expected {list(event_types)}, got {actual}"

    def assert_has(self, event_type: str) -> None:
        """Assert at least one event of the given type was collected."""
        assert any(e.event_type == event_type for e in self._events), (
            f"Expected event '{event_type}' not found. Events: {[e.event_type for e in self._events]}"
        )


class MockAgentShell:
    """A mock agent for testing patterns."""

    def __init__(
        self,
        agent_id: str = "mock_agent",
        output: str = "Mock output",
        status: str = "completed",
        delay: float = 0.0,
    ) -> None:
        self._agent_id = agent_id
        self._output = output
        self._status = status
        self._delay = delay
        self._messages: list[BusMessage] = []

    @property
    def agent_id(self) -> str:
        return self._agent_id

    async def execute(self, task: str, context: dict[str, Any] | None = None) -> AgentResult:
        if self._delay:
            await asyncio.sleep(self._delay)
        return AgentResult(
            agent_id=self._agent_id,
            status=self._status,
            output=self._output,
        )

    async def execute_streaming(self, task: str, context: dict[str, Any] | None = None) -> AsyncIterator[str]:
        for word in self._output.split():
            yield word + " "

    async def inject_message(self, message: Any) -> None:
        self._messages.append(message)

    async def cancel(self) -> None:
        pass
