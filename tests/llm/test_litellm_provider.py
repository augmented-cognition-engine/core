# tests/llm/test_litellm_provider.py
"""LiteLLMProvider conformance wiring — mocked at the SDK boundary
(`litellm.acompletion` is monkeypatched; the provider holds the module and
looks the attribute up per call), so the suite runs WITHOUT network even when
the extra is installed.

The extra is OPTIONAL and absent in CI by design — `pytest.importorskip`
skips this module honestly when litellm isn't installed (same pattern as
ace_mcp_client's optional-dep suites). Lazy-import discipline — the part of
this provider that must hold even WITHOUT the SDK — is pinned separately in
tests/llm/test_lazy_extras.py, which always runs.

No divergence knobs: this provider conforms to the HTTP-provider defaults
(raise on first garbage parse, single round-trip on empty completion).
"""

from __future__ import annotations

import pytest

litellm = pytest.importorskip("litellm", reason="optional extra not installed: pip install 'ace-core[litellm]'")

from types import SimpleNamespace
from unittest.mock import AsyncMock

from core.engine.core.llm_litellm import LiteLLMProvider
from tests.llm.conformance import CapturedRequest, LLMConformanceSuite


def _response(text: str | None, usage: tuple[int, int] = (5, 7), cost: float | None = None) -> SimpleNamespace:
    """A litellm ModelResponse stand-in: OpenAI-format choices/usage plus the
    `_hidden_params["response_cost"]` litellm computes when it knows the rates."""
    resp = SimpleNamespace(
        choices=[SimpleNamespace(message=SimpleNamespace(content=text))],
        usage=SimpleNamespace(prompt_tokens=usage[0], completion_tokens=usage[1]),
    )
    resp._hidden_params = {} if cost is None else {"response_cost": cost}
    return resp


def _stream_chunks(chunks: list[str]):
    async def _gen():
        for chunk in chunks:
            yield SimpleNamespace(choices=[SimpleNamespace(delta=SimpleNamespace(content=chunk))])

    return _gen()


