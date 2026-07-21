# tests/llm/test_openai_compat_provider.py
"""OpenAICompatProvider conformance wiring — transport mocked at httpx (the
module attribute `core.engine.core.llm.httpx`, same idiom as the Ollama
wiring, so the real client is never built).

The provider speaks the OpenAI chat-completions wire format
(`{base_url}/chat/completions`, bearer auth, `messages` array, SSE streaming)
— the de-facto ecosystem shape served by OpenAI, Azure, Groq, Together,
OpenRouter, vLLM, LM Studio, and Ollama's compat endpoint.

Provider-specific wire-shape assertions (endpoint, bearer header,
response_format + its 400 fallback, Task-4c usage persistence) live in the
section at the bottom; the behavioral contract is the shared suite. No
divergence knobs: this provider conforms to the HTTP-provider defaults
(raise on first garbage parse, single round-trip on empty).
"""

from __future__ import annotations

import json
from unittest.mock import AsyncMock, MagicMock

import httpx
import pytest

from core.engine.core.llm import OpenAICompatProvider
from tests.llm.conformance import CapturedRequest, LLMConformanceSuite

BASE_URL = "https://api.openai.com/v1"


def _completion_body(text: str | None, usage: dict | None = None) -> dict:
    body: dict = {"choices": [{"message": {"role": "assistant", "content": text}}]}
    body["usage"] = usage if usage is not None else {"prompt_tokens": 5, "completion_tokens": 7}
    return body


def _json_response(body: dict) -> MagicMock:
    resp = MagicMock()
    resp.json.return_value = body
    resp.raise_for_status = MagicMock()
    return resp


_RESPONSE_FORMAT_REJECTION_BODY = (
    '{"error": {"message": "response_format is not supported by this model",'
    ' "type": "invalid_request_error", "param": "response_format"}}'
)


def _rejected_response(status_code: int = 400, body: str = _RESPONSE_FORMAT_REJECTION_BODY) -> MagicMock:
    """A response whose raise_for_status() raises — by default a compat server
    rejecting `response_format` with a 400 whose body names the parameter."""
    resp = MagicMock()
    resp.raise_for_status.side_effect = httpx.HTTPStatusError(
        f"{status_code} error",
        request=MagicMock(),
        response=MagicMock(status_code=status_code, text=body),
    )
    return resp


