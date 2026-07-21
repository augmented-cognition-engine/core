"""Tests for the one-command local onboarding flow."""

from __future__ import annotations

import json
import stat
from pathlib import Path
from unittest.mock import MagicMock, patch

import click
import pytest
from click.testing import CliRunner

from core.engine.cli.commands.setup import (
    _onboarding_summary,
    _parse_env,
    _provider_preflight,
    _provider_updates,
    _start_local_runtime,
    _stop_local_runtime,
    _update_env,
    onboarding,
    service,
    setup,
)
from core.engine.cli.main import cli


@pytest.fixture(autouse=True)
def isolated_setup_state(tmp_path, monkeypatch):
    config_dir = tmp_path / "ace-config"
    monkeypatch.setenv("ACE_CONFIG_DIR", str(config_dir))
    return config_dir


def _project(tmp_path: Path, env: str | None = None) -> Path:
    (tmp_path / "infra").mkdir()
    (tmp_path / "infra" / "docker-compose.yml").write_text("services: {}\n")
    (tmp_path / "scripts").mkdir()
    (tmp_path / "scripts" / "schema_apply.py").write_text("")
    (tmp_path / ".env.example").write_text(
        (
            env
            or "\n".join(
                [
                    "SURREAL_URL=ws://localhost:8001",
                    "JWT_SECRET=replace-me-with-32-byte-hex-string",
                    "API_KEY=local-dev-only-not-a-secret",
                    "LLM_API_KEY=sk-test-placeholder",
                ]
            )
        )
        + "\n"
    )
    return tmp_path


def test_setup_no_start_generates_secrets_and_configures_ollama(tmp_path, monkeypatch):
    root = _project(tmp_path)
    monkeypatch.delenv("OLLAMA_HOST", raising=False)
    monkeypatch.delenv("OLLAMA_MODEL", raising=False)

    result = CliRunner().invoke(
        setup,
        ["--project-dir", str(root), "--provider", "ollama", "--no-start"],
    )

    assert result.exit_code == 0, result.output
    values = _parse_env((root / ".env").read_text())
    assert values["JWT_SECRET"] != "replace-me-with-32-byte-hex-string"
    assert len(values["JWT_SECRET"]) == 64
    assert values["API_KEY"] != "local-dev-only-not-a-secret"
    assert values["OLLAMA_HOST"] == "http://localhost:11434"
    assert values["OLLAMA_MODEL"] == "llama3.2"
    assert values["LLM_API_KEY"] == "sk-test-placeholder"
    assert stat.S_IMODE((root / ".env").stat().st_mode) == 0o600
    assert "Services were not started" in result.output


def test_setup_is_idempotent_for_existing_secrets(tmp_path, monkeypatch):
    root = _project(
        tmp_path,
        env="\n".join(
            [
                "JWT_SECRET=already-secret",
                "API_KEY=already-api-key",
                "LLM_API_KEY=sk-test-placeholder",
                "OLLAMA_HOST=http://localhost:11434",
                "OLLAMA_MODEL=qwen3",
            ]
        ),
    )
    monkeypatch.delenv("OLLAMA_HOST", raising=False)
    monkeypatch.delenv("OLLAMA_MODEL", raising=False)

    first = CliRunner().invoke(setup, ["--project-dir", str(root), "--no-start"])
    second = CliRunner().invoke(setup, ["--project-dir", str(root), "--no-start"])

    assert first.exit_code == second.exit_code == 0
    values = _parse_env((root / ".env").read_text())
    assert values["JWT_SECRET"] == "already-secret"
    assert values["API_KEY"] == "already-api-key"
    assert values["OLLAMA_MODEL"] == "qwen3"
    assert (root / ".env").read_text().count("JWT_SECRET=") == 1


def test_setup_noninteractive_requires_a_provider(tmp_path):
    root = _project(tmp_path)
    with patch("core.engine.cli.commands.setup._detect_provider", return_value=None):
        result = CliRunner().invoke(
            setup,
            ["--project-dir", str(root), "--non-interactive", "--no-start"],
        )

    assert result.exit_code != 0
    assert "No provider was detected" in result.output
    assert not (root / ".env").exists()


