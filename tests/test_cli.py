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
    assert "run" in result.output
    assert "intel" in result.output
    assert "search" in result.output
    assert "status" in result.output
