"""1.2.1 fresh-install fix (issue #253): no traceback before configuration exists.

The 1.2.0 acceptance run proved a fresh package-only install crashes on every
``ace`` command — including ``ace --help`` and ``ace setup`` — because settings
construction required a JWT secret at import time. The security property moves
to where it belongs: any actual use of the signing secret still fails fast
with an actionable message, and the API refuses to mint or verify tokens
without configuration.
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

import pytest

from core.engine.core.config import Settings, require_jwt_secret

pytestmark = pytest.mark.unit

REPO = Path(__file__).resolve().parents[1]


def _fresh_settings(monkeypatch) -> Settings:
    for name in ("JWT_SECRET", "ACE_ENV", "ENVIRONMENT"):
        monkeypatch.delenv(name, raising=False)
    return Settings(_env_file=None)


def test_settings_construct_without_any_configuration(monkeypatch) -> None:
    settings = _fresh_settings(monkeypatch)
    assert settings.jwt_secret == ""


def test_jwt_secret_use_fails_fast_with_an_actionable_message(monkeypatch) -> None:
    settings = _fresh_settings(monkeypatch)
    with pytest.raises(RuntimeError, match="ace setup"):
        require_jwt_secret(settings)


def test_configured_secret_passes_the_gate(monkeypatch) -> None:
    monkeypatch.delenv("JWT_SECRET", raising=False)
    settings = Settings(_env_file=None, jwt_secret="configured-secret")
    assert require_jwt_secret(settings) == "configured-secret"


def test_cli_help_works_in_an_unconfigured_directory(tmp_path: Path) -> None:
    # The exact F1 reproduction: no .env anywhere, no JWT_SECRET in the
    # environment, empty working directory — `ace --help` must exit 0.
    env = {
        "PATH": "/usr/bin:/bin",
        "PYTHONPATH": str(REPO),
    }
    result = subprocess.run(
        [sys.executable, "-m", "core.engine.cli.main", "--help"],
        cwd=tmp_path,
        env=env,
        capture_output=True,
        text=True,
        timeout=120,
    )
    assert result.returncode == 0, result.stderr[-2000:]
    assert "Traceback" not in result.stderr
