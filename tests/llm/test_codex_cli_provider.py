"""Codex CLI / ChatGPT-subscription provider contract."""

from __future__ import annotations

import asyncio
import json
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from pydantic import BaseModel

from core.engine.core.access import AccessClass, access_profile_for
from core.engine.core.llm import CodexAppServerProvider, CodexCLIProvider


class _Shape(BaseModel):
    answer: str


def _provider() -> CodexCLIProvider:
    provider = CodexCLIProvider(default_model="gpt-5.6-terra", codex_bin="codex")
    provider._subscription_auth_verified = True
    return provider


@pytest.mark.asyncio
async def test_codex_subprocess_is_reaped_when_caller_cancels():
    provider = _provider()
    proc = MagicMock()
    proc.communicate = AsyncMock(side_effect=asyncio.CancelledError())

    with (
        patch("core.engine.core.llm.asyncio.create_subprocess_exec", new=AsyncMock(return_value=proc)),
        patch("core.engine.core.llm._terminate_subprocess", new=AsyncMock()) as terminate,
        pytest.raises(asyncio.CancelledError),
    ):
        await provider._run("prompt", "gpt-5.6-terra")

    terminate.assert_awaited_once_with(proc)


def test_codex_cli_is_hermetic_and_never_receives_credentials():
    flags = CodexCLIProvider._BASE_FLAGS
    assert "--ephemeral" in flags
    assert "--ignore-user-config" in flags
    assert "--ignore-rules" in flags
    assert ("--sandbox", "read-only") == (flags[flags.index("--sandbox")], flags[flags.index("--sandbox") + 1])
    assert "shell_tool" in flags
    assert 'web_search="disabled"' in flags
    assert not any("auth" in flag.lower() or "token" in flag.lower() for flag in flags)


def test_codex_cli_child_environment_excludes_provider_and_ace_secrets(monkeypatch):
    monkeypatch.setenv("OPENAI_API_KEY", "do-not-forward")
    monkeypatch.setenv("LLM_API_KEY", "do-not-forward")
    monkeypatch.setenv("SURREAL_PASS", "do-not-forward")
    monkeypatch.setenv("ACE_DISCORD_BOT_TOKEN", "do-not-forward")
    monkeypatch.setenv("CODEX_HOME", "/tmp/codex-test-home")
    child_env = CodexCLIProvider._subprocess_env()
    assert child_env["CODEX_HOME"] == "/tmp/codex-test-home"
    assert "OPENAI_API_KEY" not in child_env
    assert "LLM_API_KEY" not in child_env
    assert "SURREAL_PASS" not in child_env
    assert "ACE_DISCORD_BOT_TOKEN" not in child_env


@pytest.mark.asyncio
async def test_complete_maps_ace_tier_and_records_usage():
    provider = _provider()
    provider._run = AsyncMock(
        return_value=(
            "hello",
            {
                "input_tokens": 12,
                "output_tokens": 3,
                "cached_input_tokens": 4,
                "reasoning_output_tokens": 1,
            },
        )
    )
    with patch.object(provider, "_persist_usage", new_callable=AsyncMock) as persist:
        result = await provider.complete(
            "say hello",
            model="claude-sonnet-5",
            system=[{"type": "text", "text": "stable"}, {"type": "text", "text": "dynamic"}],
        )

    assert result == "hello"
    prompt, model, effort = provider._run.await_args.args[:3]
    assert model == "gpt-5.6-terra"
    assert effort == "default"
    assert "stable dynamic" in prompt
    assert "say hello" in prompt
    persist.assert_awaited_once()
    assert provider.usage_stats["calls"] == 0  # mocked transport owns tracking


