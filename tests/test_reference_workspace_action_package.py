from __future__ import annotations

import os
import subprocess
import sys
from importlib import import_module
from pathlib import Path

import pytest

pytestmark = pytest.mark.unit

REPOSITORY = Path(__file__).resolve().parents[1]
ADAPTER = REPOSITORY / "adapters/reference_workspace_action"


def test_reference_action_adapter_remains_a_separate_distribution() -> None:
    root_package_configuration = (REPOSITORY / "pyproject.toml").read_text()
    assert "ace_reference_workspace_action" not in root_package_configuration
    assert (ADAPTER / "pyproject.toml").is_file()
    assert (ADAPTER / "src/ace_reference_workspace_action/adapter.py").is_file()


def test_reference_action_adapter_requires_explicit_exact_host_registration(monkeypatch, tmp_path: Path) -> None:
    from core.engine.core.action_execution import BoundedActionAdapterRegistry

    monkeypatch.syspath_prepend(str(ADAPTER / "src"))
    distribution = import_module("ace_reference_workspace_action")
    adapter = distribution.ReferenceWorkspaceActionAdapter(workspace_root=tmp_path)
    registry = BoundedActionAdapterRegistry((adapter,))

    assert registry.resolve(distribution.ADAPTER_ARTIFACT) is adapter


def test_reference_action_adapter_conformance_suite_passes_against_public_core() -> None:
    environment = dict(os.environ)
    environment["PYTHONPATH"] = os.pathsep.join(
        (str(ADAPTER / "src"), str(REPOSITORY), environment.get("PYTHONPATH", ""))
    ).rstrip(os.pathsep)
    completed = subprocess.run(
        [sys.executable, "-m", "pytest", "-q", str(ADAPTER / "tests")],
        cwd=ADAPTER,
        env=environment,
        capture_output=True,
        text=True,
        timeout=60,
        check=False,
    )
    assert completed.returncode == 0, completed.stdout + completed.stderr
