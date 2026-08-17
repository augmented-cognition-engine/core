# tests/test_api_scanner.py
"""Tests for the scanner API route: repository admission, authorization, and graph binding."""

import asyncio
import os
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


async def _drain(graph_id: str):
    task = _running_scans.pop(graph_id, None)
    if task:
        await asyncio.gather(task, return_exceptions=True)


class TestScanAdmission:
    @pytest.mark.asyncio
    async def test_scan_accepts_worktree_gitfile_layout(self, tmp_path, mock_pool, mock_user):
        """A linked worktree's `.git` file must be admitted like a `.git` directory, and the
        background task must run the mocked scanner — not the real one."""
        repo = _worktree_repo(tmp_path)
        scan_mock = AsyncMock(return_value={})
        with (
            patch("core.engine.scanner.scanner.scan_repo", new=scan_mock),
            patch("core.engine.api.scanner.pool", mock_pool),
        ):
            resp = await scan_repository(ScanRequest(repo_path=str(repo), graph_id="t_worktree"), user=mock_user)
            assert resp.status == "started"
            await _drain("t_worktree")
        scan_mock.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_scan_rejects_non_repository(self, tmp_path, mock_pool, mock_user):
        plain = tmp_path / "plain"
        plain.mkdir()
        with patch("core.engine.api.scanner.pool", mock_pool), pytest.raises(HTTPException) as exc:
            await scan_repository(ScanRequest(repo_path=str(plain), graph_id="t_plain"), user=mock_user)
        assert exc.value.status_code == 400

    @pytest.mark.asyncio
    async def test_scan_rejects_git_fifo(self, tmp_path, mock_pool, mock_user):
        """A `.git` FIFO must be refused at admission, never opened (Repo() would block the loop)."""
        repo = tmp_path / "fifo"
        repo.mkdir()
        os.mkfifo(str(repo / ".git"))
        with patch("core.engine.api.scanner.pool", mock_pool), pytest.raises(HTTPException) as exc:
            await scan_repository(ScanRequest(repo_path=str(repo), graph_id="t_fifo"), user=mock_user)
        assert exc.value.status_code == 400

    @pytest.mark.asyncio
    async def test_scan_rejects_git_file_without_gitdir_prefix(self, tmp_path, mock_pool, mock_user):
        repo = tmp_path / "bogus"
        repo.mkdir()
        (repo / ".git").write_text("")
        with patch("core.engine.api.scanner.pool", mock_pool), pytest.raises(HTTPException) as exc:
            await scan_repository(ScanRequest(repo_path=str(repo), graph_id="t_bogus"), user=mock_user)
        assert exc.value.status_code == 400


class TestScanAuthorization:
    @pytest.mark.asyncio
    async def test_scan_requires_product_binding(self, tmp_path, mock_pool):
        """A principal with no product cannot start a scan (it could not read the result anyway)."""
        repo = _normal_repo(tmp_path)
        user = {"sub": "user:test", "product": ""}
        with patch("core.engine.api.scanner.pool", mock_pool), pytest.raises(HTTPException) as exc:
            await scan_repository(ScanRequest(repo_path=str(repo), graph_id="t_np"), user=user)
        assert exc.value.status_code == 403

    @pytest.mark.asyncio
    async def test_scan_refuses_graph_owned_by_another_product(self, tmp_path, mock_pool, mock_db, mock_user):
        """Scanning into a graph_id already bound to a different product is refused 404."""
        repo = _normal_repo(tmp_path)
        mock_db.query = AsyncMock(return_value=[{"product": "product:competitor"}])
        with patch("core.engine.api.scanner.pool", mock_pool), pytest.raises(HTTPException) as exc:
            await scan_repository(ScanRequest(repo_path=str(repo), graph_id="t_foreign"), user=mock_user)
        assert exc.value.status_code == 404


class TestScanBinding:
    @pytest.mark.asyncio
    async def test_completed_scan_binds_only_if_unbound(self, tmp_path, mock_pool, mock_db, mock_user):
        """A completed scan binds the graph to the principal's product with a query that refuses
        to overwrite an existing (foreign) binding."""
        repo = _normal_repo(tmp_path)
        with (
            patch("core.engine.scanner.scanner.scan_repo", new=AsyncMock(return_value={})),
            patch("core.engine.api.scanner.pool", mock_pool),
        ):
            resp = await scan_repository(ScanRequest(repo_path=str(repo), graph_id="t_bind"), user=mock_user)
            assert resp.status == "started"
            await _drain("t_bind")

        binding_calls = [
            call
            for call in mock_db.query.await_args_list
            if "UPDATE graph" in call.args[0] and "product" in call.args[0]
        ]
        assert binding_calls, "no graph→product binding query was issued after the scan"
        sql = binding_calls[0].args[0]
        assert "product IS NONE" in sql, "binding must be conditional (bind-if-unbound)"
        params = binding_calls[0].args[1]
        assert params.get("product") == "product:platform"
        assert params.get("gid") == "t_bind"
