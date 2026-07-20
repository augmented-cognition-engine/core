# tests/test_runtime_bridge.py
"""Tests for E5 — Runtime Bridge: OTel config, error explanation, dependency updates.

Covers:
- _parse_stack_trace_modules: Python + Node trace extraction
- _extract_error_keywords: normalisation + dedup
- _classify_update_type: major / minor / patch detection
- _find_blocking_decision: decision gate matching
- _otel_install_commands: stack → install list
- run_instrument: file generation per stack, docker-compose always included
- run_explain_error: LLM path, runbook hit path, auto-capture, missing error guard
- run_update_deps: strategy filter, decision blocking, pip-audit/npm mocked
- MCP routing: ace_instrument, ace_explain_error, ace_update_deps
"""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

# ── Fixtures ─────────────────────────────────────────────────────────────────


@pytest.fixture
def mock_pool():
    mock_db = AsyncMock()
    mock_db.query = AsyncMock(return_value=[])
    mock_conn = MagicMock()
    mock_conn.__aenter__ = AsyncMock(return_value=mock_db)
    mock_conn.__aexit__ = AsyncMock(return_value=False)
    mock_p = MagicMock()
    mock_p.connection.return_value = mock_conn
    return mock_p, mock_db


# ── _parse_stack_trace_modules ────────────────────────────────────────────────


def test_parse_stack_python_trace():
    from core.engine.product.runtime_bridge import _parse_stack_trace_modules

    trace = (
        "Traceback (most recent call last):\n"
        '  File "/home/user/app/engine/user/create.py", line 45, in create_user\n'
        "    db.insert(user)\n"
        '  File "/home/user/app/engine/core/db.py", line 12, in insert\n'
        "    await conn.query(sql)\n"
    )

    modules = _parse_stack_trace_modules(trace)

    assert any("create.py" in m for m in modules)
    assert any("db.py" in m for m in modules)


def test_parse_stack_node_trace():
    from core.engine.product.runtime_bridge import _parse_stack_trace_modules

    trace = (
        "TypeError: Cannot read properties of undefined\n"
        "    at Object.<anonymous> (src/api/users.ts:34:12)\n"
        "    at processTicksAndRejections (node:internal/process/task_queues:95:5)\n"
    )

    modules = _parse_stack_trace_modules(trace)

    assert any("users.ts" in m for m in modules)


def test_parse_stack_empty_returns_empty():
    from core.engine.product.runtime_bridge import _parse_stack_trace_modules

    result = _parse_stack_trace_modules("")
    assert result == []


def test_parse_stack_deduplicates():
    from core.engine.product.runtime_bridge import _parse_stack_trace_modules

    trace = '  File "/app/engine/db.py", line 10, in query\n  File "/app/engine/db.py", line 20, in execute\n'

    modules = _parse_stack_trace_modules(trace)
    basenames = [m.split("/")[-1] for m in modules]
    assert basenames.count("db.py") == 1


# ── _extract_error_keywords ───────────────────────────────────────────────────


def test_extract_keywords_from_constraint_error():
    from core.engine.product.runtime_bridge import _extract_error_keywords

    error = "UNIQUE constraint failed: users.email"
    keywords = _extract_error_keywords(error)

    assert "UNIQUE" in keywords or "unique" in keywords.copy() or any(k.lower() == "unique" for k in keywords)
    # Should not include short noise words
    assert all(len(k) >= 4 for k in keywords)


def test_extract_keywords_strips_hex_addresses():
    from core.engine.product.runtime_bridge import _extract_error_keywords

    error = "Segfault at 0xDEADBEEF in module loader"
    keywords = _extract_error_keywords(error)

    assert not any("0x" in k for k in keywords)
    assert any("module" in k.lower() or "loader" in k.lower() for k in keywords)


def test_extract_keywords_max_five():
    from core.engine.product.runtime_bridge import _extract_error_keywords

    error = "alpha beta gamma delta epsilon zeta eta theta iota kappa lambda mu nu xi"
    keywords = _extract_error_keywords(error)

    assert len(keywords) <= 5


# ── _classify_update_type ─────────────────────────────────────────────────────


