"""Tests for CLI commands."""

from click.testing import CliRunner


def test_cli_status_with_no_server():
    """ace status shows error when server is not running."""
    from core.engine.cli.main import cli

    runner = CliRunner()
    result = runner.invoke(cli, ["--url", "http://localhost:19999", "status"])
    assert "Cannot connect" in result.output or result.exit_code != 0


def test_cli_help():
    """ace --help shows available commands."""
    from core.engine.cli.main import cli

    runner = CliRunner()
    result = runner.invoke(cli, ["--help"])
    assert result.exit_code == 0, result.output
    assert "ACE — Augmented Cognition Engine" in result.output
    assert "Turn product decisions into durable" in result.output
    assert "recommendations" in result.output
    assert "Organizational Intelligence Engine" not in result.output
    assert "run" in result.output
    assert "intel" in result.output
    assert "search" in result.output
    assert "status" in result.output
    assert "skills" not in result.output


def test_legacy_skills_command_remains_callable_when_hidden():
    """The legacy compatibility command remains accepted by its exact name."""
    from core.engine.cli.main import cli

    result = CliRunner().invoke(cli, ["skills", "--help"])

    assert result.exit_code == 0, result.output
    assert "Usage: cli skills" in result.output
    assert "get" in result.output