def test_setup_starts_runtime_and_logs_in_without_exposing_api_key(tmp_path, monkeypatch):
    root = _project(tmp_path)
    monkeypatch.setenv("OLLAMA_HOST", "http://localhost:11434")
    captured: dict[str, object] = {}

    def fake_start(project_root, values):
        captured["root"] = project_root
        captured["values"] = values

    def fake_login(api_key):
        captured["api_key"] = api_key

    with (
        patch("core.engine.cli.commands.setup._provider_preflight"),
        patch("core.engine.cli.commands.setup._start_local_runtime", side_effect=fake_start),
        patch("core.engine.cli.commands.setup._login_local", side_effect=fake_login),
        patch("core.engine.cli.commands.setup.get_config_path", return_value=tmp_path / "token.json"),
        patch("core.engine.cli.commands.setup.shutil.which", return_value="/usr/local/bin/ace-mcp-client"),
    ):
        result = CliRunner().invoke(
            setup,
            ["--project-dir", str(root), "--provider", "ollama", "--skip-first-task"],
        )

    assert result.exit_code == 0, result.output
    assert captured["root"] == root
    values = captured["values"]
    assert isinstance(values, dict)
    assert captured["api_key"] == values["API_KEY"]
    assert str(values["API_KEY"]) not in result.output
    assert "/usr/local/bin/ace-mcp-client" in result.output
    assert "ACE is ready" in result.output


def test_provider_selection_clears_higher_priority_routes(monkeypatch):
    monkeypatch.setattr("core.engine.cli.commands.setup.shutil.which", lambda name: f"/bin/{name}")
    updates = _provider_updates(
        "codex",
        {"LLM_API_KEY": "metered-key", "OLLAMA_HOST": "http://old-provider"},
        {},
        non_interactive=True,
    )

    assert updates["OLLAMA_HOST"] == ""
    assert updates["LLM_API_KEY"] == "sk-test-placeholder"
    assert updates["SUBSCRIPTION_PROVIDER"] == "codex"
    assert updates["REQUIRE_SUBSCRIPTION"] == "1"


def test_update_env_activates_commented_provider_setting_without_duplication():
    updated = _update_env("# SUBSCRIPTION_PROVIDER=codex\nOTHER=value\n", {"SUBSCRIPTION_PROVIDER": "codex"})

    assert updated.count("SUBSCRIPTION_PROVIDER=") == 1
    assert "SUBSCRIPTION_PROVIDER=codex" in updated


def test_setup_is_registered_in_main_cli():
    result = CliRunner().invoke(cli, ["--help"])

    assert result.exit_code == 0, result.output
    assert "setup" in result.output
    assert "service" in result.output
    assert "onboarding" in result.output


def test_service_start_reuses_saved_configuration(tmp_path, monkeypatch):
    root = _project(
        tmp_path,
        env="\n".join(
            [
                "JWT_SECRET=saved-jwt",
                "API_KEY=saved-api-key",
                "LLM_API_KEY=sk-test-placeholder",
                "OLLAMA_HOST=http://localhost:11434",
            ]
        ),
    )
    (root / ".env").write_text((root / ".env.example").read_text())
    monkeypatch.delenv("OLLAMA_HOST", raising=False)

    with (
        patch("core.engine.cli.commands.setup._provider_preflight"),
        patch("core.engine.cli.commands.setup._start_local_runtime") as start,
        patch("core.engine.cli.commands.setup._login_local") as login,
    ):
        result = CliRunner().invoke(service, ["start", "--project-dir", str(root)])

    assert result.exit_code == 0, result.output
    start.assert_called_once()
    login.assert_called_once_with("saved-api-key")
    assert "ACE is ready" in result.output


def test_service_stop_preserves_data_and_delegates_to_runtime(tmp_path):
    root = _project(tmp_path)
    with patch("core.engine.cli.commands.setup._stop_local_runtime") as stop:
        result = CliRunner().invoke(service, ["stop", "--project-dir", str(root)])

    assert result.exit_code == 0, result.output
    stop.assert_called_once_with(root)


def test_runtime_stop_accepts_a_terminated_zombie_process(tmp_path, isolated_setup_state):
    root = _project(tmp_path)
    pid_file = isolated_setup_state / "api.pid"
    pid_file.parent.mkdir(parents=True, exist_ok=True)
    pid_file.write_text("1234\n")

    with (
        patch("core.engine.cli.commands.setup._managed_api_pid", side_effect=[1234, 1234, None, None]),
        patch("core.engine.cli.commands.setup.os.kill") as kill,
        patch("core.engine.cli.commands.setup.time.monotonic", side_effect=[0, 1, 2]),
        patch("core.engine.cli.commands.setup.time.sleep"),
        patch("core.engine.cli.commands.setup._compose_command", return_value=["docker", "compose"]),
        patch("core.engine.cli.commands.setup.subprocess.run") as run,
    ):
        _stop_local_runtime(root)

    kill.assert_called_once_with(1234, 15)
    run.assert_called_once()
    assert not pid_file.exists()


