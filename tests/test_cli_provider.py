# tests/test_cli_provider.py
"""Tests for CLIProvider — claude subprocess LLM transport."""

from __future__ import annotations

import json
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from pydantic import BaseModel

from core.engine.core.llm import CLIProvider, get_llm

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_json_response(result: str) -> bytes:
    return (json.dumps({"type": "result", "subtype": "success", "result": result}) + "\n").encode()


def _make_stream_events(chunks: list[str]) -> list[bytes]:
    lines = []
    for chunk in chunks:
        event = {"type": "assistant", "message": {"content": [{"type": "text", "text": chunk}]}}
        lines.append((json.dumps(event) + "\n").encode())
    lines.append((json.dumps({"type": "result", "subtype": "success", "result": "".join(chunks)}) + "\n").encode())
    return lines


# ---------------------------------------------------------------------------
# complete()
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_complete_returns_result_field():
    provider = CLIProvider(default_model="claude-haiku-4-5-20251001", claude_bin="claude")
    with patch.object(provider, "_run", new_callable=AsyncMock) as mock_run:
        mock_run.return_value = json.dumps({"type": "result", "result": "hello world"})
        result = await provider.complete("say hello")
    assert result == "hello world"
    args = mock_run.call_args[0][0]
    assert "-p" in args
    assert "--output-format" in args
    assert "json" in args
    assert "--no-session-persistence" in args


@pytest.mark.asyncio
async def test_complete_falls_back_on_invalid_json():
    provider = CLIProvider(default_model="claude-sonnet-4-6")
    with patch.object(provider, "_run", new_callable=AsyncMock) as mock_run:
        mock_run.return_value = "plain text response"
        result = await provider.complete("prompt")
    assert result == "plain text response"


@pytest.mark.asyncio
async def test_complete_passes_model_flag():
    provider = CLIProvider(default_model="claude-sonnet-4-6")
    with patch.object(provider, "_run", new_callable=AsyncMock) as mock_run:
        mock_run.return_value = json.dumps({"result": "ok"})
        await provider.complete("prompt", model="claude-opus-4-6")
    args = mock_run.call_args[0][0]
    assert "--model" in args
    idx = args.index("--model")
    assert args[idx + 1] == "claude-opus-4-6"


# ---------------------------------------------------------------------------
# complete_json()
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_complete_json_parses_json_result():
    provider = CLIProvider(default_model="claude-haiku-4-5-20251001")
    with patch.object(provider, "complete", new_callable=AsyncMock) as mock_complete:
        mock_complete.return_value = '{"discipline": "architecture", "score": 0.9}'
        result = await provider.complete_json("classify this")
    assert result["discipline"] == "architecture"
    assert result["score"] == 0.9


@pytest.mark.asyncio
async def test_complete_json_strips_markdown_fences():
    provider = CLIProvider(default_model="claude-haiku-4-5-20251001")
    with patch.object(provider, "complete", new_callable=AsyncMock) as mock_complete:
        mock_complete.return_value = '```json\n{"key": "value"}\n```'
        result = await provider.complete_json("prompt")
    assert result == {"key": "value"}


# ---------------------------------------------------------------------------
# complete_structured()
# ---------------------------------------------------------------------------


class SampleSchema(BaseModel):
    name: str
    score: float


@pytest.mark.asyncio
async def test_complete_structured_validates_pydantic():
    provider = CLIProvider(default_model="claude-sonnet-4-6")
    with patch.object(provider, "_run", new_callable=AsyncMock) as mock_run:
        mock_run.return_value = json.dumps({"result": '{"name": "test", "score": 0.8}'})
        result = await provider.complete_structured("prompt", SampleSchema)
    assert isinstance(result, SampleSchema)
    assert result.name == "test"
    assert result.score == 0.8