@pytest.mark.asyncio
async def test_codex_subscription_usage_reaches_task_receipt():
    from core.engine.core.tokens import TokenAccumulator, clear_accumulator, set_accumulator

    provider = _provider()
    provider._run = AsyncMock(
        return_value=(
            "hello",
            {"input_tokens": 12, "output_tokens": 3, "cached_input_tokens": 4},
        )
    )
    provider._persist_usage = AsyncMock()
    acc = TokenAccumulator()
    set_accumulator(acc)
    try:
        await provider.complete("say hello", model="claude-sonnet-5")
    finally:
        clear_accumulator()

    summary = acc.summary()
    assert summary["input_tokens"] == 12
    assert summary["output_tokens"] == 3
    assert summary["cache_read_input_tokens"] == 4
    assert summary["providers"] == ["CodexCLIProvider"]
    assert summary["models"] == ["gpt-5.6-terra"]
    assert summary["cost_usd"] == 0.0


@pytest.mark.asyncio
async def test_complete_json_retries_and_parses_fences():
    provider = _provider()
    provider.complete = AsyncMock(side_effect=["not json", '```json\n{"ok": true}\n```'])
    assert await provider.complete_json("return status") == {"ok": True}
    assert provider.complete.await_count == 2


@pytest.mark.asyncio
async def test_complete_structured_validates_schema():
    provider = _provider()
    provider.complete_json = AsyncMock(return_value={"answer": "yes"})
    result = await provider.complete_structured("decide", _Shape)
    assert result == _Shape(answer="yes")
    assert "additionalProperties" in provider.complete_json.await_args.args[0]


@pytest.mark.asyncio
async def test_stream_and_stream_messages_preserve_protocol():
    provider = _provider()
    provider.complete = AsyncMock(side_effect=["one", "two"])
    assert [chunk async for chunk in provider.stream("hello")] == ["one"]
    assert [
        chunk
        async for chunk in provider.stream_messages(
            "system",
            [{"role": "user", "content": "hello"}],
        )
    ] == ["two"]


def test_codex_access_profile_is_subscription_backed():
    profile = access_profile_for(_provider())
    assert profile.access_class is AccessClass.SUBSCRIPTION
    assert profile.provider == "CodexCLIProvider"
    assert profile.billing_source == "codex_cli"
    assert profile.cost_model == "chatgpt_subscription_credit"


def test_explicit_codex_subscription_route_resolves(monkeypatch):
    from core.engine.core import llm as llm_mod

    monkeypatch.setattr(llm_mod.settings, "litellm_model", None)
    monkeypatch.setattr(llm_mod.settings, "anyllm_model", None)
    monkeypatch.setattr(llm_mod.settings, "ollama_host", None)
    monkeypatch.setattr(llm_mod.settings, "openai_compat_base_url", None)
    monkeypatch.setattr(llm_mod.settings, "subscription_provider", "codex")
    monkeypatch.setattr(llm_mod.settings, "codex_transport", "app_server")
    monkeypatch.setattr(llm_mod.settings, "codex_cli_model", "gpt-5.6-terra")
    monkeypatch.setattr(llm_mod, "_find_codex_bin", lambda: "/path/to/codex")

    provider = llm_mod._resolve_llm()
    assert isinstance(provider, CodexAppServerProvider)
    assert provider._codex_bin == "/path/to/codex"


def test_explicit_codex_exec_compatibility_route_resolves(monkeypatch):
    from core.engine.core import llm as llm_mod

    monkeypatch.setattr(llm_mod.settings, "litellm_model", None)
    monkeypatch.setattr(llm_mod.settings, "anyllm_model", None)
    monkeypatch.setattr(llm_mod.settings, "ollama_host", None)
    monkeypatch.setattr(llm_mod.settings, "openai_compat_base_url", None)
    monkeypatch.setattr(llm_mod.settings, "subscription_provider", "codex")
    monkeypatch.setattr(llm_mod.settings, "codex_transport", "exec")
    monkeypatch.setattr(llm_mod, "_find_codex_bin", lambda: "/path/to/codex")

    provider = llm_mod._resolve_llm()
    assert type(provider) is CodexCLIProvider


