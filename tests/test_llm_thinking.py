# tests/test_llm_thinking.py
from unittest.mock import AsyncMock, MagicMock

import pytest


@pytest.mark.asyncio
async def test_opus_uses_adaptive_thinking_on_standard_api():
    """Opus model uses standard API with thinking={"type": "adaptive"} — no beta header."""
    from core.engine.core.llm import ClaudeProvider

    mock_response = MagicMock()
    thinking_block = MagicMock(type="thinking", thinking="Let me analyze...")
    text_block = MagicMock(type="text", text="deep thought")
    mock_response.content = [thinking_block, text_block]
    mock_response.usage = None

    provider = ClaudeProvider.__new__(ClaudeProvider)
    provider._client = AsyncMock()
    provider._client.messages.create = AsyncMock(return_value=mock_response)
    provider._default_model = "claude-sonnet-4-6"

    result = await provider.complete("think deeply", model="claude-opus-4-6")

    # Must use standard messages.create, not beta
    provider._client.messages.create.assert_called_once()

    # Should extract text from text blocks, ignoring thinking blocks
    assert result == "deep thought"

    call_kwargs = provider._client.messages.create.call_args.kwargs
    assert call_kwargs.get("thinking") == {"type": "adaptive"}
    assert "betas" not in call_kwargs
    assert "budget_tokens" not in str(call_kwargs)


@pytest.mark.asyncio
async def test_haiku_gets_no_thinking_uses_standard_api():
    """Haiku model uses standard API with no thinking budget."""
    from core.engine.core.llm import ClaudeProvider

    mock_response = MagicMock()
    mock_response.content = [MagicMock(type="text", text="quick")]
    mock_response.usage = None

    provider = ClaudeProvider.__new__(ClaudeProvider)
    provider._client = AsyncMock()
    provider._client.messages.create = AsyncMock(return_value=mock_response)
    provider._default_model = "claude-haiku-4-5-20251001"

    result = await provider.complete("quick task")
    assert result == "quick"

    provider._client.messages.create.assert_called_once()
    call_kwargs = provider._client.messages.create.call_args.kwargs
    assert "thinking" not in call_kwargs
    assert "betas" not in call_kwargs


@pytest.mark.asyncio
async def test_sonnet_default_no_thinking():
    """Sonnet (thinking=disabled in config) uses standard API."""
    from core.engine.core.llm import ClaudeProvider

    mock_response = MagicMock()
    mock_response.content = [MagicMock(type="text", text="analysis")]
    mock_response.usage = None

    provider = ClaudeProvider.__new__(ClaudeProvider)
    provider._client = AsyncMock()
    provider._client.messages.create = AsyncMock(return_value=mock_response)
    provider._default_model = "claude-sonnet-4-6"

    await provider.complete("analyze this")

    call_kwargs = provider._client.messages.create.call_args.kwargs
    assert "thinking" not in call_kwargs


@pytest.mark.asyncio
async def test_extract_text_filters_thinking_blocks():
    """_extract_text extracts only text blocks, ignoring thinking blocks."""
    from core.engine.core.llm import _extract_text

    mock_response = MagicMock()
    mock_response.content = [
        MagicMock(type="thinking", thinking="reasoning..."),
        MagicMock(type="text", text="first answer"),
        MagicMock(type="thinking", thinking="more reasoning..."),
        MagicMock(type="text", text=" continued"),
    ]
    assert _extract_text(mock_response) == "first answer continued"


@pytest.mark.asyncio
async def test_extract_text_standard_response():
    """_extract_text works with standard single-text-block response."""
    from core.engine.core.llm import _extract_text

    mock_response = MagicMock()
    mock_response.content = [MagicMock(type="text", text="simple response")]
    assert _extract_text(mock_response) == "simple response"
