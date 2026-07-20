"""Model adapter protocol, MockAdapter, and ClaudeAdapter for the ACE Runtime.

The ModelAdapter protocol defines how the runtime calls any model. The runtime
only depends on this protocol — concrete implementations are swapped freely.
"""

from __future__ import annotations

import asyncio
import logging
from collections import deque
from typing import Any, AsyncIterator, Protocol, runtime_checkable

from core.engine.runtime.models import AssistantMessage, ToolUseBlock

logger = logging.getLogger(__name__)

# Type alias for a tool definition dict passed to the model.
ToolSchema = dict[str, Any]


# ---------------------------------------------------------------------------
# Protocol
# ---------------------------------------------------------------------------


@runtime_checkable
class ModelAdapter(Protocol):
    """Protocol satisfied by any object that can call a model."""

    def call_model(
        self,
        system: str,
        messages: list[dict],
        tools: list[ToolSchema],
        *,
        max_tokens: int = 8192,
        thinking: str = "adaptive",
    ) -> AsyncIterator[AssistantMessage]:
        """Yield AssistantMessage responses for the given conversation turn."""
        ...

    async def stream_model(
        self,
        system: str,
        messages: list[dict],
        tools: list[ToolSchema],
        *,
        max_tokens: int = 8192,
        thinking: str = "adaptive",
    ) -> AsyncIterator[str | AssistantMessage]:
        """Yield str chunks during streaming, then final AssistantMessage.

        Also yields ThinkingDelta chunks when thinking mode is active.
        """
        ...


# ---------------------------------------------------------------------------
# MockAdapter
# ---------------------------------------------------------------------------


class MockAdapter:
    """Deterministic adapter for tests. Returns pre-configured responses in order.

    If a response is a plain string it is wrapped in an AssistantMessage
    automatically. If all responses are exhausted subsequent calls raise
    StopIteration so tests catch accidental over-calls.
    """

    def __init__(self, responses: list[str | AssistantMessage]) -> None:
        self._queue: deque[str | AssistantMessage] = deque(responses)
        self._responses = self._queue  # alias for stream_model compatibility

    async def call_model(
        self,
        system: str,
        messages: list[dict],
        tools: list[ToolSchema],
        *,
        max_tokens: int = 8192,
        thinking: str = "adaptive",
    ) -> AsyncIterator[AssistantMessage]:
        response = self._queue.popleft()
        if isinstance(response, str):
            response = AssistantMessage(content=response, model="mock")
        yield response

    async def stream_model(
        self,
        system: str,
        messages: list[dict],
        tools: list[ToolSchema],
        *,
        max_tokens: int = 8192,
        thinking: str = "adaptive",
    ) -> AsyncIterator[str | AssistantMessage]:
        """Mock streaming — yields a ThinkingDelta, text word by word, then AssistantMessage."""
        from core.engine.runtime.events import ThinkingDelta

        if not self._responses:
            yield "No more mock responses."
            yield AssistantMessage(content="No more mock responses.", model="mock")
            return
        response = self._responses.popleft()
        if isinstance(response, str):
            yield ThinkingDelta(content="mock thinking")  # simulate thinking block
            for word in response.split():
                yield word + " "
            yield AssistantMessage(content=response, model="mock")
        else:
            if response.content:
                yield ThinkingDelta(content="mock thinking")
                yield response.content
            yield response


# ---------------------------------------------------------------------------
# ClaudeAdapter
# ---------------------------------------------------------------------------


