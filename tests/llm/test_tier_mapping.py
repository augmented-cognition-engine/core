# tests/llm/test_tier_mapping.py
"""Per-provider model-tier maps (Task 3) — callers keep ACE's Anthropic
model-name vocabulary; non-Anthropic providers translate at request time.

ACE routes cost-aware by passing Anthropic model names verbatim
(settings.llm_budget_model / llm_model / llm_reasoning_model — the strings in
ANTHROPIC_TIER_MODELS). Renaming that caller vocabulary is deliberately out of
scope; PROVIDERS translate via `model_map`:

  1. mapped name        → the provider-native model
  2. unmapped `claude*` → the provider's default model, ONE-TIME warning per
                          name (unknown-model grace — degrade visibly, never crash)
  3. anything else      → passed through verbatim (a native name is deliberate
                          caller intent)

ClaudeProvider/CLIProvider identity passthrough is asserted by the shared
conformance method (test_anthropic_tier_names_translate_per_provider_map with
expected_tier_translations=None) in their wirings. This file covers the
translating providers' map semantics plus the get_llm() settings wiring and
the model_costs unknown-model degradation pin.
"""

from __future__ import annotations

import logging
from unittest.mock import AsyncMock, MagicMock

import pytest

from core.engine.core.llm import OllamaProvider, OpenAICompatProvider
from tests.llm.conformance import ANTHROPIC_TIER_MODELS

HAIKU, SONNET, OPUS, FABLE = ANTHROPIC_TIER_MODELS

OLLAMA_HOST = "http://localhost:11434"
GROQ_URL = "https://api.groq.com/openai/v1"
OPENAI_URL = "https://api.openai.com/v1"


@pytest.fixture(autouse=True)
def _reset_tier_fallback_warnings():
    """The once-per-name dedupe set is module-level (it must survive throwaway
    provider instances — get_llm() builds a fresh one per call site), so tests
    asserting warning counts need a clean slate on both sides."""
    import core.engine.core.llm as llm_mod

    llm_mod._TIER_FALLBACK_WARNED.clear()
    yield
    llm_mod._TIER_FALLBACK_WARNED.clear()


@pytest.fixture
def transport(monkeypatch):
    """One mocked httpx client serving both providers — the canned body carries
    Ollama's `response` AND chat-completions `choices` so either wire parses."""
    client = MagicMock()
    client.__aenter__ = AsyncMock(return_value=client)
    client.__aexit__ = AsyncMock(return_value=None)
    resp = MagicMock()
    resp.json.return_value = {
        "response": "ok",
        "choices": [{"message": {"role": "assistant", "content": "ok"}}],
    }
    resp.raise_for_status = MagicMock()
    client.post = AsyncMock(return_value=resp)
    mock_httpx = MagicMock()
    mock_httpx.AsyncClient.return_value = client
    monkeypatch.setattr("core.engine.core.llm.httpx", mock_httpx)
    # Usage persistence is fail-open but must not attempt a live DB write.
    monkeypatch.setattr("core.engine.intelligence.token_ledger.TokenLedger.record", AsyncMock())
    return client


def _wire_model(client) -> str:
    return client.post.call_args.kwargs["json"]["model"]


# ---------------------------------------------------------------------------
# Configured maps translate before the request
# ---------------------------------------------------------------------------


async def test_ollama_configured_map_translates_before_request(transport):
    provider = OllamaProvider(
        host=OLLAMA_HOST,
        default_model="llama3.2",
        model_map={HAIKU: "llama3.2:3b", SONNET: "llama3.3"},
    )
    await provider.complete("hi", model=SONNET)
    assert _wire_model(transport) == "llama3.3"
    await provider.complete("hi", model=HAIKU)
    assert _wire_model(transport) == "llama3.2:3b"


async def test_openai_compat_configured_map_translates_before_request(transport):
    provider = OpenAICompatProvider(
        base_url=GROQ_URL,
        api_key="k",
        default_model="llama-3.3-70b-versatile",
        model_map={HAIKU: "llama-3.1-8b-instant"},
    )
    await provider.complete("hi", model=HAIKU)
    assert _wire_model(transport) == "llama-3.1-8b-instant"


async def test_openai_map_merges_over_builtin_defaults(transport):
    # One override re-points sonnet; the un-overridden tier keeps the
    # api.openai.com built-in default — merge, not replace.
    provider = OpenAICompatProvider(
        base_url=OPENAI_URL,
        api_key="k",
        model_map={SONNET: "gpt-4.1"},
    )
    await provider.complete("hi", model=SONNET)
    assert _wire_model(transport) == "gpt-4.1"
    await provider.complete("hi", model=HAIKU)
    assert _wire_model(transport) == "gpt-5.6-luna"


