# tests/test_ecosystem.py
"""Tests for EcosystemManager — ecosystem and project CRUD, hierarchy queries."""

from unittest.mock import AsyncMock, MagicMock

import pytest


@pytest.fixture
def mock_db():
    db = AsyncMock()
    db.query = AsyncMock(return_value=[])
    return db


@pytest.fixture
def mock_pool(mock_db):
    pool = MagicMock()
    cm = AsyncMock()
    cm.__aenter__ = AsyncMock(return_value=mock_db)
    cm.__aexit__ = AsyncMock(return_value=None)
    pool.connection.return_value = cm
    return pool


@pytest.fixture
def manager(mock_pool):
    from core.engine.product.ecosystem import EcosystemManager

    return EcosystemManager(mock_pool)


# ---------------------------------------------------------------------------
# test_create_ecosystem
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_create_ecosystem(manager, mock_db):
    """create_ecosystem creates and returns the ecosystem record."""
    fake_eco = {
        "id": "ecosystem:acme_suite",
        "slug": "acme-suite",
        "name": "ACME Suite",
        "product": "org:acme",
    }
    mock_db.query = AsyncMock(return_value=[fake_eco])

    result = await manager.create_ecosystem(
        {"slug": "acme-suite", "name": "ACME Suite", "description": "Main product suite"},
        "org:acme",
    )

    assert result["slug"] == "acme-suite"
    assert result["name"] == "ACME Suite"
    call_sql = mock_db.query.call_args[0][0].upper()
    assert "ECOSYSTEM" in call_sql
    assert any(kw in call_sql for kw in ("CREATE", "UPSERT", "INSERT"))


# ---------------------------------------------------------------------------
# test_get_ecosystems
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_get_ecosystems(manager, mock_db):
    """get_ecosystems returns list of all ecosystems for an org."""
    fake_rows = [
        {"id": "ecosystem:suite_a", "slug": "suite-a", "name": "Suite A", "product": "org:acme"},
        {"id": "ecosystem:suite_b", "slug": "suite-b", "name": "Suite B", "product": "org:acme"},
    ]
    mock_db.query = AsyncMock(return_value=fake_rows)

    result = await manager.get_ecosystems("org:acme")

    assert len(result) == 2
    assert result[0]["slug"] == "suite-a"
    assert result[1]["slug"] == "suite-b"
    call_sql = mock_db.query.call_args[0][0].lower()
    assert "ecosystem" in call_sql


# ---------------------------------------------------------------------------
# test_create_project_standalone
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_create_project_standalone(manager, mock_db):
    """create_project creates a project not linked to any ecosystem."""
    fake_proj = {
        "id": "project:api",
        "slug": "api",
        "name": "API Service",
        "product": "org:acme",
        "ecosystem": None,
    }
    mock_db.query = AsyncMock(return_value=[fake_proj])

    result = await manager.create_project(
        {"slug": "api", "name": "API Service", "description": "Core REST API"},
        "org:acme",
    )

    assert result["slug"] == "api"
    assert result["name"] == "API Service"
    # No ecosystem linked
    assert result.get("ecosystem") is None
    call_sql = mock_db.query.call_args[0][0].upper()
    assert "PROJECT" in call_sql
    assert any(kw in call_sql for kw in ("CREATE", "UPSERT", "INSERT"))


# ---------------------------------------------------------------------------
# test_create_project_in_ecosystem
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_create_project_in_ecosystem(manager, mock_db):
    """create_project links the project to an ecosystem when ecosystem_slug provided."""
    fake_eco = {
        "id": "ecosystem:acme_suite",
        "slug": "acme-suite",
        "name": "ACME Suite",
        "product": "org:acme",
    }
    fake_proj = {
        "id": "project:dashboard",
        "slug": "dashboard",
        "name": "Dashboard",
        "product": "org:acme",
        "ecosystem": "ecosystem:acme_suite",
    }
    # Sequence: 1st = lookup ecosystem by slug, 2nd = create project
    mock_db.query = AsyncMock(side_effect=[[fake_eco], [fake_proj]])

    result = await manager.create_project(
        {
            "slug": "dashboard",
            "name": "Dashboard",
            "ecosystem_slug": "acme-suite",
        },
        "org:acme",
    )

    assert result["slug"] == "dashboard"
    assert result["ecosystem"] == "ecosystem:acme_suite"
    assert mock_db.query.call_count == 2
    # Second call should reference project table
    second_sql = mock_db.query.call_args_list[1][0][0].upper()
    assert "PROJECT" in second_sql


# ---------------------------------------------------------------------------
# test_get_hierarchy
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_get_hierarchy(manager, mock_db):
    """get_hierarchy returns nested structure: ecosystems → projects → capability counts."""
    eco_rows = [
        {"id": "ecosystem:suite_a", "slug": "suite-a", "name": "Suite A", "product": "org:acme"},
    ]
    proj_rows = [
        {
            "id": "project:api",
            "slug": "api",
            "name": "API Service",
            "product": "org:acme",
            "ecosystem": "ecosystem:suite_a",
        },
        {
            "id": "project:worker",
            "slug": "worker",
            "name": "Worker",
            "product": "org:acme",
            "ecosystem": None,
        },
    ]
    cap_counts = [
        {"project": "project:api", "count": 5},
        {"project": "project:worker", "count": 2},
    ]
    # Sequence: ecosystems, projects, capability counts
    mock_db.query = AsyncMock(side_effect=[eco_rows, proj_rows, cap_counts])

    result = await manager.get_hierarchy("org:acme")

    assert "ecosystems" in result
    assert "standalone_projects" in result

    # Ecosystem "suite-a" should have project "api" nested
    assert len(result["ecosystems"]) == 1
    eco = result["ecosystems"][0]
    assert eco["slug"] == "suite-a"
    assert len(eco["projects"]) == 1
    assert eco["projects"][0]["slug"] == "api"
    assert eco["projects"][0]["capability_count"] == 5

    # Standalone projects (no ecosystem)
    assert len(result["standalone_projects"]) == 1
    assert result["standalone_projects"][0]["slug"] == "worker"
    assert result["standalone_projects"][0]["capability_count"] == 2
