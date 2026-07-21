# tests/test_cli_login.py
"""Tests for `ace login` (OSS Task 8c): collapses the manual 12-line
curl/python/chmod token bootstrap into one command, and wires the
previously-orphaned core.engine.cli.auth.save_config()."""

import json
import os
import stat
from unittest.mock import MagicMock, patch

import pytest
from click.testing import CliRunner

import core.engine.cli.auth as auth_mod
from core.engine.cli.commands.login import login
from core.engine.cli.main import cli


@pytest.fixture
def runner():
    return CliRunner()


@pytest.fixture
def isolated_config(tmp_path, monkeypatch):
    """Point save_config's storage at a tmp dir instead of the real ~/.ace,
    and clear ACE_URL/ACE_API_KEY so a dev-box env can't override the URL
    precedence the group-level tests assert."""
    config_dir = tmp_path / ".ace"
    token_file = config_dir / "token.json"
    monkeypatch.setattr(auth_mod, "_CONFIG_DIR", config_dir)
    monkeypatch.setattr(auth_mod, "_TOKEN_FILE", token_file)
    monkeypatch.delenv("ACE_URL", raising=False)
    monkeypatch.delenv("ACE_API_KEY", raising=False)
    return token_file


def test_login_saves_token_on_success(runner, isolated_config):
    """login --api-key exchanges the key for a token via POST /auth/token
    and saves it to token.json at mode 0600 (Task 9b's security bar)."""
    mock_resp = MagicMock()
    mock_resp.status_code = 200
    mock_resp.json.return_value = {"token": "minted-token"}

    with patch("core.engine.cli.commands.login.httpx") as mock_httpx:
        mock_httpx.post.return_value = mock_resp
        result = runner.invoke(login, ["--api-key", "testkey", "--url", "http://localhost:3000"])

    assert result.exit_code == 0, result.output
    call_args = mock_httpx.post.call_args
    assert call_args[0][0] == "http://localhost:3000/auth/token"
    assert call_args[1]["json"] == {"api_key": "testkey"}

    assert isolated_config.exists()
    saved = json.loads(isolated_config.read_text())
    assert saved == {"url": "http://localhost:3000", "token": "minted-token"}
    mode = stat.S_IMODE(isolated_config.stat().st_mode)
    assert mode == 0o600
    assert "Logged in" in result.output
    assert "ace run" in result.output


def test_login_prompts_for_api_key_when_not_provided(runner, isolated_config):
    """No --api-key/ACE_API_KEY: falls back to an interactive hidden prompt."""
    mock_resp = MagicMock()
    mock_resp.status_code = 200
    mock_resp.json.return_value = {"token": "tok"}

    with patch("core.engine.cli.commands.login.httpx") as mock_httpx:
        mock_httpx.post.return_value = mock_resp
        result = runner.invoke(login, ["--url", "http://localhost:3000"], input="prompted-key\n")

    assert result.exit_code == 0, result.output
    assert mock_httpx.post.call_args[1]["json"] == {"api_key": "prompted-key"}


def test_login_defaults_url_from_get_base_url(runner, isolated_config):
    """No --url/ACE_URL: resolves the same default get_base_url()/run.py use,
    so `ace login` and `ace run` agree on the server URL."""
    mock_resp = MagicMock()
    mock_resp.status_code = 200
    mock_resp.json.return_value = {"token": "tok"}

    with (
        patch("core.engine.cli.commands.login.httpx") as mock_httpx,
        patch("core.engine.cli.commands.login.get_base_url", return_value="http://localhost:3000"),
    ):
        mock_httpx.post.return_value = mock_resp
        result = runner.invoke(login, ["--api-key", "testkey"])

    assert result.exit_code == 0, result.output
    assert mock_httpx.post.call_args[0][0] == "http://localhost:3000/auth/token"


def test_login_401_gives_actionable_message_and_nonzero_exit(runner, isolated_config):
    """Wrong API key: friendly cause + remedy, not a raw traceback (mirrors
    the Task 8a friendly-error precedent)."""
    mock_resp = MagicMock()
    mock_resp.status_code = 401
    mock_resp.json.return_value = {"detail": "Invalid API key"}

    with patch("core.engine.cli.commands.login.httpx") as mock_httpx:
        mock_httpx.post.return_value = mock_resp
        result = runner.invoke(login, ["--api-key", "wrongkey", "--url", "http://localhost:3000"])

    assert result.exit_code != 0
    assert "invalid api key" in result.output.lower()
    assert ".env" in result.output
    assert not isolated_config.exists()


def test_login_connection_refused_gives_actionable_message_and_nonzero_exit(runner, isolated_config):
    """Server not running: friendly cause + remedy, not a raw traceback."""
    import httpx as real_httpx

    with patch("core.engine.cli.commands.login.httpx") as mock_httpx:
        mock_httpx.ConnectError = real_httpx.ConnectError
        mock_httpx.TimeoutException = real_httpx.TimeoutException
        mock_httpx.post.side_effect = real_httpx.ConnectError("refused")
        result = runner.invoke(login, ["--api-key", "testkey", "--url", "http://localhost:19999"])

    assert result.exit_code != 0
    assert "cannot connect" in result.output.lower()
    assert "ace service start" in result.output
    assert not isolated_config.exists()


def test_login_honors_group_level_url(runner, isolated_config):
    """`ace --url <X> login` must authenticate against X — the group's URL
    (the pattern every other subcommand honors), NOT a silently-dropped
    localhost default. Auth against the wrong server is dangerous."""
    mock_resp = MagicMock()
    mock_resp.status_code = 200
    mock_resp.json.return_value = {"token": "tok"}

    with patch("core.engine.cli.commands.login.httpx") as mock_httpx:
        mock_httpx.post.return_value = mock_resp
        result = runner.invoke(
            cli,
            ["--url", "http://sentinel.example", "login", "--api-key", "k"],
        )

    assert result.exit_code == 0, result.output
    assert mock_httpx.post.call_args[0][0] == "http://sentinel.example/auth/token"


def test_login_explicit_url_beats_group_url(runner, isolated_config):
    """An explicit subcommand `login --url Y` still wins over the group's
    `ace --url X` — explicit is the top precedence tier."""
    mock_resp = MagicMock()
    mock_resp.status_code = 200
    mock_resp.json.return_value = {"token": "tok"}

    with patch("core.engine.cli.commands.login.httpx") as mock_httpx:
        mock_httpx.post.return_value = mock_resp
        result = runner.invoke(
            cli,
            ["--url", "http://group.example", "login", "--api-key", "k", "--url", "http://explicit.example"],
        )

    assert result.exit_code == 0, result.output
    assert mock_httpx.post.call_args[0][0] == "http://explicit.example/auth/token"


def test_save_config_creates_token_file_0600_even_under_permissive_umask(isolated_config):
    """Defense in depth: the token file must be 0600 regardless of the process
    umask — created restrictively from the start (os.open with mode 0o600),
    not via a default-umask write that leaves a world-readable window."""
    old_umask = os.umask(0)  # most permissive: default-umask writes would be world-rw
    try:
        auth_mod.save_config("http://localhost:3000", "a-live-bearer-token")
    finally:
        os.umask(old_umask)

    assert isolated_config.exists()
    assert stat.S_IMODE(isolated_config.stat().st_mode) == 0o600
    # And the containing dir is locked down too.
    assert stat.S_IMODE(isolated_config.parent.stat().st_mode) == 0o700
