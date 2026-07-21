"""Secret-safe, provider-neutral diagnostics for the resolved model route.

Configuration is not reachability.  The default inspection therefore stops at
``configured_unverified`` (or a locally verifiable authentication state).  A
minimal model call is made only when the operator explicitly requests a live
check through ``ace doctor --live-provider``.
"""

from __future__ import annotations

import asyncio
import subprocess
import time
from dataclasses import asdict, dataclass
from enum import StrEnum
from typing import Any

import httpx

from core.engine.core.access import AccessClass, access_profile_for


class ProviderDiagnosticState(StrEnum):
    NOT_CONFIGURED = "not_configured"
    CONFIGURED_UNVERIFIED = "configured_unverified"
    AUTHENTICATED = "authenticated"
    REACHABLE = "reachable"
    RATE_LIMITED = "rate_limited"
    UNAUTHORIZED = "unauthorized"
    UNAVAILABLE = "unavailable"
    TIMED_OUT = "timed_out"
    UNSUPPORTED_MODEL = "unsupported_model"
    UNSUPPORTED_EFFORT = "unsupported_effort"
    LOCAL_DEPENDENCY_UNAVAILABLE = "local_dependency_unavailable"
    OPERATIONAL_DEGRADED = "provider_operational_but_degraded"


@dataclass(frozen=True)
class ProviderDiagnosticResult:
    ok: bool
    state: ProviderDiagnosticState
    layer: str
    provider: str
    route: str
    credential_source: str
    configured_model: str | None
    resolved_model: str | None
    requested_effort: str | None
    effort_sent: str | None
    applied_effort: str | None
    checked_live: bool
    detail: str
    action: str
    latency_ms: int | None = None
    usage: dict[str, int] | None = None

    def public_dict(self) -> dict[str, Any]:
        data = asdict(self)
        data["state"] = self.state.value
        return data


def _credential_source(provider: object) -> str:
    name = type(provider).__name__
    if name == "CodexCLIProvider":
        return "Codex CLI managed sign-in"
    if name == "CLIProvider":
        return "Claude CLI managed sign-in"
    if name == "ClaudeProvider":
        if getattr(provider, "_oauth_token", None):
            return "CLAUDE_CODE_OAUTH_TOKEN"
        if getattr(provider, "_api_key", None):
            return "LLM_API_KEY or explicitly enabled Claude credential source"
        return "none"
    if name == "OpenAICompatProvider":
        return "OPENAI_COMPAT_API_KEY / OPENAI_API_KEY or endpoint-defined"
    if name == "OllamaProvider":
        return "none (local endpoint)"
    if name in {"LiteLLMProvider", "AnyLLMProvider"}:
        return "router/backend environment"
    return "none"


def _route_details(settings: object, provider: object) -> tuple[str | None, str | None, str | None, str | None]:
    configured = str(getattr(settings, "llm_budget_model", "")) or None
    resolver = getattr(provider, "_resolve_model", None)
    if not callable(resolver):
        resolver = getattr(provider, "_model_arg", None)
    resolved = str(resolver(configured)) if callable(resolver) else configured
    effort_resolver = getattr(provider, "_resolve_effort", None)
    requested = str(effort_resolver(configured, resolved)) if callable(effort_resolver) else "provider_default"
    effort_sent = None if requested in {"default", "provider_default"} else requested
    # Current adapters do not receive an authoritative applied-effort field.
    # Keep this null instead of claiming the provider honored a request.
    return configured, resolved, requested, effort_sent


def _result(
    *,
    state: ProviderDiagnosticState,
    provider: str = "unresolved",
    route: str = "none",
    credential_source: str = "none",
    configured_model: str | None = None,
    resolved_model: str | None = None,
    requested_effort: str | None = None,
    effort_sent: str | None = None,
    checked_live: bool = False,
    detail: str,
    action: str,
    layer: str = "provider",
    latency_ms: int | None = None,
    usage: dict[str, int] | None = None,
) -> ProviderDiagnosticResult:
    return ProviderDiagnosticResult(
        ok=state is ProviderDiagnosticState.REACHABLE,
        state=state,
        layer=layer,
        provider=provider,
        route=route,
        credential_source=credential_source,
        configured_model=configured_model,
        resolved_model=resolved_model,
        requested_effort=requested_effort,
        effort_sent=effort_sent,
        applied_effort=None,
        checked_live=checked_live,
        detail=detail,
        action=action,
        latency_ms=latency_ms,
        usage=usage,
    )