async def test_non_openai_base_url_gets_no_builtin_tier_defaults(transport):
    # The built-in tiered defaults are an api.openai.com catalog; sending
    # gpt-4o to Groq/vLLM would 404 just like a claude name. Off api.openai.com
    # the map starts empty and Anthropic names collapse to default_model.
    provider = OpenAICompatProvider(
        base_url=GROQ_URL,
        api_key="k",
        default_model="llama-3.3-70b-versatile",
    )
    await provider.complete("hi", model=SONNET)
    assert _wire_model(transport) == "llama-3.3-70b-versatile"


async def test_builtin_defaults_gate_is_exact_hostname_not_substring(transport):
    # "api.openai.com" as a SUBSTRING would also match a lookalike host (or a
    # path containing the string) — the gate must compare the parsed hostname.
    provider = OpenAICompatProvider(
        base_url="https://api.openai.com.evil.tld/v1",
        api_key="k",
        default_model="whatever-model",
    )
    await provider.complete("hi", model=SONNET)
    assert _wire_model(transport) == "whatever-model"  # no gpt-4o builtin applied


# ---------------------------------------------------------------------------
# Unknown-model grace: fallback + one-time warning; native names pass through
# ---------------------------------------------------------------------------


async def test_unmapped_claude_name_falls_back_with_one_time_warning(transport, caplog):
    provider = OllamaProvider(host=OLLAMA_HOST, default_model="llama3.2")
    with caplog.at_level(logging.WARNING, logger="core.engine.core.llm"):
        await provider.complete("hi", model=OPUS)
        await provider.complete("hi", model=OPUS)
        # Providers are throwaway — get_llm() constructs a fresh instance at
        # ~75 call sites — so the once-per-name promise must hold ACROSS
        # instances, not per instance.
        second_instance = OllamaProvider(host=OLLAMA_HOST, default_model="llama3.2")
        await second_instance.complete("hi", model=OPUS)
    assert _wire_model(transport) == "llama3.2"
    warnings = [r for r in caplog.records if OPUS in r.getMessage()]
    assert len(warnings) == 1, "fallback warning must fire once per name, not per call or per instance"
    # The warning must name the settings knob that fixes the degradation.
    assert "OLLAMA_MODEL_MAP" in warnings[0].getMessage()


async def test_warning_dedupe_is_per_provider_class(transport, caplog):
    # Ollama and an OpenAI-compat backend degrading on the same tier name are
    # two different misconfigurations — each provider class warns once.
    with caplog.at_level(logging.WARNING, logger="core.engine.core.llm"):
        await OllamaProvider(host=OLLAMA_HOST, default_model="llama3.2").complete("hi", model=OPUS)
        await OpenAICompatProvider(base_url=GROQ_URL, api_key="k", default_model="llama-3.3-70b-versatile").complete(
            "hi", model=OPUS
        )
    assert len([r for r in caplog.records if "OllamaProvider" in r.getMessage()]) == 1
    assert len([r for r in caplog.records if "OpenAICompatProvider" in r.getMessage()]) == 1


async def test_each_unknown_claude_name_warns_independently(transport, caplog):
    provider = OpenAICompatProvider(base_url=GROQ_URL, api_key="k", default_model="llama-3.3-70b-versatile")
    with caplog.at_level(logging.WARNING, logger="core.engine.core.llm"):
        await provider.complete("hi", model=SONNET)
        await provider.complete("hi", model=OPUS)
        await provider.complete("hi", model=SONNET)
    assert len([r for r in caplog.records if SONNET in r.getMessage()]) == 1
    assert len([r for r in caplog.records if OPUS in r.getMessage()]) == 1
    assert "OPENAI_COMPAT_MODEL_MAP" in caplog.records[0].getMessage()


async def test_native_model_name_passes_through_untouched(transport, caplog):
    # A non-Anthropic name is deliberate caller intent (e.g. the conformance
    # override models) — no remap, no fallback, no warning.
    provider = OllamaProvider(host=OLLAMA_HOST, default_model="llama3.2")
    with caplog.at_level(logging.WARNING, logger="core.engine.core.llm"):
        await provider.complete("hi", model="qwen3:32b")
    assert _wire_model(transport) == "qwen3:32b"
    assert not caplog.records


async def test_persist_usage_records_wire_model_verbatim_no_double_resolve(transport, monkeypatch):
    # _persist_usage receives the payload's model — already wire-resolved.
    # It must record that name verbatim: re-resolving would re-map a chained
    # entry whose value is also a key ("gpt-4o" below).
    record = AsyncMock()
    monkeypatch.setattr("core.engine.intelligence.token_ledger.TokenLedger.record", record)
    transport.post.return_value.json.return_value = {
        "choices": [{"message": {"role": "assistant", "content": "ok"}}],
        "usage": {"prompt_tokens": 1, "completion_tokens": 1},
    }
    provider = OpenAICompatProvider(
        base_url=GROQ_URL,
        api_key="k",
        default_model="llama-3.3-70b-versatile",
        model_map={SONNET: "gpt-4o", "gpt-4o": "custom-alias"},
    )
    await provider.complete("hi", model=SONNET)
    assert _wire_model(transport) == "gpt-4o"  # resolved exactly once
    assert record.await_args.kwargs["executor_model"] == "gpt-4o"  # not "custom-alias"