def test_classify_major_update():
    from core.engine.product.runtime_bridge import _classify_update_type

    assert _classify_update_type("1.0.0", "2.0.0") == "major"


def test_classify_minor_update():
    from core.engine.product.runtime_bridge import _classify_update_type

    assert _classify_update_type("1.2.0", "1.3.0") == "minor"


def test_classify_patch_update():
    from core.engine.product.runtime_bridge import _classify_update_type

    assert _classify_update_type("1.2.3", "1.2.9") == "patch"


def test_classify_with_tilde_prefix():
    from core.engine.product.runtime_bridge import _classify_update_type

    # npm-style range prefix
    assert _classify_update_type("~2.0.0", "3.0.0") == "major"


def test_classify_invalid_falls_back_to_unknown():
    from core.engine.product.runtime_bridge import _classify_update_type

    assert _classify_update_type("not-semver", "also-not") == "unknown"


# ── _find_blocking_decision ───────────────────────────────────────────────────


def test_find_blocking_decision_hit():
    from core.engine.product.runtime_bridge import _find_blocking_decision

    decisions = [
        {"title": "Pin surrealdb to v0.3 for API stability", "rationale": "v1 breaks all record casts"},
    ]

    result = _find_blocking_decision("surrealdb", "0.3.2", "1.0.0", decisions)

    assert result is not None
    assert "surrealdb" in result.lower() or "Pin" in result


def test_find_blocking_decision_no_match():
    from core.engine.product.runtime_bridge import _find_blocking_decision

    decisions = [
        {"title": "Use Redis for session cache", "rationale": "low latency"},
    ]

    result = _find_blocking_decision("requests", "2.28.0", "2.31.0", decisions)

    assert result is None


def test_find_blocking_decision_empty_decisions():
    from core.engine.product.runtime_bridge import _find_blocking_decision

    result = _find_blocking_decision("fastapi", "0.95.0", "0.110.0", [])

    assert result is None


# ── _otel_install_commands ────────────────────────────────────────────────────


def test_otel_install_python_stack():
    from core.engine.product.runtime_bridge import _otel_install_commands

    cmds = _otel_install_commands(["python", "fastapi"])

    assert any("opentelemetry" in c for c in cmds)
    assert any("pip install" in c for c in cmds)


def test_otel_install_node_stack():
    from core.engine.product.runtime_bridge import _otel_install_commands

    cmds = _otel_install_commands(["typescript", "nextjs"])

    assert any("npm install" in c for c in cmds)
    assert any("@opentelemetry" in c for c in cmds)


def test_otel_install_unknown_stack_returns_fallback():
    from core.engine.product.runtime_bridge import _otel_install_commands

    cmds = _otel_install_commands(["rust"])

    assert len(cmds) == 1
    assert "No packages detected" in cmds[0]


# ── run_instrument ────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_run_instrument_python_stack(mock_pool):
    from core.engine.product import runtime_bridge
    from core.engine.product.runtime_bridge import run_instrument

    mock_p, mock_db = mock_pool

    with patch.object(runtime_bridge, "pool", mock_p):
        result = await run_instrument(product_id="product:platform", stack=["python", "fastapi"])

    assert "files" in result
    paths = [f["path"] for f in result["files"]]
    assert "otel_config.py" in paths
    assert "docker-compose.otel.yml" in paths
    assert "otel-collector-config.yml" in paths


@pytest.mark.asyncio
async def test_run_instrument_node_stack(mock_pool):
    from core.engine.product import runtime_bridge
    from core.engine.product.runtime_bridge import run_instrument

    mock_p, mock_db = mock_pool

    with patch.object(runtime_bridge, "pool", mock_p):
        result = await run_instrument(product_id="product:platform", stack=["typescript", "nextjs"])

    paths = [f["path"] for f in result["files"]]
    assert "otel.ts" in paths
    assert "docker-compose.otel.yml" in paths


@pytest.mark.asyncio
async def test_run_instrument_docker_always_included(mock_pool):
    """docker-compose.otel.yml is always generated regardless of stack."""
    from core.engine.product import runtime_bridge
    from core.engine.product.runtime_bridge import run_instrument

    mock_p, mock_db = mock_pool

    with patch.object(runtime_bridge, "pool", mock_p):
        result = await run_instrument(product_id="product:platform", stack=["go"])

    paths = [f["path"] for f in result["files"]]
    assert "docker-compose.otel.yml" in paths