class ClaudeAdapter:
    """Production adapter wrapping the Anthropic SDK.

    Auth follows the same pattern as ClaudeProvider in engine/core/llm.py:
    _resolve_api_key() reads the env var or falls back to the OAuth token
    stored in ~/.claude/.credentials.json. On a 401 AuthenticationError the
    client is refreshed once and the call is retried.

    Thinking modes:
    - "adaptive"  → sends betas=["interleaved-thinking-2025-05-14"],
                    thinking={"type": "enabled", "budget_tokens": 8000}
    - "disabled"  → sends temperature=1 (required by Anthropic when thinking
                    is not requested)

    Token usage is recorded via engine.core.tokens.get_accumulator() if an
    accumulator is active.
    """

    def __init__(
        self,
        model: str = "claude-sonnet-4-6",
        max_tokens: int = 8192,
    ) -> None:
        from anthropic import AsyncAnthropic

        from core.engine.core.llm import _resolve_api_key

        self._model = model
        self._default_max_tokens = max_tokens
        self._resolve_api_key = _resolve_api_key
        api_key = _resolve_api_key()
        self._client = AsyncAnthropic(api_key=api_key)

    def _refresh_client(self) -> bool:
        """Re-read OAuth token from disk and rebuild the client. Returns True if changed."""
        from anthropic import AsyncAnthropic

        new_key = self._resolve_api_key()
        if new_key and new_key != self._client.api_key:
            logger.info("ClaudeAdapter: refreshing API key after 401")
            self._client = AsyncAnthropic(api_key=new_key)
            return True
        return False

    async def call_model(
        self,
        system: str,
        messages: list[dict],
        tools: list[ToolSchema],
        *,
        max_tokens: int | None = None,
        thinking: str = "adaptive",
    ) -> AsyncIterator[AssistantMessage]:
        from anthropic import AuthenticationError

        from core.engine.runtime.retry import RetryPolicy

        resolved_max_tokens = max_tokens or self._default_max_tokens
        kwargs = self._build_kwargs(system, messages, tools, resolved_max_tokens, thinking)
        use_beta = kwargs.pop("_use_beta", False)

        retry_policy = RetryPolicy()
        last_error = None

        for attempt in range(1, retry_policy.max_retries + 1):
            try:
                if use_beta:
                    response = await self._client.beta.messages.create(**kwargs)
                else:
                    response = await self._client.messages.create(**kwargs)
                break  # success
            except AuthenticationError:
                if not self._refresh_client():
                    raise
                if use_beta:
                    response = await self._client.beta.messages.create(**kwargs)
                else:
                    response = await self._client.messages.create(**kwargs)
                break  # success after auth refresh
            except Exception as exc:
                error_code = getattr(exc, "status_code", 0)
                if not retry_policy.should_retry(attempt, error_code):
                    raise
                # For 429s, read the reset header so we wait the right amount
                if error_code == 429:
                    delay = _rate_limit_delay(exc)
                else:
                    delay = retry_policy.get_delay_ms(attempt) / 1000
                logger.warning(
                    "API call failed (attempt %d), retrying in %.1fs: %s",
                    attempt,
                    delay,
                    exc,
                )
                await asyncio.sleep(delay)
                last_error = exc
        else:
            if last_error:
                raise last_error

        _record_usage(response, "call_model")
        yield _parse_response(response, self._model)

    async def stream_model(
        self,
        system: str,
        messages: list[dict],
        tools: list[ToolSchema],
        *,
        max_tokens: int | None = None,
        thinking: str = "adaptive",
    ) -> AsyncIterator[str | AssistantMessage]:
        """Stream text chunks as they arrive, then yield final AssistantMessage.

        Yields:
            str: partial text chunks during streaming
            AssistantMessage: final complete message at the end
        """
        from anthropic import AuthenticationError

        resolved_max_tokens = max_tokens or self._default_max_tokens
        kwargs = self._build_kwargs(system, messages, tools, resolved_max_tokens, thinking)
        use_beta = kwargs.pop("_use_beta", False)

        try:
            if use_beta:
                stream_ctx = self._client.beta.messages.stream(**kwargs)
            else:
                stream_ctx = self._client.messages.stream(**kwargs)

            async with stream_ctx as stream:
                async for event in stream.events():
                    if event.type == "content_block_delta":
                        delta_type = getattr(event.delta, "type", None)
                        if delta_type == "thinking_delta":
                            from core.engine.runtime.events import ThinkingDelta

                            yield ThinkingDelta(content=event.delta.thinking)
                        elif delta_type == "text_delta":
                            yield event.delta.text
                response = await stream.get_final_message()
        except AuthenticationError:
            if not self._refresh_client():
                raise
            if use_beta:
                stream_ctx = self._client.beta.messages.stream(**kwargs)
            else:
                stream_ctx = self._client.messages.stream(**kwargs)
            async with stream_ctx as stream:
                async for event in stream.events():
                    if event.type == "content_block_delta":
                        delta_type = getattr(event.delta, "type", None)
                        if delta_type == "thinking_delta":
                            from core.engine.runtime.events import ThinkingDelta

                            yield ThinkingDelta(content=event.delta.thinking)
                        elif delta_type == "text_delta":
                            yield event.delta.text
                response = await stream.get_final_message()

        _record_usage(response, "stream_model")
        yield _parse_response(response, self._model)

    def _build_kwargs(
        self,
        system: str,
        messages: list[dict],
        tools: list[ToolSchema],
        max_tokens: int,
        thinking: str,
    ) -> dict:
        kwargs: dict[str, Any] = {
            "model": self._model,
            "max_tokens": max_tokens,
            "system": system,
            "messages": messages,
        }

        if tools:
            kwargs["tools"] = tools

        if thinking == "adaptive":
            # Adaptive thinking — Claude 4 native, standard messages API
            kwargs["thinking"] = {"type": "adaptive"}
        else:
            kwargs["temperature"] = 1

        return kwargs


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


