from __future__ import annotations

import ast
import os
import subprocess
import sys
from pathlib import Path

import pytest

from core.engine.api.legacy_product_intelligence import LEGACY_PRODUCT_INTELLIGENCE_MODULES
from core.engine.core.config import Settings

pytestmark = pytest.mark.unit

REPO = Path(__file__).resolve().parents[1]
MAIN = REPO / "core" / "engine" / "api" / "main.py"


def _imports(path: Path) -> set[str]:
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    names: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            names.update(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            names.add(node.module)
    return names


def test_legacy_product_intelligence_is_disabled_by_default_and_explicitly_opt_in(monkeypatch) -> None:
    monkeypatch.delenv("ENABLE_LEGACY_PRODUCT_INTELLIGENCE", raising=False)
    settings = Settings(jwt_secret="test-secret", _env_file=None)
    assert settings.enable_legacy_product_intelligence is False

    monkeypatch.setenv("ENABLE_LEGACY_PRODUCT_INTELLIGENCE", "true")
    opted_in = Settings(jwt_secret="test-secret", _env_file=None)
    assert opted_in.enable_legacy_product_intelligence is True


def test_default_registration_path_loads_no_domain_specific_legacy_engine() -> None:
    code = """
import sys
from core.engine.api.legacy_product_intelligence import (
    LEGACY_PRODUCT_INTELLIGENCE_MODULES,
    register_legacy_product_intelligence_engines,
)
loaded = register_legacy_product_intelligence_engines(enabled=False)
unexpected = sorted(name for name in LEGACY_PRODUCT_INTELLIGENCE_MODULES if name in sys.modules)
raise SystemExit(f'unexpected legacy engine imports: {unexpected}' if loaded or unexpected else 0)
"""
    environment = {
        **os.environ,
        "JWT_SECRET": "test-secret",
        "ENABLE_LEGACY_PRODUCT_INTELLIGENCE": "false",
    }
    result = subprocess.run(
        [sys.executable, "-c", code],
        cwd=REPO,
        env=environment,
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 0, result.stderr or result.stdout


def test_explicit_compatibility_opt_in_registers_only_the_frozen_legacy_set() -> None:
    code = """
from core.engine.api.legacy_product_intelligence import (
    LEGACY_PRODUCT_INTELLIGENCE_MODULES,
    register_legacy_product_intelligence_engines,
)
from core.engine.sentinel.registry import engine_registry
loaded = register_legacy_product_intelligence_engines(enabled=True)
registered = {
    'community_scanner',
    'competitive_observer',
    'github_release_watcher',
    'whitespace_engine',
}
missing = sorted(registered.difference(engine_registry))
raise SystemExit(f'compatibility registration failed: loaded={loaded!r}, missing={missing!r}' if loaded != LEGACY_PRODUCT_INTELLIGENCE_MODULES or missing else 0)
"""
    environment = {**os.environ, "JWT_SECRET": "test-secret"}
    result = subprocess.run(
        [sys.executable, "-c", code],
        cwd=REPO,
        env=environment,
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 0, result.stderr or result.stdout


def test_api_composition_root_has_no_unconditional_legacy_domain_engine_import() -> None:
    imports = _imports(MAIN)
    assert set(LEGACY_PRODUCT_INTELLIGENCE_MODULES).isdisjoint(imports)
    assert "core.engine.api.legacy_product_intelligence" in imports
