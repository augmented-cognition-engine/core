# tests/llm/test_ollama_provider.py
"""OllamaProvider conformance wiring — transport mocked at httpx (the module
attribute `core.engine.core.llm.httpx`, so the real client is never built).

This file FOLDS IN the coverage of the former tests/test_ollama_provider.py
(complete / complete_json / complete_structured happy paths are now conformance
methods); the Ollama-specific wire-shape assertions it carried live in the
provider-specific section at the bottom.
"""

from __future__ import annotations

import json
from unittest.mock import AsyncMock, MagicMock

import pytest

from core.engine.core.llm import OllamaProvider
from tests.llm.conformance import CapturedRequest, LLMConformanceSuite

HOST = "http://localhost:11434"


def _json_response(body: dict) -> MagicMock:
    resp = MagicMock()
    resp.json.return_value = body
    resp.raise_for_status = MagicMock()
    return resp


class TestOllamaProviderConformance(LLMConformanceSuite):
    default_model = "llama3.2"
    override_model = "qwen3:32b"

    # No built-in tier catalog for a local box (whatever the operator pulled is
    # the catalog) — unmapped Anthropic names collapse to the configured default
    # model with a one-time warning. Tiered local routing = OLLAMA_MODEL_MAP.
    expected_tier_translations = dict.fromkeys(
        ("claude-haiku-4-5-20251001", "claude-sonnet-5", "claude-opus-4-8", "claude-fable-5"),
        "llama3.2",
    )

    @pytest.fixture(autouse=True)
    def _transport(self, monkeypatch):
        self._client = MagicMock()
        self._client.__aenter__ = AsyncMock(return_value=self._client)
        self._client.__aexit__ = AsyncMock(return_value=None)
        self._client.post = AsyncMock()
        self._client.stream = MagicMock()
        mock_httpx = MagicMock()
        mock_httpx.AsyncClient.return_value = self._client
        monkeypatch.setattr("core.engine.core.llm.httpx", mock_httpx)

    def make_provider(self) -> OllamaProvider:
        return OllamaProvider(host=HOST, default_model=self.default_model)

    def respond_text(self, text: str) -> None:
        self._client.post.return_value = _json_response({"response": text, "done": True})

    def respond_empty(self) -> None:
        # Ollama omitting `response` (or returning "") must yield "".
        self._client.post.return_value = _json_response({"done": True})

    def respond_stream(self, chunks: list[str]) -> None:
        resp = MagicMock()
        resp.raise_for_status = MagicMock()

        async def _lines():
            for chunk in chunks:
                yield json.dumps({"response": chunk, "done": False})
            yield json.dumps({"response": "", "done": True})

        resp.aiter_lines = _lines
        ctx = MagicMock()
        ctx.__aenter__ = AsyncMock(return_value=resp)
        ctx.__aexit__ = AsyncMock(return_value=None)
        self._client.stream.return_value = ctx

    def last_request(self) -> CapturedRequest:
        call = self._client.post.call_args
        payload = call.kwargs["json"]
        return CapturedRequest(
            model=payload.get("model"),
            max_tokens=(payload.get("options") or {}).get("num_predict"),
            system_raw=payload.get("system"),
            system_text=payload.get("system"),
            prompt=payload.get("prompt"),
        )

    def transport_calls(self) -> int:
        return self._client.post.call_count

    # =======================================================================
    # Ollama-specific wire shape (folded from tests/test_ollama_provider.py)
    # =======================================================================

    async def test_complete_posts_generate_endpoint_non_streaming(self):
        provider = self.make_provider()
        self.respond_text("The answer is 42.")
        result = await provider.complete("What is the answer?")
        assert result == "The answer is 42."
        endpoint = self._client.post.call_args.args[0]
        assert endpoint == f"{HOST}/api/generate"
        assert self._client.post.call_args.kwargs["json"]["stream"] is False

    async def test_complete_json_requests_json_format(self):
        provider = self.make_provider()
        self.respond_text('{"key": "value"}')
        await provider.complete_json("give json")
        # Ollama's native JSON mode — `format: json` constrains decoding.
        assert self._client.post.call_args.kwargs["json"]["format"] == "json"
