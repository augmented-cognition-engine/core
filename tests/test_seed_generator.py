# tests/test_seed_generator.py
"""Tests for BestPracticeSeedGenerator — LLM-generated insights per specialty."""

from unittest.mock import AsyncMock, MagicMock

import pytest

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


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
def mock_llm():
    llm = AsyncMock()
    llm.complete_json = AsyncMock(
        return_value=[
            {
                "content": "API endpoints must validate input using Pydantic models before passing to business logic",
                "confidence": 0.9,
            },
            {
                "content": "Database queries must use parameterized values, never string interpolation",
                "confidence": 0.85,
            },
            {"content": "Error responses must include an error code, message, and correlation ID", "confidence": 0.8},
        ]
    )
    return llm


@pytest.fixture
def generator(mock_pool, mock_llm):
    from core.engine.product.seed_generator import BestPracticeSeedGenerator

    gen = BestPracticeSeedGenerator(db_pool=mock_pool)
    gen._llm = mock_llm
    return gen


# ---------------------------------------------------------------------------
# test_generate_for_specialty_creates_insights
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_generate_for_specialty_creates_insights(generator, mock_db):
    """Mock LLM returns practices → insights are created in DB and returned."""
    fake_insight = {
        "id": "insight:abc123",
        "content": "API endpoints must validate input using Pydantic models before passing to business logic",
        "confidence": 0.9,
        "tier": "specialty",
        "tags": ["security", "api_security", "best_practice"],
    }
    # First call: SELECT to check for duplicates → empty (no existing)
    # Second call: CREATE insight → returns the new insight
    # Repeat for each of the 3 LLM-returned practices
    mock_db.query = AsyncMock(
        side_effect=[
            [],  # duplicate check for practice 1 → not found
            [fake_insight],  # CREATE insight 1 → success
            [],  # duplicate check for practice 2
            [{"id": "insight:def456", "content": "...", "confidence": 0.85}],
            [],  # duplicate check for practice 3
            [{"id": "insight:ghi789", "content": "...", "confidence": 0.8}],
        ]
    )

    created = await generator.generate_for_specialty("api_security", "security", "product:test")

    assert len(created) == 3

    # Verify LLM was called with relevant prompt content
    generator._llm.complete_json.assert_called_once()
    prompt_used = generator._llm.complete_json.call_args[0][0]
    assert "api_security" in prompt_used
    assert "OWASP" in prompt_used  # security sources referenced

    # Verify DB was written to (at least one CREATE call)
    create_calls = [call for call in mock_db.query.call_args_list if "CREATE insight" in call[0][0]]
    assert len(create_calls) == 3

    # Verify insight fields in the CREATE call
    first_create_sql = create_calls[0][0][0]
    assert "tier" in first_create_sql
    assert "best_practice" in first_create_sql or "tags" in first_create_sql
    # The insight MUST be product-scoped, or the product-filtered loader can NEVER retrieve it — the whole
    # point of seeding best practices is that they surface in retrieval (regression: product was omitted).
    assert "product = <record>$product" in first_create_sql
    assert create_calls[0][0][1]["product"] == "product:test"


# ---------------------------------------------------------------------------
# test_generate_for_specialty_deduplicates
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_generate_for_specialty_deduplicates(generator, mock_db):
    """Existing insight with same content is skipped — no duplicate CREATE."""
    existing_insight = {
        "id": "insight:existing",
        "content": "API endpoints must validate input using Pydantic models before passing to business logic",
    }

    # All three duplicate checks return an existing record → no CREATEs
    mock_db.query = AsyncMock(
        side_effect=[
            [existing_insight],  # practice 1 duplicate found → skip
            [existing_insight],  # practice 2 duplicate found → skip
            [existing_insight],  # practice 3 duplicate found → skip
        ]
    )

    created = await generator.generate_for_specialty("api_security", "security", "product:test")

    assert created == []

    # Verify no CREATE calls were made
    create_calls = [call for call in mock_db.query.call_args_list if "CREATE insight" in call[0][0]]
    assert len(create_calls) == 0


# ---------------------------------------------------------------------------
# test_authoritative_sources_coverage
# ---------------------------------------------------------------------------


def test_authoritative_sources_coverage():
    """Every discipline in SEED_STRUCTURE has an entry in AUTHORITATIVE_SOURCES."""
    from core.engine.product.seed_generator import AUTHORITATIVE_SOURCES
    from core.engine.product.seed_packs import SEED_STRUCTURE

    missing = []
    for dimension in SEED_STRUCTURE:
        if dimension not in AUTHORITATIVE_SOURCES:
            missing.append(dimension)

    assert missing == [], (
        f"Disciplines missing from AUTHORITATIVE_SOURCES: {missing}\n"
        "Add each discipline to the AUTHORITATIVE_SOURCES dict in seed_generator.py"
    )
