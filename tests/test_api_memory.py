"""Tests for /memory API endpoints."""

import os
import time
from contextlib import asynccontextmanager
from unittest.mock import patch

import pytest
from httpx import ASGITransport, AsyncClient


@pytest.fixture
def app_client():
    from core.engine.api.main import app

    @asynccontextmanager
    async def mock_lifespan(a):
        yield

    app.router.lifespan_context = mock_lifespan
    yield app


@pytest.mark.asyncio
async def test_list_projects_empty(app_client, tmp_path):
    """GET /memory/projects returns empty list when no memory dirs exist."""
    with patch("core.engine.api.memory.CLAUDE_DIR", tmp_path / "projects"):
        async with AsyncClient(transport=ASGITransport(app=app_client), base_url="http://test") as client:
            resp = await client.get("/memory/projects")
    assert resp.status_code == 200
    assert resp.json() == {"projects": []}


@pytest.mark.asyncio
async def test_list_projects_with_memory(app_client, tmp_path):
    """GET /memory/projects returns project with entry count."""
    projects_dir = tmp_path / "projects"
    mem_dir = projects_dir / "-home-user-myproject" / "memory"
    mem_dir.mkdir(parents=True)
    (mem_dir / "feedback_test.md").write_text("---\nname: test\ntype: feedback\n---\nbody")
    (mem_dir / "MEMORY.md").write_text("# index")

    with patch("core.engine.api.memory.CLAUDE_DIR", projects_dir):
        async with AsyncClient(transport=ASGITransport(app=app_client), base_url="http://test") as client:
            resp = await client.get("/memory/projects")
    assert resp.status_code == 200
    body = resp.json()
    assert len(body["projects"]) == 1
    assert body["projects"][0]["id"] == "-home-user-myproject"
    assert body["projects"][0]["entry_count"] == 1  # MEMORY.md excluded


@pytest.mark.asyncio
async def test_memory_router_mounted(app_client, tmp_path):
    """/memory/projects is reachable from the main app (router is mounted)."""
    with patch("core.engine.api.memory.CLAUDE_DIR", tmp_path / "nonexistent"):
        async with AsyncClient(transport=ASGITransport(app=app_client), base_url="http://test") as client:
            resp = await client.get("/memory/projects")
    assert resp.status_code == 200  # not 404 — router is mounted


@pytest.mark.asyncio
async def test_list_entries_pagination(app_client, tmp_path):
    """GET /memory/entries returns paginated entries sorted by mtime."""
    projects_dir = tmp_path / "projects"
    mem_dir = projects_dir / "-home-user-ace" / "memory"
    mem_dir.mkdir(parents=True)

    for i in range(5):
        f = mem_dir / f"feedback_{i}.md"
        f.write_text(f"---\nname: entry {i}\ntype: feedback\n---\nbody {i}")
        os.utime(f, (time.time() + i, time.time() + i))

    with patch("core.engine.api.memory.CLAUDE_DIR", projects_dir):
        async with AsyncClient(transport=ASGITransport(app=app_client), base_url="http://test") as client:
            resp = await client.get("/memory/entries?limit=3&offset=0")
    assert resp.status_code == 200
    body = resp.json()
    assert body["total"] == 5
    assert len(body["entries"]) == 3


@pytest.mark.asyncio
async def test_list_entries_type_filter(app_client, tmp_path):
    """GET /memory/entries?type=feedback returns only feedback entries."""
    projects_dir = tmp_path / "projects"
    mem_dir = projects_dir / "-home-user-ace" / "memory"
    mem_dir.mkdir(parents=True)
    (mem_dir / "feedback_test.md").write_text("---\nname: f1\ntype: feedback\n---\nbody")
    (mem_dir / "project_test.md").write_text("---\nname: p1\ntype: project\n---\nbody")

    with patch("core.engine.api.memory.CLAUDE_DIR", projects_dir):
        async with AsyncClient(transport=ASGITransport(app=app_client), base_url="http://test") as client:
            resp = await client.get("/memory/entries?type=feedback")
    assert resp.status_code == 200
    body = resp.json()
    assert body["total"] == 1
    assert body["entries"][0]["type"] == "feedback"


@pytest.mark.asyncio
async def test_list_entries_search(app_client, tmp_path):
    """GET /memory/entries?search= filters by name/body."""
    projects_dir = tmp_path / "projects"
    mem_dir = projects_dir / "-home-user-ace" / "memory"
    mem_dir.mkdir(parents=True)
    (mem_dir / "feedback_parallel.md").write_text("---\nname: No parallel tool calls\ntype: feedback\n---\nbody")
    (mem_dir / "project_direction.md").write_text("---\nname: product direction\ntype: project\n---\nbody")

    with patch("core.engine.api.memory.CLAUDE_DIR", projects_dir):
        async with AsyncClient(transport=ASGITransport(app=app_client), base_url="http://test") as client:
            resp = await client.get("/memory/entries?search=parallel")
    assert resp.status_code == 200
    assert resp.json()["total"] == 1
    assert "parallel" in resp.json()["entries"][0]["name"].lower()
