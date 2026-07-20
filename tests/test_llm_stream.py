from unittest.mock import AsyncMock, patch

import pytest


@pytest.mark.asyncio
async def test_stream_yields_text_chunks():
    """stream() should yield text chunks from the Anthropic streaming API."""
    from core.engine.core.llm import ClaudeProvider

    mock_stream_ctx = AsyncMock()
    mock_stream = AsyncMock()

    # Simulate async iteration over text_stream
    async def fake_text_stream():
        for chunk in ["Hello", " world", "!"]:
            yield chunk

    mock_stream.text_stream = fake_text_stream()
    mock_stream_ctx.__aenter__ = AsyncMock(return_value=mock_stream)
    mock_stream_ctx.__aexit__ = AsyncMock(return_value=False)

    provider = ClaudeProvider(api_key="sk-test", default_model="test-model")

    with patch.object(provider._client.messages, "stream", return_value=mock_stream_ctx):
        chunks = []
        async for chunk in provider.stream("test prompt"):
            chunks.append(chunk)

    assert chunks == ["Hello", " world", "!"]


@pytest.mark.asyncio
async def test_stream_uses_default_model():
    """stream() should use default model when none specified."""
    from core.engine.core.llm import ClaudeProvider

    provider = ClaudeProvider(api_key="sk-test", default_model="claude-sonnet-4-6")

    mock_stream_ctx = AsyncMock()
    mock_stream = AsyncMock()

    async def fake_text_stream():
        yield "ok"

    mock_stream.text_stream = fake_text_stream()
    mock_stream_ctx.__aenter__ = AsyncMock(return_value=mock_stream)
    mock_stream_ctx.__aexit__ = AsyncMock(return_value=False)

    with patch.object(provider._client.messages, "stream", return_value=mock_stream_ctx) as mock_call:
        async for _ in provider.stream("test"):
            pass

    mock_call.assert_called_once()
    call_kwargs = mock_call.call_args[1]
    assert call_kwargs["model"] == "claude-sonnet-4-6"
