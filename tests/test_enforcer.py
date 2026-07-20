# tests/test_enforcer.py
"""Tests for engine.product.enforcer — decision lockfile export and violation checking."""

import os
import stat
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
import yaml

# ── Fixtures ─────────────────────────────────────────────────────────────────


@pytest.fixture
def mock_pool():
    """Mock DB pool with async connection context manager."""
    mock_db = AsyncMock()
    mock_db.query = AsyncMock(return_value=[])
    mock_conn = MagicMock()
    mock_conn.__aenter__ = AsyncMock(return_value=mock_db)
    mock_conn.__aexit__ = AsyncMock(return_value=False)
    mock_p = MagicMock()
    mock_p.connection.return_value = mock_conn
    return mock_p, mock_db


@pytest.fixture
def tmp_lockfile(tmp_path):
    """Write a minimal decisions lockfile into tmp_path and return its path."""
    lockfile_data = {
        "version": "1",
        "product": "product:platform",
        "generated_at": "2026-04-12T00:00:00Z",
        "default_mode": "warn",
        "decisions": [
            {
                "id": "decision:1",
                "title": "Use get_llm() not ClaudeProvider",
                "rationale": "Always call `get_llm()` for OAuth subscription auth",
                "enforcement_mode": "warn",
                "file_patterns": ["engine/**"],
                "violation_check": "contains",
                "violation_pattern": "ClaudeProvider",
            },
            {
                "id": "decision:2",
                "title": "Never import raw httpx in auth module",
                "rationale": "Use the shared HTTP client to ensure retries",
                "enforcement_mode": "block",
                "file_patterns": ["engine/auth/**"],
                "violation_check": "regex",
                "violation_pattern": r"import httpx",
            },
        ],
    }
    lockfile_path = tmp_path / "decisions.yml"
    lockfile_path.write_text(yaml.dump(lockfile_data))
    return str(lockfile_path)


@pytest.fixture
def tmp_config(tmp_path, monkeypatch):
    """Write a minimal enforce.config.yml and patch the constant."""
    config_data = {
        "version": "1",
        "global_mode": "warn",
        "exclude_patterns": ["venv/**", ".venv/**", "docs/**"],
    }
    config_path = tmp_path / "enforce.config.yml"
    config_path.write_text(yaml.dump(config_data))
    monkeypatch.setenv("ACE_ENFORCE_CONFIG", str(config_path))
    return str(config_path)


# ── Unit tests: _paths_to_globs ───────────────────────────────────────────────


def test_paths_to_globs_single_file():
    from core.engine.product.enforcer import _paths_to_globs

    result = _paths_to_globs(["core/engine/product/enforcer.py"])
    assert result == ["core/engine/product/enforcer.py"]


def test_paths_to_globs_same_dir_collapses():
    from core.engine.product.enforcer import _paths_to_globs

    paths = ["engine/product/enforcer.py", "engine/product/spec_generator.py"]
    result = _paths_to_globs(paths)
    assert result == ["engine/product/**"]


def test_paths_to_globs_multiple_dirs_returns_individual():
    from core.engine.product.enforcer import _paths_to_globs

    paths = [
        "core/engine/product/enforcer.py",
        "core/engine/scanner/hardening.py",
        "core/engine/mcp/tools.py",
    ]
    result = _paths_to_globs(paths)
    # Multiple dirs → individual files (capped at 5)
    assert len(result) <= 5
    assert "core/engine/product/enforcer.py" in result


def test_paths_to_globs_empty():
    from core.engine.product.enforcer import _paths_to_globs

    assert _paths_to_globs([]) == []


# ── Unit tests: _infer_violation_check ────────────────────────────────────────


def test_infer_violation_check_explicit_fields():
    from core.engine.product.enforcer import _infer_violation_check

    decision = {
        "violation_check": "regex",
        "violation_pattern": r"^import ClaudeProvider",
    }
    check_type, pattern = _infer_violation_check(decision)
    assert check_type == "regex"
    assert pattern == r"^import ClaudeProvider"


