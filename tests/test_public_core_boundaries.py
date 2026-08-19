from __future__ import annotations

import ast
import subprocess
import sys
from pathlib import Path

import pytest
from setuptools import find_packages

pytestmark = pytest.mark.unit

REPO = Path(__file__).resolve().parents[1]
LEGACY_CORE = REPO / "core"
PUBLIC_CORE = REPO / "ace" / "core"


def _imports(path: Path) -> set[str]:
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    names: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            names.update(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            names.add(node.module)
    return names


def test_core_never_imports_intelligence_bounded_context() -> None:
    offenders: list[str] = []
    for root in (LEGACY_CORE, PUBLIC_CORE):
        for path in root.rglob("*.py"):
            for name in _imports(path):
                if name == "ace.intelligence" or name.startswith("ace.intelligence."):
                    offenders.append(f"{path.relative_to(REPO)} ({name})")
    assert offenders == []


def test_public_core_contracts_have_no_host_or_provider_dependencies() -> None:
    forbidden = (
        "anthropic",
        "core.engine",
        "extensions",
        "fastapi",
        "httpx",
        "surrealdb",
    )
    offenders: list[str] = []
    for path in PUBLIC_CORE.rglob("*.py"):
        for name in _imports(path):
            if name.startswith(forbidden):
                offenders.append(f"{path.relative_to(REPO)} ({name})")
    assert offenders == []


def test_importing_ace_remains_lightweight() -> None:
    code = """
import sys
import ace
forbidden = sorted(name for name in sys.modules if name.startswith('ace.intelligence'))
raise SystemExit('unexpected intelligence imports: ' + repr(forbidden) if forbidden else 0)
"""
    result = subprocess.run(
        [sys.executable, "-c", code],
        cwd=REPO,
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 0, result.stderr or result.stdout


def test_packaging_includes_public_core_namespace() -> None:
    packages = set(find_packages(where=REPO, include=["ace", "ace.*"]))
    assert {"ace", "ace.core"} <= packages


def test_governed_state_migrations_are_additive_and_append_only() -> None:
    migrations = [
        (REPO / f"core/schema/v{version}_{name}.surql").read_text()
        for version, name in (
            (172, "governed_state_commit"),
            (173, "governed_state_approval_subject"),
            (174, "immutable_record_ledger"),
            (175, "immutable_record_canonical_payload"),
            (176, "governed_cognition_canonical_payload"),
        )
    ]
    assert "immutable_record" in migrations[2]
    assert "append_only_transaction_receipt" in migrations[2]
    assert "FOR update NONE" in migrations[2]
    assert "FOR delete NONE" in migrations[2]
    assert "payload_json" in migrations[4]
    assert "cognition_proposal" in migrations[4]
    assert "cognition_selection_receipt" in migrations[4]
    for migration in migrations:
        assert "UPDATE " not in migration
        assert "DELETE " not in migration
        for statement in migration.split(";"):
            normalized = statement.strip()
            if normalized.startswith("DEFINE "):
                assert " IF NOT EXISTS" in normalized


def test_only_host_adapters_and_installed_product_applications_import_public_ace() -> None:
    host_adapters = {
        "core/engine/core/governed_state.py",
        "core/engine/core/immutable_records.py",
        "core/engine/core/intelligence_resource_plane.py",
        "core/engine/core/intelligence_resource_feedback.py",
        "core/engine/core/intelligence_subscriptions.py",
        "core/engine/core/intelligence_build.py",
        "core/engine/core/intelligence_activation_authority.py",
        "core/engine/core/intelligence_builder_activation_plan.py",
        "core/engine/core/intelligence_build_plan.py",
        "core/engine/core/intelligence_build_resource_state.py",
        "core/engine/core/installed_intelligence_catalog.py",
        "core/engine/core/intelligence_build_executor_registry.py",
        "core/engine/core/intelligence_build_planner_registry.py",
        "core/engine/core/personal_intelligence_ownership.py",
        "core/engine/core/local_owner_authority.py",
        "core/engine/core/live_cognition.py",
        "core/engine/core/action_execution.py",
        "core/engine/core/agent_composition_runtime.py",
        "core/engine/core/agent_composition_lifecycle_runtime.py",
        "core/engine/core/external_operations.py",
        "core/engine/core/structured_reasoning_provider.py",
        # JWT verification is a host boundary. It derives one public
        # authentication receipt from verified claims without exposing the
        # public application contract to API route modules.
        "core/engine/core/auth.py",
        # Slice 7: delegated headless governed-cognition review/activation. This
        # is the only module that performs governed-state and immutable-record
        # I/O for the delegated path.
        "core/engine/core/cognition_delegated_authority.py",
        # PI8: grounded Ask and claim-bound correction host adapters. Both
        # delegate durable reads/writes to the existing resource-plane and
        # feedback services through the public application contracts.
        "core/engine/core/grounded_ask.py",
        "core/engine/core/claim_bound_correction.py",
        # Durable cognition persistence is the transaction adapter that writes
        # the public append-only record vocabulary in the same Surreal commit.
        "core/engine/cognition/governance_persistence.py",
        # PI9 delivery: workspace derivative erasure host adapter. Bridges the ownership
        # deletion journey's Core contracts to the scanner graph rows and Qdrant vectors;
        # imports ace.core contract shapes only, never ace.intelligence.
        "core/engine/core/personal_intelligence_derivative_erasure.py",
    }
    governed_authority_contracts = {
        # Slice 7: the delegated request envelope and its receipts bind the
        # public Core authority vocabulary (principal kind, authority class,
        # capability artifact identity) by design. The module performs no I/O;
        # the host adapter above owns every durable read and write.
        "core/engine/cognition/delegated_activation.py",
    }
    installed_product_applications = {
        # The disposition owns this as the optional Code application's adapter;
        # generic Core reaches it only through the extension registry factory.
        "core/engine/code_intelligence/resource_plane.py",
        "core/engine/code_intelligence/incident_source.py",
    }
    allowed = host_adapters | governed_authority_contracts | installed_product_applications
    offenders = sorted(
        str(path.relative_to(REPO))
        for path in (LEGACY_CORE / "engine").rglob("*.py")
        if "__pycache__" not in path.parts
        and str(path.relative_to(REPO)) not in allowed
        and any(name == "ace" or name.startswith("ace.") for name in _imports(path))
    )
    assert offenders == []


def test_slice7_public_contract_imports_stop_at_exact_host_adapters() -> None:
    expected = {
        "core/engine/core/auth.py": {"ace.application.agent_composition_runtime"},
        "core/engine/cognition/governance_persistence.py": {"ace.core.records"},
    }
    for relative, public_imports in expected.items():
        imports = _imports(REPO / relative)
        assert {name for name in imports if name == "ace" or name.startswith("ace.")} == public_imports

    api_imports = _imports(REPO / "core/engine/api/cognition.py")
    assert not any(name == "ace" or name.startswith("ace.") for name in api_imports)


def test_generic_resource_plane_host_does_not_import_code_solution_adapter() -> None:
    imports = _imports(LEGACY_CORE / "engine/core/intelligence_resource_plane.py")
    assert not any(name.startswith("core.engine.code_intelligence") for name in imports)


def test_code_resource_application_does_not_live_in_core_implementation_namespace() -> None:
    assert list((LEGACY_CORE / "engine/core").glob("code_intelligence*.py")) == []


def test_extension_disabled_kernel_starts_without_live_composition() -> None:
    code = """
import sys
import ace_mcp_client.server  # noqa: F401
import core.engine.cli.main  # noqa: F401
forbidden = (
    'ace.application.live_source_ingress',
    'ace.application.live_intelligence_bridge',
    'core.engine.core.live_cognition',
    'core.engine.core.action_execution',
    'extensions',
)
loaded = sorted(name for name in sys.modules if name.startswith(forbidden))
raise SystemExit('live composition loaded at kernel start: ' + repr(loaded) if loaded else 0)
"""
    result = subprocess.run(
        [sys.executable, "-c", code],
        cwd=REPO,
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 0, result.stderr or result.stdout
