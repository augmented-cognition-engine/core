# tests/test_cli_evolve.py
"""Test ace evolve CLI command."""

from unittest.mock import MagicMock, patch

from click.testing import CliRunner

from core.engine.cli.main import cli


def test_evolve_command_exists():
    runner = CliRunner()
    result = runner.invoke(cli, ["evolve", "--help"])
    assert result.exit_code == 0
    assert "evolution engine" in result.output.lower()


def test_evolve_command_calls_api():
    runner = CliRunner()
    mock_resp = MagicMock()
    mock_resp.json.return_value = {
        "status": "completed",
        "hypotheses": 3,
        "researched": 2,
        "experiments_run": 1,
        "committed": 1,
        "cost": 1.50,
    }
    mock_resp.raise_for_status = MagicMock()

    with patch("core.engine.cli.commands.evolve.httpx.post", return_value=mock_resp):
        result = runner.invoke(cli, ["evolve", "--now"], obj={"url": "http://test", "token": "tok"})

    assert result.exit_code == 0
    assert "Committed: 1" in result.output
