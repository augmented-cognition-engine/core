from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import httpx
import pytest

from core.engine.core.llm import ClaudeProvider, CodexCLIProvider, OpenAICompatProvider
from core.engine.core.provider_diagnostics import ProviderDiagnosticState, diagnose_provider


def _settings(model: str = "claude-haiku-4-5-20251001"):
    return SimpleNamespace(llm_budget_model=model)


@pytest.mark.asyncio
async def test_empty_fallback_provider_is_not_configured():
    result = await diagnose_provider(
        _settings(),
        provider=ClaudeProvider(api_key="", default_model="claude-sonnet-5"),
    )

    assert result.state is ProviderDiagnosticState.NOT_CONFIGURED
    assert result.ok is False


@pytest.mark.asyncio
async def test_configured_key_is_unverified_without_live_request():
    provider = OpenAICompatProvider(
        base_url="https://api.openai.com/v1",
        api_key="secret-that-must-never-be-rendered",
    )
    provider.complete = AsyncMock()

    result = await diagnose_provider(_settings(), provider=provider)
    payload = result.public_dict()

    assert result.state is ProviderDiagnosticState.CONFIGURED_UNVERIFIED
    assert provider.complete.await_count == 0
    assert "secret-that-must-never-be-rendered" not in str(payload)


@pytest.mark.asyncio
async def test_live_request_records_route_without_claiming_applied_effort():
    provider = OpenAICompatProvider(
        base_url="https://api.openai.com/v1",
        api_key="redacted-fixture-key",
    )
    provider.complete = AsyncMock(return_value="OK")

    result = await diagnose_provider(_settings("claude-opus-4-8"), live=True, provider=provider)

    assert result.state is ProviderDiagnosticState.REACHABLE
    assert result.resolved_model == "gpt-5.6-sol"
    assert result.requested_effort == "high"
    assert result.effort_sent == "high"
    assert result.applied_effort is None
    assert result.latency_ms is not None
    provider.complete.assert_awaited_once()


@pytest.mark.asyncio
async def test_diagnostic_closes_provider_it_resolves(monkeypatch):
    provider = OpenAICompatProvider(
        base_url="https://api.openai.com/v1",
        api_key="redacted-fixture-key",
    )
    provider.complete = AsyncMock(return_value="OK")
    provider.aclose = AsyncMock()
    monkeypatch.setattr("core.engine.core.llm.get_llm", lambda: provider)

    result = await diagnose_provider(_settings(), live=True)

    assert result.state is ProviderDiagnosticState.REACHABLE
    provider.aclose.assert_awaited_once_with()


@pytest.mark.asyncio
async def test_diagnostic_does_not_close_caller_owned_provider():
    provider = OpenAICompatProvider(
        base_url="https://api.openai.com/v1",
        api_key="redacted-fixture-key",
    )
    provider.complete = AsyncMock(return_value="OK")
    provider.aclose = AsyncMock()

    result = await diagnose_provider(_settings(), live=True, provider=provider)

    assert result.state is ProviderDiagnosticState.REACHABLE
    provider.aclose.assert_not_awaited()


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("status", "message", "expected"),
    [
        (401, "unauthorized", ProviderDiagnosticState.UNAUTHORIZED),
        (429, "rate limit", ProviderDiagnosticState.RATE_LIMITED),
        (404, "model not found", ProviderDiagnosticState.UNSUPPORTED_MODEL),
        (400, "reasoning_effort unsupported", ProviderDiagnosticState.UNSUPPORTED_EFFORT),
        (503, "upstream unavailable", ProviderDiagnosticState.UNAVAILABLE),
    ],
)
async def test_live_http_failures_are_classified_without_raw_body(status, message, expected):
    provider = OpenAICompatProvider(base_url="https://api.openai.com/v1", api_key="never-print-this-key")
    request = httpx.Request("POST", "https://api.openai.com/v1/chat/completions")
    response = httpx.Response(status, request=request, text=f"{message}: never-print-this-key")
    provider.complete = AsyncMock(
        side_effect=httpx.HTTPStatusError("request failed", request=request, response=response)
    )

    result = await diagnose_provider(_settings(), live=True, provider=provider)

    assert result.state is expected
    assert "never-print-this-key" not in str(result.public_dict())


@pytest.mark.asyncio
async def test_live_timeout_is_bounded_and_attributable():
    provider = OpenAICompatProvider(base_url="https://api.openai.com/v1", api_key="fixture")
    provider.complete = AsyncMock(side_effect=TimeoutError())

    result = await diagnose_provider(_settings(), live=True, provider=provider)

    assert result.state is ProviderDiagnosticState.TIMED_OUT
    assert "substitute" not in result.detail.lower()


@pytest.mark.asyncio
async def test_route_specific_unsupported_effort_is_classified_before_transport(monkeypatch):
    from core.engine.core import llm as llm_mod

    monkeypatch.setattr(llm_mod.settings, "llm_reasoning_model", "claude-opus-4-8", raising=False)
    monkeypatch.setattr(llm_mod.settings, "llm_reasoning_effort", "none", raising=False)
    provider = ClaudeProvider(api_key="fixture-key", default_model="claude-sonnet-5")

    result = await diagnose_provider(_settings("claude-opus-4-8"), provider=provider)

    assert result.state is ProviderDiagnosticState.UNSUPPORTED_EFFORT
    assert result.layer == "route_capability"


@pytest.mark.asyncio
async def test_codex_passive_check_reports_authentication_not_reachability():
    provider = CodexCLIProvider(codex_bin="codex")
    completed = MagicMock(returncode=0)

    with patch("core.engine.core.provider_diagnostics.subprocess.run", return_value=completed):
        result = await diagnose_provider(_settings(), provider=provider)

    assert result.state is ProviderDiagnosticState.AUTHENTICATED
    assert result.ok is False
    assert result.checked_live is False
    assert "reachability was not tested" in result.detail