class TestOpenAICompatProviderConformance(LLMConformanceSuite):
    default_model = "gpt-5.6-terra"
    override_model = "gpt-5.6-sol"

    # BASE_URL is api.openai.com, so the built-in tiered defaults apply:
    # Four Claude semantic levels map onto GPT's three-model family; the two
    # highest roles intentionally converge on Sol.
    expected_tier_translations = {
        "claude-haiku-4-5-20251001": "gpt-5.6-luna",
        "claude-sonnet-5": "gpt-5.6-terra",
        "claude-opus-4-8": "gpt-5.6-sol",
        "claude-fable-5": "gpt-5.6-sol",
    }

    @pytest.fixture(autouse=True)
    def _transport(self, monkeypatch):
        self._client = MagicMock()
        self._client.__aenter__ = AsyncMock(return_value=self._client)
        self._client.__aexit__ = AsyncMock(return_value=None)
        self._client.post = AsyncMock()
        self._client.stream = MagicMock()
        mock_httpx = MagicMock()
        # The provider catches httpx.HTTPStatusError for the response_format
        # fallback — the mocked module must carry the REAL exception class.
        mock_httpx.HTTPStatusError = httpx.HTTPStatusError
        mock_httpx.AsyncClient.return_value = self._client
        monkeypatch.setattr("core.engine.core.llm.httpx", mock_httpx)
        # Usage persistence is fail-open but must not attempt a live DB write
        # from a unit test; kept as a mock so the wire tests below can assert.
        self._record = AsyncMock()
        monkeypatch.setattr("core.engine.intelligence.token_ledger.TokenLedger.record", self._record)

    def make_provider(self) -> OpenAICompatProvider:
        return OpenAICompatProvider(base_url=BASE_URL, api_key="test-key", default_model=self.default_model)

    def respond_text(self, text: str) -> None:
        self._client.post.return_value = _json_response(_completion_body(text))

    def respond_empty(self) -> None:
        # OpenAI-format `content` may be null (e.g. refusals/tool-only turns).
        self._client.post.return_value = _json_response(_completion_body(None))

    def respond_stream(self, chunks: list[str]) -> None:
        resp = MagicMock()
        resp.raise_for_status = MagicMock()

        async def _lines():
            for chunk in chunks:
                yield "data: " + json.dumps({"choices": [{"delta": {"content": chunk}}]})
            yield "data: [DONE]"

        resp.aiter_lines = _lines
        ctx = MagicMock()
        ctx.__aenter__ = AsyncMock(return_value=resp)
        ctx.__aexit__ = AsyncMock(return_value=None)
        self._client.stream.return_value = ctx

    def last_request(self) -> CapturedRequest:
        payload = self._client.post.call_args.kwargs["json"]
        messages = payload.get("messages") or []
        system_msgs = [m for m in messages if m.get("role") == "system"]
        user_msgs = [m for m in messages if m.get("role") == "user"]
        system_raw = system_msgs[0]["content"] if system_msgs else None
        return CapturedRequest(
            model=payload.get("model"),
            max_tokens=payload.get("max_tokens", payload.get("max_completion_tokens")),
            system_raw=system_raw,
            system_text=system_raw,
            prompt=user_msgs[-1]["content"] if user_msgs else None,
        )

    def transport_calls(self) -> int:
        return self._client.post.call_count

    # =======================================================================
    # OpenAI-compat wire shape
    # =======================================================================

    async def test_complete_posts_chat_completions_with_bearer_auth(self):
        provider = self.make_provider()
        self.respond_text("ok")
        await provider.complete("hi")
        endpoint = self._client.post.call_args.args[0]
        assert endpoint == f"{BASE_URL}/chat/completions"
        headers = self._client.post.call_args.kwargs["headers"]
        assert headers["Authorization"] == "Bearer test-key"
        assert self._client.post.call_args.kwargs["json"]["stream"] is False

    async def test_no_api_key_sends_no_authorization_header(self):
        # Local servers (vLLM, LM Studio, Ollama-compat) often run keyless.
        provider = OpenAICompatProvider(base_url=BASE_URL, api_key=None, default_model=self.default_model)
        self.respond_text("ok")
        await provider.complete("hi")
        headers = self._client.post.call_args.kwargs["headers"]
        assert "Authorization" not in headers

    def test_gpt56_semantic_effort_is_sent_only_when_explicit(self):
        provider = self.make_provider()

        capable = provider._payload("hi", "claude-sonnet-5", 16, None)
        reasoning = provider._payload("hi", "claude-opus-4-8", 16, None)
        frontier = provider._payload("hi", "claude-fable-5", 16, None)

        assert "reasoning_effort" not in capable
        assert reasoning["reasoning_effort"] == "high"
        assert frontier["reasoning_effort"] == "xhigh"

    def test_gpt56_none_effort_is_sent_when_explicit(self, monkeypatch):
        from core.engine.core import llm as llm_mod

        monkeypatch.setattr(llm_mod.settings, "llm_reasoning_effort", "none", raising=False)
        provider = self.make_provider()

        payload = provider._payload("hi", "claude-opus-4-8", 16, None)

        assert payload["reasoning_effort"] == "none"

    def test_unknown_compat_backend_never_receives_assumed_effort(self):
        provider = OpenAICompatProvider(
            base_url="https://example.compat.invalid/v1",
            api_key="test-key",
            default_model="custom-model",
            model_map={"claude-opus-4-8": "custom-model"},
        )

        payload = provider._payload("hi", "claude-opus-4-8", 16, None)

        assert "reasoning_effort" not in payload
        assert provider._resolve_effort("claude-opus-4-8", "custom-model") == "provider_default"

    async def test_complete_json_requests_json_object_response_format(self):
        provider = self.make_provider()
        self.respond_text('{"key": "value"}')
        await provider.complete_json("give json")
        payload = self._client.post.call_args.kwargs["json"]
        assert payload["response_format"] == {"type": "json_object"}

    async def test_complete_json_falls_back_when_backend_rejects_response_format(self):
        # Many compat servers 400 on response_format — the provider must retry
        # ONCE without it and rely on the prompt-based JSON instruction.
        provider = self.make_provider()
        self._client.post.side_effect = [
            _rejected_response(400),
            _json_response(_completion_body('```json\n{"key": "value"}\n```')),
        ]
        assert await provider.complete_json("give json") == {"key": "value"}
        assert self._client.post.call_count == 2
        retry_payload = self._client.post.call_args.kwargs["json"]
        assert "response_format" not in retry_payload
        # The failed first attempt records nothing; the successful retry once.
        assert self._record.await_count == 1

    async def test_complete_json_propagates_non_400_errors(self):
        # The fallback is for format rejection only — a 500 is a real failure
        # (even when its body happens to mention response_format).
        provider = self.make_provider()
        self._client.post.return_value = _rejected_response(500)
        with pytest.raises(httpx.HTTPStatusError):
            await provider.complete_json("give json")
        assert self._client.post.call_count == 1

    async def test_complete_json_propagates_400_unrelated_to_response_format(self):
        # A 400 about max_tokens / a bad model must NOT be misattributed to
        # response_format — no retry, the error propagates immediately.
        provider = self.make_provider()
        self._client.post.return_value = _rejected_response(
            400, body='{"error": {"message": "max_tokens is too large", "param": "max_tokens"}}'
        )
        with pytest.raises(httpx.HTTPStatusError):
            await provider.complete_json("give json")
        assert self._client.post.call_count == 1

    async def test_complete_structured_requests_json_schema_response_format(self):
        from tests.llm.conformance import ConformanceSchema

        provider = self.make_provider()
        self.respond_text('{"name": "ace", "score": 0.9}')
        await provider.complete_structured("rate this", ConformanceSchema)
        payload = self._client.post.call_args.kwargs["json"]
        rf = payload["response_format"]
        assert rf["type"] == "json_schema"
        assert rf["json_schema"]["name"] == "ConformanceSchema"
        assert rf["json_schema"]["schema"]["type"] == "object"

    async def test_complete_structured_falls_back_when_backend_rejects_response_format(self):
        from tests.llm.conformance import ConformanceSchema

        provider = self.make_provider()
        self._client.post.side_effect = [
            _rejected_response(400),
            _json_response(_completion_body('{"name": "ace", "score": 0.9}')),
        ]
        result = await provider.complete_structured("rate this", ConformanceSchema)
        assert result.name == "ace"
        assert "response_format" not in self._client.post.call_args.kwargs["json"]
        # The prompt carries the schema, so the fallback round-trip can still
        # produce conforming output.
        assert "schema" in (self.last_request().prompt or "").lower()
        # The failed first attempt records nothing; the successful retry once.
        assert self._record.await_count == 1

    # =======================================================================
    # Per-call usage persistence (Task 4c parity)
    # =======================================================================

    async def test_complete_persists_usage_row(self):
        provider = self.make_provider()
        self._client.post.return_value = _json_response(
            _completion_body("hello", usage={"prompt_tokens": 10, "completion_tokens": 161})
        )
        assert await provider.complete("say hello") == "hello"
        self._record.assert_awaited_once()
        kwargs = self._record.await_args.kwargs
        assert kwargs["source"] == "openai_compat"
        assert kwargs["executor_model"] == "gpt-5.6-terra"
        assert kwargs["tokens_by_stage"]["input"] == 10
        assert kwargs["tokens_by_stage"]["output"] == 161
        assert kwargs["cost_usd"] == pytest.approx((10 * 2.5 + 161 * 15) / 1_000_000)

    async def test_persist_usage_costs_known_models(self):
        # A compat proxy (LiteLLM, OpenRouter) can serve Anthropic models over
        # the OpenAI wire — an explicit identity map entry keeps the name on
        # the wire (overriding the api.openai.com default sonnet→gpt-4o), and
        # known models cost normally from MODEL_RATES.
        provider = OpenAICompatProvider(
            base_url=BASE_URL,
            api_key="test-key",
            default_model=self.default_model,
            model_map={"claude-sonnet-4-6": "claude-sonnet-4-6"},
        )
        self._client.post.return_value = _json_response(
            _completion_body("ok", usage={"prompt_tokens": 1_000_000, "completion_tokens": 1_000_000})
        )
        await provider.complete("x", model="claude-sonnet-4-6")
        # sonnet rates: $3.00 in + $15.00 out per million → 18.00
        assert self._record.await_args.kwargs["cost_usd"] == pytest.approx(18.00)

    async def test_persist_usage_is_fail_open(self):
        provider = self.make_provider()
        self._record.side_effect = RuntimeError("db down")
        self.respond_text("still works")
        assert await provider.complete("hi") == "still works"
