import json
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from core.engine.orchestration.context import reset_active_bus, set_active_bus


def _make_bus():
    bus = MagicMock()
    bus.run_id = "run_test"
    bus.product_id = "product:test"
    bus.emit = AsyncMock()
    return bus


# ── ClaudeProvider ────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_claude_provider_emits_call_start_and_done():
    from core.engine.core.llm import ClaudeProvider
    from core.engine.orchestration.events import ClaudeCallDone, ClaudeCallStart

    bus = _make_bus()
    token = set_active_bus(bus)
    try:
        provider = ClaudeProvider(api_key="sk-test-key", default_model="claude-3-5-haiku-20241022")
        fake_response = MagicMock()
        fake_response.content = [MagicMock(type="text", text="hello")]
        fake_response.usage = MagicMock(
            input_tokens=10,
            output_tokens=5,
            cache_read_input_tokens=2,
            cache_creation_input_tokens=1,
        )
        with patch.object(provider._client.messages, "create", new=AsyncMock(return_value=fake_response)):
            result = await provider.complete("test prompt")

        assert result == "hello"
        assert bus.emit.call_count == 2
        start_event = bus.emit.call_args_list[0][0][0]
        done_event = bus.emit.call_args_list[1][0][0]
        assert isinstance(start_event, ClaudeCallStart)
        assert start_event.model == "claude-3-5-haiku-20241022"
        assert isinstance(done_event, ClaudeCallDone)
        assert done_event.tokens_in == 10
        assert done_event.tokens_out == 5
        assert done_event.cache_read == 2
        assert done_event.cache_write == 1
        assert done_event.duration_ms >= 0
    finally:
        reset_active_bus(token)


@pytest.mark.asyncio
async def test_claude_provider_emits_done_on_exception():
    """ClaudeCallDone is emitted even when the LLM call raises."""
    from core.engine.core.llm import ClaudeProvider
    from core.engine.orchestration.events import ClaudeCallDone, ClaudeCallStart

    bus = _make_bus()
    token = set_active_bus(bus)
    try:
        provider = ClaudeProvider(api_key="sk-test-key", default_model="claude-3-5-haiku-20241022")
        with patch.object(
            provider._client.messages,
            "create",
            new=AsyncMock(side_effect=RuntimeError("boom")),
        ):
            with pytest.raises(RuntimeError):
                await provider.complete("test prompt")

        assert bus.emit.call_count == 2
        assert isinstance(bus.emit.call_args_list[0][0][0], ClaudeCallStart)
        assert isinstance(bus.emit.call_args_list[1][0][0], ClaudeCallDone)
    finally:
        reset_active_bus(token)


@pytest.mark.asyncio
async def test_claude_provider_no_emit_without_bus():
    """No events emitted when there is no active bus (normal non-WS path)."""
    from core.engine.core.llm import ClaudeProvider

    provider = ClaudeProvider(api_key="sk-test-key", default_model="claude-3-5-haiku-20241022")
    fake_response = MagicMock()
    fake_response.content = [MagicMock(type="text", text="hi")]
    fake_response.usage = MagicMock(
        input_tokens=1,
        output_tokens=1,
        cache_read_input_tokens=0,
        cache_creation_input_tokens=0,
    )
    with patch.object(provider._client.messages, "create", new=AsyncMock(return_value=fake_response)):
        result = await provider.complete("test prompt")
    assert result == "hi"  # just completes normally, no emission


# ── CLIProvider ───────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_cli_provider_emits_call_start_and_done():
    from core.engine.core.llm import CLIProvider
    from core.engine.orchestration.events import ClaudeCallDone, ClaudeCallStart

    bus = _make_bus()
    token = set_active_bus(bus)
    try:
        provider = CLIProvider(default_model="claude-3-5-haiku-20241022")
        fake_json = json.dumps(
            {
                "result": "response text",
                "total_input_tokens": 8,
                "total_output_tokens": 4,
            }
        )
        with patch.object(provider, "_run", new=AsyncMock(return_value=fake_json)):
            result = await provider.complete("test prompt")

        assert result == "response text"
        assert bus.emit.call_count == 2
        start_event = bus.emit.call_args_list[0][0][0]
        done_event = bus.emit.call_args_list[1][0][0]
        assert isinstance(start_event, ClaudeCallStart)
        assert isinstance(done_event, ClaudeCallDone)
        assert done_event.tokens_out == 4
        assert done_event.tokens_in == 8
    finally:
        reset_active_bus(token)


@pytest.mark.asyncio
async def test_cli_provider_no_emit_without_bus():
    """No events emitted on normal CLIProvider path."""
    import json as _json

    from core.engine.core.llm import CLIProvider

    provider = CLIProvider(default_model="claude-3-5-haiku-20241022")
    fake_json = _json.dumps({"result": "plain result", "total_output_tokens": 3})
    with patch.object(provider, "_run", new=AsyncMock(return_value=fake_json)):
        result = await provider.complete("hi")
    assert result == "plain result"