@pytest.mark.asyncio
async def test_run_instrument_auto_detects_stack(mock_pool):
    """When stack=None, detects from capabilities."""
    from core.engine.product import runtime_bridge
    from core.engine.product.runtime_bridge import run_instrument

    mock_p, mock_db = mock_pool
    mock_db.query = AsyncMock(return_value=[{"slug": "fastapi_router", "title": "FastAPI Router", "category": "api"}])

    with patch.object(runtime_bridge, "pool", mock_p):
        result = await run_instrument(product_id="product:platform", stack=None)

    assert "files" in result
    assert result["stack"]  # was populated from capability detection


@pytest.mark.asyncio
async def test_run_instrument_returns_install_commands(mock_pool):
    from core.engine.product import runtime_bridge
    from core.engine.product.runtime_bridge import run_instrument

    mock_p, mock_db = mock_pool

    with patch.object(runtime_bridge, "pool", mock_p):
        result = await run_instrument(product_id="product:platform", stack=["python"])

    assert "install_commands" in result
    assert isinstance(result["install_commands"], list)


@pytest.mark.asyncio
async def test_run_instrument_returns_quickstart(mock_pool):
    from core.engine.product import runtime_bridge
    from core.engine.product.runtime_bridge import run_instrument

    mock_p, mock_db = mock_pool

    with patch.object(runtime_bridge, "pool", mock_p):
        result = await run_instrument(product_id="product:platform", stack=["python"])

    assert "quickstart" in result
    assert "Jaeger" in result["quickstart"]


# ── run_explain_error ─────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_run_explain_error_missing_error(mock_pool):
    from core.engine.product import runtime_bridge
    from core.engine.product.runtime_bridge import run_explain_error

    mock_p, mock_db = mock_pool

    with patch.object(runtime_bridge, "pool", mock_p):
        result = await run_explain_error(error="", stack_trace="", product_id="product:platform")

    assert "error" in result


@pytest.mark.asyncio
async def test_run_explain_error_llm_path(mock_pool):
    """When no runbook matches, calls LLM and captures as runbook."""
    from core.engine.product import runtime_bridge
    from core.engine.product.runtime_bridge import run_explain_error

    mock_p, mock_db = mock_pool
    mock_db.query = AsyncMock(return_value=[])  # no decisions, no runbooks

    mock_llm = AsyncMock()
    mock_llm.complete = AsyncMock(return_value="## Root cause\n\nNull pointer in user create.")

    with (
        patch.object(runtime_bridge, "pool", mock_p),
        patch.object(runtime_bridge, "get_llm", return_value=mock_llm),
    ):
        result = await run_explain_error(
            error="NullPointerError: user is None",
            stack_trace='  File "/app/engine/user/create.py", line 45, in create_user',
            product_id="product:platform",
        )

    assert "explanation" in result
    assert "Null pointer" in result["explanation"] or "Root cause" in result["explanation"]
    assert result["captured_as_runbook"] is True
    assert result["runbook_match"] is None


@pytest.mark.asyncio
async def test_run_explain_error_runbook_hit_path(mock_pool):
    """When runbook matches, return runbook_match and skip auto-capture."""
    from core.engine.product import runtime_bridge
    from core.engine.product.runtime_bridge import run_explain_error

    mock_p, mock_db = mock_pool

    # Empty stack_trace → no affected_modules → no decision queries.
    # All queries are runbook queries; return a match immediately.
    mock_db.query = AsyncMock(
        return_value=[{"title": "Error: UNIQUE constraint failed", "content": "Add unique index", "tags": ["UNIQUE"]}]
    )

    mock_llm = AsyncMock()
    mock_llm.complete = AsyncMock(return_value="LLM explanation")

    with (
        patch.object(runtime_bridge, "pool", mock_p),
        patch.object(runtime_bridge, "get_llm", return_value=mock_llm),
    ):
        result = await run_explain_error(
            error="UNIQUE constraint failed: users.email",
            stack_trace="",
            product_id="product:platform",
        )

    assert result["runbook_match"] == "Error: UNIQUE constraint failed"
    # Since runbook_match is set, captured_as_runbook should be False
    assert result["captured_as_runbook"] is False