async def test_none_model_resolves_to_default_without_warning(transport, caplog):
    provider = OpenAICompatProvider(base_url=GROQ_URL, api_key="k", default_model="llama-3.3-70b-versatile")
    with caplog.at_level(logging.WARNING, logger="core.engine.core.llm"):
        await provider.complete("hi")
    assert _wire_model(transport) == "llama-3.3-70b-versatile"
    assert not caplog.records


# ---------------------------------------------------------------------------
# get_llm() wires the settings maps into the providers it constructs
# ---------------------------------------------------------------------------


def test_get_llm_wires_ollama_settings_map(monkeypatch):
    import core.engine.core.llm as llm_mod

    monkeypatch.setattr(llm_mod.settings, "ollama_host", OLLAMA_HOST, raising=False)
    monkeypatch.setattr(llm_mod.settings, "ollama_model", "llama3.2", raising=False)
    monkeypatch.setattr(llm_mod.settings, "ollama_model_map", {SONNET: "llama3.3"}, raising=False)

    provider = llm_mod.get_llm()

    assert isinstance(provider, llm_mod.OllamaProvider)
    assert provider._resolve_model(SONNET) == "llama3.3"


def test_get_llm_wires_openai_settings_map(monkeypatch):
    import core.engine.core.llm as llm_mod

    monkeypatch.setattr(llm_mod.settings, "ollama_host", None, raising=False)
    monkeypatch.setattr(llm_mod.settings, "openai_compat_base_url", GROQ_URL, raising=False)
    monkeypatch.setattr(llm_mod.settings, "openai_compat_api_key", "k", raising=False)
    monkeypatch.setattr(llm_mod.settings, "openai_compat_model", "llama-3.3-70b-versatile", raising=False)
    monkeypatch.setattr(llm_mod.settings, "openai_compat_model_map", {HAIKU: "llama-3.1-8b-instant"}, raising=False)

    provider = llm_mod.get_llm()

    assert isinstance(provider, llm_mod.OpenAICompatProvider)
    assert provider._resolve_model(HAIKU) == "llama-3.1-8b-instant"


def test_model_map_settings_parse_json_env(monkeypatch):
    # pydantic-settings decodes dict fields from JSON env strings — the
    # documented configuration shape for both maps (canonical names).
    monkeypatch.delenv("OPENAI_MODEL_MAP", raising=False)
    monkeypatch.setenv("OLLAMA_MODEL_MAP", '{"claude-sonnet-4-6": "llama3.3"}')
    monkeypatch.setenv("OPENAI_COMPAT_MODEL_MAP", '{"claude-haiku-4-5-20251001": "gpt-4o-mini"}')
    from core.engine.core.config import Settings

    s = Settings(jwt_secret="test-secret", llm_api_key="sk-test-placeholder-key-not-real")
    assert s.ollama_model_map == {"claude-sonnet-4-6": "llama3.3"}
    assert s.openai_compat_model_map == {"claude-haiku-4-5-20251001": "gpt-4o-mini"}


def test_model_map_legacy_env_alias_still_parses_json(monkeypatch):
    # Back-compat pin: the legacy OPENAI_MODEL_MAP alias keeps the JSON-dict
    # parsing — copy-pasted configs from before the rename keep working.
    monkeypatch.delenv("OPENAI_COMPAT_MODEL_MAP", raising=False)
    monkeypatch.setenv("OPENAI_MODEL_MAP", '{"claude-haiku-4-5-20251001": "gpt-4o-mini"}')
    from core.engine.core.config import Settings

    s = Settings(jwt_secret="test-secret", llm_api_key="sk-test-placeholder-key-not-real", _env_file=None)
    assert s.openai_compat_model_map == {"claude-haiku-4-5-20251001": "gpt-4o-mini"}


# ---------------------------------------------------------------------------
# model_costs degradation pin (plan Task 3 Step 4)
# ---------------------------------------------------------------------------


def test_cost_for_call_unknown_model_degrades_to_zero():
    # Mapped wire models (gpt-4o-mini, llama3.3, ...) have no MODEL_RATES
    # entry — cost_for_call must return 0.0 (no false alarms), never KeyError.
    from core.engine.core.model_costs import cost_for_call

    assert cost_for_call("gpt-4o-mini", 1_000_000, 1_000_000) == 0.0
    assert cost_for_call("llama3.3", 500, 500) == 0.0
    # Known current tiers price normally.
    assert cost_for_call(SONNET, 1_000_000, 1_000_000) == pytest.approx(12.00)