def _classify_failure(exc: BaseException) -> tuple[ProviderDiagnosticState, str, str]:
    status = getattr(exc, "status_code", None)
    response = getattr(exc, "response", None)
    status = status or getattr(response, "status_code", None)
    lowered = str(exc).lower()
    try:
        # Response text is used only for classification and is never returned,
        # logged, or persisted; some providers name the rejected parameter only
        # in this body.
        lowered = f"{lowered} {str(response.text)[:2000].lower()}" if response is not None else lowered
    except Exception:
        pass

    if isinstance(exc, (TimeoutError, asyncio.TimeoutError, httpx.TimeoutException)) or "timed out" in lowered:
        return (
            ProviderDiagnosticState.TIMED_OUT,
            "The configured provider did not answer before the diagnostic deadline.",
            "Check provider status and network access, then retry with a larger --provider-timeout if appropriate.",
        )
    if status in {401, 403} or any(word in lowered for word in ("unauthorized", "authentication", "not signed in")):
        return (
            ProviderDiagnosticState.UNAUTHORIZED,
            "The provider rejected the configured authentication.",
            "Sign in again or replace the rejected credential through `ace setup`, then rerun the live check.",
        )
    if status == 429 or "rate limit" in lowered or "rate_limit" in lowered:
        return (
            ProviderDiagnosticState.RATE_LIMITED,
            "The provider is reachable but is currently rate-limiting this route.",
            "Wait for provider capacity or quota to recover; ACE did not substitute another provider.",
        )
    if (status in {400, 404, 422} or "unsupported" in lowered) and ("reasoning" in lowered or "effort" in lowered):
        return (
            ProviderDiagnosticState.UNSUPPORTED_EFFORT,
            "The selected route rejected the requested reasoning effort.",
            "Choose an effort supported by this route or use `default` so the provider selects it.",
        )
    if (status in {400, 404, 422} or "unsupported" in lowered) and "model" in lowered:
        return (
            ProviderDiagnosticState.UNSUPPORTED_MODEL,
            "The selected route does not expose the resolved model.",
            "Correct the provider model map or select an available ACE tier, then retry.",
        )
    if isinstance(exc, (FileNotFoundError, ModuleNotFoundError)) or "executable was found" in lowered:
        return (
            ProviderDiagnosticState.LOCAL_DEPENDENCY_UNAVAILABLE,
            "A required local provider executable or optional adapter is unavailable.",
            "Install the named CLI/extra for the selected route, authenticate it, and retry.",
        )
    if status is not None and int(status) >= 500:
        return (
            ProviderDiagnosticState.UNAVAILABLE,
            "The provider returned an upstream service failure.",
            "Check provider status and retry later; ACE did not substitute another provider.",
        )
    if isinstance(exc, (ValueError, UnicodeError)) or "no agent message" in lowered or "malformed" in lowered:
        return (
            ProviderDiagnosticState.OPERATIONAL_DEGRADED,
            "The provider answered but the response did not satisfy ACE's completion contract.",
            "Inspect the selected model's structured-output support and route mapping.",
        )
    return (
        ProviderDiagnosticState.UNAVAILABLE,
        "The configured provider route could not complete the diagnostic request.",
        "Check the selected route, provider status, and local/network dependencies, then retry.",
    )


def _codex_auth_state(settings: object, provider: object, timeout: float) -> ProviderDiagnosticResult | None:
    if type(provider).__name__ != "CodexCLIProvider":
        return None
    configured, resolved, requested, effort_sent = _route_details(settings, provider)
    try:
        completed = subprocess.run(
            [str(getattr(provider, "_codex_bin")), "login", "status"],
            stdin=subprocess.DEVNULL,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            check=False,
            timeout=min(timeout, 15.0),
            env=getattr(provider, "_subprocess_env")(),
        )
    except subprocess.TimeoutExpired:
        state, detail, action = _classify_failure(TimeoutError("timed out"))
    except OSError:
        state = ProviderDiagnosticState.LOCAL_DEPENDENCY_UNAVAILABLE
        detail = "The configured Codex CLI executable could not be started."
        action = "Install or repair Codex, run `codex login`, and retry."
    else:
        if completed.returncode == 0:
            state = ProviderDiagnosticState.AUTHENTICATED
            detail = "Codex CLI reports an authenticated session; model reachability was not tested."
            action = "Run `ace doctor --live-provider` to verify the resolved model with one minimal request."
        else:
            state = ProviderDiagnosticState.UNAUTHORIZED
            detail = "Codex CLI is installed but does not report an authenticated session."
            action = "Run `codex login`, then rerun `ace doctor --live-provider`."
    return _result(
        state=state,
        provider=type(provider).__name__,
        route="explicit_subscription_provider",
        credential_source=_credential_source(provider),
        configured_model=configured,
        resolved_model=resolved,
        requested_effort=requested,
        effort_sent=effort_sent,
        detail=detail,
        action=action,
    )