@pytest.mark.asyncio
async def test_complete_structured_injects_schema_in_prompt():
    # --json-schema flag produces empty result field in CLI; schema is injected
    # into the prompt instead and --json-schema is NOT passed as a flag.
    provider = CLIProvider(default_model="claude-sonnet-4-6")
    with patch.object(provider, "_run", new_callable=AsyncMock) as mock_run:
        mock_run.return_value = json.dumps({"result": '{"name": "x", "score": 1.0}'})
        await provider.complete_structured("prompt", SampleSchema)
    args = mock_run.call_args[0][0]
    assert "--json-schema" not in args
    prompt_arg = args[args.index("-p") + 1]
    assert "Schema:" in prompt_arg
    assert "SampleSchema" in prompt_arg


@pytest.mark.asyncio
async def test_complete_structured_strips_markdown_fences():
    # CLI sometimes wraps JSON in ```json...``` — must be stripped before parse.
    provider = CLIProvider(default_model="claude-sonnet-4-6")
    fenced = "```json\n" + '{"name": "fenced", "score": 0.5}' + "\n```"
    with patch.object(provider, "_run", new_callable=AsyncMock) as mock_run:
        mock_run.return_value = json.dumps({"result": fenced})
        result = await provider.complete_structured("prompt", SampleSchema)
    assert result.name == "fenced"
    assert result.score == 0.5


# ---------------------------------------------------------------------------
# stream()
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_stream_yields_text_chunks():
    provider = CLIProvider(default_model="claude-sonnet-4-6", claude_bin="claude")
    stream_lines = _make_stream_events(["Hello", " world"])

    mock_proc = MagicMock()
    mock_proc.returncode = 0
    mock_proc.wait = AsyncMock()

    async def fake_stdout():
        for line in stream_lines:
            yield line

    mock_proc.stdout = fake_stdout()

    with patch("asyncio.create_subprocess_exec", new_callable=AsyncMock) as mock_exec:
        mock_exec.return_value = mock_proc
        chunks = []
        async for chunk in provider.stream("say hello"):
            chunks.append(chunk)

    assert chunks == ["Hello", " world"]


@pytest.mark.asyncio
async def test_stream_skips_non_assistant_events():
    provider = CLIProvider(default_model="claude-sonnet-4-6", claude_bin="claude")
    lines = [
        (json.dumps({"type": "system", "subtype": "init"}) + "\n").encode(),
        (json.dumps({"type": "assistant", "message": {"content": [{"type": "text", "text": "hi"}]}}) + "\n").encode(),
        (json.dumps({"type": "result", "subtype": "success", "result": "hi"}) + "\n").encode(),
    ]

    mock_proc = MagicMock()
    mock_proc.returncode = 0
    mock_proc.wait = AsyncMock()

    async def fake_stdout():
        for line in lines:
            yield line

    mock_proc.stdout = fake_stdout()

    with patch("asyncio.create_subprocess_exec", new_callable=AsyncMock) as mock_exec:
        mock_exec.return_value = mock_proc
        chunks = [c async for c in provider.stream("hi")]

    assert chunks == ["hi"]


# ---------------------------------------------------------------------------
# get_llm() priority
# ---------------------------------------------------------------------------


def test_get_llm_returns_cliprovider_when_no_api_key_and_no_oauth(monkeypatch):
    """No explicit key + no OAuth → CLI subprocess fallback."""
    monkeypatch.setattr("core.engine.core.llm.settings.llm_api_key", "")
    monkeypatch.setattr("core.engine.core.llm.settings.force_cli_provider", False, raising=False)
    monkeypatch.setattr("core.engine.core.llm._resolve_api_key", lambda: "")
    with patch("shutil.which", return_value="/usr/local/bin/claude"):
        provider = get_llm()
    assert isinstance(provider, CLIProvider)


