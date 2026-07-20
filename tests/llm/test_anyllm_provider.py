# tests/llm/test_anyllm_provider.py
"""AnyLLMProvider conformance wiring — mocked at the SDK boundary
(`any_llm.acompletion` is monkeypatched; the provider holds the module and
looks the attribute up per call), so the suite runs WITHOUT network even when
the extra is installed.

The extra is OPTIONAL and absent in CI by design — `pytest.importorskip`
skips this module honestly when any-llm-sdk isn't installed. Lazy-import
discipline is pinned separately in tests/llm/test_lazy_extras.py, which
always runs.

Wire shape note: any-llm's recommended call passes `provider=` and `model=`
separately (combined "provider/model" strings are deprecated SDK-side), so
the adapter splits ACE's single configured string at the call boundary. The
`CapturedRequest.model` hook reconstructs the combined form — the suite's
tier-translation assertions speak routing intent, not SDK kwargs.

No divergence knobs: HTTP-provider defaults (raise on first garbage parse,
single round-trip on empty completion).
"""

from __future__ import annotations

import pytest

any_llm = pytest.importorskip("any_llm", reason="optional extra not installed: pip install 'ace-core[any-llm]'")

from types import SimpleNamespace
from unittest.mock import AsyncMock

from core.engine.core.llm_anyllm import AnyLLMProvider
from tests.llm.conformance import CapturedRequest, LLMConformanceSuite


def _response(text: str | None, usage: tuple[int, int] = (5, 7)) -> SimpleNamespace:
    """An OpenAI-format ChatCompletion stand-in (any-llm returns that shape)."""
    return SimpleNamespace(
        choices=[SimpleNamespace(message=SimpleNamespace(content=text))],
        usage=SimpleNamespace(prompt_tokens=usage[0], completion_tokens=usage[1]),
    )


def _stream_chunks(chunks: list[str]):
    async def _gen():
        for chunk in chunks:
            yield SimpleNamespace(choices=[SimpleNamespace(delta=SimpleNamespace(content=chunk))])

    return _gen()


