"""1.2.1 setup isolation fix (issue #254): setup never claims or mutates a foreign stack.

The 1.2.0 acceptance run's incident I1: on a host with an existing ACE stack,
``ace setup`` applied schema migrations to the pre-existing database, declared
a foreign API on hardcoded port 3000 to be "already running", and wrote
runtime files before failing. These tests pin the fail-closed replacements:
a configurable API port, managed-process evidence before any "ours" claim,
and explicit adoption before migrating a database that already has schema.
"""

from __future__ import annotations

import click
import pytest

from core.engine.cli.commands.setup import (
    _api_launch_command,
    _api_url,
    _assert_database_adoptable,
    _treat_ready_api_as_ours,
)

pytestmark = pytest.mark.unit


class TestConfigurableApiPort:
    def test_default_port_is_3000(self, monkeypatch):
        monkeypatch.delenv("ACE_API_PORT", raising=False)
        assert _api_url() == "http://localhost:3000"

    def test_port_override_via_environment(self, monkeypatch):
        monkeypatch.setenv("ACE_API_PORT", "13000")
        assert _api_url() == "http://localhost:13000"

    def test_invalid_port_fails_closed(self, monkeypatch):
        monkeypatch.setenv("ACE_API_PORT", "not-a-port")
        with pytest.raises(click.ClickException, match="ACE_API_PORT"):
            _api_url()

    def test_launch_command_uses_the_configured_port(self, monkeypatch):
        monkeypatch.setenv("ACE_API_PORT", "13000")
        command = _api_launch_command()
        assert "13000" in command
        assert "3000" not in [part for part in command if part != "13000"]


class TestForeignApiIsNeverOurs:
    def test_ready_api_with_managed_pid_is_ours(self):
        assert _treat_ready_api_as_ours(api_ready=True, managed_pid=12345) is True

    def test_ready_api_without_managed_pid_is_foreign(self):
        # The I1 trigger: a live /health/live on our port, no managed process.
        assert _treat_ready_api_as_ours(api_ready=True, managed_pid=None) is False

    def test_unready_api_is_not_ours(self):
        assert _treat_ready_api_as_ours(api_ready=False, managed_pid=12345) is False


class TestDatabaseAdoption:
    def test_fresh_database_is_adoptable(self):
        _assert_database_adoptable(current_version=0, adopt_existing=False)

    def test_pre_existing_schema_requires_explicit_adoption(self):
        with pytest.raises(click.ClickException, match="adopt-existing-database"):
            _assert_database_adoptable(current_version=177, adopt_existing=False)

    def test_explicit_adoption_is_honored(self):
        _assert_database_adoptable(current_version=177, adopt_existing=True)

    def test_error_names_what_was_found_and_the_isolation_variables(self):
        with pytest.raises(click.ClickException) as excinfo:
            _assert_database_adoptable(current_version=177, adopt_existing=False)
        message = str(excinfo.value)
        assert "v177" in message
        assert "ACE_SURREAL_HOST_PORT" in message