async def diagnose_provider(
    settings: object,
    *,
    live: bool = False,
    timeout: float = 30.0,
    provider: object | None = None,
) -> ProviderDiagnosticResult:
    """Inspect or minimally probe the selected provider without exposing credentials."""
    try:
        if provider is None:
            from core.engine.core.llm import get_llm

            provider = get_llm()
    except Exception as exc:
        state, detail, action = _classify_failure(exc)
        return _result(state=state, checked_live=live, detail=detail, action=action, layer="route_selection")

    profile = access_profile_for(provider)
    name = type(provider).__name__
    empty_claude = name == "ClaudeProvider" and not (
        getattr(provider, "_api_key", None) or getattr(provider, "_oauth_token", None)
    )
    if profile.access_class is AccessClass.UNAVAILABLE or empty_claude:
        return _result(
            state=ProviderDiagnosticState.NOT_CONFIGURED,
            provider=name,
            route=profile.selected_by,
            detail="No usable model-provider route is configured.",
            action="Run `ace setup` and select one provider route, then rerun `ace doctor`.",
            layer="configuration",
        )

    try:
        configured, resolved, requested, effort_sent = _route_details(settings, provider)
    except Exception as exc:
        state, detail, action = _classify_failure(exc)
        return _result(
            state=state,
            provider=name,
            route=profile.selected_by,
            credential_source=_credential_source(provider),
            checked_live=live,
            detail=detail,
            action=action,
            layer="route_capability",
        )
    common = {
        "provider": name,
        "route": profile.selected_by,
        "credential_source": _credential_source(provider),
        "configured_model": configured,
        "resolved_model": resolved,
        "requested_effort": requested,
        "effort_sent": effort_sent,
    }

    if not live:
        codex_state = _codex_auth_state(settings, provider, timeout)
        if codex_state is not None:
            return codex_state
        return _result(
            state=ProviderDiagnosticState.CONFIGURED_UNVERIFIED,
            **common,
            detail="The route is configured, but authentication and model reachability were not tested.",
            action="Run `ace doctor --live-provider` to make one minimal, explicitly labeled provider request.",
        )

    started = time.monotonic()
    try:
        text = await asyncio.wait_for(
            provider.complete(
                "Reply with exactly OK.",
                model=configured,
                max_tokens=16,
                system="Return only the requested text. Do not use tools.",
            ),
            timeout=timeout,
        )
        latency_ms = int((time.monotonic() - started) * 1000)
        if not str(text).strip():
            return _result(
                state=ProviderDiagnosticState.OPERATIONAL_DEGRADED,
                checked_live=True,
                latency_ms=latency_ms,
                **common,
                detail="The provider accepted the request but returned no usable text.",
                action="Inspect model compatibility and provider response handling; no fallback was attempted.",
            )
        usage = getattr(provider, "usage_stats", None)
        return _result(
            state=ProviderDiagnosticState.REACHABLE,
            checked_live=True,
            latency_ms=latency_ms,
            usage=dict(usage) if isinstance(usage, dict) else None,
            **common,
            detail="The configured route completed one minimal diagnostic request.",
            action="No provider action is required.",
        )
    except BaseException as exc:
        if isinstance(exc, (asyncio.CancelledError, KeyboardInterrupt, SystemExit)):
            raise
        state, detail, action = _classify_failure(exc)
        return _result(
            state=state,
            checked_live=True,
            latency_ms=int((time.monotonic() - started) * 1000),
            **common,
            detail=detail,
            action=action,
        )
