"""``scripts.schema_apply`` ships in the Core wheel and is imported in-process by hosts.

Its repository-root path insert must be idempotent: in an installed
environment that "root" is site-packages itself, and a duplicated
``sys.path`` entry makes ``importlib.metadata`` enumerate every distribution
twice, which breaks installed-artifact discovery for the rest of the process.
"""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

import pytest

pytestmark = pytest.mark.unit

REPO = Path(__file__).resolve().parents[1]


def test_importing_schema_apply_never_duplicates_an_existing_sys_path_entry() -> None:
    code = """
import sys
before = len(sys.path) - len(set(sys.path))
import scripts.schema_apply  # noqa: F401
after = len(sys.path) - len(set(sys.path))
raise SystemExit(0 if after == before else f"sys.path duplicates grew from {before} to {after}")
"""
    env = {**os.environ, "PYTHONPATH": str(REPO)}
    result = subprocess.run([sys.executable, "-c", code], cwd=REPO, env=env, capture_output=True, text=True)
    assert result.returncode == 0, result.stdout + result.stderr