def test_infer_violation_check_backtick_heuristic():
    from core.engine.product.enforcer import _infer_violation_check

    decision = {
        "title": "Use get_llm()",
        "rationale": "Always use `get_llm()` not `ClaudeProvider()` directly",
    }
    check_type, pattern = _infer_violation_check(decision)
    assert check_type == "contains"
    assert pattern == "get_llm()"  # First backtick-quoted identifier


def test_infer_violation_check_no_hints_falls_back_to_llm():
    from core.engine.product.enforcer import _infer_violation_check

    decision = {
        "title": "Prefer structured logging",
        "rationale": "Structured logging is required for observability.",
    }
    check_type, pattern = _infer_violation_check(decision)
    assert check_type == "llm"
    assert pattern == ""


# ── Unit tests: _run_violation_check ─────────────────────────────────────────


def test_run_violation_check_contains_in_path():
    from core.engine.product.enforcer import _run_violation_check

    decision = {"violation_check": "contains", "violation_pattern": "ClaudeProvider"}
    assert _run_violation_check(decision, "engine/provider/ClaudeProvider.py", None) is True


def test_run_violation_check_contains_in_diff():
    from core.engine.product.enforcer import _run_violation_check

    decision = {"violation_check": "contains", "violation_pattern": "ClaudeProvider"}
    diff = "+from engine.providers import ClaudeProvider\n"
    assert _run_violation_check(decision, "engine/llm.py", diff) is True


def test_run_violation_check_contains_no_match():
    from core.engine.product.enforcer import _run_violation_check

    decision = {"violation_check": "contains", "violation_pattern": "ClaudeProvider"}
    assert _run_violation_check(decision, "core/engine/product/enforcer.py", None) is False


def test_run_violation_check_regex_match():
    from core.engine.product.enforcer import _run_violation_check

    decision = {"violation_check": "regex", "violation_pattern": r"test_.*\.py$"}
    assert _run_violation_check(decision, "tests/test_enforcer.py", None) is True


def test_run_violation_check_regex_no_match():
    from core.engine.product.enforcer import _run_violation_check

    decision = {"violation_check": "regex", "violation_pattern": r"test_.*\.py$"}
    assert _run_violation_check(decision, "core/engine/product/enforcer.py", None) is False


def test_run_violation_check_llm_always_flags():
    from core.engine.product.enforcer import _run_violation_check

    decision = {"violation_check": "llm", "violation_pattern": ""}
    # LLM-mode is conservative — always returns True for scope matches
    assert _run_violation_check(decision, "any/file.py", None) is True


# ── Unit tests: _load_config ─────────────────────────────────────────────────


