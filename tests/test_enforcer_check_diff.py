"""Tests for check_diff — CI enforcement against a base branch."""

from unittest.mock import patch

import pytest


@pytest.mark.asyncio
async def test_check_diff_no_lockfile(tmp_path):
    from core.engine.product.enforcer import check_diff

    result = await check_diff(
        base_ref="origin/main",
        lockfile_path=str(tmp_path / "nonexistent.yml"),
    )
    assert result["lockfile_missing"] is True
    assert result["blocked"] is False
    assert result["violations"] == []


@pytest.mark.asyncio
async def test_check_diff_clean(tmp_path):
    lockfile = tmp_path / "decisions.yml"
    lockfile.write_text("decisions: []\n")

    with patch("subprocess.check_output") as mock_sub:
        mock_sub.side_effect = [
            b"engine/api/main.py\n",  # changed files
            b"--- a/engine/api/main.py\n+++ b/engine/api/main.py\n",  # diff
        ]
        from core.engine.product.enforcer import check_diff

        result = await check_diff(
            base_ref="origin/main",
            lockfile_path=str(lockfile),
        )

    assert result["blocked"] is False
    assert result["files_checked"] == 1
    assert result["violations"] == []


@pytest.mark.asyncio
async def test_check_diff_git_error_non_fatal(tmp_path):
    import subprocess

    lockfile = tmp_path / "decisions.yml"
    lockfile.write_text("decisions: []\n")

    with patch("subprocess.check_output", side_effect=subprocess.CalledProcessError(1, "git")):
        from core.engine.product.enforcer import check_diff

        result = await check_diff(
            base_ref="origin/main",
            lockfile_path=str(lockfile),
        )

    assert result["blocked"] is False
    assert "error" in result


@pytest.mark.asyncio
async def test_check_diff_blocking_violation(tmp_path):
    lockfile = tmp_path / "decisions.yml"
    lockfile.write_text(
        "decisions:\n"
        "  - id: decision:1\n"
        "    title: No direct DB writes outside engine/core/\n"
        "    rationale: All DB calls must go through pool\n"
        "    enforcement_mode: block\n"
        "    file_patterns:\n"
        "      - 'engine/**/*.py'\n"
        "    violation_check: contains\n"
        "    violation_pattern: surrealdb.connect\n"
    )

    diff = "--- a/engine/api/foo.py\n+++ b/engine/api/foo.py\n+db = surrealdb.connect('ws://localhost')\n"

    with patch("subprocess.check_output") as mock_sub:
        mock_sub.side_effect = [
            b"engine/api/foo.py\n",
            diff.encode(),
        ]
        from core.engine.product.enforcer import check_diff

        result = await check_diff(
            base_ref="origin/main",
            lockfile_path=str(lockfile),
        )

    assert result["blocked"] is True
    assert len(result["violations"]) == 1
    assert result["violations"][0]["mode"] == "block"
