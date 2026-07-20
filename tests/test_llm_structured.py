# tests/test_llm_structured.py
from unittest.mock import AsyncMock, MagicMock

import pytest
from pydantic import BaseModel, ValidationError


class SampleOutput(BaseModel):
    name: str
    score: float


@pytest.mark.asyncio
async def test_complete_structured_returns_pydantic_instance():
    """complete_structured returns a validated Pydantic model instance."""
    from core.engine.core.llm import ClaudeProvider

    provider = ClaudeProvider.__new__(ClaudeProvider)
    provider._client = MagicMock()
    provider._default_model = "test-model"

    mock_response = MagicMock()
    mock_content = MagicMock()
    mock_content.type = "text"
    mock_content.text = '{"name": "test", "score": 0.95}'
    mock_response.content = [mock_content]
    provider._client.messages.create = AsyncMock(return_value=mock_response)

    result = await provider.complete_structured("Classify this", SampleOutput)
    assert isinstance(result, SampleOutput)
    assert result.name == "test"
    assert result.score == 0.95


@pytest.mark.asyncio
async def test_complete_structured_passes_output_config():
    """complete_structured passes output_config with json_schema to Anthropic API."""
    from core.engine.core.llm import ClaudeProvider

    provider = ClaudeProvider.__new__(ClaudeProvider)
    provider._client = MagicMock()
    provider._default_model = "test-model"

    mock_response = MagicMock()
    mock_content = MagicMock()
    mock_content.type = "text"
    mock_content.text = '{"name": "test", "score": 0.5}'
    mock_response.content = [mock_content]
    provider._client.messages.create = AsyncMock(return_value=mock_response)

    await provider.complete_structured("test", SampleOutput)

    # Verify output_config was passed with json_schema format
    call_kwargs = provider._client.messages.create.call_args[1]
    assert "output_config" in call_kwargs
    assert call_kwargs["output_config"]["format"]["type"] == "json_schema"
    assert "schema" in call_kwargs["output_config"]["format"]


@pytest.mark.asyncio
async def test_complete_structured_raises_on_invalid_schema():
    """complete_structured raises ValidationError if response doesn't match schema."""
    from core.engine.core.llm import ClaudeProvider

    provider = ClaudeProvider.__new__(ClaudeProvider)
    provider._client = MagicMock()
    provider._default_model = "test-model"

    mock_response = MagicMock()
    mock_content = MagicMock()
    mock_content.type = "text"
    mock_content.text = '{"wrong_field": true}'
    mock_response.content = [mock_content]
    provider._client.messages.create = AsyncMock(return_value=mock_response)

    with pytest.raises(ValidationError):
        await provider.complete_structured("test", SampleOutput)


@pytest.mark.asyncio
async def test_complete_structured_in_protocol():
    """LLMProvider protocol includes complete_structured."""
    from core.engine.core.llm import LLMProvider

    assert hasattr(LLMProvider, "complete_structured")


@pytest.mark.asyncio
async def test_cli_provider_complete_structured_appends_json_instruction():
    """CLIProvider.complete_structured appends 'Return valid JSON only' to prevent markdown prose responses."""
    from core.engine.core.llm import CLIProvider

    provider = CLIProvider.__new__(CLIProvider)
    provider._default_model = "claude-sonnet-4-6"
    provider._claude_bin = "claude"
    provider._stats = {
        "calls": 0,
        "input_tokens": 0,
        "output_tokens": 0,
        "cache_read_tokens": 0,
        "cache_write_tokens": 0,
    }

    captured_args = []

    async def mock_run(args, timeout=60.0):
        captured_args.append(args)
        return '{"result": "{\\"name\\": \\"test\\", \\"score\\": 0.9}"}'

    provider._run = mock_run

    result = await provider.complete_structured("Classify this idea", SampleOutput)

    assert isinstance(result, SampleOutput)
    # The -p prompt arg must contain the JSON-only instruction
    p_idx = captured_args[0].index("-p")
    prompt_sent = captured_args[0][p_idx + 1]
    assert "Return valid JSON only" in prompt_sent
    assert "No markdown" in prompt_sent
