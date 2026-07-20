"""OpenAI model adapter — stub for GPT models.

Full implementation requires openai SDK. This provides the interface
and a minimal implementation that will work once the SDK is installed.
"""

from __future__ import annotations

import logging
from typing import Any, AsyncIterator

from core.engine.runtime.models import AssistantMessage, ToolUseBlock

logger = logging.getLogger(__name__)


class OpenAIAdapter:
    """Adapter for OpenAI models (GPT-4o, o1, o3, etc.)."""

    def __init__(self, model: str = "gpt-4o", api_key: str | None = None) -> None:
        self._model = model
        self._api_key = api_key

    async def call_model(
        self,
        system: str,
        messages: list[dict[str, Any]],
        tools: list[dict[str, Any]],
        *,
        max_tokens: int = 8192,
        thinking: str = "adaptive",
    ) -> AsyncIterator[AssistantMessage]:
        """Call OpenAI with tool-use support."""
        try:
            from openai import AsyncOpenAI

            client = AsyncOpenAI(api_key=self._api_key)

            openai_tools = (
                [
                    {
                        "type": "function",
                        "function": {
                            "name": t["name"],
                            "description": t.get("description", ""),
                            "parameters": t.get("input_schema", {}),
                        },
                    }
                    for t in tools
                ]
                if tools
                else None
            )

            openai_messages = [{"role": "system", "content": system}]
            for msg in messages:
                openai_messages.append(msg)

            response = await client.chat.completions.create(
                model=self._model,
                messages=openai_messages,
                tools=openai_tools,
                max_tokens=max_tokens,
            )

            choice = response.choices[0]
            text = choice.message.content or ""
            tool_uses = []
            if choice.message.tool_calls:
                import json

                for tc in choice.message.tool_calls:
                    tool_uses.append(
                        ToolUseBlock(
                            id=tc.id,
                            name=tc.function.name,
                            input=json.loads(tc.function.arguments),
                        )
                    )

            yield AssistantMessage(
                content=text,
                model=self._model,
                tool_use=tool_uses,
                stop_reason=choice.finish_reason,
            )
        except ImportError:
            yield AssistantMessage(
                content="Error: openai package not installed. Run: pip install openai",
                model=self._model,
            )
        except Exception as e:
            yield AssistantMessage(
                content=f"OpenAI API error: {e}",
                model=self._model,
            )

    async def stream_model(
        self,
        system: str,
        messages: list[dict[str, Any]],
        tools: list[dict[str, Any]],
        *,
        max_tokens: int = 8192,
        thinking: str = "adaptive",
    ) -> AsyncIterator[str | AssistantMessage]:
        """Non-streaming fallback — yields full response as single chunk."""
        async for msg in self.call_model(
            system=system,
            messages=messages,
            tools=tools,
            max_tokens=max_tokens,
            thinking=thinking,
        ):
            if msg.content:
                yield msg.content
            yield msg