class TestLiteLLMProviderConformance(LLMConformanceSuite):
    # An anthropic/-prefixed default → the built-in tier defaults apply (same
    # billing target the operator chose; see llm_litellm.py module docstring).
    default_model = "anthropic/claude-sonnet-5"
    # litellm's provider/model syntax IS the tier vocabulary — a non-claude
    # name passes through verbatim (deliberate caller intent).
    override_model = "groq/llama-3.3-70b-versatile"

    expected_tier_translations = {
        "claude-haiku-4-5-20251001": "anthropic/claude-haiku-4-5-20251001",
        "claude-sonnet-5": "anthropic/claude-sonnet-5",
        "claude-opus-4-8": "anthropic/claude-opus-4-8",
        "claude-fable-5": "anthropic/claude-fable-5",
    }

    @pytest.fixture(autouse=True)
    def _transport(self, monkeypatch):
        self._acompletion = AsyncMock()
        monkeypatch.setattr(litellm, "acompletion", self._acompletion)
        # Usage persistence is fail-open but must not attempt a live DB write
        # from a unit test; kept as a mock so the wire tests below can assert.
        self._record = AsyncMock()
        monkeypatch.setattr("core.engine.intelligence.token_ledger.TokenLedger.record", self._record)

    def make_provider(self) -> LiteLLMProvider:
        return LiteLLMProvider(default_model=self.default_model)

    def respond_text(self, text: str) -> None:
        self._acompletion.return_value = _response(text)

    def respond_empty(self) -> None:
        # OpenAI-format `content` may be null (refusals / tool-only turns).
        self._acompletion.return_value = _response(None)

    def respond_stream(self, chunks: list[str]) -> None:
        self._acompletion.return_value = _stream_chunks(chunks)

    def last_request(self) -> CapturedRequest:
        kwargs = self._acompletion.call_args.kwargs
        messages = kwargs.get("messages") or []
        system_msgs = [m for m in messages if m.get("role") == "system"]
        user_msgs = [m for m in messages if m.get("role") == "user"]
        system_raw = system_msgs[0]["content"] if system_msgs else None
        return CapturedRequest(
            model=kwargs.get("model"),
            max_tokens=kwargs.get("max_tokens"),
            system_raw=system_raw,
            system_text=system_raw,
            prompt=user_msgs[-1]["content"] if user_msgs else None,
        )

    def transport_calls(self) -> int:
        return self._acompletion.call_count

    # =======================================================================
    # litellm-specific wire shape
    # =======================================================================

    async def test_non_anthropic_default_starts_with_empty_map(self):
        # A groq-targeting config must NOT silently re-route tier names to a
        # metered Anthropic key the operator never chose — tiers collapse to
        # the configured default (one-time warning) until LITELLM_MODEL_MAP
        # says otherwise.
        provider = LiteLLMProvider(default_model="groq/llama-3.3-70b-versatile")
        self.respond_text("ok")
        await provider.complete("hi", model="claude-haiku-4-5-20251001")
        assert self.last_request().model == "groq/llama-3.3-70b-versatile"

    async def test_model_map_overrides_builtin_defaults(self):
        provider = LiteLLMProvider(
            default_model=self.default_model,
            model_map={"claude-haiku-4-5-20251001": "groq/llama-3.1-8b-instant"},
        )
        self.respond_text("ok")
        await provider.complete("hi", model="claude-haiku-4-5-20251001")
        assert self.last_request().model == "groq/llama-3.1-8b-instant"
        # The merge keeps the untouched defaults.
        self.respond_text("ok")
        await provider.complete("hi", model="claude-opus-4-6")
        assert self.last_request().model == "anthropic/claude-opus-4-6"

    async def test_streaming_passes_stream_flag(self):
        provider = self.make_provider()
        self.respond_stream(["a"])
        [c async for c in provider.stream("go")]
        assert self._acompletion.call_args.kwargs["stream"] is True

    # =======================================================================
    # Per-call usage persistence (Task 4c parity)
    # =======================================================================

    async def test_complete_persists_usage_with_litellm_cost(self):
        # litellm computes its own response_cost for models it knows — prefer
        # it over ACE's Anthropic-only rates table.
        provider = self.make_provider()
        self._acompletion.return_value = _response("hello", usage=(10, 161), cost=0.0123)
        assert await provider.complete("say hello") == "hello"
        self._record.assert_awaited_once()
        kwargs = self._record.await_args.kwargs
        assert kwargs["source"] == "litellm"
        assert kwargs["billing"] == "metered_estimate"
        assert kwargs["executor_model"] == "anthropic/claude-sonnet-4-6"
        assert kwargs["tokens_by_stage"]["input"] == 10
        assert kwargs["tokens_by_stage"]["output"] == 161
        assert kwargs["cost_usd"] == pytest.approx(0.0123)

    async def test_usage_cost_falls_back_to_model_rates_then_zero(self):
        # No response_cost hidden param: cost_for_call prices known names; an
        # identity map entry keeps the bare Anthropic name on the wire so the
        # rates table matches.
        provider = LiteLLMProvider(
            default_model=self.default_model,
            model_map={"claude-sonnet-4-6": "claude-sonnet-4-6"},
        )
        self._acompletion.return_value = _response("ok", usage=(1_000_000, 1_000_000))
        await provider.complete("x", model="claude-sonnet-4-6")
        # sonnet rates: $3.00 in + $15.00 out per million → 18.00
        assert self._record.await_args.kwargs["cost_usd"] == pytest.approx(18.00)
        # Unknown wire name ("anthropic/..." isn't in MODEL_RATES) → 0.0,
        # unknown-model grace, never a crash.
        self._acompletion.return_value = _response("ok", usage=(10, 10))
        await provider.complete("x")
        assert self._record.await_args.kwargs["cost_usd"] == 0.0

    async def test_persist_usage_is_fail_open(self):
        provider = self.make_provider()
        self._record.side_effect = RuntimeError("db down")
        self.respond_text("still works")
        assert await provider.complete("hi") == "still works"
