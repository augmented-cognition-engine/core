from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

pytestmark = pytest.mark.unit

REPO = Path(__file__).resolve().parents[3]


def _fresh_process_identity() -> dict[str, str]:
    code = """
import json
from ace.core.agent_memory import AgentMemoryScopeV1Alpha1, MemoryVisibility, RetentionClass
from ace.core.agent_memory_ingestion import CanonicalSessionIdentityV1Alpha1

scope = AgentMemoryScopeV1Alpha1(
    product_id='product:agent-memory-am1-fixture',
    actor_id='principal:fixture-user',
    session_id='native-session:fixture-001',
    source_id='source:fixture-session-export',
    visibility=MemoryVisibility.PRIVATE,
    retention_class=RetentionClass.STANDARD,
    authority_receipt_ref='authority_receipt:fixture-import',
)
session = CanonicalSessionIdentityV1Alpha1(
    scope_id=scope.scope_id,
    source_id='source:fixture-session-export',
    source_version_id='source_version:fixture-session-export-v1',
    native_session_coordinate='fixture-001',
)
print(json.dumps({'scope_id': scope.scope_id, 'session_id': session.session_id}, sort_keys=True))
"""
    environment = {**os.environ, "ACE_DISABLE_EXTENSIONS": "1"}
    result = subprocess.run(
        [sys.executable, "-c", code],
        cwd=REPO,
        env=environment,
        check=False,
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0, result.stderr or result.stdout
    return json.loads(result.stdout)


def test_fresh_extension_disabled_process_reproduces_frozen_session_identity() -> None:
    first = _fresh_process_identity()
    reopened = _fresh_process_identity()

    assert (
        first
        == reopened
        == {
            "scope_id": "agent_memory_scope:53a988d6fc6eea9c29cb6f45d1f92e39",
            "session_id": "agent_memory_session:a5926f27a3fe0bb34b43e3fbfed2386e",
        }
    )


def test_am1_core_contract_import_composes_no_provider_host_or_extension() -> None:
    code = """
import sys
import ace.core.agent_memory_ingestion
forbidden = (
    'ace_mcp_client', 'core.engine.api', 'core.engine.cli', 'core.engine.extensions',
    'core.engine.mcp', 'extensions', 'surrealdb',
)
loaded = sorted(name for name in sys.modules if name.startswith(forbidden))
raise SystemExit('unexpected host/provider imports: ' + repr(loaded) if loaded else 0)
"""
    result = subprocess.run(
        [sys.executable, "-c", code],
        cwd=REPO,
        env={**os.environ, "ACE_DISABLE_EXTENSIONS": "1"},
        check=False,
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0, result.stderr or result.stdout