def _neutralize_higher_priority_slots(monkeypatch):
    """Slot 5 (metered LLM_API_KEY → ClaudeProvider) only wins when slots 1-4 are
    empty. These tests assert slot-5 behavior, so they must null the higher-priority
    resolvers explicitly — otherwise an ambient .env (e.g. OPENAI_COMPAT_BASE_URL)
    silently routes get_llm() to a different provider and the test is non-hermetic."""
    monkeypatch.setattr("core.engine.core.llm.settings.litellm_model", None, raising=False)
    monkeypatch.setattr("core.engine.core.llm.settings.anyllm_model", None, raising=False)
    monkeypatch.setattr("core.engine.core.llm.settings.ollama_host", None, raising=False)
    monkeypatch.setattr("core.engine.core.llm.settings.openai_compat_base_url", None, raising=False)
    monkeypatch.setattr("core.engine.core.llm.settings.require_subscription", False, raising=False)


def test_get_llm_returns_claude_provider_when_api_key_set(monkeypatch):
    from core.engine.core.llm import ClaudeProvider

    _neutralize_higher_priority_slots(monkeypatch)
    monkeypatch.setattr("core.engine.core.llm.settings.llm_api_key", "sk-ant-real-key-123456789012345")
    provider = get_llm()
    assert isinstance(provider, ClaudeProvider)


def test_get_llm_prefers_api_key_over_cli(monkeypatch):
    from core.engine.core.llm import ClaudeProvider

    _neutralize_higher_priority_slots(monkeypatch)
    monkeypatch.setattr("core.engine.core.llm.settings.llm_api_key", "sk-ant-real-key-123456789012345")
    with patch("shutil.which", return_value="/usr/local/bin/claude"):
        provider = get_llm()
    assert isinstance(provider, ClaudeProvider)


def test_get_llm_promotes_oauth_over_cli_subprocess_when_opted_in(monkeypatch):
    """Undocumented OAuth-as-API path (slot 7): only promotes over the CLI when
    ALLOW_OAUTH_API_PATH=1. Post-Task-4b it is OFF by default — the shape is
    unsanctioned, so the default chain prefers CLAUDE_CODE_OAUTH_TOKEN / the CLI.
    With the opt-in set, the store token still promotes to a fast-HTTP ClaudeProvider.
    """
    from core.engine.core.llm import ClaudeProvider

    monkeypatch.setattr("core.engine.core.llm.settings.llm_api_key", "")
    monkeypatch.setattr("core.engine.core.llm.settings.force_cli_provider", False, raising=False)
    monkeypatch.setattr("core.engine.core.llm.settings.allow_oauth_api_path", True, raising=False)
    monkeypatch.delenv("CLAUDE_CODE_OAUTH_TOKEN", raising=False)
    monkeypatch.setattr("core.engine.core.llm._resolve_api_key", lambda: "oauth-bearer-token-pretending-to-be-30-chars")
    with patch("shutil.which", return_value="/usr/local/bin/claude"):
        provider = get_llm()
    assert isinstance(provider, ClaudeProvider)


def test_get_llm_oauth_api_path_gated_off_by_default(monkeypatch):
    """Default (no opt-in): the store-token OAuth-as-API slot is skipped and
    resolution falls through to the CLI — the Task-4b realignment."""
    monkeypatch.setattr("core.engine.core.llm.settings.llm_api_key", "")
    monkeypatch.setattr("core.engine.core.llm.settings.force_cli_provider", False, raising=False)
    monkeypatch.setattr("core.engine.core.llm.settings.allow_oauth_api_path", False, raising=False)
    monkeypatch.delenv("CLAUDE_CODE_OAUTH_TOKEN", raising=False)
    monkeypatch.setattr("core.engine.core.llm._resolve_api_key", lambda: "oauth-bearer-token-pretending-to-be-30-chars")
    with patch("shutil.which", return_value="/usr/local/bin/claude"):
        provider = get_llm()
    assert isinstance(provider, CLIProvider)