@pytest.mark.asyncio
async def test_run_explain_error_llm_failure_still_returns(mock_pool):
    """LLM failure returns graceful degraded response."""
    from core.engine.product import runtime_bridge
    from core.engine.product.runtime_bridge import run_explain_error

    mock_p, mock_db = mock_pool
    mock_db.query = AsyncMock(return_value=[])

    mock_llm = AsyncMock()
    mock_llm.complete = AsyncMock(side_effect=Exception("model overloaded"))

    with (
        patch.object(runtime_bridge, "pool", mock_p),
        patch.object(runtime_bridge, "get_llm", return_value=mock_llm),
    ):
        result = await run_explain_error(
            error="ValueError: bad input",
            stack_trace="",
            product_id="product:platform",
        )

    assert "explanation" in result
    assert "LLM unavailable" in result["explanation"] or "ValueError" in result["explanation"]


@pytest.mark.asyncio
async def test_run_explain_error_returns_affected_modules(mock_pool):
    """Affected modules are returned even without LLM synthesis."""
    from core.engine.product import runtime_bridge
    from core.engine.product.runtime_bridge import run_explain_error

    mock_p, mock_db = mock_pool
    mock_db.query = AsyncMock(return_value=[])

    mock_llm = AsyncMock()
    mock_llm.complete = AsyncMock(return_value="explanation text")

    with (
        patch.object(runtime_bridge, "pool", mock_p),
        patch.object(runtime_bridge, "get_llm", return_value=mock_llm),
    ):
        result = await run_explain_error(
            error="AttributeError: 'NoneType' object has no attribute 'id'",
            stack_trace='  File "/app/engine/orders/create.py", line 22, in process',
            product_id="product:platform",
        )

    assert "affected_modules" in result
    assert any("create.py" in m for m in result["affected_modules"])


# ── run_update_deps ───────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_run_update_deps_invalid_strategy():
    from core.engine.product.runtime_bridge import run_update_deps

    result = await run_update_deps(strategy="aggressive", repo_path=".", product_id=None)

    assert "error" in result
    assert "aggressive" in result["error"]


@pytest.mark.asyncio
async def test_run_update_deps_no_audit_tools(tmp_path):
    """When pip-audit and npm are absent, returns empty update list without error."""
    from core.engine.product.runtime_bridge import run_update_deps

    # tmp_path has no requirements.txt or package.json
    result = await run_update_deps(strategy="minor", repo_path=str(tmp_path), product_id=None)

    assert "updates" in result
    assert result["updates"] == []
    assert result["total_updates"] == 0


@pytest.mark.asyncio
async def test_run_update_deps_strategy_patch_filters_minor(tmp_path):
    """patch strategy excludes minor updates."""
    import json

    from core.engine.product.runtime_bridge import run_update_deps

    # Create fake requirements.txt so pip-audit path is attempted
    req = tmp_path / "requirements.txt"
    req.write_text("requests==2.28.0\n")

    pip_audit_output = json.dumps(
        {
            "dependencies": [
                {
                    "name": "requests",
                    "version": "2.28.0",
                    "vulns": [
                        {
                            "id": "CVE-2023-9999",
                            "description": "header injection",
                            "fix_versions": ["2.29.0"],
                        }
                    ],
                }
            ]
        }
    )

    mock_run = MagicMock()
    mock_run.stdout = pip_audit_output
    mock_run.returncode = 0

    with patch("core.engine.product.runtime_bridge.subprocess.run", return_value=mock_run):
        result = await run_update_deps(strategy="patch", repo_path=str(tmp_path), product_id=None)

    # 2.28.0 → 2.29.0 is minor, so should be filtered out under 'patch'
    assert result["strategy"] == "patch"
    # All returned updates should only be patch-level
    for u in result["updates"]:
        assert u["update_type"] in ("patch", "unknown")


