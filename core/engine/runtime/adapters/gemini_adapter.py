"""Gemini model adapter — stub for Google models.

Full implementation requires google-genai SDK. Provides the interface
and a minimal implementation.
"""

from __future__ import annotations

import logging
from typing import Any, AsyncIterator

from core.engine.runtime.models import AssistantMessage

logger = logging.getLogger(__name__)


class GeminiAdapter:
    """Adapter for Google Gemini models."""

    def __init__(self, model: str = "gemini-2.5-pro", api_key: str | None = None) -> None:
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
        """Call Gemini API."""
        try:
            from google import genai

            client = genai.Client(api_key=self._api_key)
            contents = []
            for msg in messages:
                role = "model" if msg.get("role") == "assistant" else "user"
                content = msg.get("content", "")
                if isinstance(content, str):
                    contents.append({"role": role, "parts": [{"text": content}]})

            response = await client.aio.models.generate_content(
                model=self._model,
                contents=contents,
                config={"system_instruction": system, "max_output_tokens": max_tokens},
            )

            yield AssistantMessage(
                content=response.text or "",
                model=self._model,
            )
        except ImportError:
            yield AssistantMessage(
                content="Error: google-genai package not installed. Run: pip install google-genai",
                model=self._model,
            )
        except Exception as e:
            yield AssistantMessage(
                content=f"Gemini API error: {e}",
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
    ) -> AsyncIterator[AssistantMessage]:
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
