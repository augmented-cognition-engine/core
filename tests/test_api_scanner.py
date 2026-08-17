# tests/test_api_scanner.py
"""Tests for the scanner API route: repository admission and graph-product binding."""

import asyncio
from contextlib import asynccontextmanager
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi import HTTPException

from core.engine.api.scanner import ScanRequest, _running_scans, scan_repository


@pytest.fixture
def mock_db():
    db = AsyncMock()
    db.query = AsyncMock(return_value=[])
    return db


@pytest.fixture
def mock_pool(mock_db):
    mock_p = MagicMock()

    @asynccontextmanager
    async def _conn():
        yield mock_db

    mock_p.connection = _conn
    return mock_p


@pytest.fixture
def mock_user():
    return {"sub": "user:test", "email": "test@example.com", "product": "product:platform"}


def _worktree_repo(tmp_path):
    """A repository laid out like a linked git worktree: `.git` is a file, not a directory."""
    repo = tmp_path / "wt"
    repo.mkdir()
    (repo / ".git").write_text("gitdir: /somewhere/.git/worktrees/wt\n")
    return repo


def _normal_repo(tmp_path):
    repo = tmp_path / "repo"
    repo.mkdir()
    (repo / ".git").mkdir()
    return repo


class TestScanAdmitsWorktrees:
    @pytest.mark.asyncio
    async def test_scan_accepts_worktree_gitfile_layout(self, tmp_path, mock_user):
        """A linked worktree's `.git` file must be admitted like a `.git` directory."""
        repo = _worktree_repo(tmp_path)
        with patch("core.engine.scanner.scanner.scan_repo", new=AsyncMock(return_value={})):
            resp = await scan_repository(ScanRequest(repo_path=str(repo), graph_id="t_worktree"), user=mock_user)
        try:
            assert resp.status == "started"
        finally:
            task = _running_scans.pop("t_worktree", None)
            if task:
                await asyncio.gather(task, return_exceptions=True)

    @pytest.mark.asyncio
    async def test_scan_still_rejects_non_repository(self, tmp_path, mock_user):
        plain = tmp_path / "plain"
        plain.mkdir()
        with pytest.raises(HTTPException) as exc_info:
            await scan_repository(ScanRequest(repo_path=str(plain), graph_id="t_plain"), user=mock_user)
        assert exc_info.value.status_code == 400


class TestScanBindsGraphToProduct:
    @pytest.mark.asyncio
    async def test_completed_scan_binds_graph_to_principal_product(self, tmp_path, mock_pool, mock_db, mock_user):
        """After a successful scan, the graph record must be bound to the
        authenticated principal's product so the traversal authorization gate
        (`_graph_bound_to_product`) can admit reads of the new graph."""
        repo = _normal_repo(tmp_path)
        with (
            patch("core.engine.scanner.scanner.scan_repo", new=AsyncMock(return_value={})),
            patch("core.engine.api.scanner.pool", mock_pool),
        ):
            resp = await scan_repository(ScanRequest(repo_path=str(repo), graph_id="t_bind"), user=mock_user)
            assert resp.status == "started"
            task = _running_scans.pop("t_bind", None)
            assert task is not None
            await asyncio.gather(task, return_exceptions=True)

        binding_calls = [
            call
            for call in mock_db.query.await_args_list
            if "UPDATE graph" in call.args[0] and "product" in call.args[0]
        ]
        assert binding_calls, "no graph→product binding query was issued after the scan"
        params = binding_calls[0].args[1]
        assert params.get("product") == "product:platform"
        assert params.get("gid") == "t_bind"