@pytest.mark.asyncio
async def test_run_update_deps_decision_blocks_package(tmp_path, mock_pool):
    """A decision mentioning a package blocks it with rationale."""
    import json

    from core.engine.product import runtime_bridge
    from core.engine.product.runtime_bridge import run_update_deps

    req = tmp_path / "requirements.txt"
    req.write_text("surrealdb==0.3.2\n")

    pip_audit_output = json.dumps(
        {
            "dependencies": [
                {
                    "name": "surrealdb",
                    "version": "0.3.2",
                    "vulns": [
                        {
                            "id": "CVE-2024-0001",
                            "description": "arbitrary code execution",
                            "fix_versions": ["1.0.0"],
                        }
                    ],
                }
            ]
        }
    )

    mock_p, mock_db = mock_pool
    mock_db.query = AsyncMock(
        return_value=[
            {
                "title": "Pin surrealdb to 0.3.x for v3 API compatibility",
                "rationale": "v1 API breaks all record casts",
                "discipline": "dependency_management",
            }
        ]
    )

    mock_run = MagicMock()
    mock_run.stdout = pip_audit_output
    mock_run.returncode = 0

    with (
        patch("core.engine.product.runtime_bridge.subprocess.run", return_value=mock_run),
        patch.object(runtime_bridge, "pool", mock_p),
    ):
        result = await run_update_deps(strategy="semver", repo_path=str(tmp_path), product_id="product:platform")

    blocked = [u for u in result["updates"] if u.get("blocked_by_decision")]
    assert len(blocked) >= 1
    assert "surrealdb" in blocked[0]["package"].lower()
    assert result["blocked_count"] >= 1


@pytest.mark.asyncio
async def test_run_update_deps_returns_vulnerabilities(tmp_path):
    """Vulnerabilities are returned even if strategy filters the update."""
    import json

    from core.engine.product.runtime_bridge import run_update_deps

    req = tmp_path / "requirements.txt"
    req.write_text("cryptography==41.0.0\n")

    pip_audit_output = json.dumps(
        {
            "dependencies": [
                {
                    "name": "cryptography",
                    "version": "41.0.0",
                    "vulns": [
                        {
                            "id": "CVE-2024-1234",
                            "description": "padding oracle attack",
                            "fix_versions": ["42.0.0"],
                        }
                    ],
                }
            ]
        }
    )

    mock_run = MagicMock()
    mock_run.stdout = pip_audit_output
    mock_run.returncode = 0

    with patch("core.engine.product.runtime_bridge.subprocess.run", return_value=mock_run):
        result = await run_update_deps(strategy="minor", repo_path=str(tmp_path), product_id=None)

    assert "vulnerabilities" in result
    assert any(v["package"] == "cryptography" for v in result["vulnerabilities"])


# ── MCP routing ───────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_ace_instrument_mcp_tool(mock_pool):
    from core.engine.mcp import tools
    from core.engine.product import runtime_bridge

    mock_p, _ = mock_pool

    with patch.object(runtime_bridge, "pool", mock_p):
        result = await tools.ace_instrument(stack=["python", "fastapi"], product_id="product:platform")

    assert "files" in result
    assert "install_commands" in result


@pytest.mark.asyncio
async def test_ace_explain_error_mcp_tool(mock_pool):
    from core.engine.mcp import tools
    from core.engine.product import runtime_bridge

    mock_p, mock_db = mock_pool
    mock_db.query = AsyncMock(return_value=[])

    mock_llm = AsyncMock()
    mock_llm.complete = AsyncMock(return_value="Root cause: bad input validation.")

    with (
        patch.object(runtime_bridge, "pool", mock_p),
        patch.object(runtime_bridge, "get_llm", return_value=mock_llm),
    ):
        result = await tools.ace_explain_error(
            error="ValueError: invalid email",
            stack_trace="",
            product_id="product:platform",
        )

    assert "explanation" in result
    assert "affected_modules" in result


@pytest.mark.asyncio
async def test_ace_update_deps_mcp_tool(tmp_path):
    from core.engine.mcp import tools

    result = await tools.ace_update_deps(
        strategy="minor",
        repo_path=str(tmp_path),
        product_id="product:platform",
    )

    assert "updates" in result
    assert "strategy" in result
    assert result["strategy"] == "minor"
