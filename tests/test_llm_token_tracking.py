from unittest.mock import AsyncMock, MagicMock

import pytest

from core.engine.core.tokens import TokenAccumulator, clear_accumulator, get_accumulator, set_accumulator


@pytest.fixture(autouse=True)
def _clean_accumulator():
    clear_accumulator()
    yield
    clear_accumulator()


@pytest.mark.asyncio
async def test_complete_records_tokens():
    """complete() auto-records to active accumulator without changing return type."""
    acc = TokenAccumulator()
    set_accumulator(acc)

    mock_response = MagicMock()
    mock_response.content = [MagicMock(type="text", text="hello")]
    mock_response.usage = MagicMock(input_tokens=100, output_tokens=25)

    from core.engine.core.llm import ClaudeProvider

    provider = ClaudeProvider.__new__(ClaudeProvider)
    provider._client = AsyncMock()
    provider._client.messages.create = AsyncMock(return_value=mock_response)
    provider._default_model = "test-model"

    result = await provider.complete("test prompt")

    assert result == "hello"  # Return type unchanged
    assert acc.total_input() == 100
    assert acc.total_output() == 25


@pytest.mark.asyncio
async def test_no_accumulator_no_error():
    """complete() works fine when no accumulator is set."""
    assert get_accumulator() is None

    mock_response = MagicMock()
    mock_response.content = [MagicMock(type="text", text="hello")]
    mock_response.usage = MagicMock(input_tokens=100, output_tokens=25)

    from core.engine.core.llm import ClaudeProvider

    provider = ClaudeProvider.__new__(ClaudeProvider)
    provider._client = AsyncMock()
    provider._client.messages.create = AsyncMock(return_value=mock_response)
    provider._default_model = "test-model"

    result = await provider.complete("test prompt")
    assert result == "hello"


@pytest.mark.asyncio
async def test_ollama_records_exact_local_usage_and_route():
    from core.engine.core.llm import OllamaProvider

    acc = TokenAccumulator()
    set_accumulator(acc)
    provider = OllamaProvider("http://ollama.test", default_model="qwen3:4b")
    provider._post = AsyncMock(
        return_value={
            "model": "qwen3:4b",
            "response": "local answer",
            "prompt_eval_count": 123,
            "eval_count": 17,
        }
    )

    assert await provider.complete("test") == "local answer"
    summary = acc.summary()
    assert summary["input_tokens"] == 123
    assert summary["output_tokens"] == 17
    assert summary["cost_usd"] == 0.0
    assert summary["providers"] == ["OllamaProvider"]
    assert summary["models"] == ["qwen3:4b"]


@pytest.mark.asyncio
async def test_structured_records_tokens():
    """complete_structured() records tokens to accumulator."""
    from pydantic import BaseModel

    class TestSchema(BaseModel):
        answer: str

    acc = TokenAccumulator()
    set_accumulator(acc)

    mock_response = MagicMock()
    mock_response.content = [MagicMock(type="text", text='{"answer": "yes"}')]
    mock_response.usage = MagicMock(input_tokens=200, output_tokens=50)

    from core.engine.core.llm import ClaudeProvider

    provider = ClaudeProvider.__new__(ClaudeProvider)
    provider._client = AsyncMock()
    provider._client.messages.create = AsyncMock(return_value=mock_response)
    provider._default_model = "test-model"

    result = await provider.complete_structured("test", TestSchema)
    assert result.answer == "yes"
    assert acc.total() == 250


def test_accumulator_records_cache_tokens():
    """TokenAccumulator tracks cache_read and cache_creation tokens."""
    acc = TokenAccumulator()
    acc.record(
        method="complete",
        input_tokens=100,
        output_tokens=25,
        cache_read_input_tokens=80,
        cache_creation_input_tokens=10,
    )
    s = acc.summary()
    assert s["cache_read_input_tokens"] == 80
    assert s["cache_creation_input_tokens"] == 10
    assert s["input_tokens"] == 100


def test_accumulator_cache_tokens_default_zero():
    """Cache fields default to 0 for backward compat."""
    acc = TokenAccumulator()
    acc.record(method="complete", input_tokens=50, output_tokens=10)
    s = acc.summary()
    assert s["cache_read_input_tokens"] == 0
    assert s["cache_creation_input_tokens"] == 0


@pytest.mark.asyncio
async def test_complete_records_cache_tokens():
    """complete() records cache_read and cache_creation from API response."""
    acc = TokenAccumulator()
    set_accumulator(acc)

    mock_response = MagicMock()
    mock_response.content = [MagicMock(type="text", text="cached")]
    mock_response.usage = MagicMock(
        input_tokens=100,
        output_tokens=25,
        cache_read_input_tokens=80,
        cache_creation_input_tokens=15,
    )

    from core.engine.core.llm import ClaudeProvider

    provider = ClaudeProvider.__new__(ClaudeProvider)
    provider._client = AsyncMock()
    provider._client.messages.create = AsyncMock(return_value=mock_response)
    provider._default_model = "test-model"

    await provider.complete("test")

    s = acc.summary()
    assert s["cache_read_input_tokens"] == 80
    assert s["cache_creation_input_tokens"] == 15
