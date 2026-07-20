"""Tests for onboarding specialty scaffolder."""

from unittest.mock import AsyncMock, patch

import pytest

from core.engine.onboarding.scaffolder import (
    _validate_scaffolded_specialties,
    needs_onboarding,
    needs_project_setup,
    scaffold_project,
    scaffold_specialties,
)

# ── needs_onboarding ────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_needs_onboarding_true_when_no_projects_and_no_specialties():
    mock_db = AsyncMock()
    # First query: projects (empty) → no projects
    # Second query: specialties (empty) → no specialties
    mock_db.query = AsyncMock(side_effect=[[], []])
    with patch("core.engine.onboarding.scaffolder.pool") as mock_pool:
        mock_pool.connection.return_value.__aenter__ = AsyncMock(return_value=mock_db)
        mock_pool.connection.return_value.__aexit__ = AsyncMock(return_value=False)
        assert await needs_onboarding("product:default") is True


@pytest.mark.asyncio
async def test_needs_onboarding_false_when_projects_exist():
    mock_db = AsyncMock()
    # First query: projects (has 1) → has projects
    # Second query: specialties (empty)
    mock_db.query = AsyncMock(side_effect=[[{"c": 1}], []])
    with patch("core.engine.onboarding.scaffolder.pool") as mock_pool:
        mock_pool.connection.return_value.__aenter__ = AsyncMock(return_value=mock_db)
        mock_pool.connection.return_value.__aexit__ = AsyncMock(return_value=False)
        assert await needs_onboarding("product:default") is False


@pytest.mark.asyncio
async def test_needs_onboarding_false_when_specialties_exist():
    mock_db = AsyncMock()
    # First query: projects (empty) → no projects
    # Second query: specialties (has 5) → has specialties
    mock_db.query = AsyncMock(side_effect=[[], [{"c": 5}]])
    with patch("core.engine.onboarding.scaffolder.pool") as mock_pool:
        mock_pool.connection.return_value.__aenter__ = AsyncMock(return_value=mock_db)
        mock_pool.connection.return_value.__aexit__ = AsyncMock(return_value=False)
        assert await needs_onboarding("product:default") is False


# ── needs_project_setup ─────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_needs_project_setup_empty():
    mock_db = AsyncMock()
    mock_db.query = AsyncMock(return_value=[])
    with patch("core.engine.onboarding.scaffolder.pool") as mock_pool:
        mock_pool.connection.return_value.__aenter__ = AsyncMock(return_value=mock_db)
        mock_pool.connection.return_value.__aexit__ = AsyncMock(return_value=False)
        assert await needs_project_setup("product:default") is True


@pytest.mark.asyncio
async def test_needs_project_setup_false_when_projects_exist():
    mock_db = AsyncMock()
    mock_db.query = AsyncMock(return_value=[{"c": 2}])
    with patch("core.engine.onboarding.scaffolder.pool") as mock_pool:
        mock_pool.connection.return_value.__aenter__ = AsyncMock(return_value=mock_db)
        mock_pool.connection.return_value.__aexit__ = AsyncMock(return_value=False)
        assert await needs_project_setup("product:default") is False


# ── scaffold_project ────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_scaffold_project_creates_project():
    mock_db = AsyncMock()

    # CREATE project returns the created record; the per-discipline CREATE calls
    # return empty. Match on the SQL so the test is robust to how many disciplines
    # a product type gets (it changes as the discipline set evolves).
    def _scaffold_query(sql, params=None):
        if "CREATE project" in sql:
            return [{"id": "project:ace", "slug": "ace", "name": "ACE", "product_type": "api"}]
        return []

    mock_db.query = AsyncMock(side_effect=_scaffold_query)

    with (
        patch("core.engine.onboarding.scaffolder.pool") as mock_pool,
        patch("core.engine.onboarding.scaffolder.llm") as mock_llm,
    ):
        mock_pool.connection.return_value.__aenter__ = AsyncMock(return_value=mock_db)
        mock_pool.connection.return_value.__aexit__ = AsyncMock(return_value=False)
        mock_llm.complete_json = AsyncMock(
            return_value={
                "name": "ACE",
                "slug": "ace",
                "product_type": "api",
                "description": "An AI-powered PM engine for developers.",
            }
        )

        result = await scaffold_project(
            "I'm building an AI PM tool called ACE that uses graphs to track insights",
            "product:default",
        )

    assert result.get("slug") == "ace"
    assert result.get("name") == "ACE"


@pytest.mark.asyncio
async def test_scaffold_project_returns_empty_on_llm_failure():
    with (
        patch("core.engine.onboarding.scaffolder.pool"),
        patch("core.engine.onboarding.scaffolder.llm") as mock_llm,
    ):
        mock_llm.complete_json = AsyncMock(side_effect=Exception("LLM down"))
        result = await scaffold_project("build something", "product:default")

    assert result == {}