class TestAnyLLMProviderConformance(LLMConformanceSuite):
    # An anthropic-targeting default → the built-in tier defaults apply (same
    # billing target the operator chose; see llm_anyllm.py module docstring).
    default_model = "anthropic/claude-sonnet-5"
    override_model = "mistral/mistral-small-latest"

    expected_tier_translations = {
        "claude-haiku-4-5-20251001": "anthropic/claude-haiku-4-5-20251001",
        "claude-sonnet-5": "anthropic/claude-sonnet-5",
        "claude-opus-4-8": "anthropic/claude-opus-4-8",
        "claude-fable-5": "anthropic/claude-fable-5",
    }

    @pytest.fixture(autouse=True)
    def _transport(self, monkeypatch):
        self._acompletion = AsyncMock()
        monkeypatch.setattr(any_llm, "acompletion", self._acompletion)
        self._record = AsyncMock()
        monkeypatch.setattr("core.engine.intelligence.token_ledger.TokenLedger.record", self._record)

    def make_provider(self) -> AnyLLMProvider:
        return AnyLLMProvider(default_model=self.default_model)

    def respond_text(self, text: str) -> None:
        self._acompletion.return_value = _response(text)

    def respond_empty(self) -> None:
        self._acompletion.return_value = _response(None)

    def respond_stream(self, chunks: list[str]) -> None:
        self._acompletion.return_value = _stream_chunks(chunks)

    def last_request(self) -> CapturedRequest:
        kwargs = self._acompletion.call_args.kwargs
        messages = kwargs.get("messages") or []
        system_msgs = [m for m in messages if m.get("role") == "system"]
        user_msgs = [m for m in messages if m.get("role") == "user"]
        system_raw = system_msgs[0]["content"] if system_msgs else None
        provider = kwargs.get("provider")
        name = kwargs.get("model")
        return CapturedRequest(
            model=f"{provider}/{name}" if provider else name,
            max_tokens=kwargs.get("max_tokens"),
            system_raw=system_raw,
            system_text=system_raw,
            prompt=user_msgs[-1]["content"] if user_msgs else None,
        )

    def transport_calls(self) -> int:
        return self._acompletion.call_count

    # =======================================================================
    # any-llm-specific wire shape
    # =======================================================================

    async def test_provider_prefix_split_into_separate_kwargs(self):
        # The SDK's recommended shape: provider= and model= separately — the
        # deprecated combined string must never reach acompletion.
        provider = self.make_provider()
        self.respond_text("ok")
        await provider.complete("hi")
        kwargs = self._acompletion.call_args.kwargs
        assert kwargs["provider"] == "anthropic"
        assert kwargs["model"] == "claude-sonnet-4-6"

    async def test_colon_separator_and_slashy_model_names(self):
        # ':' wins over '/' so "huggingface:org/model" keeps the slash inside
        # the model name.
        provider = AnyLLMProvider(default_model="huggingface:org/some-model")
        self.respond_text("ok")
        await provider.complete("hi")
        kwargs = self._acompletion.call_args.kwargs
        assert kwargs["provider"] == "huggingface"
        assert kwargs["model"] == "org/some-model"

    async def test_non_anthropic_default_starts_with_empty_map(self):
        # Tier names must not silently re-route to a provider the operator
        # never chose — they collapse to the configured default.
        provider = AnyLLMProvider(default_model="mistral/mistral-small-latest")
        self.respond_text("ok")
        await provider.complete("hi", model="claude-opus-4-6")
        assert self.last_request().model == "mistral/mistral-small-latest"

    async def test_streaming_passes_stream_flag(self):
        provider = self.make_provider()
        self.respond_stream(["a"])
        [c async for c in provider.stream("go")]
        assert self._acompletion.call_args.kwargs["stream"] is True

    # =======================================================================
    # Per-call usage persistence (Task 4c parity)
    # =======================================================================

    async def test_complete_persists_usage_row(self):
        provider = self.make_provider()
        self._acompletion.return_value = _response("hello", usage=(10, 161))
        assert await provider.complete("say hello") == "hello"
        self._record.assert_awaited_once()
        kwargs = self._record.await_args.kwargs
        assert kwargs["source"] == "anyllm"
        assert kwargs["billing"] == "metered_estimate"
        # The ledger keeps the COMBINED string — the row names routing intent.
        assert kwargs["executor_model"] == "anthropic/claude-sonnet-4-6"
        assert kwargs["tokens_by_stage"]["input"] == 10
        assert kwargs["tokens_by_stage"]["output"] == 161
        # any-llm exposes no per-call cost; "anthropic/..." isn't in the
        # Anthropic-only rates table → 0.0, unknown-model grace.
        assert kwargs["cost_usd"] == 0.0

    async def test_persist_usage_costs_known_models(self):
        # An identity map entry keeps the bare Anthropic name on the ledger
        # (no provider prefix → the SDK gets no provider kwarg and resolves it
        # itself), so cost_for_call prices it from MODEL_RATES.
        provider = AnyLLMProvider(
            default_model=self.default_model,
            model_map={"claude-sonnet-4-6": "claude-sonnet-4-6"},
        )
        self._acompletion.return_value = _response("ok", usage=(1_000_000, 1_000_000))
        await provider.complete("x", model="claude-sonnet-4-6")
        assert "provider" not in self._acompletion.call_args.kwargs
        assert self._record.await_args.kwargs["executor_model"] == "claude-sonnet-4-6"
        # sonnet rates: $3.00 in + $15.00 out per million → 18.00
        assert self._record.await_args.kwargs["cost_usd"] == pytest.approx(18.00)

    async def test_persist_usage_is_fail_open(self):
        provider = self.make_provider()
        self._record.side_effect = RuntimeError("db down")
        self.respond_text("still works")
        assert await provider.complete("hi") == "still works"
