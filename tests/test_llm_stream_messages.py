# tests/test_llm_stream_messages.py
"""Tests for ClaudeProvider.stream_messages — multi-turn streaming."""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest


@pytest.mark.asyncio
async def test_stream_messages_yields_tokens():
    """stream_messages yields text chunks from the Anthropic streaming API."""
    from core.engine.core.llm import ClaudeProvider

    mock_stream_ctx = AsyncMock()

    async def fake_text_stream():
        yield "Hello "
        yield "world"

    mock_stream_ctx.text_stream = fake_text_stream()

    with patch("core.engine.core.llm.AsyncAnthropic") as MockClient:
        mock_client = MagicMock()
        MockClient.return_value = mock_client

        mock_stream_obj = MagicMock()
        mock_stream_obj.__aenter__ = AsyncMock(return_value=mock_stream_ctx)
        mock_stream_obj.__aexit__ = AsyncMock(return_value=False)
        mock_client.messages.stream = MagicMock(return_value=mock_stream_obj)

        provider = ClaudeProvider(api_key="test-key", default_model="claude-sonnet-4-20250514")
        tokens = []
        async for token in provider.stream_messages(
            system="You are helpful.",
            messages=[{"role": "user", "content": "Hi"}],
        ):
            tokens.append(token)

    assert tokens == ["Hello ", "world"]
    mock_client.messages.stream.assert_called_once()
    call_kwargs = mock_client.messages.stream.call_args[1]
    assert call_kwargs["system"] == "You are helpful."
    assert call_kwargs["messages"] == [{"role": "user", "content": "Hi"}]


@pytest.mark.asyncio
async def test_stream_messages_uses_specified_model():
    """stream_messages passes model override to the API."""
    from core.engine.core.llm import ClaudeProvider

    mock_stream_ctx = AsyncMock()

    async def fake_text_stream():
        yield "ok"

    mock_stream_ctx.text_stream = fake_text_stream()

    with patch("core.engine.core.llm.AsyncAnthropic") as MockClient:
        mock_client = MagicMock()
        MockClient.return_value = mock_client

        mock_stream_obj = MagicMock()
        mock_stream_obj.__aenter__ = AsyncMock(return_value=mock_stream_ctx)
        mock_stream_obj.__aexit__ = AsyncMock(return_value=False)
        mock_client.messages.stream = MagicMock(return_value=mock_stream_obj)

        provider = ClaudeProvider(api_key="test-key", default_model="claude-sonnet-4-20250514")
        tokens = []
        async for token in provider.stream_messages(
            system="System",
            messages=[{"role": "user", "content": "Hi"}],
            model="claude-haiku-4-20250514",
        ):
            tokens.append(token)

    call_kwargs = mock_client.messages.stream.call_args[1]
    assert call_kwargs["model"] == "claude-haiku-4-20250514"
