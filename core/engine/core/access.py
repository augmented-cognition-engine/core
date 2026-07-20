"""Operational access description for an already-resolved LLM provider.

Access profiles describe what ACE can observe about a route.  They are not
product plans or entitlement checks, and they never contain credential values.
The reasoning contract remains :class:`LLMProvider` for every access class.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass
from enum import StrEnum
from urllib.parse import urlparse


class AccessClass(StrEnum):
    SUBSCRIPTION = "subscription"
    METERED_API = "metered_api"
    LOCAL = "local"
    UNAVAILABLE = "unavailable"


class HealthState(StrEnum):
    UNKNOWN = "unknown"
    HEALTHY = "healthy"
    DEGRADED = "degraded"
    UNAVAILABLE = "unavailable"


@dataclass(frozen=True)
class AccessProfile:
    """Observed/safely inferred route properties, never commercial entitlement."""

    access_class: AccessClass
    provider: str
    speed: str
    concurrency: str
    privacy: str
    availability: str
    cost_model: str
    session_continuity: str
    health: HealthState = HealthState.UNKNOWN
    health_reasons: tuple[str, ...] = ()
    selected_by: str = "resolved_provider"
    billing_source: str = "none"

    def public_dict(self) -> dict:
        """JSON-safe provenance. No host URLs, tokens, keys, or credential paths."""
        data = asdict(self)
        data["access_class"] = self.access_class.value
        data["health"] = self.health.value
        data["health_reasons"] = list(self.health_reasons)
        return data


def access_profile_for(provider) -> AccessProfile:
    """Describe a concrete provider without inspecting ambient credentials."""
    name = type(provider).__name__

    if name == "CLIProvider":
        return AccessProfile(
            AccessClass.SUBSCRIPTION,
            name,
            "subprocess",
            "provider_plan_limited",
            "provider_managed",
            "cli_and_account_dependent",
            "subscription_credit",
            "checkpointed_stateless_calls",
            selected_by="available_cli",
            billing_source="cli_provider",
        )
    if name == "CodexCLIProvider":
        return AccessProfile(
            AccessClass.SUBSCRIPTION,
            name,
            "subprocess",
            "provider_plan_limited",
            "openai_managed",
            "cli_account_and_workspace_dependent",
            "chatgpt_subscription_credit",
            "checkpointed_stateless_calls",
            selected_by="explicit_subscription_provider",
            billing_source="codex_cli",
        )
    if name == "ClaudeProvider" and getattr(provider, "_oauth_token", None):
        return AccessProfile(
            AccessClass.SUBSCRIPTION,
            name,
            "network",
            "provider_plan_limited",
            "provider_managed",
            "network_and_account_dependent",
            "subscription_credit",
            "checkpointed_stateless_calls",
            selected_by="explicit_oauth_token",
            billing_source="anthropic_oauth",
        )
    if name == "ClaudeProvider" and getattr(provider, "_api_key", None):
        return AccessProfile(
            AccessClass.METERED_API,
            name,
            "network",
            "provider_rate_limited",
            "provider_managed",
            "network_and_account_dependent",
            "per_token_metered",
            "checkpointed_stateless_calls",
            selected_by="explicit_api_key",
            billing_source="anthropic_api",
        )
    if name == "OllamaProvider":
        return AccessProfile(
            AccessClass.LOCAL,
            name,
            "hardware_dependent",
            "hardware_limited",
            "local_or_operator_network",
            "host_and_model_dependent",
            "operator_compute",
            "checkpointed_stateless_calls",
            selected_by="explicit_ollama_host",
            billing_source="local_compute",
        )
    if name == "OpenAICompatProvider":
        host = urlparse(getattr(provider, "_base_url", "")).hostname or ""
        local = host in {"localhost", "127.0.0.1", "::1"}
        return AccessProfile(
            AccessClass.LOCAL if local else AccessClass.METERED_API,
            name,
            "hardware_dependent" if local else "network",
            "backend_limited",
            "local_process" if local else "backend_managed",
            "endpoint_dependent",
            "operator_compute" if local else "backend_metered_or_operator_managed",
            "checkpointed_stateless_calls",
            selected_by="explicit_compat_endpoint",
            billing_source="local_compute" if local else "openai_compat",
        )
    if name in {"LiteLLMProvider", "AnyLLMProvider"}:
        return AccessProfile(
            AccessClass.METERED_API,
            name,
            "backend_dependent",
            "backend_limited",
            "backend_managed",
            "router_and_backend_dependent",
            "backend_defined",
            "checkpointed_stateless_calls",
            selected_by="explicit_router_model",
            billing_source=name.removesuffix("Provider").lower(),
        )
    return AccessProfile(
        AccessClass.UNAVAILABLE,
        name,
        "unknown",
        "unknown",
        "unknown",
        "not_confirmed",
        "none",
        "none",
        health=HealthState.UNAVAILABLE,
        health_reasons=("unrecognized_or_unconfigured_provider",),
    )


def with_health(profile: AccessProfile, state: HealthState, *reasons: str) -> AccessProfile:
    """Return an updated immutable profile after active probing."""
    values = profile.public_dict()
    values["access_class"] = profile.access_class
    values["health"] = state
    values["health_reasons"] = tuple(reasons)
    return AccessProfile(**values)
