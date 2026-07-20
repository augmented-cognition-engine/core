"""Kernel/extension boundary guard.

The dependency direction is one-way: extensions import core; core NEVER
imports extensions. This is the load-bearing contract of the open-core
split (docs/ace-architecture.md §1.3) — the Apache-2.0 kernel must run
with zero extensions installed.
"""

from __future__ import annotations

import ast
import re
import subprocess
import sys
from pathlib import Path

import pytest

CORE = Path(__file__).resolve().parents[1] / "core"
REPO = CORE.parent
THIN_CLIENT = REPO / "ace_mcp_client"
LIVING_PRODUCT_PROJECTOR = CORE / "engine" / "product" / "living_graph.py"
LIVING_PRODUCT_STORE = CORE / "engine" / "product" / "living_graph_store.py"

# Matches `import extensions...` / `from extensions...` as a statement,
# including indented (function-local) imports.
_IMPORT_RE = re.compile(r"^\s*(?:from|import)\s+extensions[.\s]", re.MULTILINE)


@pytest.mark.unit
def test_core_never_imports_extensions():
    offenders: list[str] = []
    for py in CORE.rglob("*.py"):
        if "__pycache__" in py.parts:
            continue
        text = py.read_text(encoding="utf-8", errors="ignore")
        if _IMPORT_RE.search(text):
            offenders.append(str(py.relative_to(CORE.parent)))
    assert offenders == [], (
        "Kernel code imports extension code — the open-core boundary is "
        f"broken in: {offenders}. Move the dependency behind a Registry "
        "seam (core/engine/extensions/registry.py) instead."
    )


@pytest.mark.unit
def test_thin_mcp_client_never_imports_engine_or_extensions():
    """The public 11-tool adapter stays an HTTP client, not a second kernel host."""
    forbidden_roots = {"core", "extensions"}
    offenders: list[str] = []

    for py in THIN_CLIENT.rglob("*.py"):
        tree = ast.parse(py.read_text(encoding="utf-8"), filename=str(py))
        for node in ast.walk(tree):
            names: list[str] = []
            if isinstance(node, ast.Import):
                names = [alias.name for alias in node.names]
            elif isinstance(node, ast.ImportFrom) and node.module:
                names = [node.module]
            for name in names:
                if name.split(".", 1)[0] in forbidden_roots:
                    offenders.append(f"{py.relative_to(REPO)}:{node.lineno} ({name})")

    assert offenders == [], (
        "The thin public MCP client imported engine or extension implementation. "
        f"Keep it HTTP-only; offenders: {offenders}"
    )


@pytest.mark.unit
def test_thin_mcp_server_import_does_not_load_engine_hosts():
    """Importing the public adapter must not compose the API, broad MCP, CLI, or worker."""
    code = """
import sys
import ace_mcp_client.server  # noqa: F401

forbidden = (
    "core.engine.api",
    "core.engine.mcp",
    "core.engine.cli",
    "core.engine.worker",
)
loaded = sorted(name for name in sys.modules if name.startswith(forbidden))
raise SystemExit("unexpected host imports: " + repr(loaded) if loaded else 0)
"""
    result = subprocess.run(
        [sys.executable, "-c", code],
        cwd=REPO,
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 0, result.stderr or result.stdout


@pytest.mark.unit
def test_living_product_graph_projection_is_transport_and_composition_independent():
    """G1 stays a kernel read contract; its adapter receives a store explicitly."""
    tree = ast.parse(LIVING_PRODUCT_PROJECTOR.read_text(encoding="utf-8"))
    imported: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            imported.update(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            imported.add(node.module)

    forbidden = (
        "ace_mcp_client",
        "core.engine.api",
        "core.engine.cli",
        "core.engine.core.db",
        "core.engine.extensions",
        "core.engine.mcp",
        "core.engine.worker",
        "core.ui",
    )
    offenders = sorted(name for name in imported if name.startswith(forbidden))
    assert offenders == []

    store_source = LIVING_PRODUCT_STORE.read_text(encoding="utf-8")
    assert "import pool" not in store_source
    assert "db.pool" not in store_source