def test_load_config_missing_file_returns_defaults(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    from core.engine.product import enforcer

    with patch.object(enforcer, "_CONFIG_FILE", str(tmp_path / "nonexistent.yml")):
        config = enforcer._load_config()
    assert config["global_mode"] == "warn"
    assert "venv/**" in config["exclude_patterns"]


def test_load_config_reads_file(tmp_path, monkeypatch):
    config_path = tmp_path / "enforce.config.yml"
    config_path.write_text("global_mode: 'block'\nexclude_patterns:\n  - 'dist/**'\n")
    from core.engine.product import enforcer

    with patch.object(enforcer, "_CONFIG_FILE", str(config_path)):
        config = enforcer._load_config()
    assert config["global_mode"] == "block"
    assert "dist/**" in config["exclude_patterns"]


# ── Integration tests: check_file ────────────────────────────────────────────


@pytest.mark.asyncio
async def test_check_file_missing_lockfile(tmp_path):
    from core.engine.product.enforcer import check_file

    result = await check_file("engine/llm.py", lockfile_path=str(tmp_path / "missing.yml"))
    assert result["lockfile_missing"] is True
    assert result["clean"] is True


@pytest.mark.asyncio
async def test_check_file_no_violations(tmp_lockfile, tmp_path, monkeypatch):
    """File outside all decision scopes → clean."""
    monkeypatch.chdir(tmp_path)
    from core.engine.product import enforcer

    # Patch config to avoid side-effects from real config files
    with patch.object(enforcer, "_CONFIG_FILE", str(tmp_path / "no_config.yml")):
        result = await enforcer.check_file("tests/test_enforcer.py", lockfile_path=tmp_lockfile)
    # tests/ doesn't match engine/** or engine/auth/**
    assert result["clean"] is True
    assert result["violations"] == []


@pytest.mark.asyncio
async def test_check_file_warn_violation(tmp_lockfile, tmp_path, monkeypatch):
    """File in scope with contains match → warn violation returned."""
    monkeypatch.chdir(tmp_path)
    from core.engine.product import enforcer

    with patch.object(enforcer, "_CONFIG_FILE", str(tmp_path / "no_config.yml")):
        result = await enforcer.check_file(
            "engine/llm.py",
            diff_content="+from engine.providers import ClaudeProvider\n",
            lockfile_path=tmp_lockfile,
        )
    assert not result["clean"]
    assert len(result["violations"]) == 1
    v = result["violations"][0]
    assert v["decision_id"] == "decision:1"
    assert v["mode"] == "warn"


@pytest.mark.asyncio
async def test_check_file_block_violation(tmp_lockfile, tmp_path, monkeypatch):
    """File matching block-mode decision → violation with mode=block."""
    monkeypatch.chdir(tmp_path)
    from core.engine.product import enforcer

    with patch.object(enforcer, "_CONFIG_FILE", str(tmp_path / "no_config.yml")):
        result = await enforcer.check_file(
            "engine/auth/session.py",
            diff_content="+import httpx\n",
            lockfile_path=tmp_lockfile,
        )
    # Should be caught by decision:2 (block, regex ^import httpx)
    block_violations = [v for v in result["violations"] if v["mode"] == "block"]
    assert len(block_violations) >= 1
    assert block_violations[0]["decision_id"] == "decision:2"


@pytest.mark.asyncio
async def test_check_file_excluded_path(tmp_lockfile, tmp_path, monkeypatch):
    """Excluded path → skipped, no violations even on match."""
    monkeypatch.chdir(tmp_path)
    config_path = tmp_path / "config.yml"
    config_path.write_text("global_mode: warn\nexclude_patterns:\n  - 'engine/**'\n")
    from core.engine.product import enforcer

    with patch.object(enforcer, "_CONFIG_FILE", str(config_path)):
        result = await enforcer.check_file(
            "engine/llm.py",
            diff_content="+ClaudeProvider()\n",
            lockfile_path=tmp_lockfile,
        )
    assert result["clean"] is True
    assert result.get("excluded") is True


@pytest.mark.asyncio
async def test_check_file_global_block_mode_overrides(tmp_lockfile, tmp_path, monkeypatch):
    """global_mode=block overrides per-decision warn mode."""
    monkeypatch.chdir(tmp_path)
    config_path = tmp_path / "config.yml"
    config_path.write_text("global_mode: block\nexclude_patterns: []\n")
    from core.engine.product import enforcer

    with patch.object(enforcer, "_CONFIG_FILE", str(config_path)):
        result = await enforcer.check_file(
            "engine/llm.py",
            diff_content="+ClaudeProvider()\n",
            lockfile_path=tmp_lockfile,
        )
    assert not result["clean"]
    assert result["violations"][0]["mode"] == "block"


# ── Integration tests: check_staged ──────────────────────────────────────────


@pytest.mark.asyncio
async def test_check_staged_missing_lockfile(tmp_path):
    from core.engine.product.enforcer import check_staged

    result = await check_staged(lockfile_path=str(tmp_path / "missing.yml"))
    assert result["lockfile_missing"] is True
    assert result["blocked"] is False


@pytest.mark.asyncio
async def test_check_staged_aggregates_violations(tmp_lockfile, tmp_path, monkeypatch):
    """check_staged calls git diff and aggregates per-file violations."""
    monkeypatch.chdir(tmp_path)
    from core.engine.product import enforcer

    staged_output = b"engine/llm.py\nengine/auth/session.py\n"
    diff_output = b"+from engine.providers import ClaudeProvider\n+import httpx\n"

    with (
        patch("core.engine.product.enforcer.subprocess.check_output") as mock_sp,
        patch.object(enforcer, "_CONFIG_FILE", str(tmp_path / "no_config.yml")),
    ):
        mock_sp.side_effect = [staged_output, diff_output]
        result = await enforcer.check_staged(lockfile_path=tmp_lockfile)

    assert result["files_checked"] == 2
    # At least one violation expected (decision:2 block on engine/auth/session.py)
    assert len(result["violations"]) >= 1
    has_block = any(v["mode"] == "block" for v in result["violations"])
    assert result["blocked"] == has_block


@pytest.mark.asyncio
async def test_check_staged_clean_returns_not_blocked(tmp_lockfile, tmp_path, monkeypatch):
    """Staged files outside decision scopes → clean."""
    monkeypatch.chdir(tmp_path)
    from core.engine.product import enforcer

    staged_output = b"tests/test_something.py\n"
    diff_output = b"+def test_foo(): pass\n"

    with (
        patch("core.engine.product.enforcer.subprocess.check_output") as mock_sp,
        patch.object(enforcer, "_CONFIG_FILE", str(tmp_path / "no_config.yml")),
    ):
        mock_sp.side_effect = [staged_output, diff_output]
        result = await enforcer.check_staged(lockfile_path=tmp_lockfile)

    assert result["blocked"] is False


# ── Integration tests: install_git_hook ──────────────────────────────────────


def test_install_git_hook_success(tmp_path):
    """install_git_hook writes hook file with correct content and executable bit."""
    # Create a fake .git/hooks/ directory
    hooks_dir = tmp_path / ".git" / "hooks"
    hooks_dir.mkdir(parents=True)

    from core.engine.product.enforcer import _GIT_HOOK_SCRIPT, install_git_hook

    result = install_git_hook(project_root=str(tmp_path))
    assert result["installed"] is True

    hook_path = Path(result["hook_path"])
    assert hook_path.exists()
    assert hook_path.read_text() == _GIT_HOOK_SCRIPT

    # Executable bit set for owner
    mode = hook_path.stat().st_mode
    assert mode & stat.S_IXUSR, "Owner executable bit not set"


def test_install_git_hook_not_git_repo(tmp_path):
    """install_git_hook returns installed=False when .git/hooks/ is absent."""
    from core.engine.product.enforcer import install_git_hook

    result = install_git_hook(project_root=str(tmp_path))
    assert result["installed"] is False
    assert "Not a git repository" in result["message"]


def test_install_git_hook_overwrites_existing(tmp_path):
    """Re-running install_git_hook overwrites the existing hook safely."""
    hooks_dir = tmp_path / ".git" / "hooks"
    hooks_dir.mkdir(parents=True)
    hook_path = hooks_dir / "pre-commit"
    hook_path.write_text("#!/bin/sh\necho old hook\n")

    from core.engine.product.enforcer import install_git_hook

    result = install_git_hook(project_root=str(tmp_path))
    assert result["installed"] is True
    assert "echo old hook" not in hook_path.read_text()


# ── Integration tests: export_decisions ──────────────────────────────────────


@pytest.mark.asyncio
async def test_export_decisions_empty_product(tmp_path, mock_pool):
    """export_decisions with no decisions → exports 0, writes lockfile, warns."""
    mock_p, mock_db = mock_pool
    mock_db.query = AsyncMock(return_value=[])

    output_path = str(tmp_path / "decisions.yml")

    with patch("core.engine.core.db.pool", mock_p), patch("core.engine.core.db.parse_rows", return_value=[]):
        from core.engine.product import enforcer

        with patch.object(enforcer, "_CONFIG_FILE", str(tmp_path / "enforce.config.yml")):
            result = await enforcer.export_decisions(
                product_id="product:platform",
                output_path=output_path,
                mode="warn",
            )

    assert result["exported"] == 0
    assert result["output_path"] == output_path
    assert len(result["warnings"]) > 0

    # Lockfile written with correct structure
    with open(output_path) as f:
        content = yaml.safe_load(f)
    assert content["version"] == "1"
    assert content["product"] == "product:platform"
    assert content["decisions"] == []


@pytest.mark.asyncio
async def test_export_decisions_writes_yaml_structure(tmp_path, mock_pool):
    """export_decisions serializes decisions with all required keys."""
    mock_p, mock_db = mock_pool

    fake_decisions = [
        {
            "id": "decision:42",
            "title": "Enforce snake_case filenames",
            "decision_type": "convention",
            "rationale": "Consistency across the `engine/` directory.",
            "enforcement_mode": "warn",
            "discipline_hint": "code_conventions",
            "created_at": "2026-04-12T00:00:00",
        }
    ]

    output_path = str(tmp_path / "decisions.yml")

    with (
        patch("core.engine.core.db.pool", mock_p),
        patch("core.engine.core.db.parse_rows", return_value=fake_decisions),
    ):
        # Sub-queries for capabilities and file patterns return empty
        mock_db.query = AsyncMock(return_value=[])
        from core.engine.product import enforcer

        with patch.object(enforcer, "_CONFIG_FILE", str(tmp_path / "enforce.config.yml")):
            result = await enforcer.export_decisions(
                product_id="product:platform",
                output_path=output_path,
            )

    assert result["exported"] == 1

    with open(output_path) as f:
        content = yaml.safe_load(f)

    dec = content["decisions"][0]
    assert dec["id"] == "decision:42"
    assert dec["title"] == "Enforce snake_case filenames"
    assert dec["enforcement_mode"] == "warn"
    assert "violation_check" in dec
    assert "file_patterns" in dec


@pytest.mark.asyncio
async def test_export_decisions_derives_file_patterns(tmp_path, mock_pool):
    """File patterns are derived from path rows returned by realizes edge query."""
    mock_p, mock_db = mock_pool

    fake_decision = [
        {
            "id": "decision:99",
            "title": "No raw DB calls outside engine/core",
            "rationale": "Use `pool.connection()` everywhere",
            "enforcement_mode": "warn",
            "created_at": "2026-04-12T00:00:00",
        }
    ]
    # Capability query returns empty; file path query returns two files
    file_rows = [
        {"path": "engine/product/enforcer.py"},
        {"path": "engine/product/spec_generator.py"},
    ]

    output_path = str(tmp_path / "decisions.yml")

    call_count = 0

    async def query_side_effect(sql, params=None):
        nonlocal call_count
        call_count += 1
        if call_count == 1:
            return []  # capability slugs
        return file_rows  # file paths

    mock_db.query = AsyncMock(side_effect=query_side_effect)

    with (
        patch("core.engine.core.db.pool", mock_p),
        patch("core.engine.core.db.parse_rows") as mock_parse,
    ):
        # First call: main decisions query; subsequent: sub-queries
        parse_call_count = 0

        def parse_side_effect(val):
            nonlocal parse_call_count
            parse_call_count += 1
            if parse_call_count == 1:
                return fake_decision
            if parse_call_count == 2:
                return []  # cap slugs
            return file_rows

        mock_parse.side_effect = parse_side_effect
        from core.engine.product import enforcer

        with patch.object(enforcer, "_CONFIG_FILE", str(tmp_path / "enforce.config.yml")):
            result = await enforcer.export_decisions(
                product_id="product:platform",
                output_path=output_path,
            )

    with open(output_path) as f:
        content = yaml.safe_load(f)

    dec = content["decisions"][0]
    # Both paths in same dir → collapsed to engine/product/**
    assert dec["file_patterns"] == ["engine/product/**"]


# ── Acceptance criteria: sentinel check ──────────────────────────────────────


@pytest.mark.asyncio
async def test_export_decisions_creates_lockfile_and_config(tmp_path, mock_pool):
    """Sentinel: lockfile written and config template created on first run."""
    mock_p, mock_db = mock_pool
    output_path = str(tmp_path / ".ace" / "decisions.yml")
    config_path = str(tmp_path / ".ace" / "enforce.config.yml")

    with (
        patch("core.engine.core.db.pool", mock_p),
        patch("core.engine.core.db.parse_rows", return_value=[]),
    ):
        from core.engine.product import enforcer

        with patch.object(enforcer, "_CONFIG_FILE", config_path):
            result = await enforcer.export_decisions(
                product_id="product:platform",
                output_path=output_path,
            )

    assert os.path.exists(output_path), "Lockfile not created — sentinel FAILED"
    assert os.path.exists(config_path), "Config template not created — sentinel FAILED"

    with open(output_path) as f:
        lockfile = yaml.safe_load(f)
    assert lockfile["version"] == "1"
    assert "decisions" in lockfile