def test_setup_records_time_to_first_use_and_trial_answers(tmp_path, monkeypatch, isolated_setup_state):
    root = _project(tmp_path)
    monkeypatch.setenv("OLLAMA_HOST", "http://localhost:11434")

    with (
        patch("core.engine.cli.commands.setup._provider_preflight"),
        patch("core.engine.cli.commands.setup._start_local_runtime"),
        patch("core.engine.cli.commands.setup._login_local"),
        patch("core.engine.cli.commands.setup._run_first_task", return_value=(True, 2.5)),
    ):
        result = CliRunner().invoke(
            setup,
            [
                "--project-dir",
                str(root),
                "--provider",
                "ollama",
                "--first-task",
                "Which customer should I serve first?",
                "--onboarding-trial",
            ],
            input="n\nn\n",
        )

    assert result.exit_code == 0, result.output
    evidence_path = isolated_setup_state / "onboarding.jsonl"
    event = json.loads(evidence_path.read_text().splitlines()[-1])
    assert event["success"] is True
    assert event["first_result_attempted"] is True
    assert event["first_result_succeeded"] is True
    assert event["first_result_seconds"] == 2.5
    assert event["time_to_first_result_seconds"] >= 0
    assert event["maintainer_help_reported"] is False
    assert event["architecture_knowledge_reported"] is False
    assert "provider" in event


def test_setup_first_result_failure_is_not_reported_as_success(tmp_path, monkeypatch, isolated_setup_state):
    root = _project(tmp_path)
    monkeypatch.setenv("OLLAMA_HOST", "http://localhost:11434")

    with (
        patch("core.engine.cli.commands.setup._provider_preflight"),
        patch("core.engine.cli.commands.setup._start_local_runtime"),
        patch("core.engine.cli.commands.setup._login_local"),
        patch("core.engine.cli.commands.setup._run_first_task", return_value=(False, 900.0)),
    ):
        result = CliRunner().invoke(
            setup,
            [
                "--project-dir",
                str(root),
                "--provider",
                "ollama",
                "--first-task",
                "Which customer should I serve first?",
                "--onboarding-trial",
            ],
            input="n\nn\n",
        )

    assert result.exit_code != 0
    assert "did not reach a useful reasoning result" in result.output
    event = json.loads((isolated_setup_state / "onboarding.jsonl").read_text().splitlines()[-1])
    assert event["success"] is False
    assert event["setup_succeeded"] is True
    assert event["first_result_attempted"] is True
    assert event["first_result_succeeded"] is False
    assert event["path_succeeded"] is False
    assert event["failure_stage"] == "first_result"


def test_setup_failure_records_stage_and_preserves_guided_recovery(tmp_path, monkeypatch, isolated_setup_state):
    root = _project(tmp_path)
    monkeypatch.setenv("OLLAMA_HOST", "http://localhost:11434")
    recovery = (
        "Start Docker Desktop or your Docker-compatible engine (for Colima: `colima start`), "
        "then rerun `ace setup`; your saved configuration will be reused."
    )

    with (
        patch("core.engine.cli.commands.setup._provider_preflight"),
        patch(
            "core.engine.cli.commands.setup._start_local_runtime",
            side_effect=click.ClickException(recovery),
        ),
    ):
        result = CliRunner().invoke(
            setup,
            ["--project-dir", str(root), "--provider", "ollama", "--skip-first-task"],
        )

    assert result.exit_code != 0
    assert recovery in result.output
    event = json.loads((isolated_setup_state / "onboarding.jsonl").read_text().splitlines()[-1])
    assert event["success"] is False
    assert event["failure_stage"] == "local_services"
    assert event["failure_type"] == "ClickException"
    assert (root / ".env").exists()


def test_ollama_preflight_reports_missing_model():
    response = MagicMock()
    response.json.return_value = {"models": [{"name": "qwen3:latest"}]}
    response.raise_for_status.return_value = None

    with patch("core.engine.cli.commands.setup.httpx.get", return_value=response):
        with pytest.raises(click.ClickException, match="ollama pull llama3.2"):
            _provider_preflight(
                "ollama",
                {"OLLAMA_HOST": "http://localhost:11434", "OLLAMA_MODEL": "llama3.2"},
            )


def test_ollama_preflight_accepts_installed_model():
    response = MagicMock()
    response.json.return_value = {"models": [{"name": "llama3.2:3b"}]}
    response.raise_for_status.return_value = None

    with patch("core.engine.cli.commands.setup.httpx.get", return_value=response):
        _provider_preflight(
            "ollama",
            {"OLLAMA_HOST": "http://localhost:11434", "OLLAMA_MODEL": "llama3.2"},
        )


