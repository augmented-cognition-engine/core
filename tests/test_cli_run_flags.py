# tests/test_cli_run_flags.py
"""Tests for CLI run command extensions: --deep, --skill, --framework flags."""

from unittest.mock import MagicMock, patch

import pytest
from click.testing import CliRunner

from core.engine.cli.commands.run import run


@pytest.fixture
def runner():
    return CliRunner()


def test_run_deep_flag_passes_to_api(runner):
    """--deep flag sends deep=true in request body."""
    with patch("core.engine.cli.commands.run.httpx") as mock_httpx:
        mock_resp = MagicMock()
        mock_resp.status_code = 202
        mock_resp.json.return_value = {
            "id": "task:1",
            "output": "result",
            "domain_path": "tech",
            "intelligence_loaded": {"total_count": 0},
        }
        mock_httpx.post.return_value = mock_resp

        result = runner.invoke(
            run,
            ["--deep", "Analyze our token system"],
            obj={"url": "http://localhost:3000", "token": "test"},
            input="a\n",
        )

    call_json = mock_httpx.post.call_args[1]["json"]
    assert call_json.get("deep") is True


def test_run_skill_flag_passes_force_skill(runner):
    """--skill flag sends force_skill in request body."""
    with patch("core.engine.cli.commands.run.httpx") as mock_httpx:
        mock_resp = MagicMock()
        mock_resp.status_code = 202
        mock_resp.json.return_value = {
            "id": "task:1",
            "output": "result",
            "domain_path": "tech",
            "intelligence_loaded": {"total_count": 0},
        }
        mock_httpx.post.return_value = mock_resp

        result = runner.invoke(
            run,
            ["--skill", "code_review", "Review this module"],
            obj={"url": "http://localhost:3000", "token": "test"},
            input="a\n",
        )

    call_json = mock_httpx.post.call_args[1]["json"]
    assert call_json.get("force_skill") == "code_review"


def test_run_framework_flag_passes_hint(runner):
    """--framework flag sends frameworks_hint in request body."""
    with patch("core.engine.cli.commands.run.httpx") as mock_httpx:
        mock_resp = MagicMock()
        mock_resp.status_code = 202
        mock_resp.json.return_value = {
            "id": "task:1",
            "output": "result",
            "domain_path": "tech",
            "intelligence_loaded": {"total_count": 0},
        }
        mock_httpx.post.return_value = mock_resp

        result = runner.invoke(
            run,
            ["--framework", "first_principles", "Design the API"],
            obj={"url": "http://localhost:3000", "token": "test"},
            input="a\n",
        )

    call_json = mock_httpx.post.call_args[1]["json"]
    assert "first_principles" in call_json.get("frameworks_hint", [])


def test_run_multiple_framework_flags(runner):
    """Multiple --framework flags accumulate into frameworks_hint list."""
    with patch("core.engine.cli.commands.run.httpx") as mock_httpx:
        mock_resp = MagicMock()
        mock_resp.status_code = 202
        mock_resp.json.return_value = {
            "id": "task:1",
            "output": "result",
            "domain_path": "tech",
            "intelligence_loaded": {"total_count": 0},
        }
        mock_httpx.post.return_value = mock_resp

        result = runner.invoke(
            run,
            [
                "--framework",
                "first_principles",
                "--framework",
                "pre_mortem",
                "Design the caching layer",
            ],
            obj={"url": "http://localhost:3000", "token": "test"},
            input="a\n",
        )

    call_json = mock_httpx.post.call_args[1]["json"]
    hints = call_json.get("frameworks_hint", [])
    assert "first_principles" in hints
    assert "pre_mortem" in hints
    assert len(hints) == 2


def test_run_without_flags_unchanged(runner):
    """Default run behavior unchanged — no deep, force_skill, or frameworks_hint fields."""
    with patch("core.engine.cli.commands.run.httpx") as mock_httpx:
        mock_resp = MagicMock()
        mock_resp.status_code = 202
        mock_resp.json.return_value = {
            "id": "task:1",
            "output": "result",
            "domain_path": "tech",
            "intelligence_loaded": {"total_count": 0},
        }
        mock_httpx.post.return_value = mock_resp

        result = runner.invoke(run, ["Simple task"], obj={"url": "http://localhost:3000", "token": "test"}, input="a\n")

    call_json = mock_httpx.post.call_args[1]["json"]
    assert "deep" not in call_json
    assert "force_skill" not in call_json
    assert "frameworks_hint" not in call_json


def test_run_shows_framework_info_in_output(runner):
    """When frameworks are used, output shows framework names."""
    with patch("core.engine.cli.commands.run.httpx") as mock_httpx:
        mock_resp = MagicMock()
        mock_resp.status_code = 202
        mock_resp.json.return_value = {
            "id": "task:1",
            "output": "result",
            "domain_path": "tech",
            "intelligence_loaded": {"total_count": 0},
            "strategies_used": ["first_principles", "pre_mortem"],
        }
        mock_httpx.post.return_value = mock_resp

        result = runner.invoke(
            run, ["--deep", "Analyze"], obj={"url": "http://localhost:3000", "token": "test"}, input="a\n"
        )

    assert "first_principles" in result.output


def test_run_shows_skill_info_in_output(runner):
    """When a skill is used, output shows skill slug."""
    with patch("core.engine.cli.commands.run.httpx") as mock_httpx:
        mock_resp = MagicMock()
        mock_resp.status_code = 202
        mock_resp.json.return_value = {
            "id": "task:1",
            "output": "result",
            "domain_path": "tech",
            "intelligence_loaded": {"total_count": 0},
            "skill_slug": "code_review",
        }
        mock_httpx.post.return_value = mock_resp

        result = runner.invoke(
            run,
            ["--skill", "code_review", "Review PR"],
            obj={"url": "http://localhost:3000", "token": "test"},
            input="a\n",
        )

    assert "code_review" in result.output