@pytest.mark.asyncio
async def test_doctor_reports_codex_route():
    from types import SimpleNamespace

    from core.engine.core.provider_diagnostics import ProviderDiagnosticState, diagnose_provider

    configured = SimpleNamespace(
        llm_budget_model="claude-haiku-4-5-20251001",
        subscription_provider="codex",
        codex_cli_model="gpt-5.6-terra",
        codex_cli_effort="default",
        openai_compat_base_url=None,
        ollama_host=None,
    )
    completed = MagicMock(returncode=0, stdout="Logged in using ChatGPT", stderr="")
    with patch("core.engine.core.provider_diagnostics.subprocess.run", return_value=completed):
        result = await diagnose_provider(configured, provider=CodexCLIProvider(codex_bin="/path/to/codex"))

    assert result.state is ProviderDiagnosticState.AUTHENTICATED
    assert result.provider == "CodexCLIProvider"
    assert result.resolved_model == "gpt-5.6-luna"


def test_codex_maps_the_unequal_provider_tiers_explicitly():
    provider = _provider()
    assert provider._model_arg("claude-haiku-4-5-20251001") == "gpt-5.6-luna"
    assert provider._model_arg("claude-sonnet-5") == "gpt-5.6-terra"
    assert provider._model_arg("claude-opus-4-8") == "gpt-5.6-sol"
    assert provider._model_arg("claude-fable-5") == "gpt-5.6-sol"
    assert provider._resolve_effort("claude-haiku-4-5-20251001", "gpt-5.6-luna") == "default"
    assert provider._resolve_effort("claude-sonnet-5", "gpt-5.6-terra") == "default"
    assert provider._resolve_effort("claude-opus-4-8", "gpt-5.6-sol") == "high"
    assert provider._resolve_effort("claude-fable-5", "gpt-5.6-sol") == "xhigh"


def test_codex_effort_map_is_operator_overridable():
    provider = CodexCLIProvider(
        codex_bin="codex",
        default_effort="low",
        effort_map={"claude-fable-5": "xhigh"},
    )
    assert provider._resolve_effort("claude-fable-5", "gpt-5.6-sol") == "xhigh"
    assert provider._resolve_effort("custom-model", "custom-model") == "low"


def test_explicit_codex_route_fails_loudly_when_cli_missing(monkeypatch):
    from core.engine.core import llm as llm_mod

    monkeypatch.setattr(llm_mod.settings, "litellm_model", None)
    monkeypatch.setattr(llm_mod.settings, "anyllm_model", None)
    monkeypatch.setattr(llm_mod.settings, "ollama_host", None)
    monkeypatch.setattr(llm_mod.settings, "openai_compat_base_url", None)
    monkeypatch.setattr(llm_mod.settings, "subscription_provider", "codex")
    monkeypatch.setattr(llm_mod, "_find_codex_bin", lambda: None)

    with pytest.raises(RuntimeError, match="codex login"):
        llm_mod._resolve_llm()


@pytest.mark.asyncio
async def test_jsonl_parser_uses_final_agent_message_and_usage(monkeypatch):
    provider = _provider()
    stdout = "\n".join(
        [
            json.dumps({"type": "thread.started", "thread_id": "thread:test"}),
            json.dumps(
                {
                    "type": "item.completed",
                    "item": {"id": "item_0", "type": "agent_message", "text": "ACE_CODEX_OK"},
                }
            ),
            json.dumps(
                {
                    "type": "turn.completed",
                    "usage": {
                        "input_tokens": 10,
                        "cached_input_tokens": 6,
                        "output_tokens": 2,
                        "reasoning_output_tokens": 0,
                    },
                }
            ),
        ]
    ).encode()

    class _Process:
        returncode = 0

        async def communicate(self, _input):
            return stdout, b""

    create = AsyncMock(return_value=_Process())
    monkeypatch.setattr("asyncio.create_subprocess_exec", create)
    text, usage = await provider._run("prompt", "gpt-5.6-sol", "xhigh")
    assert text == "ACE_CODEX_OK"
    assert usage == {
        "input_tokens": 10,
        "output_tokens": 2,
        "cached_input_tokens": 6,
        "reasoning_output_tokens": 0,
    }
    args = create.await_args.args
    assert args[-1] == "-"
    assert "--model" in args
    assert "gpt-5.6-sol" in args
    assert 'model_reasoning_effort="xhigh"' in args
