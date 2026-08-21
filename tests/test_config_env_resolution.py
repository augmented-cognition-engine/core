"""Regression tests for issue #260: ``.env`` resolution independent of cwd.

``Settings`` (and therefore ``ace doctor``) must load the installation's
configured ``.env`` from ``ACE_CONFIG_DIR`` (or an explicit ``ACE_ENV_FILE``
override) rather than silently reading whatever ``.env`` happens to sit in
the process's current working directory.
"""

from __future__ import annotations

import importlib

import pytest


@pytest.fixture
def config_module(monkeypatch):
    """Reimport ``core.engine.core.config`` fresh for each test.

    ``_resolved_env_files`` is evaluated once, at class-body time, so each
    test must reimport the module after adjusting the environment.
    """

    import core.engine.core.config as config

    def _reload():
        return importlib.reload(config)

    yield _reload


def test_env_file_resolution_prefers_ace_config_dir_over_cwd(tmp_path, monkeypatch, config_module):
    cwd_dir = tmp_path / "unrelated_checkout"
    cwd_dir.mkdir()
    (cwd_dir / ".env").write_text("SURREAL_URL=ws://cwd-should-not-win:8001\n")

    config_dir = tmp_path / "ace_config"
    config_dir.mkdir()
    (config_dir / ".env").write_text("SURREAL_URL=ws://configured-instance:8001\n")

    monkeypatch.chdir(cwd_dir)
    monkeypatch.setenv("ACE_CONFIG_DIR", str(config_dir))
    monkeypatch.delenv("ACE_ENV_FILE", raising=False)
    monkeypatch.delenv("SURREAL_URL", raising=False)

    config = config_module()
    settings = config.Settings()
    assert settings.surreal_url == "ws://configured-instance:8001"


def test_env_file_resolution_respects_explicit_ace_env_file_override(tmp_path, monkeypatch, config_module):
    cwd_dir = tmp_path / "cwd"
    cwd_dir.mkdir()
    (cwd_dir / ".env").write_text("SURREAL_URL=ws://cwd:8001\n")

    config_dir = tmp_path / "ace_config"
    config_dir.mkdir()
    (config_dir / ".env").write_text("SURREAL_URL=ws://configured:8001\n")

    explicit_env = tmp_path / "explicit.env"
    explicit_env.write_text("SURREAL_URL=ws://explicit-override:8001\n")

    monkeypatch.chdir(cwd_dir)
    monkeypatch.setenv("ACE_CONFIG_DIR", str(config_dir))
    monkeypatch.setenv("ACE_ENV_FILE", str(explicit_env))
    monkeypatch.delenv("SURREAL_URL", raising=False)

    config = config_module()
    settings = config.Settings()
    assert settings.surreal_url == "ws://explicit-override:8001"


def test_env_file_resolution_falls_back_to_runtime_subdirectory(tmp_path, monkeypatch, config_module):
    cwd_dir = tmp_path / "cwd"
    cwd_dir.mkdir()

    config_dir = tmp_path / "ace_config"
    runtime_dir = config_dir / "runtime"
    runtime_dir.mkdir(parents=True)
    (runtime_dir / ".env").write_text("SURREAL_URL=ws://packaged-runtime:8001\n")

    monkeypatch.chdir(cwd_dir)
    monkeypatch.setenv("ACE_CONFIG_DIR", str(config_dir))
    monkeypatch.delenv("ACE_ENV_FILE", raising=False)
    monkeypatch.delenv("SURREAL_URL", raising=False)

    config = config_module()
    settings = config.Settings()
    assert settings.surreal_url == "ws://packaged-runtime:8001"


def test_env_file_resolution_ignores_unrelated_cwd_env_file(tmp_path, monkeypatch, config_module):
    """An unrelated cwd ``.env`` must never be an implicit candidate.

    With no ``ACE_ENV_FILE``, no ``ACE_CONFIG_DIR``/.env, and no source-checkout
    ``.env`` present, a stray ``.env`` sitting in the cwd must be ignored
    entirely rather than silently supplying settings.
    """

    cwd_dir = tmp_path / "unrelated_checkout"
    cwd_dir.mkdir()
    (cwd_dir / ".env").write_text("SURREAL_URL=ws://cwd-should-not-win:8001\n")

    config_dir = tmp_path / "ace_config_missing"

    monkeypatch.chdir(cwd_dir)
    monkeypatch.setenv("ACE_CONFIG_DIR", str(config_dir))
    monkeypatch.delenv("ACE_ENV_FILE", raising=False)
    monkeypatch.delenv("SURREAL_URL", raising=False)

    config = config_module()
    settings = config.Settings()
    assert settings.surreal_url != "ws://cwd-should-not-win:8001"
    assert settings.surreal_url == "ws://localhost:8001"


def test_env_file_resolution_explicit_environment_variable_wins_over_env_files(tmp_path, monkeypatch, config_module):
    config_dir = tmp_path / "ace_config"
    config_dir.mkdir()
    (config_dir / ".env").write_text("SURREAL_URL=ws://configured:8001\n")

    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("ACE_CONFIG_DIR", str(config_dir))
    monkeypatch.setenv("SURREAL_URL", "ws://process-env-override:8001")

    config = config_module()
    settings = config.Settings()
    assert settings.surreal_url == "ws://process-env-override:8001"