def test_get_llm_force_cli_overrides_oauth_promotion(monkeypatch):
    """ACE_FORCE_CLI_PROVIDER=1 (settings.force_cli_provider=True) skips OAuth and uses CLI.

    Escape hatch for cases where OAuth-as-API breaks or the operator wants the
    hermetic subprocess invocation explicitly."""
    monkeypatch.setattr("core.engine.core.llm.settings.llm_api_key", "")
    monkeypatch.setattr("core.engine.core.llm.settings.force_cli_provider", True, raising=False)
    monkeypatch.setattr("core.engine.core.llm._resolve_api_key", lambda: "oauth-bearer-token-pretending-to-be-30-chars")
    with patch("shutil.which", return_value="/usr/local/bin/claude"):
        provider = get_llm()
    assert isinstance(provider, CLIProvider)


# ---------------------------------------------------------------------------
# Subprocess timeout cleanup — regression: prior to fix, `proc.kill()` was
# fire-and-forget, so concurrent callers stacked up unreaped child procs
# (root cause of the 2026-05-12 engine lockup: 5 hung `claude` subprocesses
# after a single briefing trigger).
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_run_uses_configured_default_timeout(monkeypatch):
    provider = CLIProvider(default_model="claude-sonnet-5", claude_bin="claude")
    proc = MagicMock(returncode=0)
    proc.communicate = AsyncMock(return_value=(b"ok", b""))
    observed: dict[str, float] = {}

    async def capture_timeout(awaitable, timeout):
        observed["timeout"] = timeout
        return await awaitable

    monkeypatch.setattr("core.engine.core.llm.settings.claude_cli_timeout_seconds", 321.0)
    monkeypatch.setattr("asyncio.create_subprocess_exec", AsyncMock(return_value=proc))
    monkeypatch.setattr("asyncio.wait_for", capture_timeout)

    assert await provider._run([]) == "ok"
    assert observed["timeout"] == 321.0


@pytest.mark.asyncio
async def test_run_reaps_subprocess_on_timeout(tmp_path):
    import asyncio
    import subprocess

    from core.engine.core.exceptions import LLMError

    sleeper = tmp_path / "sleeper.sh"
    sleeper.write_text("#!/bin/sh\ntrap '' TERM\nexec sleep 60\n")
    sleeper.chmod(0o755)

    provider = CLIProvider(default_model="claude-haiku-4-5-20251001", claude_bin=str(sleeper))
    with pytest.raises(LLMError, match="timed out"):
        await provider._run([], timeout=0.2)

    await asyncio.sleep(0.1)
    leftover = subprocess.run(["pgrep", "-f", str(sleeper)], capture_output=True, text=True)
    assert leftover.stdout.strip() == "", f"subprocess not reaped after timeout — leftover PIDs: {leftover.stdout!r}"


# ---------------------------------------------------------------------------
# Per-call usage persistence (Task 4c) — make the subscription draw observable.
# The CLI nests counts under `usage` and reports `total_cost_usd` (the
# API-rate-equivalent subscription-credit-draw estimate). Persistence is
# fail-open: a DB failure must NEVER break the LLM call.
# ---------------------------------------------------------------------------


def _make_usage_response(result: str) -> str:
    """A realistic `claude -p --output-format json` payload: counts nested under
    `usage`, plus the top-level `total_cost_usd` Claude Code computes."""
    return json.dumps(
        {
            "type": "result",
            "subtype": "success",
            "result": result,
            "usage": {
                "input_tokens": 10,
                "output_tokens": 161,
                "cache_read_input_tokens": 0,
                "cache_creation_input_tokens": 35691,
            },
            "total_cost_usd": 0.0454,
        }
    )


def test_track_usage_reads_nested_usage_shape():
    """The nested `usage` object is the source of truth — the prior flat-only
    read recorded zeros against it."""
    provider = CLIProvider(default_model="claude-haiku-4-5-20251001", claude_bin="claude")
    usage = provider._track_usage(json.loads(_make_usage_response("hi")))
    assert usage["input_tokens"] == 10
    assert usage["output_tokens"] == 161
    assert usage["cache_write_tokens"] == 35691
    assert usage["cost_usd"] == 0.0454
    # In-memory stats accumulated the real numbers, not zeros.
    assert provider.usage_stats["input_tokens"] == 10
    assert provider.usage_stats["output_tokens"] == 161


