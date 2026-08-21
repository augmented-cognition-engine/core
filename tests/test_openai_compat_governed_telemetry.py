"""OpenAI-compatible provider: governed structured calls need in-process usage telemetry.

``complete_structured_provider_call`` derives ``input_units``/``output_units``
from the in-process ``TokenAccumulator``; the governed reasoning path fails
closed when they are unavailable. The compat provider already persists usage
to the durable token ledger; it must also record the same exact usage into
the accumulator, as the Ollama provider does, or every governed call through
an OpenAI-compatible endpoint is refused for "missing telemetry".
"""

from __future__ import annotations

import pytest

from core.engine.core.llm import OpenAICompatProvider
from core.engine.core.tokens import TokenAccumulator, clear_accumulator, get_accumulator, set_accumulator

pytestmark = pytest.mark.unit


@pytest.fixture
def accumulator():
    acc = TokenAccumulator()
    set_accumulator(acc)
    try:
        yield acc
    finally:
        clear_accumulator()


@pytest.mark.asyncio
async def test_complete_json_records_exact_usage_into_the_accumulator(monkeypatch, accumulator) -> None:
    provider = OpenAICompatProvider(base_url="http://stub.local/v1", default_model="stub-model")
    posted: list[dict] = []

    async def fake_post_chat(payload: dict) -> dict:
        posted.append(payload)
        await provider._persist_usage({"prompt_tokens": 17, "completion_tokens": 5}, payload.get("model"))
        return {
            "id": "chatcmpl-stub",
            "model": "stub-model",
            "choices": [{"message": {"role": "assistant", "content": '{"ok": true}'}}],
            "usage": {"prompt_tokens": 17, "completion_tokens": 5},
        }

    monkeypatch.setattr(provider, "_post_chat", fake_post_chat)

    result = await provider.complete_json("{}")

    assert result == {"ok": True}
    assert get_accumulator() is accumulator
    calls = accumulator.calls_snapshot()
    assert len(calls) == 1
    call = calls[0]
    assert call["input_tokens"] == 17
    assert call["output_tokens"] == 5
    assert call["provider"] == "OpenAICompatProvider"
    assert call["model"] == "stub-model"
    assert call["purpose"] == "openai_compat"


@pytest.mark.asyncio
async def test_empty_usage_records_nothing(monkeypatch, accumulator) -> None:
    provider = OpenAICompatProvider(base_url="http://stub.local/v1", default_model="stub-model")

    await provider._persist_usage({}, "stub-model")

    assert accumulator.calls_snapshot() == ()