import time as _time


def _rate_limit_delay(exc: Exception, default: float = 60.0) -> float:
    """Read the Anthropic rate-limit reset header and return seconds to wait.

    Falls back to ``default`` (60s) when the header is absent or unparseable.
    Much better than the exponential backoff default for 429s, which retries
    too fast and wastes all remaining retry budget.
    """
    try:
        headers = getattr(getattr(exc, "response", None), "headers", {})
        reset_ts = headers.get("anthropic-ratelimit-unified-reset")
        if reset_ts:
            wait = float(reset_ts) - _time.time() + 2  # +2s buffer
            return max(5.0, min(wait, 300.0))  # clamp 5s–5min
    except Exception:
        pass
    return default


def _parse_response(response: Any, model: str) -> AssistantMessage:
    """Convert an Anthropic SDK response object to AssistantMessage."""
    text_parts: list[str] = []
    tool_uses: list[ToolUseBlock] = []

    for block in response.content:
        block_type = getattr(block, "type", None)
        if block_type == "text":
            text_parts.append(block.text)
        elif block_type == "tool_use":
            tool_uses.append(
                ToolUseBlock(
                    id=block.id,
                    name=block.name,
                    input=dict(block.input) if block.input else {},
                )
            )
        # thinking blocks are intentionally ignored at this layer

    usage = None
    if hasattr(response, "usage") and response.usage is not None:
        usage = {
            "input_tokens": getattr(response.usage, "input_tokens", 0),
            "output_tokens": getattr(response.usage, "output_tokens", 0),
        }

    return AssistantMessage(
        content=" ".join(text_parts),
        model=getattr(response, "model", model),
        tool_use=tool_uses,
        stop_reason=getattr(response, "stop_reason", None),
        usage=usage,
    )


def _record_usage(response: Any, method: str) -> None:
    """Record token usage to the active accumulator if one is set."""
    from core.engine.core.tokens import get_accumulator

    acc = get_accumulator()
    if acc is None:
        return
    usage = getattr(response, "usage", None)
    if usage is None:
        return
    acc.record(
        method=method,
        input_tokens=getattr(usage, "input_tokens", 0),
        output_tokens=getattr(usage, "output_tokens", 0),
        cache_read_input_tokens=getattr(usage, "cache_read_input_tokens", 0),
        cache_creation_input_tokens=getattr(usage, "cache_creation_input_tokens", 0),
    )
