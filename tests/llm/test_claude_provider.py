# tests/llm/test_claude_provider.py
"""ClaudeProvider conformance wiring — transport mocked at the Anthropic SDK
client (the established idiom: the AsyncAnthropic client object IS the
transport boundary for this provider; see tests/test_llm_system_prompt.py's
predecessor pattern).

Claude-specific mechanics live elsewhere and are NOT duplicated here:
- structured output_config payload + ValidationError: tests/test_llm_structured.py
- adaptive thinking + thinking-block filtering: tests/test_llm_thinking.py
- token accumulator recording: tests/test_llm_token_tracking.py
- event-bus ClaudeCallStart/Done emission: tests/test_llm_claude_call_events.py
- auth shapes + get_llm() resolution chain: tests/test_llm.py, tests/test_cli_provider.py
"""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

import pytest

from core.engine.core.llm import ClaudeProvider
from tests.llm.conformance import CapturedRequest, LLMConformanceSuite


def _text_response(text: str) -> MagicMock:
    resp = MagicMock()
    resp.content = [MagicMock(type="text", text=text)]
    resp.usage = None
    return resp


class TestClaudeProviderConformance(LLMConformanceSuite):
    default_model = "claude-haiku-4-5-20251001"
    override_model = "claude-sonnet-4-6"

    # Anthropic is the one backend with native cache_control support — the
    # multiphase stable_prefix caching depends on blocks passing through verbatim.
    passes_cache_blocks_through = True

    @pytest.fixture(autouse=True)
    def _transport(self):
        self._client = MagicMock()
        self._client.messages.create = AsyncMock()
        self._client.messages.stream = MagicMock()

    def make_provider(self) -> ClaudeProvider:
        provider = ClaudeProvider(api_key="sk-test", default_model=self.default_model)
        provider._client = self._client
        return provider

    def respond_text(self, text: str) -> None:
        self._client.messages.create.return_value = _text_response(text)

    def respond_empty(self) -> None:
        # An empty content list — _extract_text() must yield "".
        resp = MagicMock()
        resp.content = []
        resp.usage = None
        self._client.messages.create.return_value = resp

    def respond_stream(self, chunks: list[str]) -> None:
        stream = MagicMock()

        async def _text_stream():
            for chunk in chunks:
                yield chunk

        stream.text_stream = _text_stream()
        ctx = MagicMock()
        ctx.__aenter__ = AsyncMock(return_value=stream)
        ctx.__aexit__ = AsyncMock(return_value=False)
        self._client.messages.stream.return_value = ctx

    def last_request(self) -> CapturedRequest:
        if self._client.messages.create.call_args is not None:
            kwargs = self._client.messages.create.call_args.kwargs
        else:
            kwargs = self._client.messages.stream.call_args.kwargs
        system = kwargs.get("system")
        if isinstance(system, list):
            system_text = " ".join(b.get("text", "") for b in system if isinstance(b, dict))
        else:
            system_text = system
        messages = kwargs.get("messages") or [{}]
        return CapturedRequest(
            model=kwargs.get("model"),
            max_tokens=kwargs.get("max_tokens"),
            system_raw=system,
            system_text=system_text,
            prompt=messages[0].get("content"),
        )

    def transport_calls(self) -> int:
        return self._client.messages.create.call_count


@pytest.mark.asyncio
async def test_claude_effort_follows_semantic_role_independently_of_model(monkeypatch):
    from core.engine.core import llm as llm_mod

    monkeypatch.setattr(llm_mod.settings, "llm_model", "claude-sonnet-5")
    monkeypatch.setattr(llm_mod.settings, "llm_effort", "default", raising=False)
    monkeypatch.setattr(llm_mod.settings, "llm_budget_model", "claude-haiku-4-5-20251001")
    monkeypatch.setattr(llm_mod.settings, "llm_budget_effort", "default", raising=False)
    monkeypatch.setattr(llm_mod.settings, "llm_reasoning_model", "claude-opus-4-8", raising=False)
    monkeypatch.setattr(llm_mod.settings, "llm_reasoning_effort", "high", raising=False)
    monkeypatch.setattr(llm_mod.settings, "llm_frontier_model", "claude-fable-5", raising=False)
    monkeypatch.setattr(llm_mod.settings, "llm_frontier_effort", "xhigh", raising=False)
    provider = ClaudeProvider(api_key="sk-test", default_model="claude-sonnet-5")
    provider._client = MagicMock()
    provider._client.messages.create = AsyncMock(return_value=_text_response("ok"))

    expected = {
        "claude-haiku-4-5-20251001": None,
        "claude-sonnet-5": None,
        "claude-opus-4-8": "high",
        "claude-fable-5": "xhigh",
    }
    for model, effort in expected.items():
        await provider.complete("request", model=model)
        output_config = provider._client.messages.create.await_args.kwargs.get("output_config")
        assert output_config == ({"effort": effort} if effort else None)
