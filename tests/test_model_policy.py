from types import SimpleNamespace

from click.testing import CliRunner

from core.engine.cli.main import cli
from core.engine.core.model_policy import build_model_policy, configuration_exposure


class OllamaProvider:
    _default_model = "local-default"

    def _resolve_model(self, requested):
        return {
            "budget": "small",
            "default": "medium",
            "reasoning": "large",
            "frontier": "frontier",
        }[requested]


def _settings():
    return SimpleNamespace(
        llm_budget_model="budget",
        llm_model="default",
        llm_reasoning_model="reasoning",
        llm_frontier_model="frontier",
    )


def test_policy_projects_existing_router_into_provider_neutral_roles():
    policy = build_model_policy(_settings(), OllamaProvider())
    payload = policy.public_dict()
    assert policy.valid
    assert payload["access"]["access_class"] == "local"
    assert [role["role"] for role in payload["roles"]] == ["fast", "capable", "reasoning", "frontier"]
    assert [role["resolved_model"] for role in payload["roles"]] == ["small", "medium", "large", "frontier"]
    assert "secret-reference" in str(payload)
    assert "redacted-secret-value" not in str(payload)


def test_configuration_exposure_never_returns_values():
    inventory = configuration_exposure()
    assert any(item["category"] == "secret-reference" for item in inventory)
    assert all(set(item) == {"category", "settings"} for item in inventory)


def test_model_policy_cli_exposes_effective_policy(monkeypatch):
    monkeypatch.setattr(
        "core.engine.cli.commands.model_policy.build_model_policy",
        lambda _configured_settings: build_model_policy(_settings(), OllamaProvider()),
    )
    result = CliRunner().invoke(cli, ["model-policy", "--json-output"])
    assert result.exit_code == 0
    assert '"fast"' in result.output
    assert '"local"' in result.output


def test_codex_policy_exposes_distinct_effort_for_shared_sol_model():
    from core.engine.core.llm import CodexCLIProvider

    settings = _settings()
    settings.llm_budget_model = "claude-haiku-4-5-20251001"
    settings.llm_model = "claude-sonnet-5"
    settings.llm_reasoning_model = "claude-opus-4-8"
    settings.llm_frontier_model = "claude-fable-5"
    policy = build_model_policy(settings, CodexCLIProvider(codex_bin="codex"))
    roles = {role.role.value: role for role in policy.roles}
    assert roles["reasoning"].resolved_model == "gpt-5.6-sol"
    assert roles["reasoning"].resolved_effort == "high"
    assert roles["frontier"].resolved_model == "gpt-5.6-sol"
    assert roles["frontier"].resolved_effort == "xhigh"
