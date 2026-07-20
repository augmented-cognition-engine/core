from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

from click.testing import CliRunner

from core.engine.cli.main import cli


def test_doctor_reports_all_preview_checks(monkeypatch):
    monkeypatch.setenv("ACE_API_KEY", "test")
    with (
        patch(
            "core.engine.cli.commands.doctor._database_check",
            new=AsyncMock(return_value=(True, "ws://localhost:8001", True, "141 (expected 141)")),
        ),
        patch("core.engine.cli.commands.doctor._provider_configured", return_value=(True, "test provider")),
        patch(
            "core.engine.cli.commands.doctor._model_policy_check",
            return_value=(True, {"valid": True, "roles": []}),
        ),
        patch(
            "core.engine.cli.commands.doctor.get_headers",
            return_value={"Authorization": "Bearer redacted"},
        ),
        patch("core.engine.cli.commands.doctor.httpx.get") as get,
        patch(
            "ace_mcp_client.server.mcp.list_tools",
            new=AsyncMock(
                return_value=[
                    SimpleNamespace(name=name)
                    for name in (
                        "ace_start",
                        "ace_load",
                        "ace_capture",
                        "ace_task",
                        "ace_status",
                        "ace_capture_idea",
                        "ace_search",
                        "ace_briefing",
                        "ace_impact",
                        "ace_history",
                        "ace_related",
                    )
                ]
            ),
        ),
    ):
        get.return_value.status_code = 200
        result = CliRunner().invoke(cli, ["doctor", "--json-output"])
    assert "configuration" in result.output
    assert "surrealdb" in result.output
    assert "schema" in result.output
    assert "model_provider" in result.output
    assert "model_policy" in result.output
    assert "authentication" in result.output
    assert "api" in result.output
    assert "mcp" in result.output
    assert result.exit_code == 0


def test_doctor_rejects_stale_saved_token(monkeypatch):
    monkeypatch.setenv("ACE_API_KEY", "test")
    healthy = SimpleNamespace(status_code=200)
    rejected = SimpleNamespace(status_code=401)
    with (
        patch(
            "core.engine.cli.commands.doctor._database_check",
            new=AsyncMock(return_value=(True, "ws://localhost:8001", True, "142 (expected 142)")),
        ),
        patch("core.engine.cli.commands.doctor._provider_configured", return_value=(True, "test provider")),
        patch("core.engine.cli.commands.doctor._model_policy_check", return_value=(True, {"valid": True})),
        patch(
            "core.engine.cli.commands.doctor.get_headers",
            return_value={"Authorization": "Bearer stale"},
        ),
        patch("core.engine.cli.commands.doctor.httpx.get", side_effect=[healthy, rejected]),
        patch(
            "ace_mcp_client.server.mcp.list_tools",
            new=AsyncMock(return_value=[SimpleNamespace(name=f"tool-{index}") for index in range(11)]),
        ),
    ):
        result = CliRunner().invoke(cli, ["doctor", "--json-output"])
    assert result.exit_code == 1
    assert "protected request rejected (401)" in result.output
    assert "ace login" in result.output


def test_provider_check_accepts_claude_cli_without_settings_field(monkeypatch):
    from core.engine.cli.commands.doctor import _provider_configured

    monkeypatch.delenv("CLAUDE_CODE_OAUTH_TOKEN", raising=False)
    settings = SimpleNamespace(
        openai_compat_base_url=None,
        ollama_host=None,
        llm_api_key="dev-placeholder-not-a-real-key",
    )
    with patch("core.engine.cli.commands.doctor.shutil.which", return_value="/usr/local/bin/claude"):
        assert _provider_configured(settings) == (True, "Claude CLI")