@pytest.mark.asyncio
async def test_complete_persists_usage_row():
    """A completed CLI call writes exactly one ledger row, carrying the CLI's
    own cost and the subscription-credit billing label."""
    provider = CLIProvider(default_model="claude-haiku-4-5-20251001", claude_bin="claude")
    with (
        patch.object(provider, "_run", new_callable=AsyncMock) as mock_run,
        patch("core.engine.intelligence.token_ledger.TokenLedger.record", new_callable=AsyncMock) as mock_record,
    ):
        mock_run.return_value = _make_usage_response("hello world")
        result = await provider.complete("say hello")

    assert result == "hello world"
    mock_record.assert_awaited_once()
    kwargs = mock_record.await_args.kwargs
    assert kwargs["source"] == "cli_provider"
    assert kwargs["billing"] == "subscription_credit_estimate"
    assert kwargs["cost_usd"] == 0.0454  # CLI's own total_cost_usd, not a recompute
    assert kwargs["executor_model"] == "claude-haiku-4-5-20251001"
    assert kwargs["tokens_by_stage"]["output"] == 161
    assert kwargs["tokens_by_stage"]["cache_creation"] == 35691


@pytest.mark.asyncio
async def test_persist_usage_falls_back_to_cost_for_call_without_cli_cost():
    """When the CLI omits total_cost_usd, cost is recomputed from model rates."""
    provider = CLIProvider(default_model="claude-haiku-4-5-20251001", claude_bin="claude")
    payload = json.dumps(
        {
            "type": "result",
            "result": "ok",
            "usage": {"input_tokens": 1_000_000, "output_tokens": 1_000_000},
        }
    )
    with (
        patch.object(provider, "_run", new_callable=AsyncMock) as mock_run,
        patch("core.engine.intelligence.token_ledger.TokenLedger.record", new_callable=AsyncMock) as mock_record,
    ):
        mock_run.return_value = payload
        await provider.complete("x")

    # haiku rates: $0.80 in + $4.00 out per million → 0.80 + 4.00 = 4.80
    assert mock_record.await_args.kwargs["cost_usd"] == pytest.approx(4.80)


@pytest.mark.asyncio
async def test_persist_usage_is_fail_open():
    """A ledger-write failure must NOT break the LLM call — the result returns."""
    provider = CLIProvider(default_model="claude-haiku-4-5-20251001", claude_bin="claude")
    with (
        patch.object(provider, "_run", new_callable=AsyncMock) as mock_run,
        patch(
            "core.engine.intelligence.token_ledger.TokenLedger.record",
            new_callable=AsyncMock,
            side_effect=RuntimeError("db down"),
        ),
    ):
        mock_run.return_value = _make_usage_response("still works")
        result = await provider.complete("say hello")

    assert result == "still works"


@pytest.mark.asyncio
async def test_complete_structured_persists_usage_even_when_result_fails_schema():
    """Tokens are spent whether or not the result parses — a schema-validation
    failure in complete_structured must still record the ledger row. The
    persist call sits OUTSIDE the result-parse path: only the CLI envelope
    (where the usage counts live) gates it, never the result's fate."""
    from pydantic import BaseModel, ValidationError

    class _Shape(BaseModel):
        name: str

    provider = CLIProvider(default_model="claude-haiku-4-5-20251001", claude_bin="claude")
    with (
        patch.object(provider, "_run", new_callable=AsyncMock) as mock_run,
        patch("core.engine.intelligence.token_ledger.TokenLedger.record", new_callable=AsyncMock) as mock_record,
    ):
        mock_run.return_value = _make_usage_response('{"wrong_field": 1}')
        with pytest.raises(ValidationError):
            await provider.complete_structured("shape it", _Shape)

    mock_record.assert_awaited_once()
    kwargs = mock_record.await_args.kwargs
    assert kwargs["source"] == "cli_provider"
    assert kwargs["tokens_by_stage"]["output"] == 161