def test_codex_preflight_requires_an_authenticated_cli():
    status = MagicMock(returncode=1)
    with (
        patch("core.engine.cli.commands.setup.shutil.which", return_value="/usr/local/bin/codex"),
        patch("core.engine.cli.commands.setup.subprocess.run", return_value=status),
        pytest.raises(click.ClickException, match="not signed in"),
    ):
        _provider_preflight("codex", {"SUBSCRIPTION_PROVIDER": "codex"})


def test_runtime_reports_port_collision_before_launching_api(tmp_path):
    root = _project(tmp_path)
    with (
        patch("core.engine.cli.commands.setup._compose_command", return_value=["docker", "compose"]),
        patch("core.engine.cli.commands.setup.subprocess.run"),
        patch("core.engine.cli.commands.setup._api_is_ready", return_value=False),
        patch("core.engine.cli.commands.setup._api_port_is_occupied", return_value=True),
        patch("core.engine.cli.commands.setup.subprocess.Popen") as popen,
        pytest.raises(click.ClickException, match="Port 3000"),
    ):
        _start_local_runtime(root, {"JWT_SECRET": "safe", "API_KEY": "safe"})

    popen.assert_not_called()


def test_runtime_timeout_points_to_supported_log_command(tmp_path):
    root = _project(tmp_path)
    process = MagicMock(pid=1234)
    with (
        patch("core.engine.cli.commands.setup._compose_command", return_value=["docker", "compose"]),
        patch("core.engine.cli.commands.setup.subprocess.run"),
        patch("core.engine.cli.commands.setup._api_is_ready", return_value=False),
        patch("core.engine.cli.commands.setup._api_port_is_occupied", return_value=False),
        patch("core.engine.cli.commands.setup._managed_api_pid", return_value=None),
        patch("core.engine.cli.commands.setup.subprocess.Popen", return_value=process),
        patch("core.engine.cli.commands.setup.time.monotonic", side_effect=[0, 31]),
        pytest.raises(click.ClickException, match=r"ace service logs --lines 80"),
    ):
        _start_local_runtime(root, {"JWT_SECRET": "safe", "API_KEY": "safe"})


def test_provider_rejects_an_incomplete_api_key():
    with pytest.raises(click.ClickException, match="looks incomplete"):
        _provider_updates(
            "anthropic",
            {"LLM_API_KEY": "too-short"},
            {},
            non_interactive=True,
        )


def test_service_logs_shows_recent_lines(isolated_setup_state):
    (isolated_setup_state / "api.log").parent.mkdir(parents=True, exist_ok=True)
    (isolated_setup_state / "api.log").write_text("one\ntwo\nthree\n")

    result = CliRunner().invoke(service, ["logs", "--lines", "2"])

    assert result.exit_code == 0, result.output
    assert result.output == "two\nthree\n"


def test_onboarding_report_summarizes_activation_and_clean_user_evidence(isolated_setup_state):
    events = [
        {
            "event": "local_setup",
            "platform": "darwin",
            "success": True,
            "setup_succeeded": True,
            "first_result_attempted": True,
            "first_result_succeeded": True,
            "time_to_ready_seconds": 10,
            "time_to_first_result_seconds": 30,
            "maintainer_help_reported": False,
            "architecture_knowledge_reported": False,
        },
        {
            "event": "local_setup",
            "platform": "linux",
            "success": False,
            "setup_succeeded": False,
            "first_result_attempted": False,
            "failure_stage": "local_services",
        },
    ]
    isolated_setup_state.mkdir(parents=True, exist_ok=True)
    (isolated_setup_state / "onboarding.jsonl").write_text("".join(json.dumps(event) + "\n" for event in events))

    result = CliRunner().invoke(onboarding, ["report", "--json-output"])

    assert result.exit_code == 0, result.output
    report = json.loads(result.output)
    assert report["runtime_attempts"] == 2
    assert report["setup_success_rate"] == 0.5
    assert report["activation_success_rate"] == 1.0
    assert report["median_time_to_first_result_seconds"] == 30.0
    assert report["failure_stages"] == {"local_services": 1}
    assert report["platforms"] == {"darwin": 1, "linux": 1}
    assert report["trials_without_maintainer_help"] == 1


def test_onboarding_summary_does_not_count_configuration_only_as_runtime_attempt():
    report = _onboarding_summary(
        [
            {
                "event": "local_setup",
                "platform": "linux",
                "outcome": "configured_only",
                "success": True,
            }
        ]
    )

    assert report["attempts"] == 1
    assert report["runtime_attempts"] == 0
    assert report["setup_success_rate"] is None
