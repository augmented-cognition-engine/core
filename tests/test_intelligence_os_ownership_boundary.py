from __future__ import annotations

import ast
import json
from pathlib import Path

import pytest

pytestmark = pytest.mark.unit

REPO = Path(__file__).resolve().parents[1]
ACE = REPO / "ace"
LEGACY_HOST = REPO / "core" / "engine"
DISPOSITION = REPO / "docs" / "design" / "core-engine-compatibility-disposition-v0.8.0.json"


def _imports(path: Path) -> list[tuple[int, str]]:
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    found: list[tuple[int, str]] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            found.extend((node.lineno, alias.name) for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            found.append((node.lineno, node.module))
    return found


def _offenders(root: Path, forbidden: tuple[str, ...]) -> list[str]:
    offenders: list[str] = []
    for path in root.rglob("*.py"):
        if "__pycache__" in path.parts:
            continue
        for line, imported in _imports(path):
            if imported.startswith(forbidden):
                offenders.append(f"{path.relative_to(REPO)}:{line} ({imported})")
    return sorted(offenders)


def test_core_has_no_inward_intelligence_application_or_host_dependency() -> None:
    assert (
        _offenders(
            ACE / "core",
            (
                "ace.intelligence",
                "ace.application",
                "core.engine",
                "extensions",
                "ace_mcp_client",
                "fastapi",
            ),
        )
        == []
    )


def test_intelligence_has_no_application_host_transport_or_extension_dependency() -> None:
    assert (
        _offenders(
            ACE / "intelligence",
            ("ace.application", "core.engine", "extensions", "ace_mcp_client", "fastapi"),
        )
        == []
    )


def test_application_composes_public_ports_without_importing_legacy_hosts() -> None:
    assert (
        _offenders(
            ACE / "application",
            ("core.engine", "extensions", "ace_mcp_client", "fastapi"),
        )
        == []
    )


def test_public_ace_layers_do_not_acquire_sources_or_execute_effects_directly() -> None:
    forbidden_effect_modules = (
        "requests",
        "httpx",
        "aiohttp",
        "urllib.request",
        "urllib3",
        "boto3",
        "subprocess",
        "socket",
    )
    assert _offenders(ACE / "core", forbidden_effect_modules) == []
    assert _offenders(ACE / "intelligence", forbidden_effect_modules) == []
    assert _offenders(ACE / "application", forbidden_effect_modules) == []


def test_every_legacy_engine_package_has_one_explicit_0_8_disposition() -> None:
    manifest = json.loads(DISPOSITION.read_text(encoding="utf-8"))
    assert manifest["schema_version"] == "ace.architecture.core-engine-disposition/v1"
    assert manifest["canonical_public_roots"] == ["ace.core", "ace.intelligence", "ace.application"]

    declared: list[str] = []
    for disposition in manifest["dispositions"].values():
        assert disposition["owner"] in {"core", "intelligence", "application", "adapter_or_strategy"}
        assert disposition["treatment"].strip()
        declared.extend(disposition["packages"])

    actual = sorted(
        path.name
        for path in LEGACY_HOST.iterdir()
        if path.is_dir() and path.name != "__pycache__" and any(path.rglob("*.py"))
    )
    assert len(declared) == len(set(declared)), "a legacy host package has multiple owners"
    assert sorted(declared) == actual


def test_product_era_surface_is_explicitly_frozen_compatibility() -> None:
    manifest = json.loads(DISPOSITION.read_text(encoding="utf-8"))
    legacy = manifest["dispositions"]["legacy_product_application"]
    assert legacy["owner"] == "application"
    assert "frozen" in legacy["treatment"]
    assert {"arms", "product", "product_state", "canvas"}.issubset(legacy["packages"])
