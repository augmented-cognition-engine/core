from __future__ import annotations

import ast
import subprocess
import sys
from pathlib import Path

import pytest
from setuptools import find_packages

pytestmark = pytest.mark.unit

REPO = Path(__file__).resolve().parents[2]
INTELLIGENCE = REPO / "ace" / "intelligence"
CONTRACTS = INTELLIGENCE / "contracts"
PACKS = INTELLIGENCE / "packs"
APPLICATION = REPO / "ace" / "application"
TESTING = REPO / "ace" / "testing"


def _imports(path: Path) -> set[str]:
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    names: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            names.update(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            names.add(node.module)
    return names


def test_contracts_never_import_application_compiler_or_host_dependencies() -> None:
    forbidden = (
        "ace.application",
        "ace.intelligence.packs",
        "ace_mcp_client",
        "anthropic",
        "core.engine",
        "extensions",
        "fastapi",
        "httpx",
        "surrealdb",
    )
    offenders = [
        f"{path.relative_to(REPO)} ({name})"
        for path in CONTRACTS.rglob("*.py")
        for name in _imports(path)
        if name.startswith(forbidden)
    ]
    assert offenders == []


def test_intelligence_initializer_exports_contracts_and_pure_interpreters_only() -> None:
    imports = _imports(INTELLIGENCE / "__init__.py")
    assert imports == {
        "ace.intelligence.contracts",
        "ace.intelligence.derivation",
        "ace.intelligence.detection",
        "ace.intelligence.epistemic",
        "ace.intelligence.impact",
        "ace.intelligence.routing",
        "ace.intelligence.source_mapping",
        "ace.intelligence.supersession",
        "ace.intelligence.synthesis",
    }


def test_intelligence_has_no_host_storage_provider_or_extension_dependencies() -> None:
    forbidden = (
        "ace.application",
        "ace_mcp_client",
        "aiohttp",
        "anthropic",
        "core.engine",
        "extensions",
        "fastapi",
        "httpx",
        "requests",
        "surrealdb",
        "urllib.request",
    )
    offenders = [
        f"{path.relative_to(REPO)} ({name})"
        for path in INTELLIGENCE.rglob("*.py")
        for name in _imports(path)
        if name.startswith(forbidden)
    ]
    assert offenders == []


def test_importing_intelligence_composes_no_application_runtime_or_host() -> None:
    code = """
import sys
import ace.intelligence
forbidden = (
    'ace.application', 'ace_mcp_client',
    'core.engine.api', 'core.engine.cli', 'core.engine.db',
    'core.engine.extensions', 'core.engine.mcp', 'core.engine.worker', 'extensions',
)
loaded = sorted(name for name in sys.modules if name.startswith(forbidden))
raise SystemExit('unexpected runtime imports: ' + repr(loaded) if loaded else 0)
"""
    result = subprocess.run(
        [sys.executable, "-c", code],
        cwd=REPO,
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 0, result.stderr or result.stdout


def test_packaging_includes_contracts_application_and_public_testing_seam() -> None:
    packages = set(find_packages(where=REPO, include=["ace", "ace.*"]))
    assert {
        "ace",
        "ace.application",
        "ace.core",
        "ace.intelligence",
        "ace.intelligence.contracts",
        "ace.intelligence.detection",
        "ace.intelligence.packs",
        "ace.testing",
    } <= packages


def test_application_and_testing_seams_use_only_public_ports() -> None:
    forbidden = (
        "ace_mcp_client",
        "aiohttp",
        "anthropic",
        "core.engine",
        "extensions",
        "fastapi",
        "httpx",
        "requests",
        "surrealdb",
        "urllib.request",
    )
    offenders = [
        f"{path.relative_to(REPO)} ({name})"
        for root in (APPLICATION, TESTING)
        for path in root.rglob("*.py")
        for name in _imports(path)
        if name.startswith(forbidden)
    ]
    assert offenders == []


def test_live_ingress_and_live_bridge_are_packaged_public_services() -> None:
    import ace.application
    import ace.testing

    assert (APPLICATION / "live_source_ingress.py").exists()
    assert (APPLICATION / "live_intelligence_bridge.py").exists()
    assert (TESTING / "live_source_ingress.py").exists()
    for name in (
        "LiveSourceIngressService",
        "LiveIntelligenceBridgeService",
        "LiveBriefSynthesisService",
    ):
        assert hasattr(ace.application, name)
    assert hasattr(ace.testing, "exercise_live_source_ingress_restart")


def test_live_services_use_only_public_ports_and_declarative_composition() -> None:
    live_modules = (
        APPLICATION / "live_source_ingress.py",
        APPLICATION / "live_intelligence_bridge.py",
        TESTING / "live_source_ingress.py",
    )
    allowed = ("ace.application", "ace.core", "ace.intelligence", "pydantic")
    offenders = [
        f"{path.relative_to(REPO)} ({name})"
        for path in live_modules
        for name in _imports(path)
        if not (
            name.split(".")[0] in sys.stdlib_module_names
            or any(name == prefix or name.startswith(f"{prefix}.") for prefix in allowed)
        )
    ]
    assert offenders == []
    source = "\n".join(path.read_text(encoding="utf-8") for path in live_modules)
    for loader_hook in ("entry_point", "importlib", "__import__", "subprocess", "exec(", "eval("):
        assert loader_hook not in source, f"live services must stay bounded; found {loader_hook!r}"


def test_every_application_and_testing_module_is_loaded_by_its_public_surface() -> None:
    import ace.application  # noqa: F401
    import ace.testing  # noqa: F401

    expected = {
        f"ace.{root.name}.{path.stem}"
        for root in (APPLICATION, TESTING)
        for path in root.glob("*.py")
        if path.name != "__init__.py" and not path.name.startswith("_")
    }
    missing = sorted(expected.difference(sys.modules))
    assert missing == []


def test_every_pure_intelligence_module_is_loaded_by_the_public_surface() -> None:
    import ace.intelligence  # noqa: F401

    expected = {
        f"ace.intelligence.{path.stem}"
        for path in INTELLIGENCE.glob("*.py")
        if path.name != "__init__.py" and not path.name.startswith("_")
    }
    expected.add("ace.intelligence.detection")
    missing = sorted(expected.difference(sys.modules))
    assert missing == []


def test_packs_import_no_application_host_provider_or_storage_code() -> None:
    allowed = (
        "ace.core",
        "ace.intelligence.contracts",
        "ace.intelligence.packs",
        "pydantic",
    )
    offenders = [
        f"{path.relative_to(REPO)} ({name})"
        for path in PACKS.rglob("*.py")
        for name in _imports(path)
        if not (
            name.split(".")[0] in sys.stdlib_module_names
            or any(name == prefix or name.startswith(f"{prefix}.") for prefix in allowed)
        )
    ]
    assert offenders == []


def test_packs_contain_no_imperative_plugin_loader() -> None:
    source = "\n".join(path.read_text(encoding="utf-8") for path in PACKS.rglob("*.py"))
    for loader_hook in (
        "entry_point",
        "importlib",
        "__import__",
        "subprocess",
        "exec(",
        "eval(",
        ".load()",
    ):
        assert loader_hook not in source, f"packs must stay declarative; found {loader_hook!r}"


def test_every_contract_module_is_loaded_by_the_public_contract_surface() -> None:
    import ace.intelligence.contracts  # noqa: F401

    expected = {
        f"ace.intelligence.contracts.{path.stem}"
        for path in CONTRACTS.glob("*.py")
        if path.name != "__init__.py" and not path.name.startswith("_")
    }
    missing = sorted(expected.difference(sys.modules))
    assert missing == []


def test_contract_surface_stays_domain_neutral_and_non_executable() -> None:
    source = "\n".join(path.read_text(encoding="utf-8").lower() for path in CONTRACTS.rglob("*.py"))
    for noun in ("competitor", "supplier", "patient", "malware", "portfolio"):
        assert noun not in source
    for executable_hook in ("entry_point", ".load()", "subprocess", "exec("):
        assert executable_hook not in source