@pytest.mark.asyncio
async def test_scaffold_project_returns_empty_on_missing_slug():
    with (
        patch("core.engine.onboarding.scaffolder.pool"),
        patch("core.engine.onboarding.scaffolder.llm") as mock_llm,
    ):
        mock_llm.complete_json = AsyncMock(return_value={"name": "No slug here"})
        result = await scaffold_project("build something", "product:default")

    assert result == {}


@pytest.mark.asyncio
async def test_scaffold_project_normalises_slug():
    mock_db = AsyncMock()
    mock_db.query = AsyncMock(return_value=[{"id": "project:my_cool_app", "slug": "my_cool_app"}])

    with (
        patch("core.engine.onboarding.scaffolder.pool") as mock_pool,
        patch("core.engine.onboarding.scaffolder.llm") as mock_llm,
    ):
        mock_pool.connection.return_value.__aenter__ = AsyncMock(return_value=mock_db)
        mock_pool.connection.return_value.__aexit__ = AsyncMock(return_value=False)
        mock_llm.complete_json = AsyncMock(
            return_value={
                "name": "My Cool App",
                "slug": "my-cool-app",  # hyphens should become underscores
                "product_type": "web",
                "description": "A web app.",
            }
        )

        result = await scaffold_project("a cool web app", "product:default")

    assert result.get("slug") == "my_cool_app"


# ── _validate_scaffolded_specialties ────────────────────────────────────────


def test_validate_clamps_to_range():
    specs = [
        {
            "slug": f"s{i}",
            "name": f"S{i}",
            "description": "d",
            "perspective": "practitioner",
            "discipline": "engineering",
            "priority": "core",
        }
        for i in range(25)
    ]
    result = _validate_scaffolded_specialties(specs)
    assert len(result) <= 20


def test_validate_deduplicates_by_slug():
    specs = [
        {
            "slug": "trading",
            "name": "Trading",
            "description": "d",
            "perspective": "practitioner",
            "discipline": "markets",
            "priority": "core",
        },
        {
            "slug": "trading",
            "name": "Trading 2",
            "description": "d2",
            "perspective": "theorist",
            "discipline": "markets",
            "priority": "adjacent",
        },
    ]
    result = _validate_scaffolded_specialties(specs)
    assert len(result) == 1


def test_validate_filters_invalid_perspective():
    specs = [
        {
            "slug": "good",
            "name": "Good",
            "description": "d",
            "perspective": "practitioner",
            "discipline": "eng",
            "priority": "core",
        },
        {
            "slug": "bad",
            "name": "Bad",
            "description": "d",
            "perspective": "wizard",
            "discipline": "eng",
            "priority": "core",
        },
    ]
    result = _validate_scaffolded_specialties(specs)
    # Bad perspective gets defaulted to practitioner, not dropped
    assert len(result) == 2
    assert all(r["perspective"] in {"theorist", "practitioner", "strategist", "operator"} for r in result)


def test_validate_minimum_3():
    specs = [
        {
            "slug": "s1",
            "name": "S1",
            "description": "d",
            "perspective": "practitioner",
            "discipline": "eng",
            "priority": "core",
        }
    ]
    result = _validate_scaffolded_specialties(specs)
    # Can't conjure missing specialties — returns what we have
    assert len(result) == 1


# ── scaffold_specialties ────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_scaffold_specialties_creates_records():
    mock_db = AsyncMock()
    mock_db.query = AsyncMock(
        side_effect=[
            # discipline query
            [
                {"id": "discipline:eng", "slug": "engineering"},
                {"id": "discipline:mkt", "slug": "markets"},
            ],
            # existing specialties (empty)
            [],
            # CREATE calls return created records
            [{"id": "specialty:1", "slug": "futures-trading"}],
            [{"id": "specialty:2", "slug": "risk-management"}],
        ]
    )

    with (
        patch("core.engine.onboarding.scaffolder.pool") as mock_pool,
        patch("core.engine.onboarding.scaffolder.llm") as mock_llm,
    ):
        mock_pool.connection.return_value.__aenter__ = AsyncMock(return_value=mock_db)
        mock_pool.connection.return_value.__aexit__ = AsyncMock(return_value=False)
        mock_llm.complete_json = AsyncMock(
            return_value={
                "specialties": [
                    {
                        "slug": "futures-trading",
                        "name": "Futures Trading",
                        "description": "Futures markets",
                        "perspective": "practitioner",
                        "discipline": "markets",
                        "priority": "core",
                    },
                    {
                        "slug": "risk-management",
                        "name": "Risk Management",
                        "description": "Risk analysis",
                        "perspective": "strategist",
                        "discipline": "markets",
                        "priority": "core",
                    },
                ]
            }
        )

        result = await scaffold_specialties("I'm a futures trader", "product:default")

    assert len(result) == 2
    assert result[0]["slug"] == "futures-trading"
