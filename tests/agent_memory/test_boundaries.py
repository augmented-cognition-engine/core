from __future__ import annotations

import ast
import os
import subprocess
import sys
from pathlib import Path

import pytest

from ace.core.agent_memory_ports import AgentMemoryLedgerWriter
from ace.testing.immutable_records import InMemoryImmutableRecordStore

pytestmark = pytest.mark.unit

REPO = Path(__file__).resolve().parents[2]
CORE_CONTRACTS = (
    REPO / "ace/core/agent_memory.py",
    REPO / "ace/core/agent_memory_bridges.py",
    REPO / "ace/core/agent_memory_ports.py",
)
INTELLIGENCE_CONTRACT = REPO / "ace/intelligence/contracts/agent_memory.py"
THIN_MCP = REPO / "ace_mcp_client/server.py"


def _imports(path: Path) -> set[str]:
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    names: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            names.update(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            names.add(node.module)
    return names


def test_agent_memory_contracts_are_provider_host_and_extension_free() -> None:
    forbidden = (
        "ace_mcp_client",
        "aiohttp",
        "core.engine",
        "extensions",
        "fastapi",
        "httpx",
        "surrealdb",
    )
    offenders = [
        f"{path.relative_to(REPO)} ({name})"
        for path in (*CORE_CONTRACTS, INTELLIGENCE_CONTRACT)
        for name in _imports(path)
        if name.startswith(forbidden)
    ]
    assert offenders == []
    source = "\n".join(path.read_text(encoding="utf-8") for path in (*CORE_CONTRACTS, INTELLIGENCE_CONTRACT))
    assert "RecordID" not in source


def test_core_agent_memory_contracts_do_not_import_intelligence() -> None:
    offenders = [
        f"{path.relative_to(REPO)} ({name})"
        for path in CORE_CONTRACTS
        for name in _imports(path)
        if name == "ace.intelligence" or name.startswith("ace.intelligence.")
    ]
    assert offenders == []


def test_core_agent_memory_surface_contains_no_semantic_retrieval_or_composition_types() -> None:
    core_source = "\n".join(path.read_text(encoding="utf-8") for path in CORE_CONTRACTS)
    forbidden_type_names = {
        "AgentMemoryQueryV1Alpha1",
        "CandidateSignalContributionV1Alpha1",
        "CandidateRecordV1Alpha1",
        "CandidateReceiptV1Alpha1",
        "MemoryGraphProjectionRepository",
        "MemoryQueryRepository",
        "MemoryContextLineageV1Alpha1",
    }
    assert not any(name in core_source for name in forbidden_type_names)


def test_existing_in_memory_store_conforms_to_agent_memory_ledger_writer_port() -> None:
    assert isinstance(InMemoryImmutableRecordStore(), AgentMemoryLedgerWriter)


def test_naked_contract_import_composes_no_engine_host_or_extension() -> None:
    code = """
import sys
import ace.core.agent_memory
import ace.core.agent_memory_ports
import ace.intelligence.contracts.agent_memory
forbidden = (
    'ace_mcp_client', 'core.engine.api', 'core.engine.cli', 'core.engine.db',
    'core.engine.extensions', 'core.engine.mcp', 'core.engine.worker', 'extensions',
)
loaded = sorted(name for name in sys.modules if name.startswith(forbidden))
raise SystemExit('unexpected host imports: ' + repr(loaded) if loaded else 0)
"""
    environment = {**os.environ, "ACE_DISABLE_EXTENSIONS": "1"}
    result = subprocess.run(
        [sys.executable, "-c", code],
        cwd=REPO,
        env=environment,
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 0, result.stderr or result.stdout


def test_thin_public_mcp_inventory_remains_exactly_eleven_tools() -> None:
    tree = ast.parse(THIN_MCP.read_text(encoding="utf-8"), filename=str(THIN_MCP))
    names: list[str] = []
    for node in ast.walk(tree):
        if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            continue
        for decorator in node.decorator_list:
            if not isinstance(decorator, ast.Call) or not isinstance(decorator.func, ast.Attribute):
                continue
            if decorator.func.attr != "tool":
                continue
            for keyword in decorator.keywords:
                if keyword.arg == "name" and isinstance(keyword.value, ast.Constant):
                    names.append(str(keyword.value.value))
    assert names == [
        "ace_start",
        "ace_load",
        "ace_capture",
        "ace_task",
        "ace_status",
        "ace_capture_idea",
        "ace_search",
        "ace_briefing",
        "ace_impact",
        "ace_history",
        "ace_related",
    ]
