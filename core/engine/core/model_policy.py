"""Provider-neutral rendering of ACE's existing model-routing policy.

This module does not route requests. It projects the already-authoritative
``get_llm()`` resolver and the existing budget/default/reasoning model slots
into operator-facing ``fast``/``capable``/``reasoning``/``frontier`` roles.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass
from enum import StrEnum
from typing import Any

from core.engine.core.access import AccessClass, AccessProfile, access_profile_for


class ModelRole(StrEnum):
    FAST = "fast"
    CAPABLE = "capable"
    REASONING = "reasoning"
    FRONTIER = "frontier"


@dataclass(frozen=True)
class RoleMapping:
    role: ModelRole
    requested_model: str
    resolved_model: str
    purpose: str
    resolved_effort: str = "provider_default"

    def public_dict(self) -> dict[str, str]:
        data = asdict(self)
        data["role"] = self.role.value
        return data


@dataclass(frozen=True)
class EffectiveModelPolicy:
    access: AccessProfile
    roles: tuple[RoleMapping, ...]
    escalation: str
    fallback: str
    context_limits: str
    validation_errors: tuple[str, ...] = ()
    warnings: tuple[str, ...] = ()

    @property
    def valid(self) -> bool:
        return not self.validation_errors

    def public_dict(self) -> dict[str, Any]:
        return {
            "valid": self.valid,
            "access": self.access.public_dict(),
            "roles": [role.public_dict() for role in self.roles],
            "escalation": self.escalation,
            "fallback": self.fallback,
            "context_limits": self.context_limits,
            "validation_errors": list(self.validation_errors),
            "warnings": list(self.warnings),
            "configuration_exposure": configuration_exposure(),
        }


def configuration_exposure() -> list[dict[str, object]]:
    """Inventory consequential settings without reading or returning secrets."""
    return [
        {
            "category": "onboarding-required",
            "settings": [
                "LLM_BUDGET_MODEL",
                "LLM_MODEL",
                "LLM_REASONING_MODEL",
                "LLM_FRONTIER_MODEL",
                "LLM_BUDGET_EFFORT",
                "LLM_EFFORT",
                "LLM_REASONING_EFFORT",
                "LLM_FRONTIER_EFFORT",
                "REQUIRE_SUBSCRIPTION",
                "FORCE_CLI_PROVIDER",
                "SUBSCRIPTION_PROVIDER",
                "CODEX_CLI_MODEL",
                "CODEX_CLI_EFFORT",
            ],
        },
        {
            "category": "route-selection",
            "settings": [
                "LITELLM_MODEL",
                "ANYLLM_MODEL",
                "OLLAMA_HOST",
                "OPENAI_COMPAT_BASE_URL",
                "CLAUDE_CODE_OAUTH_TOKEN",
            ],
        },
        {
            "category": "secret-reference",
            "settings": ["LLM_API_KEY", "OPENAI_COMPAT_API_KEY"],
        },
        {
            "category": "advanced-visible",
            "settings": [
                "LITELLM_MODEL_MAP",
                "ANYLLM_MODEL_MAP",
                "OLLAMA_MODEL_MAP",
                "OPENAI_COMPAT_MODEL_MAP",
                "CODEX_CLI_MODEL_MAP",
                "CODEX_CLI_EFFORT_MAP",
                "ALLOW_OAUTH_API_PATH",
            ],
        },
        {
            "category": "project-or-user-override",
            "settings": ["~/.ace/models.yml", ".ace/models.yml"],
        },
    ]


def _resolved_model(provider: object, requested: str) -> str:
    resolver = getattr(provider, "_resolve_model", None)
    if callable(resolver):
        return str(resolver(requested))
    model_arg = getattr(provider, "_model_arg", None)
    if callable(model_arg):
        return str(model_arg(requested))
    return requested


def _resolved_effort(provider: object, requested: str, resolved: str) -> str:
    resolver = getattr(provider, "_resolve_effort", None)
    if callable(resolver):
        return str(resolver(requested, resolved))
    return "provider_default"


def build_model_policy(settings: object, provider: object | None = None) -> EffectiveModelPolicy:
    """Render and validate the current provider/model policy without making a model call."""
    if provider is None:
        from core.engine.core.llm import get_llm

        provider = get_llm()

    access = access_profile_for(provider)
    requested = (
        (ModelRole.FAST, str(getattr(settings, "llm_budget_model", "")), "routine and bounded work"),
        (ModelRole.CAPABLE, str(getattr(settings, "llm_model", "")), "default reasoning"),
        (
            ModelRole.REASONING,
            str(getattr(settings, "llm_reasoning_model", "")),
            "explicit high-stakes escalation",
        ),
        (
            ModelRole.FRONTIER,
            str(getattr(settings, "llm_frontier_model", "")),
            "hardest long-horizon escalation",
        ),
    )
    roles_list: list[RoleMapping] = []
    for role, model, purpose in requested:
        resolved = _resolved_model(provider, model)
        roles_list.append(RoleMapping(role, model, resolved, purpose, _resolved_effort(provider, model, resolved)))
    roles = tuple(roles_list)

    errors = [f"{role.role.value} model is empty" for role in roles if not role.requested_model]
    if access.access_class is AccessClass.UNAVAILABLE:
        errors.append("no usable provider route resolved")

    warnings: list[str] = []
    resolved_count = len({role.resolved_model for role in roles})
    if resolved_count == 1:
        warnings.append("all semantic roles resolve to one model; escalation changes policy intent, not model identity")
    elif resolved_count < len(roles):
        warnings.append(
            "some semantic roles share a provider-native model because this provider has fewer native tiers"
        )
    if access.access_class is AccessClass.METERED_API:
        warnings.append("the selected route may incur provider charges")
    if access.access_class is AccessClass.SUBSCRIPTION:
        warnings.append("subscription-backed capacity, latency, and concurrency are provider-plan dependent")
    if access.access_class is AccessClass.LOCAL:
        warnings.append("quality, latency, context, and availability depend on operator hardware and the local model")

    return EffectiveModelPolicy(
        access=access,
        roles=roles,
        escalation=(
            "reasoning and frontier are explicit high-stakes escalations; they are never paid ACE capability tiers"
        ),
        fallback=(
            "the existing resolver honors explicit router/local/base-url intent before ambient credentials; "
            "unsupported or unavailable routes fail or degrade explicitly"
        ),
        context_limits="provider/model specific; ACE does not silently remove reasoning artifacts to fit a slower route",
        validation_errors=tuple(errors),
        warnings=tuple(warnings),
    )
